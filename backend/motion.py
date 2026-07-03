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
    """start/duration을 씬 길이 안으로 클램프. 알 수 없는 레이어/타입은 스키마가 차단.
    camera.amount 단위 정규화: 0.06(비율) → 6(퍼센트/px 계열) + 타입별 범위 클램프."""
    for L in plan.get("layers", []):
        for mv in L.get("moves", []):
            mv["start"] = max(0.0, min(float(mv.get("start") or 0), dur))
            mv["duration"] = max(0.1, min(float(mv.get("duration") or 0.5), dur - mv["start"]))
    cam = plan.get("camera") or {}
    amt = cam.get("amount")
    if amt is not None:
        amt = float(amt)
        if 0 < amt <= 1.0:
            amt *= 100.0                        # 비율 표기 → 퍼센트
        ctype = cam.get("type", "")
        if ctype in ("slow_zoom_in", "slow_zoom_out"):
            amt = max(2.0, min(amt, 6.0))       # 줌 2~6% — '느껴지되 보이지 않게'
        elif ctype in ("pan_left", "pan_right"):
            amt = max(16.0, min(amt, 60.0))     # 팬 16~60px — 과한 팬은 촌스러움
        cam["amount"] = round(amt, 2)
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
    # kind 사이드카(분리 시 저장) — 현재 규칙: 캐릭터만 모션, 사물은 모션 금지(규칙 추후 별도 설계)
    kinds = {}
    kp = proj_dir / "layers" / f"{sid}__kinds.json"
    if kp.is_file():
        try:
            kinds = json.loads(kp.read_text(encoding="utf-8"))
        except Exception:
            kinds = {}
    if kinds:
        chars = [e for e in elements if kinds.get(e) == "character"]
    else:   # 사이드카 없는 구버전 분리 — 이름으로 LLM이 판단(프롬프트에서 인물만 지시)
        chars = elements
    if not chars:
        return {"error": "캐릭터 레이어 없음 — 현재 모션 규칙은 캐릭터(bob)만"}
    dur = _scene_duration(proj_dir, s)
    prompt = (
        "너는 모션그래픽 연출가다. 아래 씬의 '캐릭터(인물)' 레이어에만 idle 모션을 설계해라.\n\n"
        f"## 내레이션(씬 길이 {dur:.1f}초)\n{s.get('narration', '') or '(없음)'}\n\n"
        f"## 레이어(이 이름을 정확히 그대로 사용)\n" + "\n".join(f"- {e}" for e in chars) + "\n\n"
        f"## 사용 가능한 모션 프리셋\n{_PRESET_GUIDE}\n"
        "## 연출 원칙(현행 규칙 — 엄수)\n"
        "1) 인물(사람·캐릭터) 레이어에만 모션을 준다. 사물·가구·차량 등 오브젝트로 보이는 레이어는 "
        "모션을 주지 말고 목록에서 제외한다.\n"
        "2) 인물 기본은 bob(까딱임 idle) 1개. 씬 시작에 등장 연출이 어울리면 fade_in을 앞에 추가해도 된다.\n"
        "3) slide_in/pop/drift/shake/zoom_emphasis 는 인물에 쓰지 않는다(현행 규칙).\n"
        "4) 모든 start+duration은 씬 길이 이내.\n"
        "5) camera 기본은 none — 정지 프레임이 세련의 기본값이다. 내레이션이 공간·규모·시간의 흐름을 "
        "말할 때만 slow_zoom_in/slow_zoom_out(amount 3~4), 이동·대비를 말할 때만 pan_left/pan_right"
        "(amount 20~40). 매 씬 카메라를 넣지 말 것 — 연속된 씬 2~3개에 1번이면 충분하다.\n"
        "6) 모션은 적을수록 좋다 — 씬당 시선을 끄는 모션은 1개 원칙, 나머지는 정지."
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
    # 결정적 강제: 캐릭터 레이어만 + 허용 프리셋(bob/fade_in)만 — 사물 모션 규칙은 추후 별도
    valid = set(chars)
    allowed = {"bob", "fade_in"}
    filtered = []
    for L in plan.get("layers", []):
        if L.get("layer") not in valid:
            continue
        mvs = [m for m in L.get("moves", []) if m.get("type") in allowed]
        if mvs:
            filtered.append({"layer": L["layer"], "moves": mvs})
    plan["layers"] = filtered
    plan = _clamp_plan(plan, dur)
    motion_path(proj_dir, sid).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan
