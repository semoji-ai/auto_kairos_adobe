import json

from backend import timeline


def _proj(tmp_path, scenes_list):
    proj = tmp_path / "p"
    (proj / "audio").mkdir(parents=True)
    (proj / "scenes.json").write_text(json.dumps(
        {"project_id": "p", "scenes": scenes_list}, ensure_ascii=False), encoding="utf-8")
    return proj


def test_build_plan_accumulates_tts_duration(tmp_path, monkeypatch):
    proj = _proj(tmp_path, [
        {"sceneNumber": 1, "sceneId": "aaa", "narration": "첫 씬"},
        {"sceneNumber": 2, "sceneId": "bbb", "narration": "둘째 씬"},   # 오디오 없음 → 5초
        {"sceneNumber": 3, "sceneId": "ccc", "narration": "셋째 씬"},
    ])
    (proj / "audio" / "tts_aaa.mp3").write_bytes(b"x")
    (proj / "audio" / "tts_ccc.mp3").write_bytes(b"x")
    monkeypatch.setattr(timeline._tts, "audio_duration", lambda p: 2.0)

    plan = timeline.build_plan(proj)
    starts = [i["start"] for i in plan["items"]]
    durs = [i["duration"] for i in plan["items"]]
    assert durs == [2.0, timeline.DEFAULT_DUR, 2.0]
    assert starts == [0.0, 2.0, 7.0]
    assert plan["total"] == 9.0
    assert plan["items"][0]["comp"] == "S01_aaa"


def test_build_plan_only_scene_keeps_global_start(tmp_path, monkeypatch):
    proj = _proj(tmp_path, [
        {"sceneNumber": 1, "sceneId": "aaa", "narration": "첫 씬"},
        {"sceneNumber": 2, "sceneId": "bbb", "narration": "둘째 씬"},
    ])
    monkeypatch.setattr(timeline._tts, "audio_duration", lambda p: 0.0)

    one = timeline.build_plan(proj, only_scene=2)
    every = timeline.build_plan(proj)
    assert len(one["items"]) == 1
    assert one["items"][0]["start"] == every["items"][1]["start"] == timeline.DEFAULT_DUR
    assert one["items"][0]["duration"] == timeline.DEFAULT_DUR


def test_comp_name_prefers_existing():
    assert timeline.comp_name({"sceneNumber": 7, "sceneId": "zz"}) == "S07_zz"
    assert timeline.comp_name({"sceneNumber": 7, "sceneId": "zz", "ae_comp_name": "Custom"}) == "Custom"
