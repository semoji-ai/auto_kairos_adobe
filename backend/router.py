"""순수 라우팅 — (method, path, query, body, ctx) -> (status, dict). 소켓 의존 없음."""
from __future__ import annotations

import shutil
from pathlib import Path

from backend import projects, skills_cfg, sessions, pipeline
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
