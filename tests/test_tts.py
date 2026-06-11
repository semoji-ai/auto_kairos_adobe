from pathlib import Path
from backend import tts


def test_parse_afinfo_duration():
    sample = "File: x.aiff\nestimated duration: 3.456 sec\nbit rate: ..."
    assert abs(tts._parse_afinfo_duration(sample) - 3.456) < 0.001


def test_parse_afinfo_duration_missing():
    assert tts._parse_afinfo_duration("no duration here") == 0.0


def test_scene_audio_name():
    assert tts.scene_audio_name("abc123") == "tts_abc123.wav"


def test_synthesize_invokes_say(tmp_path, monkeypatch):
    calls = {}

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"FORM")   # 더미 오디오
        class R: returncode = 0
        return R()

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    monkeypatch.setattr(tts, "audio_duration", lambda p: 2.5)
    out = tmp_path / "a.wav"
    res = tts.synthesize("안녕하세요", out, voice="Yuna")
    assert res["status"] == "completed" and out.exists() and res["duration"] == 2.5
    assert "say" in calls["cmd"][0] and "Yuna" in calls["cmd"]


def test_generate_scene_tts(tmp_path, monkeypatch):
    monkeypatch.setattr(tts, "synthesize",
                        lambda text, out, voice=None: (Path(out).write_bytes(b"x"),
                                                       {"status": "completed", "path": str(out), "duration": 1.0})[1])
    proj = tmp_path / "p"; proj.mkdir()
    res = tts.generate_scene_tts(proj, "sid9", "내레이션", voice="Yuna")
    assert res["status"] == "completed"
    assert (proj / "audio" / "tts_sid9.wav").exists()
    assert res["rel"] == "audio/tts_sid9.wav"


def test_generate_scene_tts_empty_text(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    res = tts.generate_scene_tts(proj, "sid9", "   ")
    assert res["status"] == "failed"            # 빈 내레이션
