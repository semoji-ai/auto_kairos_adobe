from pathlib import Path
from backend import tts


def test_parse_afinfo_duration():
    sample = "File: x.mp3\nestimated duration: 3.456 sec\nbit rate: ..."
    assert abs(tts._parse_afinfo_duration(sample) - 3.456) < 0.001


def test_parse_afinfo_duration_missing():
    assert tts._parse_afinfo_duration("no duration here") == 0.0


def test_clean_text_strips_directions_and_emoji():
    assert tts._clean_text("안녕(웃으며) 하세요 🙂") == "안녕 하세요"


def test_clean_text_middle_dot_to_comma():
    # 가운뎃점(U+00B7) — ElevenLabs가 붙여 읽어 → 쉼표로 끊어 읽기
    assert tts._clean_text("미국·영국·프랑스") == "미국, 영국, 프랑스"


def test_clean_text_middle_dot_variants():
    # 한글 가운뎃점(U+318D)·홑화살괄호형(U+2027)도 동일 처리
    assert tts._clean_text("사과ㆍ배") == "사과, 배"
    assert tts._clean_text("가‧나") == "가, 나"


def test_clean_text_middle_dot_no_double_space_or_comma():
    # 가운뎃점 주변 공백/중복이 있어도 ", " 하나로 정리(이중 공백·", ," 방지)
    assert tts._clean_text("미국 · 영국") == "미국, 영국"
    assert tts._clean_text("가··나") == "가, 나"
    assert tts._clean_text("·시작·") == "시작"


def test_engine_and_ext_by_key(monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    assert tts._engine() == "elevenlabs" and tts._ext() == "mp3"
    assert tts.scene_audio_name("abc") == "tts_abc.mp3"
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "")
    assert tts._engine() == "say" and tts._ext() == "wav"
    assert tts.scene_audio_name("abc") == "tts_abc.wav"


def test_synthesize_elevenlabs(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    monkeypatch.setattr(tts, "_eleven_fetch", lambda text, cfg=None: (b"ID3mp3bytes", None))
    monkeypatch.setattr(tts, "audio_duration", lambda p: 4.2)
    out = tmp_path / "a.mp3"
    res = tts.synthesize("안녕하세요", out, cfg={"voice_id": "V", "model": "m", "voice_settings": {}})
    assert res["status"] == "completed" and res["engine"] == "elevenlabs"
    assert out.read_bytes() == b"ID3mp3bytes" and res["duration"] == 4.2
    assert not (tmp_path / "a.timestamps.json").exists()    # alignment 없음 → 사이드카 없음


def test_synthesize_saves_timestamp_sidecar(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    align = {"characters": ["안", "녕"],
             "character_start_times_seconds": [0.0, 0.3],
             "character_end_times_seconds": [0.3, 0.7]}
    monkeypatch.setattr(tts, "_eleven_fetch", lambda text, cfg=None: (b"ID3x", align))
    monkeypatch.setattr(tts, "audio_duration", lambda p: 4.2)
    out = tmp_path / "tts_s1.mp3"
    res = tts.synthesize("안녕", out)
    assert res["status"] == "completed"
    side = tmp_path / "tts_s1.timestamps.json"
    assert side.exists()
    d = _json.loads(side.read_text(encoding="utf-8"))
    assert d["text"] == "안녕" and d["characters"] == ["안", "녕"]
    assert d["starts"] == [0.0, 0.3] and d["ends"] == [0.3, 0.7]
    assert res["duration"] == 0.7                            # duration = ends[-1] 우선


def test_synthesize_elevenlabs_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    def boom(text, cfg=None): raise RuntimeError("401")
    monkeypatch.setattr(tts, "_eleven_fetch", boom)
    res = tts.synthesize("안녕", tmp_path / "a.mp3")
    assert res["status"] == "failed" and "401" in res["error"]


def test_synthesize_say_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "")     # 키 없음 → say
    calls = {}

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"RIFFwav")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    monkeypatch.setattr(tts.shutil, "which", lambda n: "/usr/bin/say")
    monkeypatch.setattr(tts, "audio_duration", lambda p: 2.5)
    res = tts.synthesize("안녕하세요", tmp_path / "a.wav")     # say는 cfg 무시·SAY_VOICE
    assert res["status"] == "completed" and res["engine"] == "say"
    assert "say" in calls["cmd"][0] and tts.SAY_VOICE in calls["cmd"] and res["duration"] == 2.5


def test_generate_scene_tts(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    monkeypatch.setattr(tts, "synthesize",
                        lambda text, out, cfg=None: (Path(out).write_bytes(b"x"),
                                                     {"status": "completed", "path": str(out), "duration": 1.0})[1])
    proj = tmp_path / "p"; proj.mkdir()
    res = tts.generate_scene_tts(proj, "sid9", "내레이션")
    assert res["status"] == "completed"
    assert (proj / "audio" / "tts_sid9.mp3").exists()     # 엔진 elevenlabs → mp3
    assert res["rel"] == "audio/tts_sid9.mp3"


def test_generate_scene_tts_clears_narration_dirty(tmp_path, monkeypatch):
    """TTS 재생성 성공 시 해당 씬 narration_dirty 제거(재생성 배지 끔)."""
    import json as _json
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    monkeypatch.setattr(tts, "synthesize",
                        lambda text, out, cfg=None: (Path(out).write_bytes(b"x"),
                                                     {"status": "completed", "path": str(out), "duration": 1.0})[1])
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text(_json.dumps({"scenes": [
        {"sceneNumber": 1, "sceneId": "sidD", "narration": "n", "narration_dirty": True}]}),
        encoding="utf-8")
    res = tts.generate_scene_tts(proj, "sidD", "내레이션")
    assert res["status"] == "completed"
    saved = _json.loads((proj / "scenes.json").read_text(encoding="utf-8"))
    assert "narration_dirty" not in saved["scenes"][0]      # dirty 해제됨


def test_generate_scene_tts_empty_text(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    res = tts.generate_scene_tts(proj, "sid9", "   ")
    assert res["status"] == "failed"            # 빈 내레이션


def test_load_presets_has_semoji_default():
    pr = tts.load_voice_presets()
    assert pr["default_style"] == "semoji"
    assert pr["presets"]["semoji"]["voice_id"] == "W7FnAxJNpD5WGjrF5GLp"


def test_effective_voice_default_semoji(tmp_path):
    cfg = tts.effective_voice(tmp_path / "p")     # 설정 파일 없음 → semoji 기본
    assert cfg["style"] == "semoji" and cfg["voice_id"] == "W7FnAxJNpD5WGjrF5GLp"
    assert cfg["voice_settings"]["similarity_boost"] == 0.9


def test_set_and_get_tts_config_style(tmp_path):
    d = tmp_path / "p"; d.mkdir()
    tts.set_tts_config(d, style="lego")
    cfg = tts.effective_voice(d)
    assert cfg["style"] == "lego" and cfg["voice_id"] == "4JJwo477JUAx3HV0T7n7"


def test_set_tts_config_voice_id_override(tmp_path):
    d = tmp_path / "p"; d.mkdir()
    tts.set_tts_config(d, style="semoji", voice_id="CUSTOM123")
    cfg = tts.effective_voice(d)
    assert cfg["voice_id"] == "CUSTOM123" and cfg["style"] == "semoji"   # override 우선


def test_effective_voice_unknown_style_falls_back(tmp_path):
    d = tmp_path / "p"; d.mkdir()
    tts.set_tts_config(d, style="nonexistent")
    cfg = tts.effective_voice(d)
    assert cfg["voice_id"] == "W7FnAxJNpD5WGjrF5GLp"    # semoji 프리셋으로 폴백
