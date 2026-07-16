import subprocess
from pathlib import Path
from backend import upscale


class _CP:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_status_not_installed(monkeypatch):
    monkeypatch.setattr(upscale, "_bin", lambda: None)
    st = upscale.upscale_status()
    assert st["installed"] is False


def test_status_installed_no_models(monkeypatch, tmp_path):
    monkeypatch.setattr(upscale, "_bin", lambda: "/bin/upscayl-bin")
    monkeypatch.setattr(upscale, "available_models", lambda: [])
    assert upscale.upscale_status()["installed"] and not upscale.upscale_status()["models"]


def test_pick_model_by_content(monkeypatch):
    monkeypatch.setattr(upscale, "available_models",
                        lambda: ["digital-art-4x", "upscayl-standard-4x", "remacri-4x"])
    assert upscale._pick_model("illustration", None) == "digital-art-4x"
    assert upscale._pick_model("photo", None) == "upscayl-standard-4x"
    assert upscale._pick_model("photo_detail", None) == "remacri-4x"
    assert upscale._pick_model("photo", "digital-art-4x") == "digital-art-4x"   # 명시 우선


def test_pick_model_fallback(monkeypatch):
    monkeypatch.setattr(upscale, "available_models", lambda: ["digital-art-4x"])
    assert upscale._pick_model("photo", None) == "digital-art-4x"   # photo 모델 없으면 폴백


def test_upscale_builds_cmd(monkeypatch, tmp_path):
    (tmp_path / "s.png").write_bytes(b"img")
    seen = {}

    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"up")   # 출력 생성
        return _CP(0, "Upscayled Successfully")

    monkeypatch.setattr(upscale, "_bin", lambda: "/bin/upscayl-bin")
    monkeypatch.setattr(upscale, "available_models", lambda: ["digital-art-4x", "upscayl-standard-4x"])
    monkeypatch.setattr(upscale.subprocess, "run", fake_run)
    r = upscale.upscale_image(str(tmp_path / "s.png"), str(tmp_path / "o.png"),
                              content="illustration", scale=2)
    assert r["status"] == "completed" and r["model"] == "digital-art-4x" and r["scale"] == 2
    cmd = seen["cmd"]
    assert "-n" in cmd and "digital-art-4x" in cmd and "-s" in cmd and "2" in cmd


def test_upscale_missing_input(monkeypatch, tmp_path):
    monkeypatch.setattr(upscale, "_bin", lambda: "/bin/upscayl-bin")
    monkeypatch.setattr(upscale, "available_models", lambda: ["digital-art-4x"])
    r = upscale.upscale_image(str(tmp_path / "nope.png"))
    assert r["status"] == "failed"
