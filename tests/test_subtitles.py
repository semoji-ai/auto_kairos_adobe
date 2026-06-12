import json
from pathlib import Path

from backend import subtitles


def test_split_lines_word_boundary():
    text = "우주 탐사의 역사는 인류의 도전 정신을 보여줍니다"
    lines = subtitles.split_lines(text, max_len=20)
    assert all(len(l) <= 20 for l in lines)
    assert " ".join(lines) == text                  # 어절 보존
    assert len(lines) >= 2


def test_split_lines_empty():
    assert subtitles.split_lines("") == []
    assert subtitles.split_lines(None) == []


def test_split_lines_single_short():
    assert subtitles.split_lines("짧다") == ["짧다"]


def test_fmt_srt_time():
    assert subtitles._fmt_srt_time(0.0) == "00:00:00,000"
    assert subtitles._fmt_srt_time(3.456) == "00:00:03,456"
    assert subtitles._fmt_srt_time(3661.5) == "01:01:01,500"


def test_line_cues_maps_char_timings():
    # "안녕 하세요" — alignment에 공백 포함, 줄 분할은 max 3자 → ["안녕", "하세요"]
    ts = {"text": "안녕 하세요",
          "characters": ["안", "녕", " ", "하", "세", "요"],
          "starts": [0.0, 0.2, 0.4, 0.5, 0.7, 0.9],
          "ends": [0.2, 0.4, 0.5, 0.7, 0.9, 1.1]}
    cues = subtitles.line_cues(ts, max_len=3)
    assert [c["text"] for c in cues] == ["안녕", "하세요"]
    assert cues[0]["start"] == 0.0 and cues[0]["end"] == 0.4
    assert cues[1]["start"] == 0.5 and cues[1]["end"] == 1.1


def test_line_cues_empty_alignment():
    assert subtitles.line_cues({"text": "안녕", "characters": [], "starts": [], "ends": []}) == []


def _proj(tmp_path, scenes_list):
    proj = tmp_path / "p"
    (proj / "audio").mkdir(parents=True)
    (proj / "scenes.json").write_text(json.dumps(
        {"project_id": "p", "scenes": scenes_list}, ensure_ascii=False), encoding="utf-8")
    return proj


def test_build_subtitles_offsets_and_fallback(tmp_path, monkeypatch):
    scenes_list = [
        {"sceneNumber": 1, "sceneId": "aaa", "narration": "안녕 하세요", "duration_estimate_sec": 9},
        {"sceneNumber": 2, "sceneId": "bbb", "narration": "둘째 씬 자막", "duration_estimate_sec": 4},
    ]
    proj = _proj(tmp_path, scenes_list)
    # 씬1: 오디오 + 타임스탬프 사이드카(길이 2.0초로 가장)
    (proj / "audio" / "tts_aaa.mp3").write_bytes(b"x")
    (proj / "audio" / "tts_aaa.timestamps.json").write_text(json.dumps({
        "text": "안녕 하세요",
        "characters": ["안", "녕", " ", "하", "세", "요"],
        "starts": [0.0, 0.2, 0.4, 0.5, 0.7, 0.9],
        "ends": [0.2, 0.4, 0.5, 0.7, 0.9, 1.1]}), encoding="utf-8")
    monkeypatch.setattr(subtitles.tts, "audio_duration", lambda p: 2.0)

    res = subtitles.build_subtitles(proj)
    cues = json.loads((proj / "subtitles.json").read_text(encoding="utf-8"))["cues"]
    # 씬1: 타임스탬프 기반 1줄("안녕 하세요" ≤20자) — [0, 1.1]
    assert cues[0]["text"] == "안녕 하세요"
    assert cues[0]["start"] == 0.0 and cues[0]["end"] == 1.1
    # 씬2: 사이드카 없음 → 균등 폴백, 오프셋 = 씬1 길이(오디오 2.0초)
    assert res["scenes_no_ts"] == [2]
    s2 = [c for c in cues if c["start"] >= 2.0]
    assert s2 and s2[0]["start"] == 2.0
    assert all(c["end"] <= 2.0 + 4.0 for c in s2)            # estimate=4초 내
    assert res["lines"] == len(cues)
    # SRT 형식
    srt = (proj / "subtitles.srt").read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,100\n안녕 하세요\n")
    assert " --> " in srt
    assert res["json"].endswith("subtitles.json") and res["srt"].endswith("subtitles.srt")


def test_build_subtitles_no_audio_uses_estimate(tmp_path, monkeypatch):
    scenes_list = [
        {"sceneNumber": 1, "sceneId": "ccc", "narration": "첫 씬", "duration_estimate_sec": 5},
        {"sceneNumber": 2, "sceneId": "ddd", "narration": "둘째 씬"},
    ]
    proj = _proj(tmp_path, scenes_list)
    res = subtitles.build_subtitles(proj)
    cues = json.loads((proj / "subtitles.json").read_text(encoding="utf-8"))["cues"]
    # 씬2 오프셋 = 씬1 estimate(5초); 씬2 길이=기본 3.0
    assert cues[1]["start"] == 5.0
    assert res["scenes_no_ts"] == [1, 2]
