"""순수 라우팅 — (method, path, query, body, ctx) -> (status, dict). 소켓 의존 없음."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from backend import projects, skills_cfg, sessions, pipeline, imagegen, scenes, search, media, tts, manifest, assistant, llm
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
        result = llm.run_orchestrator(
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

    if method == "GET" and p == "/api/scenes":
        pid = query.get("project_id", "")
        return 200, scenes.load_scenes(root / pid)

    if method == "POST" and p == "/api/scenes/narration":
        b = body or {}
        pid = b.get("project_id", "")
        proj_dir = root / pid
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        sn = b.get("sceneNumber")
        res = scenes.update_narration(proj_dir, sn, b.get("narration", ""))
        return (200, res) if res.get("ok") else (404, res)

    if method == "POST" and p in ("/api/scenes/add", "/api/scenes/delete",
                                  "/api/scenes/split", "/api/scenes/merge"):
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        if p == "/api/scenes/add":
            return 200, scenes.add_scene(proj_dir, after_number=b.get("after"),
                                         narration=b.get("narration", ""), title=b.get("title", ""))
        if p == "/api/scenes/delete":
            return 200, scenes.remove_scene(proj_dir, b.get("sceneNumber"))
        if p == "/api/scenes/split":
            return 200, scenes.split_scene(proj_dir, b.get("sceneNumber"),
                                           first=b.get("first"), second=b.get("second"))
        return 200, scenes.merge_scenes(proj_dir, b.get("sceneNumber"))

    if method == "POST" and p in ("/api/scenes/tts", "/api/tts/all"):
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        data = scenes.load_scenes(proj_dir)
        jobs = ctx["jobs"]
        voice = b.get("voice")
        if p == "/api/tts/all":
            jid = jobs.create("tts-all", b.get("project_id", ""))
            results = []
            for s in data["scenes"]:
                res = tts.generate_scene_tts(proj_dir, s.get("sceneId"), s.get("narration", ""), voice=voice)
                results.append({"sceneNumber": s.get("sceneNumber"), **res})
                jobs.append_log(jid, f"S{s.get('sceneNumber')}: {res.get('status')}")
            ok = any(x.get("status") == "completed" for x in results)
            jobs.set_status(jid, "completed" if ok else "failed", artifact_paths=[str(proj_dir / "audio")])
            return 200, {"job_id": jid, "results": results}
        sn = b.get("sceneNumber")
        sc = next((s for s in data["scenes"] if s.get("sceneNumber") == sn), None)
        if not sc:
            return 404, {"error": "씬 없음"}
        if not (sc.get("narration") or "").strip():
            return 422, {"error": "내레이션 비어있음"}
        jid = jobs.create("tts", b.get("project_id", ""))
        res = tts.generate_scene_tts(proj_dir, sc.get("sceneId"), sc.get("narration", ""), voice=voice)
        jobs.set_status(jid, "completed" if res.get("status") == "completed" else "failed",
                        artifact_paths=[str(proj_dir / "audio")])
        return 200, {"job_id": jid, "result": res}

    if method == "POST" and p == "/api/assembly/manifest":
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        return 200, manifest.build_manifest(proj_dir, only_scene=b.get("sceneNumber"))

    if p == "/api/tts/settings" and method in ("GET", "POST"):
        pid = (query.get("project_id") if method == "GET" else (body or {}).get("project_id")) or ""
        proj_dir = root / pid
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        if method == "POST":
            b = body or {}
            tts.set_tts_config(proj_dir, style=b.get("style"), voice_id=b.get("voice_id"),
                               model=b.get("model"), voice_settings=b.get("voice_settings"))
        return 200, {"config": tts.effective_voice(proj_dir), "presets": tts.load_voice_presets()}

    if p == "/api/llm/settings" and method in ("GET", "POST"):
        if method == "POST":
            llm.set_orchestrator((body or {}).get("orchestrator", ""))
        return 200, {"orchestrator": llm.get_orchestrator(), "choices": list(llm.VALID)}

    if method == "POST" and p == "/api/assistant":
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        instruction = (b.get("instruction") or "").strip()
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        if not instruction:
            return 400, {"error": "instruction 필요"}
        jobs = ctx["jobs"]
        jid = jobs.create("assistant", b.get("project_id", ""))
        out = assistant.run_assistant(proj_dir, instruction,
                                      on_event=lambda ln: jobs.append_log(jid, ln))
        jobs.set_status(jid, "completed")
        return 200, {"job_id": jid, **out}

    if method == "POST" and p == "/api/scenes/image":
        b = body or {}
        pid = b.get("project_id", "")
        proj_dir = root / pid
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        sn = b.get("sceneNumber")
        data = scenes.load_scenes(proj_dir)
        scene = next((s for s in data["scenes"] if s.get("sceneNumber") == sn), None)
        if not scene:
            return 404, {"error": f"scene {sn} 없음"}
        sid = scene.get("sceneId")
        char = (b.get("character") or "").strip()
        character_ref = None
        if char:
            cref = proj_dir / "characters" / f"char_{char}.png"
            if cref.exists():
                character_ref = str(cref)
        jobs = ctx["jobs"]
        jid = jobs.create("scene-image", pid)
        name = scenes.new_scene_image_name(sid)
        res = imagegen.generate_one(
            proj_dir, name,
            (b.get("prompt") or "").strip() or scene.get("image_prompt", "") or scene.get("visual_summary", ""),
            subdir="storyboard", character_ref=character_ref,
            on_line=lambda ln: jobs.append_log(jid, ln))
        if res.get("status") == "completed":
            from pathlib import Path as _P
            rel = _P(res["path"]).relative_to(proj_dir).as_posix()
            scenes.set_image_ref(proj_dir, sn, rel)
        jobs.set_status(jid, "completed" if res.get("status") == "completed" else "failed",
                        artifact_paths=[str(proj_dir / "storyboard")])
        return 200, {"job_id": jid, "result": res}

    if method == "POST" and p == "/api/assets/generate":
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        cat = (b.get("category") or "").strip()
        prompt = (b.get("prompt") or "").strip()
        if cat not in ("background", "prop"):
            return 400, {"error": "category는 background 또는 prop"}
        if not prompt:
            return 400, {"error": "prompt 필요"}
        char = (b.get("character") or "").strip()
        char_ref = None
        if char:
            cref = proj_dir / "characters" / f"char_{char}.png"
            if cref.exists():
                char_ref = str(cref)
        jobs = ctx["jobs"]
        jid = jobs.create("asset", b.get("project_id", ""))
        name = f"{cat}_{uuid.uuid4().hex[:6]}.png"
        res = imagegen.generate_asset(
            proj_dir, name, prompt, char_ref=char_ref, subdir="images",
            on_line=lambda ln: jobs.append_log(jid, ln))
        jobs.set_status(jid, "completed" if res.get("status") == "completed" else "failed",
                        artifact_paths=[str(proj_dir / "images")])
        return 200, {"job_id": jid, "result": res}

    if method == "POST" and p == "/api/scenes/unlink-image":
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        res = scenes.set_image_ref(proj_dir, b.get("sceneNumber"), "")
        return (200, res) if res.get("ok") else (404, res)

    if method == "POST" and p == "/api/scenes/analyze-layers":
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        data = scenes.load_scenes(proj_dir)
        sc = next((s for s in data["scenes"] if s.get("sceneNumber") == b.get("sceneNumber")), None)
        if not sc:
            return 404, {"error": "씬 없음"}
        if not sc.get("_image"):
            return 422, {"error": "씬 이미지 먼저 생성/링크 필요"}
        jobs = ctx["jobs"]
        jid = jobs.create("analyze-layers", b.get("project_id", ""))
        ctx_str = f"제목: {sc.get('title', '')} / 요약: {sc.get('visual_summary', '')}"
        res = imagegen.analyze_scene_layers(
            proj_dir, str(proj_dir / sc["_image"]),
            narration=sc.get("narration", "") or "", context=ctx_str,
            on_line=lambda ln: jobs.append_log(jid, ln))
        jobs.set_status(jid, "completed" if res.get("elements") else "failed")
        return 200, {"job_id": jid, "elements": res.get("elements", []), "error": res.get("error")}

    if method == "POST" and p == "/api/scenes/split-layers":
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        data = scenes.load_scenes(proj_dir)
        sc = next((s for s in data["scenes"] if s.get("sceneNumber") == b.get("sceneNumber")), None)
        if not sc:
            return 404, {"error": "씬 없음"}
        if not sc.get("_image"):
            return 422, {"error": "씬 이미지 없음"}
        elements = b.get("elements") or []
        if not elements:
            return 400, {"error": "elements 필요"}
        jobs = ctx["jobs"]
        jid = jobs.create("split-layers", b.get("project_id", ""))
        conc = int(b.get("concurrency", 4))
        res = imagegen.split_scene_to_elements(
            proj_dir, str(proj_dir / sc["_image"]), sc.get("sceneId"), elements,
            concurrency=conc, on_event=lambda r: jobs.append_log(jid, f"{r['name']}: {r['status']}"))
        ok = any(l.get("status") == "completed" for l in res.get("layers", []))
        jobs.set_status(jid, "completed" if ok else "failed", artifact_paths=[str(proj_dir / "layers")])
        return 200, {"job_id": jid, "result": res}

    if method == "GET" and p == "/api/media":
        pid = query.get("project_id", "")
        return 200, {"items": media.list_media(root / pid)}

    if method == "GET" and p == "/api/search-images":
        pid = query.get("project_id", "")
        q = (query.get("q") or "").strip()
        if not (root / pid).is_dir():
            return 404, {"error": "프로젝트 없음"}
        if not q:
            return 400, {"error": "검색어 필요"}
        return 200, search.search_images(q, engine=query.get("engine", "serper"))

    if method == "POST" and p == "/api/search-images/save":
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        url, name = b.get("url", ""), b.get("name", "")
        if not url or not name:
            return 400, {"error": "url, name 필요"}
        return 200, {"result": search.save_image(proj_dir, url, name)}

    if method == "POST" and p == "/api/scenes/set-image":
        b = body or {}
        proj_dir = root / b.get("project_id", "")
        if not proj_dir.is_dir():
            return 404, {"error": "프로젝트 없음"}
        return 200, {"result": media.set_scene_image(proj_dir, b.get("sceneNumber"), b.get("src", ""))}

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
        data = scenes.load_scenes(proj_dir)   # sceneId 보장 + enrich
        scene_list = data["scenes"]
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
        for sc in scene_list:
            sid = sc.get("sceneId")
            prompt = sc.get("image_prompt") or sc.get("visual_summary") or sc.get("narration", "")
            items.append((f"sb_{sid}.png", prompt))
        results = imagegen.generate_many(
            proj_dir, items, subdir="storyboard", concurrency=conc, character_ref=character_ref,
            on_event=lambda rel, res: jobs.append_log(jid, f"{rel}: {res['status']}"))
        done = sum(1 for r in results.values() if r["status"] == "completed")
        jobs.set_status(jid, "completed" if done else "failed",
                        artifact_paths=[str(proj_dir / "storyboard")])
        return 200, {"job_id": jid, "status": jobs.get(jid)["status"],
                     "generated": done, "total": len(scene_list)}

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
        data = scenes.load_scenes(proj_dir)
        items = []        # (sid, sb_path)
        sid_to_n = {}
        for sc in data["scenes"]:
            sid, n = sc.get("sceneId"), sc.get("sceneNumber")
            if sc.get("_image"):
                items.append((sid, proj_dir / sc["_image"]))
                sid_to_n[sid] = n
        if not items:
            return 422, {"error": "씬 이미지 없음(sb_{sid}.png)"}
        jobs = ctx["jobs"]
        jid = jobs.create("layers", pid)
        conc = int(b.get("concurrency", 4))
        results = imagegen.generate_scene_layers(
            proj_dir, items, concurrency=conc,
            on_event=lambda key, kind, res: jobs.append_log(jid, f"{key}/{kind}: {res['status']}"))
        ok = sum(1 for v in results.values()
                 if v.get("background", {}).get("status") == "completed"
                 and v.get("character", {}).get("status") == "completed")
        layers = {"project_id": pid, "scenes": [
            {"sceneNumber": sid_to_n[sid], "background": f"layers/bg_{sid}.png",
             "character": f"layers/char_{sid}.png"} for sid in sid_to_n]}
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
