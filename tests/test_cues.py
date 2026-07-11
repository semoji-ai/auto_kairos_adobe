import json
from backend import cues


def _ts(pairs):
    """pairs=[(char, start)] → timestamps dict."""
    return {"characters": [c for c, _ in pairs], "starts": [s for _, s in pairs],
            "ends": [s + 0.1 for _, s in pairs]}


def test_phrase_start_basic():
    ts = _ts([("제", 1.5), ("이", 1.6), ("콥", 1.7), (" ", 1.8), ("은", 1.9)])
    assert cues.phrase_start_sec(ts, "제이콥", preprocess=False) == 1.5
    assert cues.phrase_start_sec(ts, "콥", preprocess=False) == 1.7


def test_phrase_ignores_spaces():
    ts = _ts([("특", 2.9), ("허", 3.0), (" ", 3.1), ("문", 3.2), ("서", 3.3)])
    assert cues.phrase_start_sec(ts, "특허 문서", preprocess=False) == 2.9


def test_phrase_not_found():
    ts = _ts([("가", 0.0), ("나", 0.2)])
    assert cues.phrase_start_sec(ts, "없는말", preprocess=False) is None


def test_phrase_number_spoken_form(monkeypatch):
    # '96%' → 발화형 '구십육퍼센트'로 변환해 매칭
    monkeypatch.setattr(cues, "_spoken_form", lambda p: "구십육퍼센트" if "96" in p else p)
    ts = _ts([("보", 0.0), ("유", 0.2), ("율", 0.4), ("은", 0.6),
              ("구", 0.8), ("십", 0.9), ("육", 1.0), ("퍼", 1.1), ("센", 1.2), ("트", 1.3)])
    assert cues.phrase_start_sec(ts, "96%") == 0.8


def test_scene_text_cue_metric(tmp_path, monkeypatch):
    (tmp_path / "audio").mkdir()
    ts = _ts([("구", 0.8), ("십", 0.9), ("육", 1.0), ("퍼", 1.1), ("센", 1.2), ("트", 1.3)])
    (tmp_path / "audio" / "tts_m1.timestamps.json").write_text(json.dumps(ts), encoding="utf-8")
    monkeypatch.setattr(cues, "_spoken_form", lambda p: "구십육퍼센트" if "96" in p else p)
    scene = {"sceneId": "m1", "layout": "metric_spotlight", "value": "96%", "label": "보유율"}
    cue = cues.scene_text_cue(tmp_path, scene, lead=0.15)
    assert cue == 0.65        # 0.8 - 0.15


def test_scene_text_cue_no_timestamps(tmp_path):
    scene = {"sceneId": "x", "layout": "metric_spotlight", "value": "96%"}
    assert cues.scene_text_cue(tmp_path, scene) is None
