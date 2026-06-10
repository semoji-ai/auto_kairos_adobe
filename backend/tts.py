"""씬 내레이션 TTS — macOS `say`(기본) 기반. 한국어 보이스 Yuna. afinfo로 길이 측정."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

DEFAULT_VOICE = os.environ.get("TTS_VOICE", "Yuna")     # 한국어 ko_KR


def scene_audio_name(sid: str) -> str:
    return f"tts_{sid}.aiff"


def _parse_afinfo_duration(text: str) -> float:
    m = re.search(r"estimated duration:\s*([\d.]+)\s*sec", text)
    return float(m.group(1)) if m else 0.0


def audio_duration(path: Path) -> float:
    """afinfo로 길이(초). 실패 시 0.0."""
    try:
        r = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, timeout=20)
        return _parse_afinfo_duration(r.stdout)
    except Exception:
        return 0.0


def synthesize(text: str, out_path: Path, voice: str | None = None) -> dict:
    """`say`로 합성해 out_path(.aiff) 생성. {status, path, duration}."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("say") is None:
        return {"status": "failed", "error": "say 없음(macOS 전용)", "path": str(out_path), "duration": 0.0}
    cmd = ["say", "-v", voice or DEFAULT_VOICE, "-o", str(out_path), text]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except Exception as e:
        return {"status": "failed", "error": str(e), "path": str(out_path), "duration": 0.0}
    if r.returncode != 0 or not out_path.exists():
        return {"status": "failed", "error": (r.stderr or "")[:200], "path": str(out_path), "duration": 0.0}
    return {"status": "completed", "path": str(out_path), "duration": audio_duration(out_path)}


def generate_scene_tts(proj_dir: Path, sid: str, text: str, voice: str | None = None) -> dict:
    """씬 오디오 audio/tts_{sid}.aiff 생성(갱신). 빈 텍스트면 failed."""
    if not (text or "").strip():
        return {"status": "failed", "error": "내레이션 비어있음"}
    out = Path(proj_dir) / "audio" / scene_audio_name(sid)
    out.parent.mkdir(parents=True, exist_ok=True)
    res = synthesize(text, out, voice=voice)
    if res.get("status") == "completed":
        res["rel"] = f"audio/{scene_audio_name(sid)}"
    return res
