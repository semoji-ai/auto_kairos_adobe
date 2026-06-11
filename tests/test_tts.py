from pathlib import Path
from backend import tts


def test_parse_afinfo_duration():
    sample = "File: x.mp3\nestimated duration: 3.456 sec\nbit rate: ..."
    assert abs(tts._parse_afinfo_duration(sample) - 3.456) < 0.001


def test_parse_afinfo_duration_missing():
    assert tts._parse_afinfo_duration("no duration here") == 0.0


def test_clean_text_strips_directions_and_emoji():
    assert tts._clean_text("안녕(웃으며) 하세요 🙂") == "안녕 하세요"


def test_engine_and_ext_by_key(monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    assert tts._engine() == "elevenlabs" and tts._ext() == "mp3"
    assert tts.scene_audio_name("abc") == "tts_abc.mp3"
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "")
    assert tts._engine() == "say" and tts._ext() == "wav"
    assert tts.scene_audio_name("abc") == "tts_abc.wav"


def test_synthesize_elevenlabs(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    monkeypatch.setattr(tts, "_eleven_fetch", lambda text, voice=None: b"ID3mp3bytes")
    monkeypatch.setattr(tts, "audio_duration", lambda p: 4.2)
    out = tmp_path / "a.mp3"
    res = tts.synthesize("안녕하세요", out)
    assert res["status"] == "completed" and res["engine"] == "elevenlabs"
    assert out.read_bytes() == b"ID3mp3bytes" and res["duration"] == 4.2


def test_synthesize_elevenlabs_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    def boom(text, voice=None): raise RuntimeError("401")
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
    res = tts.synthesize("안녕하세요", tmp_path / "a.wav", voice="Yuna")
    assert res["status"] == "completed" and res["engine"] == "say"
    assert "say" in calls["cmd"][0] and "Yuna" in calls["cmd"] and res["duration"] == 2.5


def test_generate_scene_tts(tmp_path, monkeypatch):
    monkeypatch.setattr(tts.env, "get_key", lambda k, *a: "KEY" if k == "ELEVENLABS_API_KEY" else "")
    monkeypatch.setattr(tts, "synthesize",
                        lambda text, out, voice=None: (Path(out).write_bytes(b"x"),
                                                       {"status": "completed", "path": str(out), "duration": 1.0})[1])
    proj = tmp_path / "p"; proj.mkdir()
    res = tts.generate_scene_tts(proj, "sid9", "내레이션")
    assert res["status"] == "completed"
    assert (proj / "audio" / "tts_sid9.mp3").exists()     # 엔진 elevenlabs → mp3
    assert res["rel"] == "audio/tts_sid9.mp3"


def test_generate_scene_tts_empty_text(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    res = tts.generate_scene_tts(proj, "sid9", "   ")
    assert res["status"] == "failed"            # 빈 내레이션
