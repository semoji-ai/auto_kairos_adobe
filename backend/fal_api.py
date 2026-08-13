"""fal 이미지 편집 API 호출 — 레이어 분리 전용.

CLAUDE.md의 '이미지 생성은 codex $imagegen 전용' 규칙의 명시적 예외.
씬 이미지·캐릭터 생성은 여전히 codex를 쓰고, 레이어 분리만 이 경로를 탄다.
새 의존성 없이 stdlib urllib만 사용(tts.py의 ElevenLabs 호출과 같은 방식).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import urllib.request
from pathlib import Path

from backend import env

ENDPOINT = "https://fal.run/xai/grok-imagine-image/v2.0/edit"
MAX_INPUT_IMAGES = 3          # 모델 상한 — 초과분은 앞에서부터 자른다


class FalError(Exception):
    """fal 호출 실패 — 키 없음·비200·응답 이상. 상위 잡이 실패로 표면화한다."""


def data_uri(path: Path) -> str:
    """로컬 이미지를 base64 data URI로. fal 입력이 URL이라 로컬 파일을 그대로 못 넘긴다."""
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def edit_image(prompt: str, image_paths: list, *, output_format: str = "png",
               resolution: str = "2k", timeout: int = 180) -> bytes:
    """참조 이미지들을 두고 prompt대로 편집한 이미지 1장을 바이트로 반환."""
    key = env.get_key("FAL_KEY")
    if not key:
        raise FalError("FAL_KEY 없음(auto_kairos .env 또는 환경변수)")
    paths = [Path(p) for p in (image_paths or []) if Path(p).is_file()]
    if not paths:
        raise FalError("입력 이미지 없음")
    body = json.dumps({
        "prompt": prompt,
        "image_urls": [data_uri(p) for p in paths[:MAX_INPUT_IMAGES]],
        "num_images": 1,
        "output_format": output_format,
        "resolution": resolution,
    }).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT, data=body, method="POST",
        headers={"Authorization": f"Key {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except FalError:
        raise
    except Exception as e:                       # HTTPError·URLError·타임아웃·파싱 실패
        raise FalError(f"fal 호출 실패: {str(e)[:200]}") from e
    images = data.get("images") or []
    if not images or not images[0].get("url"):
        raise FalError(f"fal 응답에 이미지 없음: {str(data)[:200]}")
    try:
        img_req = urllib.request.Request(images[0]["url"])
        with urllib.request.urlopen(img_req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        raise FalError(f"fal 결과 내려받기 실패: {str(e)[:200]}") from e
