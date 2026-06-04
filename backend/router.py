"""순수 라우팅 — (method, path, query, body, ctx) -> (status, dict). 소켓 의존 없음."""
from __future__ import annotations

import shutil
from pathlib import Path

from backend import projects
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
        jobs = ctx["jobs"]
        jid = jobs.create(skill, pid)
        skill_md = (SKILLS_DIR / skill / "SKILL.md")
        schema = (SKILLS_DIR / skill / "scenes.schema.json")
        out = proj_dir / "scenes.json"
        manuscript = (proj_dir / "final_manuscript.md")
        prompt = (
            skill_md.read_text(encoding="utf-8") if skill_md.exists() else f"skill: {skill}"
        ) + "\n\n## 입력 원고\n" + (
            manuscript.read_text(encoding="utf-8") if manuscript.exists() else ""
        ) + f"\n\nproject_id={pid}. scenes.json 형식으로만 출력."
        result = run_skill(
            prompt, proj_dir,
            output_schema=str(schema) if schema.exists() else None,
            output_last=str(out),
            on_line=lambda ln: jobs.append_log(jid, ln),
        )
        if result["returncode"] == 0 and out.exists():
            jobs.set_status(jid, "completed", artifact_paths=[str(out)])
        else:
            jobs.set_status(jid, "failed", error=f"rc={result['returncode']}")
        return 200, {"job_id": jid, "status": jobs.get(jid)["status"]}

    if method == "GET" and p.startswith("/api/jobs/"):
        jid = p.rsplit("/", 1)[-1]
        j = ctx["jobs"].get(jid)
        if not j:
            return 404, {"error": f"job not found: {jid}"}
        return 200, j

    return 404, {"error": "not found", "path": path}
