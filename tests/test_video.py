import json
import subprocess
from pathlib import Path
from backend import video


class _CP:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_status_not_installed(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda b: None)
    st = video.higgsfield_status()
    assert st["installed"] is False and st["authed"] is False


def test_status_installed_authed(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda b: "/bin/higgsfield")
    monkeypatch.setattr(video, "_run", lambda a, **k: _CP(0, "tok_xyz"))
    st = video.higgsfield_status()
    assert st["installed"] and st["authed"]


def test_status_installed_not_authed(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda b: "/bin/higgsfield")
    monkeypatch.setattr(video, "_run", lambda a, **k: _CP(1, ""))
    assert video.higgsfield_status()["authed"] is False


def test_list_models_dynamic_params(monkeypatch):
    video._CACHE.clear()
    _PARAMS = json.dumps({"params": [
        {"name": "prompt", "type": "string", "required": True},
        {"name": "mode", "type": "string", "enum": ["std", "fast"], "default": "std"},
        {"name": "start_image", "type": "object"},         # 미디어 → 제외
        {"name": "image_references", "type": "array"}]})    # 배열 → 제외

    def fake_run(a, **k):
        return _CP(0, "tok") if a[:2] == ["auth", "token"] else _CP(0, _PARAMS)

    monkeypatch.setattr(video.shutil, "which", lambda b: "/bin/higgsfield")
    monkeypatch.setattr(video, "_run", fake_run)
    reg = video.list_models()
    assert reg["status"]["authed"]
    m = reg["models"][0]
    names = [p["name"] for p in m["params"]]
    assert "mode" in names and "prompt" in names
    assert "start_image" not in names and "image_references" not in names   # 미디어/배열 제외


def test_build_video_prompt_uses_model_style(tmp_path, monkeypatch):
    from backend import llm
    (tmp_path / "s.png").write_bytes(b"x")
    scene = {"sceneNumber": 1, "visual_summary": "부엌", "narration": "n", "_image": "s.png"}

    def fake(prompt, cwd, *, output_last=None, images=None, on_line=None, **k):
        assert "Kling" in prompt                      # 모델 스타일 주입
        Path(output_last).write_text("a cat slowly turns, slow push-in", encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    r = video.build_video_prompt(tmp_path, scene, "kling3_0")
    assert r["prompt"].startswith("a cat")


def test_generate_video_builds_cmd_and_downloads(tmp_path, monkeypatch):
    (tmp_path / "scene.png").write_bytes(b"img")
    seen = {}

    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        return _CP(0, json.dumps({"results": [{"url": "https://x/out.mp4"}]}))

    monkeypatch.setattr(video.shutil, "which", lambda b: "/bin/higgsfield")
    monkeypatch.setattr(video.subprocess, "run", fake_run)
    monkeypatch.setattr(video, "_download", lambda url, dest, **k: dest.write_bytes(b"vid") or True)
    r = video.generate_video(tmp_path, str(tmp_path / "scene.png"), "seedance_2_0",
                             {"resolution": "1080p", "mode": "std", "duration": 5},
                             "cinematic push in", out_name="scene_1_seedance_2_0")
    assert r["status"] == "completed" and r["rel"].endswith(".mp4")
    cmd = seen["cmd"]
    assert "generate" in cmd and "create" in cmd and "seedance_2_0" in cmd
    assert "--start-image" in cmd and "--prompt" in cmd
    assert "--resolution" in cmd and "1080p" in cmd and "--mode" in cmd   # 파라미터 전달
    assert "--wait" in cmd


def test_generate_video_no_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda b: "/bin/higgsfield")
    (tmp_path / "s.png").write_bytes(b"x")
    r = video.generate_video(tmp_path, str(tmp_path / "s.png"), "seedance_2_0", {}, "  ", out_name="x")
    assert r["status"] == "failed"


def test_result_url_and_to_sec():
    assert video._result_url('{"data":{"video_url":"https://a/b.mp4"}}') == "https://a/b.mp4"
    assert video._result_url("noise https://c/d.mp4 tail") == "https://c/d.mp4"
    assert video._to_sec("20m") == 1200 and video._to_sec("90s") == 90 and video._to_sec("1h") == 3600
