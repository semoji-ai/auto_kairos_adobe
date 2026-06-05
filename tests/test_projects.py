from backend import projects


def _make_project(root, pid, *, plan=True, manuscript=True, scenes=False):
    d = root / pid
    d.mkdir(parents=True)
    if plan:
        (d / "plan.md").write_text("# 테스트 제목\n\n톤: 다큐", encoding="utf-8")
    if manuscript:
        (d / "final_manuscript.md").write_text("원고 본문.", encoding="utf-8")
    if scenes:
        (d / "scenes.json").write_text("{}", encoding="utf-8")
    return d


def test_scan_finds_project(tmp_path):
    _make_project(tmp_path, "p1")
    rows = projects.scan_projects(tmp_path)
    assert any(r["project_id"] == "p1" for r in rows)


def test_scan_row_shape(tmp_path):
    _make_project(tmp_path, "p1")
    row = next(r for r in projects.scan_projects(tmp_path) if r["project_id"] == "p1")
    assert row["title"] == "테스트 제목"
    assert row["status"] == "manuscript"
    assert set(["project_id", "title", "status", "updated_at", "artifacts"]) <= set(row)
    assert row["artifacts"]["final_manuscript.md"] is True
    assert row["artifacts"]["scenes.json"] is False


def test_status_decomposed_when_scenes(tmp_path):
    _make_project(tmp_path, "p2", scenes=True)
    row = next(r for r in projects.scan_projects(tmp_path) if r["project_id"] == "p2")
    assert row["status"] == "decomposed"


def test_load_project_next_actions(tmp_path):
    _make_project(tmp_path, "p1")
    info = projects.load_project(tmp_path, "p1")
    assert info["project_id"] == "p1"
    assert "scene-decompose" in info["next_actions"]
