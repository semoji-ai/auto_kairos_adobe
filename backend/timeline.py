"""AE 타임라인 배치 계획 — 씬 컴프를 어느 시점에 얼마 길이로 놓을지 계산.

씬 길이 = TTS 오디오 길이, 없으면 DEFAULT_DUR(5초).
씬 시작 = 앞 씬 길이의 누적합. only_scene을 줘도 시작 시점은 전체 기준과 같으므로,
한 씬만 다시 내려도 제자리에 들어간다.
"""
from __future__ import annotations

from pathlib import Path

from backend import scenes as _scenes
from backend import tts as _tts

DEFAULT_DUR = 5.0


def comp_name(scene: dict) -> str:
    """매니페스트와 같은 컴프 이름 규칙(S01_abcd1234)."""
    existing = (scene.get("ae_comp_name") or "").strip()
    if existing:
        return existing
    return f"S{int(scene.get('sceneNumber') or 0):02d}_{scene.get('sceneId') or ''}"


def scene_duration(proj_dir: Path, scene: dict) -> float:
    """TTS 오디오 길이(초). 없거나 0이면 DEFAULT_DUR."""
    rel = scene.get("_audio")
    if rel:
        d = scene.get("_audio_dur")
        if not d:
            d = _tts.audio_duration(Path(proj_dir) / rel)
        if d:
            return round(float(d), 3)
    return DEFAULT_DUR


def build_plan(proj_dir: Path, only_scene: int | None = None) -> dict:
    """{items:[{sceneNumber, sceneId, comp, start, duration}], total, scenes}.
    only_scene이 있으면 그 씬만 담되 start는 전체 누적 기준을 유지."""
    proj_dir = Path(proj_dir)
    data = _scenes.load_scenes(proj_dir)
    items, offset = [], 0.0
    for s in data.get("scenes", []):
        dur = scene_duration(proj_dir, s)
        if only_scene is None or s.get("sceneNumber") == only_scene:
            items.append({
                "sceneNumber": s.get("sceneNumber"),
                "sceneId": s.get("sceneId"),
                "comp": comp_name(s),
                "start": round(offset, 3),
                "duration": dur,
            })
        offset += dur
    return {"items": items, "total": round(offset, 3), "scenes": len(items)}
