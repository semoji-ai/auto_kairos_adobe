"""씬 타이밍·컴프 이름의 단일 기준.

컴프 조립(manifest)·말자막(subtitles)·타임라인 배치가 **모두 여기 함수를 쓴다.**
각자 계산하면 셋의 씬 경계가 어긋나 자막이 밀리고 음성이 잘린다.

씬 길이 = TTS 오디오 길이 → duration_estimate_sec → DEFAULT_DUR.
씬 시작 = 앞 씬 길이의 누적합. only_scene을 줘도 시작 시점은 전체 기준과 같으므로,
한 씬만 다시 내려도 제자리에 들어간다.
"""
from __future__ import annotations

from pathlib import Path

from backend import scenes as _scenes
from backend import tts as _tts

DEFAULT_DUR = 5.0


def comp_num(scene_number) -> str:
    """컴프 이름에 쓰는 씬 번호 표기. 정수는 2자리 0채움, 소수는 점을 밑줄로.

    씬을 삽입하면 25.25 같은 소수 번호가 생기는데, 이때 %02d는 그대로 터진다."""
    try:
        n = float(scene_number)
    except (TypeError, ValueError):
        return "00"
    if n == int(n):
        return f"{int(n):02d}"
    return str(n).replace(".", "_")


def comp_name(scene: dict) -> str:
    """씬 컴프 이름(S01_abcd1234). manifest·타임라인 배치가 같은 이름을 봐야 한다."""
    existing = (scene.get("ae_comp_name") or "").strip()
    if existing:
        return existing
    return f"S{comp_num(scene.get('sceneNumber'))}_{scene.get('sceneId') or ''}"


def scene_duration(proj_dir: Path, scene: dict) -> float:
    """씬 길이(초). TTS 오디오 → duration_estimate_sec → DEFAULT_DUR."""
    rel = scene.get("_audio")
    if rel:
        d = scene.get("_audio_dur")
        if not d:
            d = _tts.audio_duration(Path(proj_dir) / rel)
        if d:
            return round(float(d), 3)
    est = scene.get("duration_estimate_sec")
    try:
        if est and float(est) > 0:
            return round(float(est), 3)
    except (TypeError, ValueError):
        pass
    return DEFAULT_DUR


def scene_timings(proj_dir: Path, data: dict) -> list:
    """[(scene, start, duration)] — 전체 씬 기준 누적 시작 시점."""
    out, offset = [], 0.0
    for s in data.get("scenes", []):
        dur = scene_duration(proj_dir, s)
        out.append((s, round(offset, 3), dur))
        offset += dur
    return out


def build_plan(proj_dir: Path, only_scene: int | None = None) -> dict:
    """{items:[{sceneNumber, sceneId, comp, start, duration}], total, scenes}.
    only_scene이 있으면 그 씬만 담되 start는 전체 누적 기준을 유지."""
    proj_dir = Path(proj_dir)
    data = _scenes.load_scenes(proj_dir)
    items, total = [], 0.0
    for s, start, dur in scene_timings(proj_dir, data):
        total = start + dur
        if only_scene is None or s.get("sceneNumber") == only_scene:
            items.append({
                "sceneNumber": s.get("sceneNumber"),
                "sceneId": s.get("sceneId"),
                "comp": comp_name(s),
                "start": start,
                "duration": dur,
            })
    return {"items": items, "total": round(total, 3), "scenes": len(items)}
