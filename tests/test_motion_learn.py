import json
from pathlib import Path
from scripts.motion_learn import state


def test_state_roundtrip(tmp_path):
    ref = tmp_path / "abc123"
    state.set_stage(ref, "collected", {"title": "Test"})
    s = state.get_state(ref)
    assert s["stage"] == "collected" and s["title"] == "Test"
    state.set_stage(ref, "analyzed")
    assert state.get_state(ref)["stage"] == "analyzed"
    assert state.get_state(ref)["title"] == "Test"   # 기존 필드 보존


def test_state_missing(tmp_path):
    assert state.get_state(tmp_path / "none") == {}
