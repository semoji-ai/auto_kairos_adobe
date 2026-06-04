from pathlib import Path
from backend import projects

ROOT = Path(__file__).resolve().parents[1] / "projects"


def test_scan_finds_demo_project():
    rows = projects.scan_projects(ROOT)
    ids = [r["project_id"] for r in rows]
    assert "demo01" in ids


def test_scan_row_shape():
    row = next(r for r in projects.scan_projects(ROOT) if r["project_id"] == "demo01")
    assert row["title"] == "트럼프의 세 번의 파산과 두 번의 백악관"
    assert row["status"] == "manuscript"
    assert set(["project_id", "title", "status", "updated_at", "artifacts"]) <= set(row)
    assert row["artifacts"]["final_manuscript.md"] is True
    assert row["artifacts"]["scenes.json"] is False


def test_load_project_next_actions():
    info = projects.load_project(ROOT, "demo01")
    assert info["project_id"] == "demo01"
    assert "scene-decompose" in info["next_actions"]
