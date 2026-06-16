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


def test_slug_stable():
    from scripts.motion_learn import collect
    s1 = collect.slug_for("https://youtu.be/AbC123xyz")
    s2 = collect.slug_for("https://youtu.be/AbC123xyz")
    assert s1 == s2 and len(s1) == 12 and s1.isalnum()


def test_collect_skips_existing(tmp_path, monkeypatch):
    from scripts.motion_learn import collect
    calls = []
    monkeypatch.setattr(collect, "_run_ytdlp", lambda url, out: (calls.append(url), out.write_bytes(b"x"))[-1])
    monkeypatch.setattr(collect, "_probe_meta", lambda p: {"title": "T", "duration": 10.0, "width": 1920, "height": 1080})
    refs = tmp_path / "refs"
    r1 = collect.collect(["https://youtu.be/AbC123xyz"], refs)
    assert len(r1) == 1 and len(calls) == 1
    r2 = collect.collect(["https://youtu.be/AbC123xyz"], refs)   # 이미 받음 → 스킵
    assert len(calls) == 1 and r2[0]["slug"] == r1[0]["slug"]
