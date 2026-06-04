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
