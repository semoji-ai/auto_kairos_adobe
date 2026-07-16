"""이미지 업스케일 — Upscayl 엔진(upscayl-bin, Real-ESRGAN 계열) CLI 연동. API 키 불필요·로컬 GPU.
콘텐츠 타입에 맞는 모델 자동 선택: 생성 semoji(flat)=digital-art, 실사 사진=upscayl-standard.
이미지 생성(codex $imagegen)과 별개 후처리. 런타임 v3 의존 없음."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

# 설치 위치 — env 우선, 없으면 표준 위치. (install.sh --upscayl가 여기에 받음)
_HOME_SHARE = Path.home() / ".local" / "share" / "upscayl"
BIN = os.environ.get("UPSCAYL_BIN") or str(_HOME_SHARE / "bin" / "upscayl-bin")
MODELS_DIR = os.environ.get("UPSCAYL_MODELS") or str(_HOME_SHARE / "models")

# 콘텐츠 타입 → 모델. illustration=평면 벡터(스타일 보존), photo=실사(그레인/아티팩트 제거).
_MODEL_BY_CONTENT = {
    "illustration": "digital-art-4x",
    "photo": "upscayl-standard-4x",
    "photo_detail": "remacri-4x",     # 질감 더 보존(덜 매끈)
}
DEFAULT_CONTENT = "illustration"


def _bin() -> str | None:
    if os.path.isfile(BIN) and os.access(BIN, os.X_OK):
        return BIN
    found = shutil.which("upscayl-bin")
    return found


def available_models() -> list:
    """models 폴더의 설치된 모델명(.param 기준)."""
    d = Path(MODELS_DIR)
    if not d.is_dir():
        return []
    return sorted({p.stem for p in d.glob("*.param")})


def upscale_status() -> dict:
    """엔진·모델 설치 여부. {installed, models, hint}."""
    b = _bin()
    models = available_models()
    if not b:
        return {"installed": False, "models": [], "hint": "upscayl-bin 미설치 — ./install.sh --upscayl"}
    if not models:
        return {"installed": True, "models": [], "hint": f"모델 없음 — {MODELS_DIR}에 .param/.bin 필요"}
    return {"installed": True, "models": models, "hint": ""}


def _pick_model(content: str, model: str | None) -> str | None:
    """명시 model 우선(설치돼 있으면), 없으면 content로 자동. 미설치면 설치된 것 중 폴백."""
    installed = available_models()
    if model and model in installed:
        return model
    want = _MODEL_BY_CONTENT.get(content or DEFAULT_CONTENT, _MODEL_BY_CONTENT[DEFAULT_CONTENT])
    if want in installed:
        return want
    # 폴백: illustration이면 아무 art류, photo면 아무 standard류, 그래도 없으면 첫 모델
    for m in installed:
        if content == "photo" and "art" not in m:
            return m
        if content != "photo" and "art" in m:
            return m
    return installed[0] if installed else None


def upscale_image(src_png, out_png=None, *, content: str = DEFAULT_CONTENT,
                  model: str | None = None, scale: int = 2, on_event=None) -> dict:
    """src를 업스케일해 out(기본: src 옆 _up 접미사)으로. {status, path, model, scale}|{status:failed,error}.
    content: 'illustration'(생성 semoji) / 'photo'(실사). model 명시하면 우선."""
    b = _bin()
    if not b:
        return {"status": "failed", "error": "upscayl-bin 미설치"}
    src = Path(src_png)
    if not src.is_file():
        return {"status": "failed", "error": f"입력 없음: {src_png}"}
    m = _pick_model(content, model)
    if not m:
        return {"status": "failed", "error": "설치된 업스케일 모델 없음"}
    out = Path(out_png) if out_png else src.with_name(f"{src.stem}_up{src.suffix or '.png'}")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [b, "-i", str(src), "-o", str(out), "-n", m, "-m", MODELS_DIR,
           "-s", str(int(scale)), "-f", "png"]
    if on_event:
        on_event(f"업스케일 {m} x{scale}: {src.name}")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "업스케일 타임아웃"}
    if p.returncode != 0 or not out.is_file():
        tail = ((p.stdout or "") + (p.stderr or ""))[-300:]
        return {"status": "failed", "error": "업스케일 실패", "log_tail": tail}
    return {"status": "completed", "path": str(out), "model": m, "scale": int(scale)}
