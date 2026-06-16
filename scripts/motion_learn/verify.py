"""Phase B 검증 — 헤드리스 렌더 + 듀얼 비디오 gemini 대조 + 2층 게이트.
이 파일 전반부는 순수 로직(테스트 대상), verify()는 오케스트레이션."""
from __future__ import annotations

import json


def structural_check(motion: dict, lib: dict) -> dict:
    """motion.json 정합성: 컷 존재 + 사용 프리셋이 라이브러리에 존재하는가(결정론적)."""
    issues = []
    cuts = motion.get("cuts", []) or []
    if not cuts:
        issues.append("컷 없음")
    presets = set((lib.get("presets") or {}).keys())
    for i, c in enumerate(cuts):
        for lyr in (c.get("layers", []) or []):
            for an in (lyr.get("anim", []) or []):
                pn = an.get("preset")
                if pn and pn not in presets:
                    issues.append(f"cut{i}: 미존재 프리셋 {pn}")
    return {"pass": not issues, "issues": issues, "cut_count": len(cuts)}


def passes_gate(structural_pass: bool, score: int, threshold: int = 75) -> bool:
    return bool(structural_pass) and int(score) >= int(threshold)


def parse_verdict(raw) -> dict:
    data = raw if isinstance(raw, dict) else json.loads(raw)
    return {
        "score": int(data.get("score", 0)),
        "diffs": data.get("diffs", []) or [],
        "summary": data.get("summary", "") or "",
    }


def build_ae_command(afterfx_bin: str, jsx_path: str) -> list:
    return [afterfx_bin, "-r", jsx_path]


def build_ffmpeg_command(mov: str, mp4: str) -> list:
    return ["ffmpeg", "-y", "-i", mov, "-c:v", "libx264", "-pix_fmt", "yuv420p", mp4]
