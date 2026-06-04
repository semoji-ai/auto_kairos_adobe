"""프로젝트 스토어 — projects/{id}/ 스캔/로드 (순수 로직)."""
from __future__ import annotations

import os
from pathlib import Path

ARTIFACT_FILES = ["plan.md", "final_manuscript.md", "scenes.json", "pd_notebook.md"]


def projects_root() -> Path:
    env = os.environ.get("AK_PROJECTS_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "projects"


def _title(proj_dir: Path) -> str:
    plan = proj_dir / "plan.md"
    if plan.exists():
        for line in plan.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return proj_dir.name


def _artifacts(proj_dir: Path) -> dict:
    return {f: (proj_dir / f).exists() for f in ARTIFACT_FILES}


def _status(arts: dict) -> str:
    if arts.get("scenes.json"):
        return "decomposed"
    if arts.get("final_manuscript.md"):
        return "manuscript"
    return "empty"


def _updated_at(proj_dir: Path) -> float:
    mtimes = [p.stat().st_mtime for p in proj_dir.glob("*") if p.is_file()]
    return max(mtimes) if mtimes else proj_dir.stat().st_mtime


def scan_projects(root: Path) -> list[dict]:
    if not root.exists():
        return []
    rows = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        arts = _artifacts(d)
        if not (arts["final_manuscript.md"] or arts["plan.md"]):
            continue
        rows.append({
            "project_id": d.name,
            "title": _title(d),
            "status": _status(arts),
            "updated_at": _updated_at(d),
            "artifacts": arts,
        })
    return rows


def load_project(root: Path, project_id: str) -> dict:
    d = root / project_id
    if not d.is_dir():
        raise FileNotFoundError(f"project not found: {project_id}")
    arts = _artifacts(d)
    next_actions = []
    if arts["final_manuscript.md"] and not arts["scenes.json"]:
        next_actions.append("scene-decompose")
    return {
        "project_id": project_id,
        "title": _title(d),
        "status": _status(arts),
        "artifacts": arts,
        "next_actions": next_actions,
    }
