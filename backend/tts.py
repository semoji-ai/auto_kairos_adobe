"""씬 내레이션 TTS.

기본 엔진: **ElevenLabs**(MP3 — CEP/Chromium 재생·AE 가져오기 호환).
ELEVENLABS_API_KEY 없으면 macOS `say`(WAV)로 폴백(개발용).
길이는 afinfo(초). stdlib만 사용(urllib).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from backend import env

# ElevenLabs 기본값(v3 narrator와 동일 계열 — semoji)
DEFAULT_VOICE_ID = "W7FnAxJNpD5WGjrF5GLp"
DEFAULT_MODEL = "eleven_multilingual_v2"
VOICE_SETTINGS = {
    "stability": 1.0, "similarity_boost": 0.9, "style": 0.9,
    "use_speaker_boost": True, "speed": 1.1,
}
SAY_VOICE = os.environ.get("TTS_SAY_VOICE", "Yuna")     # 폴백용 한국어 보이스

_VOICES_FILE = Path(__file__).resolve().parents[1] / "data" / "artstyle" / "voices.json"


def load_voice_presets() -> dict:
    try:
        return json.loads(_VOICES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"default_style": "semoji", "presets": {}}


def _tts_config_path(proj_dir: Path) -> Path:
    return Path(proj_dir) / "tts_config.json"


def get_tts_config(proj_dir: Path) -> dict:
    """프로젝트 tts_config.json(없으면 {})."""
    p = _tts_config_path(proj_dir)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def set_tts_config(proj_dir: Path, *, style=None, voice_id=None, model=None, voice_settings=None) -> dict:
    """프로젝트 TTS 설정 저장(부분 갱신). 반환=effective_voice."""
    proj_dir = Path(proj_dir)
    cfg = get_tts_config(proj_dir)
    if style is not None:
        cfg["style"] = style
    if voice_id is not None:
        cfg["voice_id"] = voice_id          # 빈 문자열이면 override 해제(스타일 프리셋 사용)
        if voice_id == "":
            cfg.pop("voice_id", None)
    if model is not None:
        cfg["model"] = model
    if voice_settings is not None:
        cfg["voice_settings"] = voice_settings
    _tts_config_path(proj_dir).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return effective_voice(proj_dir)


def effective_voice(proj_dir: Path) -> dict:
    """유효 voice 설정 해석: 프로젝트 override → 스타일 프리셋 → semoji 기본.
    반환 {style, voice_id, model, voice_settings}."""
    presets = load_voice_presets()
    table = presets.get("presets", {})
    default_style = presets.get("default_style", "semoji")
    cfg = get_tts_config(proj_dir)
    style = cfg.get("style") or default_style
    base = table.get(style) or table.get(default_style) or {}
    voice_id = cfg.get("voice_id") or base.get("voice_id") or DEFAULT_VOICE_ID
    voice_settings = cfg.get("voice_settings") or base.get("voice_settings") or VOICE_SETTINGS
    model = cfg.get("model") or base.get("model") or DEFAULT_MODEL
    return {"style": style, "voice_id": voice_id, "model": model, "voice_settings": voice_settings}


def _engine() -> str:
    """ELEVENLABS_API_KEY 있으면 elevenlabs, 없으면 say."""
    return "elevenlabs" if env.get_key("ELEVENLABS_API_KEY") else "say"


def _ext() -> str:
    return "mp3" if _engine() == "elevenlabs" else "wav"


def scene_audio_name(sid: str) -> str:
    return f"tts_{sid}.{_ext()}"


def _light_clean(text: str) -> str:
    """경량 정리(폴백) — 지문(괄호)·이모지 제거 + 가운뎃점→쉼표."""
    t = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]", "", text or "")
    t = re.sub(r"[\U0001F000-\U0001FAFF\U00002600-\U000027BF]", "", t)
    t = re.sub(r"\s*[·ㆍ‧]\s*", ", ", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s*,(?:\s*,)+", ",", t)
    t = re.sub(r"\s+,", ",", t)
    return t.strip().strip(",").strip()


def _clean_text(text: str) -> str:
    """TTS 전처리 — v3 KoreanTTSPreprocessor 이식(숫자·날짜·단위·영어약어 한글 음차 등) +
    가운뎃점(·)→쉼표(ElevenLabs가 가운뎃점을 무시하고 붙여 읽는 문제). 전처리기 실패 시 경량 폴백."""
    t = re.sub(r"\s*[·ㆍ‧]\s*", ", ", text or "")        # 가운뎃점 먼저(숫자 변환 전 끊어읽기 고정)
    try:
        from backend.korean_tts_preprocessor import KoreanTTSPreprocessor
        out, _ = KoreanTTSPreprocessor().process_text(t)   # 괄호·이모지·마크다운 정리 포함
    except Exception:
        return _light_clean(t)
    out = re.sub(r"\s*,(?:\s*,)+", ",", out)               # 연속 쉼표(가운뎃점 중복 등) 축약
    out = re.sub(r",(?=\S)", ", ", out)                    # 쉼표 뒤 공백 보장
    out = re.sub(r"\s+,", ",", out)                        # 쉼표 앞 공백 제거
    return out.strip().strip(",").strip()


def _parse_afinfo_duration(text: str) -> float:
    m = re.search(r"estimated duration:\s*([\d.]+)\s*sec", text)
    return float(m.group(1)) if m else 0.0


def audio_duration(path: Path) -> float:
    """afinfo로 길이(초). wav·mp3 모두 가능. 실패 시 0.0."""
    try:
        r = subprocess.run(["afinfo", str(path)], capture_output=True, text=True, timeout=20)
        return _parse_afinfo_duration(r.stdout)
    except Exception:
        return 0.0


def _eleven_fetch(text: str, cfg: dict | None = None):
    """ElevenLabs with-timestamps — (MP3 bytes, alignment dict|None). 실패 시 일반 엔드포인트 폴백."""
    cfg = cfg or {}
    key = env.get_key("ELEVENLABS_API_KEY")
    vid = cfg.get("voice_id") or DEFAULT_VOICE_ID
    model = cfg.get("model") or DEFAULT_MODEL
    settings = cfg.get("voice_settings") or VOICE_SETTINGS
    body = json.dumps({"text": text, "model_id": model, "voice_settings": settings}).encode("utf-8")
    headers = {"xi-api-key": key, "Content-Type": "application/json"}
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/with-timestamps?output_format=mp3_44100_128"
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        import base64
        return base64.b64decode(data["audio_base64"]), data.get("alignment") or data.get("normalized_alignment")
    except Exception:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_128"
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={**headers, "Accept": "audio/mpeg"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read(), None


def _synth_say(text: str, out_path: Path, voice: str | None) -> None:
    cmd = ["say", "-v", voice or SAY_VOICE, "-o", str(out_path),
           "--data-format=LEI16@22050", "--file-format=WAVE", text]
    subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)


def synthesize(text: str, out_path: Path, cfg: dict | None = None) -> dict:
    """text를 out_path로 합성. 엔진(elevenlabs/say)은 키 유무로 결정. {status, path, duration, engine}."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    eng = _engine()
    clean = _clean_text(text)
    align = None
    try:
        if eng == "elevenlabs":
            audio, align = _eleven_fetch(clean, cfg)
            out_path.write_bytes(audio)
            if align:
                side = out_path.parent / (out_path.stem + ".timestamps.json")
                side.write_text(json.dumps({
                    "text": clean,
                    "characters": align.get("characters", []),
                    "starts": align.get("character_start_times_seconds", []),
                    "ends": align.get("character_end_times_seconds", []),
                }, ensure_ascii=False), encoding="utf-8")
        else:
            if shutil.which("say") is None:
                return {"status": "failed", "error": "say 없음·ElevenLabs 키 없음", "path": str(out_path), "duration": 0.0}
            _synth_say(clean, out_path, SAY_VOICE)
    except Exception as e:
        return {"status": "failed", "error": str(e)[:200], "path": str(out_path), "duration": 0.0, "engine": eng}
    if not out_path.exists() or out_path.stat().st_size == 0:
        return {"status": "failed", "error": "출력 없음", "path": str(out_path), "duration": 0.0, "engine": eng}
    ends = (align or {}).get("character_end_times_seconds") or []
    if ends:                                        # alignment가 가장 정확
        dur = round(float(ends[-1]), 3)
    else:
        dur = audio_duration(out_path)
        if dur == 0.0 and eng == "elevenlabs":      # afinfo 실패 시 비트레이트 추정(128kbps)
            dur = round(out_path.stat().st_size * 8 / 128000, 3)
    return {"status": "completed", "path": str(out_path), "duration": dur, "engine": eng}


def generate_scene_tts(proj_dir: Path, sid: str, text: str, voice: str | None = None) -> dict:
    """씬 오디오 audio/tts_{sid}.{ext} 생성(갱신). 빈 텍스트면 failed."""
    if not (text or "").strip():
        return {"status": "failed", "error": "내레이션 비어있음"}
    cfg = effective_voice(proj_dir)
    if voice:
        cfg = {**cfg, "voice_id": voice}
    out = Path(proj_dir) / "audio" / scene_audio_name(sid)
    out.parent.mkdir(parents=True, exist_ok=True)
    res = synthesize(text, out, cfg=cfg)
    if res.get("status") == "completed":
        res["rel"] = f"audio/{out.name}"
        res["voice_id"] = cfg["voice_id"]
        try:                                # TTS 재생성 성공 → narration_dirty 해제(재생성 배지 끄기)
            from backend import scenes as _scenes
            _scenes.clear_narration_dirty(Path(proj_dir), sid)
        except Exception:
            pass
    return res
