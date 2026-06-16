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


def test_merge_presets(tmp_path):
    from scripts.motion_learn import merge_presets
    lib = tmp_path / "motion_presets.json"
    lib.write_text(json.dumps({"presets": {"fade_scale_in": {"props": ["opacity"], "ease": "easeOut"}}}), encoding="utf-8")
    candidates = [
        {"name": "wipe_in", "props": ["trimEnd"], "ease": "easeInOut", "params": {}},
        {"name": "fade_scale_in", "props": ["opacity"], "ease": "easeOut"},   # 중복 → 스킵
        {"name": "particle_burst", "props": ["particles"], "ease": "easeOut"}  # 새 props → 빌더확장 플래그
    ]
    res = merge_presets.merge(lib, candidates, approved=["wipe_in", "fade_scale_in", "particle_burst"])
    d = json.loads(lib.read_text())
    assert "wipe_in" in d["presets"]
    assert res["skipped_duplicate"] == ["fade_scale_in"]
    assert res["needs_builder"] == ["particle_burst"]
    assert "particle_burst" in d["presets"]


def test_merge_known_props_only():
    from scripts.motion_learn import merge_presets
    assert merge_presets.is_builder_supported({"props": ["opacity", "scale"]})
    assert not merge_presets.is_builder_supported({"props": ["particles"]})


def test_analyze_splits_output(tmp_path, monkeypatch):
    """gemini 응답(JSON)을 motion.json + new_presets.json으로 분리 저장."""
    from scripts.motion_learn import analyze, state
    refs = tmp_path / "refs"; ref = refs / "slug1"; ref.mkdir(parents=True)
    (refs / "slug1.mp4").write_bytes(b"x")
    state.set_stage(ref, "collected", {"url": "u"})
    lib = tmp_path / "motion_presets.json"
    lib.write_text(json.dumps({"presets": {"fade_scale_in": {}}}), encoding="utf-8")
    fake = {"cuts": [{"type": "cut", "start": 0, "dur": 1, "layers": []}],
            "new_presets": [{"name": "wipe_in", "props": ["trimEnd"], "ease": "easeInOut"}]}
    monkeypatch.setattr(analyze, "_gemini_analyze", lambda mp4, lib_keys: fake)
    res = analyze.analyze("slug1", refs, lib)
    assert json.loads((ref / "motion.json").read_text())["cuts"][0]["dur"] == 1
    assert json.loads((ref / "new_presets.json").read_text())[0]["name"] == "wipe_in"
    assert state.get_state(ref)["stage"] == "analyzed"
    assert res["new_preset_count"] == 1


def test_cli_help_lists_commands():
    """CLI가 collect/analyze/merge 서브커맨드를 제공."""
    import scripts.motion_learn.__main__ as cli
    p = cli.build_parser()
    sub = p._subparsers._group_actions[0].choices
    assert "collect" in sub and "analyze" in sub and "merge" in sub


def test_cli_merge_syncs_jsx(tmp_path, monkeypatch):
    """merge 후 jsx 빌더 복사본 동기화 — 새 프리셋이 빌더에도 반영."""
    import scripts.motion_learn.__main__ as cli
    # ROOT 하위 구조 모킹
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    lib = tmp_path / "data" / "artstyle" / "motion" / "motion_presets.json"; lib.parent.mkdir(parents=True)
    lib.write_text(json.dumps({"presets": {}}), encoding="utf-8")
    monkeypatch.setattr(cli, "LIB", lib)
    jsxdir = tmp_path / "cep" / "com.autokairos.pd" / "jsx" / "tylenol"; jsxdir.mkdir(parents=True)
    ref = tmp_path / "refs" / "s1"; ref.mkdir(parents=True)
    monkeypatch.setattr(cli, "REFS", tmp_path / "refs")
    (ref / "new_presets.json").write_text(json.dumps([{"name": "wipe_in", "props": ["trimEnd"], "ease": "easeInOut"}]), encoding="utf-8")
    cli.main(["merge", "--slug", "s1", "--approve", "wipe_in"])
    assert "wipe_in" in json.loads((jsxdir / "motion_presets.json").read_text())["presets"]


def test_smoothness_to_influence_anchors():
    from scripts.motion_learn.curve import smoothness_to_influence
    assert smoothness_to_influence(0.0) == 0
    assert smoothness_to_influence(0.5) == 33
    assert smoothness_to_influence(0.75) == 75
    assert smoothness_to_influence(0.9) == 90
    assert smoothness_to_influence(1.0) == 95


def test_smoothness_to_influence_interp_and_clamp():
    from scripts.motion_learn.curve import smoothness_to_influence
    # 0.5~0.75 구간 중앙(0.625): 33 + (75-33)*0.5 = 54
    assert smoothness_to_influence(0.625) == 54
    # 범위 밖 클램프
    assert smoothness_to_influence(-1.0) == 0
    assert smoothness_to_influence(2.0) == 95


def test_gemini_client_compare_videos(monkeypatch):
    from scripts.motion_learn import gemini_client as gc
    monkeypatch.setattr(gc, "_client", lambda: object())
    monkeypatch.setattr(gc, "_upload", lambda client, p: "FILE:" + p)
    captured = {}
    monkeypatch.setattr(gc, "_generate_json",
                        lambda client, contents, models=None: (captured.update(contents=contents), {"score": 88})[1])
    out = gc.compare_videos("orig.mp4", "render.mp4", "PROMPT")
    assert out == {"score": 88}
    assert captured["contents"] == ["FILE:orig.mp4", "FILE:render.mp4", "PROMPT"]


def test_gemini_client_analyze_video(monkeypatch):
    from scripts.motion_learn import gemini_client as gc
    monkeypatch.setattr(gc, "_client", lambda: object())
    monkeypatch.setattr(gc, "_upload", lambda client, p: "F:" + p)
    monkeypatch.setattr(gc, "_generate_json",
                        lambda client, contents, models=None: {"cuts": [], "contents_len": len(contents)})
    out = gc.analyze_video("v.mp4", "PROMPT")
    assert out["contents_len"] == 2  # [file, prompt]
