from backend.jobs import JobRegistry


def test_create_and_get():
    reg = JobRegistry()
    jid = reg.create("scene-decompose", "demo01")
    assert jid.startswith("job_")
    j = reg.get(jid)
    assert j["status"] == "running"
    assert j["skill_name"] == "scene-decompose"
    assert j["project_id"] == "demo01"
    assert j["logs"] == []


def test_append_log_and_complete():
    reg = JobRegistry()
    jid = reg.create("scene-decompose", "demo01")
    reg.append_log(jid, "line1")
    reg.append_log(jid, "line2")
    reg.set_status(jid, "completed", artifact_paths=["projects/demo01/scenes.json"])
    j = reg.get(jid)
    assert j["logs"] == ["line1", "line2"]
    assert j["status"] == "completed"
    assert j["artifact_paths"] == ["projects/demo01/scenes.json"]


def test_get_unknown_returns_none():
    assert JobRegistry().get("job_999") is None
