"""모션 디렉터 — 내레이션+레이어 목록으로 LLM이 프리셋 모션 플랜 생성(바운디드 enum).
임의 키프레임 좌표는 LLM이 내지 않음 — 수치는 jsx가 결정적으로 계산."""
from __future__ import annotations

import json
from pathlib import Path

from backend import scenes, llm, tts

_SCHEMA = Path(__file__).resolve().parent / "schemas" / "motion_plan.schema.json"

_PRESET_GUIDE = (
    "- slide_in: 화면 밖에서 등장(direction 필수). 등장 연출.\n"
    "- fade_in: 서서히 나타남.\n"
    "- pop: 통통 튀며 등장(스케일 바운스). 강조 등장.\n"
    "- drift: 천천히 떠다님(미세 이동). 정적 씬의 생동감.\n"
    "- bob: 위아래로 살랑임. 캐릭터 idle 기본.\n"
    "- shake: 짧고 빠른 흔들림. 충격·놀람.\n"
    "- zoom_emphasis: 살짝 커졌다 복귀. 내레이션 강조 시점.\n"
    "- exit_fade: 서서히 사라짐(씬 끝 무렵).\n"
)


def motion_path(proj_dir: Path, sid: str) -> Path:
    return Path(proj_dir) / f"motion_{sid}.json"


def _scene_duration(proj_dir: Path, s: dict) -> float:
    if s.get("_audio"):
        d = tts.audio_duration(Path(proj_dir) / s["_audio"])
        if d:
            return d
    return float(s.get("duration_estimate_sec") or 3.0)


def _clamp_plan(plan: dict, dur: float) -> dict:
    """start/duration을 씬 길이 안으로 클램프. 알 수 없는 레이어/타입은 스키마가 차단."""
    for L in plan.get("layers", []):
        for mv in L.get("moves", []):
            mv["start"] = max(0.0, min(float(mv.get("start") or 0), dur))
            mv["duration"] = max(0.1, min(float(mv.get("duration") or 0.5), dur - mv["start"]))
    return plan


def plan_scene_motion(proj_dir: Path, scene_number: int, *, on_line=None) -> dict:
    """씬 모션 플랜 생성 → motion_{sid}.json 저장. 반환=플랜 dict 또는 {error}."""
    proj_dir = Path(proj_dir)
    data = scenes.load_scenes(proj_dir)
    s = next((x for x in data.get("scenes", []) if x.get("sceneNumber") == scene_number), None)
    if not s:
        return {"error": f"scene {scene_number} 없음"}
    sid = s.get("sceneId")
    elements = [Path(r).stem for r in (s.get("_layers") or []) if "__bg" not in Path(r).name]
    if not elements:
        return {"error": "레이어 없음 — 먼저 레이어 분리 필요"}
    dur = _scene_duration(proj_dir, s)
    prompt = (
        "너는 모션그래픽 연출가다. 아래 씬의 레이어들에 모션을 설계해라.\n\n"
        f"## 내레이션(씬 길이 {dur:.1f}초)\n{s.get('narration', '') or '(없음)'}\n\n"
        f"## 레이어(이 이름을 정확히 그대로 사용)\n" + "\n".join(f"- {e}" for e in elements) + "\n\n"
        f"## 사용 가능한 모션 프리셋\n{_PRESET_GUIDE}\n"
        "## 연출 원칙\n"
        "1) 캐릭터(인물) 레이어는 bob 또는 drift로 idle 생동감을 기본으로 준다.\n"
        "2) 내레이션이 강조하는 사물은 등장(slide_in/pop) 또는 zoom_emphasis.\n"
        "3) 배경 레이어는 목록에 없다 — 카메라(camera)로만 표현.\n"
        "4) 모든 start+duration은 씬 길이 이내. 과하지 않게 — 레이어당 1~2개 모션.\n"
        "5) camera는 씬 분위기에 맞게 none/slow_zoom_in/slow_zoom_out/pan_left/pan_right 중 선택."
    )
    out = proj_dir / f".motion_plan_{sid}.json"
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_SCHEMA),
                               output_last=str(out), on_line=on_line)
    if res.get("returncode") != 0 or not out.is_file():
        return {"error": "모션 플랜 생성 실패"}
    try:
        plan = json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "모션 플랜 파싱 실패"}
    valid = {e for e in elements}
    plan["layers"] = [L for L in plan.get("layers", []) if L.get("layer") in valid]
    plan = _clamp_plan(plan, dur)
    motion_path(proj_dir, sid).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan
