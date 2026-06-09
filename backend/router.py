"""순수 라우팅 — (method, path, query, body, ctx) -> (status, dict). 소켓 의존 없음."""
from __future__ import annotations

import shutil
from pathlib import Path

from backend import projects, skills_cfg, sessions, pipeline, imagegen
from backend.codex_runner import run_skill

VERSION = "0.2.0-m2"

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def _codex_status() -> str:
    if shutil.which("codex") is None:
        return "not_installed"
    return "ready" if (Path.home() / ".codex" / "auth.json").exists() else "not_authenticated"


def handle_request(method: str, path: str, query: dict, body: dict | None, ctx: dict):
    root: Path = ctx["root"]
    p = path.rstrip("/") or "/"

    if method == "GET" and p == "/health":
        return 200, {"backend_status": "connected", "codex_status": _codex_status(),
                     "version": VERSION}

    if method == "GET" and p == "/api/projects":
        return 200, {"projects": projects.scan_projects(root)}

    if method == "POST" and p == "/api/projects/load":
        pid = (body or {}).get("project_id", "")
        try:
            return 200, projects.load_project(root, pid)
        except FileNotFoundError as e:
            return 404, {"error": str(e)}

    if method == "POST" and p == "/api/projects/create":
        b = body or {}
        title = (b.get("title") or "").strip()
        if not title:
            return 400, {"error": "title 필요"}
        info = projects.create_project(
            root, title,
            channel=b.get("channel", "semoji"),
            duration=b.get("duration", "1분"))
        return 200, info

    if method == "POST" and p == "/api/skills/run":
        b = body or {}
        pid, skill = b.get("project_id", ""), b.get("skill_name", "")
        proj_dir = root / pid
        if not proj_dir.is_dir():
            return 404, {"error": f"project not found: {pid}"}
        try:
            cfg = skills_cfg.load_config(SKILLS_DIR, skill)
        except FileNotFoundError:
            return 404, {"error": f"skill not found: {skill}"}
        miss = skills_cfg.missing_inputs(cfg, proj_dir)
        if miss:
            return 422, {"error": f"입력 누락: {', '.join(miss)}"}
        jobs = ctx["jobs"]
        jid = jobs.create(skill, pid)
        prompt = skills_cfg.build_prompt(SKILLS_DIR, skill, cfg, proj_dir)
        out = proj_dir / cfg["output"]
        out.parent.mkdir(parents=True, exist_ok=True)
        schema = (SKILLS_DIR / skill / cfg["schema"]) if cfg.get("schema") else None
        sid = sessions.load_session(proj_dir)
        result = run_skill(
            prompt, proj_dir,
            session_id=sid,
            output_schema=str(schema) if schema else None,
            output_last=str(out),
            on_line=lambda ln: jobs.append_log(jid, ln),
        )
        if result.get("session_id"):
            sessions.save_session(proj_dir, result["session_id"])
        if result["returncode"] == 0 and out.exists():
            jobs.set_status(jid, "completed", artifact_paths=[str(out)])
        else:
            jobs.set_status(jid, "failed", error=f"rc={result['returncode']}")
        return 200, {"job_id": jid, "status": jobs.get(jid)["status"]}

    if method == "POST" and p == "/api/pipeline/run":
        b = body or {}
        pid = b.get("project_id", "")
        proj_dir = root / pid
        if not proj_dir.is_dir():
            return 404, {"error": f"project not found: {pid}"}
        jobs = ctx["jobs"]
        jid = jobs.create("pipeline", pid)
        res = pipeline.run_pipeline(SKILLS_DIR, proj_dir,
                                    on_line=lambda ln: jobs.append_log(jid, ln))
        if res["status"] == "completed":
            jobs.set_status(jid, "completed", artifact_paths=[res["final"]])
        else:
            jobs.set_status(jid, "failed", error=f"{res.get('stage')}: {res.get('error')}")
        return 200, {"job_id": jid, "status": jobs.get(jid)["status"],
                     "completed": res.get("completed", [])}

    if method == "POST" and p == "/api/characters/generate":
        b = body or {}
        pid = b.get("project_id", "")
        name = (b.get("name") or "").strip()
        looks = (b.get("looks") or "").strip()
        if not pid or not name or not looks:
            return 400, {"error": "project_id, name, looks 필요"}
        proj_dir = root / pid
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        jobs = ctx["jobs"]
        jid = jobs.create("character", pid)
        res = imagegen.generate_character(
            proj_dir, name, looks,
            on_line=lambda ln: jobs.append_log(jid, ln))
        ok = res.get("status") == "completed"
        jobs.set_status(jid, "completed" if ok else "failed",
                        artifact_paths=[str(proj_dir / "characters")])
        return 200, {"job_id": jid, "status": jobs.get(jid)["status"], "character": res}

    if method == "GET" and p == "/api/characters/list":
        pid = query.get("project_id", "")
        cd = root / pid / "characters"
        if not cd.is_dir():
            return 200, {"images": []}
        names = sorted(f.name for f in cd.glob("*.png"))
        return 200, {"images": names, "dir": str(cd)}

    if method == "POST" and p == "/api/images/generate":
        b = body or {}
        pid = b.get("project_id", "")
        proj_dir = root / pid
        refs_fp = proj_dir / "references.json"
        if not refs_fp.exists():
            return 422, {"error": "references.json 없음 — reference-list 먼저 실행"}
        import json as _json
        refs = _json.loads(refs_fp.read_text(encoding="utf-8")).get("references", [])
        jobs = ctx["jobs"]
        jid = jobs.create("images", pid)
        conc = int(b.get("concurrency", 4))
        items = [(f"{ref['id']}.png", ref["image_prompt"]) for ref in refs]
        results = imagegen.generate_many(
            proj_dir, items, subdir="images", concurrency=conc,
            on_event=lambda rel, res: jobs.append_log(jid, f"{rel}: {res['status']}"))
        done = sum(1 for r in results.values() if r["status"] == "completed")
        jobs.set_status(jid, "completed" if done else "failed",
                        artifact_paths=[str(proj_dir / "images")])
        return 200, {"job_id": jid, "status": jobs.get(jid)["status"],
                     "generated": done, "total": len(refs)}

    if method == "GET" and p == "/api/images/list":
        pid = query.get("project_id", "")
        images_dir = root / pid / "images"
        if not images_dir.is_dir():
            return 200, {"images": []}
        names = sorted(f.name for f in images_dir.glob("*.png"))
        return 200, {"images": names, "dir": str(images_dir)}

    if method == "POST" and p == "/api/storyboard/generate":
        b = body or {}
        pid = b.get("project_id", "")
        proj_dir = root / pid
        scenes_fp = proj_dir / "scenes.json"
        if not scenes_fp.exists():
            return 422, {"error": "scenes.json 없음 — 씬 분해(scene-decompose) 먼저 실행"}
        import json as _json
        scenes = _json.loads(scenes_fp.read_text(encoding="utf-8")).get("scenes", [])
        jobs = ctx["jobs"]
        jid = jobs.create("storyboard", pid)
        conc = int(b.get("concurrency", 4))
        char = (b.get("character") or "").strip()
        character_ref = None
        if char:
            cref = proj_dir / "characters" / f"char_{char}.png"
            if cref.exists():
                character_ref = str(cref)
        items = []
        for sc in scenes:
            n = sc.get("sceneNumber", len(items) + 1)
            prompt = sc.get("image_prompt") or sc.get("visual_summary") or sc.get("narration", "")
            items.append((f"sb_{n}.png", prompt))
        results = imagegen.generate_many(
            proj_dir, items, subdir="storyboard", concurrency=conc, character_ref=character_ref,
            on_event=lambda rel, res: jobs.append_log(jid, f"{rel}: {res['status']}"))
        done = sum(1 for r in results.values() if r["status"] == "completed")
        jobs.set_status(jid, "completed" if done else "failed",
                        artifact_paths=[str(proj_dir / "storyboard")])
        return 200, {"job_id": jid, "status": jobs.get(jid)["status"],
                     "generated": done, "total": len(scenes)}

    if method == "GET" and p == "/api/storyboard/list":
        pid = query.get("project_id", "")
        sb_dir = root / pid / "storyboard"
        if not sb_dir.is_dir():
            return 200, {"images": []}
        names = sorted(f.name for f in sb_dir.glob("*.png"))
        return 200, {"images": names, "dir": str(sb_dir)}

    if method == "POST" and p == "/api/layers/generate":
        b = body or {}
        pid = b.get("project_id", "")
        proj_dir = root / pid
        scenes_fp = proj_dir / "scenes.json"
        sb_dir = proj_dir / "storyboard"
        if not scenes_fp.exists() or not sb_dir.is_dir():
            return 422, {"error": "scenes.json + storyboard/ 필요 — 씬분해·스토리보드 먼저"}
        import json as _json
        scenes = _json.loads(scenes_fp.read_text(encoding="utf-8")).get("scenes", [])
        items = []
        for sc in scenes:
            n = sc.get("sceneNumber")
            sb = sb_dir / f"sb_{n}.png"
            if sb.exists():
                items.append((n, sb))
        if not items:
            return 422, {"error": "storyboard 프레임 없음(sb_N.png)"}
        jobs = ctx["jobs"]
        jid = jobs.create("layers", pid)
        conc = int(b.get("concurrency", 4))
        results = imagegen.generate_scene_layers(
            proj_dir, items, concurrency=conc,
            on_event=lambda n, kind, res: jobs.append_log(jid, f"scene{n}/{kind}: {res['status']}"))
        ok = sum(1 for v in results.values()
                 if v.get("background", {}).get("status") == "completed"
                 and v.get("character", {}).get("status") == "completed")
        layers = {"project_id": pid, "scenes": [
            {"sceneNumber": n, "background": f"layers/bg_{n}.png", "character": f"layers/char_{n}.png"}
            for n, _ in items]}
        (proj_dir / "layers.json").write_text(_json.dumps(layers, ensure_ascii=False, indent=2), encoding="utf-8")
        jobs.set_status(jid, "completed" if ok else "failed", artifact_paths=[str(proj_dir / "layers.json")])
        return 200, {"job_id": jid, "status": jobs.get(jid)["status"], "scenes": ok, "total": len(items)}

    if method == "GET" and p == "/api/layers/list":
        pid = query.get("project_id", "")
        ld = root / pid / "layers"
        if not ld.is_dir():
            return 200, {"images": []}
        names = sorted(f.name for f in ld.glob("*.png"))
        return 200, {"images": names, "dir": str(ld)}

    if method == "GET" and p == "/api/projects/files":
        pid = query.get("project_id", "")
        return 200, {"groups": projects.list_files(root / pid)}

    if method == "GET" and p == "/api/projects/file":
        pid = query.get("project_id", "")
        name = query.get("name", "")
        proj_dir = root / pid
        if not proj_dir.is_dir():
            return 404, {"error": f"project not found: {pid}"}
        if not name:
            return 400, {"error": "invalid name"}
        fp = (proj_dir / name).resolve()
        # 경로 탈출 방지: resolve된 경로가 프로젝트 디렉토리 내부여야 함
        if not fp.is_relative_to(proj_dir.resolve()):
            return 400, {"error": "invalid name"}
        if not fp.is_file():
            return 404, {"error": f"file not found: {name}"}
        try:
            content = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return 415, {"error": "binary file not supported"}
        return 200, {"name": name, "content": content}

    if method == "GET" and p.startswith("/api/jobs/"):
        jid = p.rsplit("/", 1)[-1]
        j = ctx["jobs"].get(jid)
        if not j:
            return 404, {"error": f"job not found: {jid}"}
        return 200, j

    return 404, {"error": "not found", "path": path}
