import json
from pathlib import Path
from backend.router import handle_request
from backend.jobs import JobRegistry

ROOT = Path(__file__).resolve().parents[1] / "projects"


def _ctx():
    return {"root": ROOT, "jobs": JobRegistry()}


def test_health():
    code, body = handle_request("GET", "/health", {}, None, _ctx())
    assert code == 200
    assert body["backend_status"] == "connected"


def test_projects_list():
    code, body = handle_request("GET", "/api/projects", {}, None, _ctx())
    assert code == 200
    assert any(p["project_id"] == "demo01" for p in body["projects"])


def test_project_load():
    code, body = handle_request("POST", "/api/projects/load", {},
                                {"project_id": "demo01"}, _ctx())
    assert code == 200
    assert body["project_id"] == "demo01"


def test_unknown_404():
    code, body = handle_request("GET", "/nope", {}, None, _ctx())
    assert code == 404


def test_skills_run_returns_job_id(monkeypatch, tmp_path):
    import backend.router as r
    proj = tmp_path / "demoX"
    proj.mkdir()
    (proj / "final_manuscript.md").write_text("원고 텍스트.", encoding="utf-8")

    def fake_run(prompt, cwd, **kw):
        out = kw.get("output_last")
        if out:
            from pathlib import Path as _P
            _P(out).write_text(
                '{"version":"adobe-0.1","project_id":"demoX","total_scenes":0,"scenes":[]}',
                encoding="utf-8")
        return {"returncode": 0, "session_id": "sess-1", "output_last": out}

    monkeypatch.setattr(r, "run_skill", fake_run)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/skills/run", {},
                                {"project_id": "demoX", "skill_name": "scene-decompose"}, ctx)
    assert code == 200
    jid = body["job_id"]
    code2, jbody = handle_request("GET", f"/api/jobs/{jid}", {}, None, ctx)
    assert code2 == 200
    assert jbody["status"] == "completed"
    assert any("scenes.json" in a for a in jbody["artifact_paths"])


def test_skills_run_missing_manuscript_422(tmp_path):
    proj = tmp_path / "noman"
    proj.mkdir()
    (proj / "plan.md").write_text("# 제목", encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/skills/run", {},
                                {"project_id": "noman", "skill_name": "scene-decompose"}, ctx)
    assert code == 422
    assert "final_manuscript.md" in body["error"]


def test_projects_file_returns_manuscript():
    ctx = _ctx()
    code, body = handle_request("GET", "/api/projects/file",
                                {"project_id": "demo01", "name": "final_manuscript.md"}, None, ctx)
    assert code == 200
    assert body["name"] == "final_manuscript.md"
    assert "카지노" in body["content"]


def test_projects_file_rejects_traversal():
    ctx = _ctx()
    code, body = handle_request("GET", "/api/projects/file",
                                {"project_id": "demo01", "name": "../../backend/app.py"}, None, ctx)
    assert code == 400


def test_projects_file_404_missing():
    ctx = _ctx()
    code, body = handle_request("GET", "/api/projects/file",
                                {"project_id": "demo01", "name": "nope.md"}, None, ctx)
    assert code == 404


def test_projects_file_rejects_absolute(tmp_path):
    proj = tmp_path / "p1"; proj.mkdir()
    (proj / "final_manuscript.md").write_text("원고", encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/projects/file",
                                {"project_id": "p1", "name": "/etc/hosts"}, None, ctx)
    assert code == 400


def test_images_generate_from_references(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "references.json").write_text(
        '{"project_id":"p","references":[{"id":"ref_1","subject":"차","image_prompt":"전기차"}]}',
        encoding="utf-8")

    def fake_gen(proj_dir, rel_out, image_prompt, **kw):
        out = proj_dir / "images" / rel_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(r.imagegen, "generate_one", fake_gen)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/images/generate", {},
                                {"project_id": "p"}, ctx)
    assert code == 200
    assert body["generated"] == 1


def test_images_list(tmp_path):
    proj = tmp_path / "p"; (proj / "images").mkdir(parents=True)
    (proj / "images" / "ref_1.png").write_bytes(b"\x89PNG")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/images/list",
                                {"project_id": "p"}, None, ctx)
    assert code == 200
    assert "ref_1.png" in body["images"]


def test_storyboard_generate_from_scenes(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text(
        '{"project_id":"p","total_scenes":2,"scenes":['
        '{"sceneNumber":1,"title":"A","narration":"가","image_prompt":"장면1"},'
        '{"sceneNumber":2,"title":"B","narration":"나","image_prompt":"장면2"}]}',
        encoding="utf-8")

    def fake_gen(proj_dir, rel_out, image_prompt, **kw):
        assert kw.get("subdir") == "storyboard"
        out = proj_dir / "storyboard" / rel_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(r.imagegen, "generate_one", fake_gen)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/storyboard/generate", {},
                                {"project_id": "p"}, ctx)
    assert code == 200
    assert body["generated"] == 2


def test_storyboard_generate_requires_scenes(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/storyboard/generate", {},
                                {"project_id": "p"}, ctx)
    assert code == 422


def test_storyboard_list(tmp_path):
    proj = tmp_path / "p"; (proj / "storyboard").mkdir(parents=True)
    (proj / "storyboard" / "sb_1.png").write_bytes(b"\x89PNG")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/storyboard/list",
                                {"project_id": "p"}, None, ctx)
    assert code == 200
    assert "sb_1.png" in body["images"]
