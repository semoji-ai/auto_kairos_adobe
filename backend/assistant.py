"""실행형 제작 비서 — 자연어 지시를 안전한 액션 카탈로그로 매핑(codex)해 순차 실행.
LLM은 ACTION_HANDLERS의 enum 안에서만 선택한다(임의 실행 불가)."""
from __future__ import annotations

import json
from pathlib import Path

from backend import scenes, imagegen, tts, manifest, llm, motion
from backend.codex_runner import run_skill

_PLAN_SCHEMA = Path(__file__).resolve().parent / "schemas" / "assistant_plan.schema.json"


# ---- 액션 핸들러(각 (proj_dir, on_event=None) -> result dict) ----

def _h_generate_missing_images(proj_dir: Path, on_event=None) -> dict:
    data = scenes.load_scenes(proj_dir)
    n = 0
    for s in data["scenes"]:
        if s.get("_image"):
            continue
        prompt = (s.get("image_prompt") or s.get("visual_summary") or "").strip()
        if not prompt:
            continue
        name = scenes.new_scene_image_name(s.get("sceneId"))
        res = imagegen.generate_one(proj_dir, name, prompt, subdir="storyboard")
        if res.get("status") == "completed":
            rel = Path(res["path"]).relative_to(proj_dir).as_posix()
            scenes.set_image_ref(proj_dir, s.get("sceneNumber"), rel)
            n += 1
        if on_event:
            on_event(f"S{s.get('sceneNumber')} 이미지: {res.get('status')}")
    return {"generated": n}


def _h_split_layers(proj_dir: Path, on_event=None) -> dict:
    data = scenes.load_scenes(proj_dir)
    n = 0
    for s in data["scenes"]:
        if not s.get("_image") or s.get("_layers"):
            continue
        img = str(proj_dir / s["_image"])
        ctx = f"제목: {s.get('title', '')} / 요약: {s.get('visual_summary', '')}"
        els = imagegen.analyze_scene_layers(proj_dir, img,
                                            narration=s.get("narration", "") or "", context=ctx).get("elements", [])
        if not els:
            continue
        imagegen.split_scene_to_elements(proj_dir, img, s.get("sceneId"), els)
        n += 1
        if on_event:
            on_event(f"S{s.get('sceneNumber')} 레이어 {len(els)}개")
    return {"split_scenes": n}


def _h_tts_all(proj_dir: Path, on_event=None) -> dict:
    data = scenes.load_scenes(proj_dir)
    n = 0
    for s in data["scenes"]:
        text = (s.get("narration_tts") or s.get("narration") or "")
        if not text.strip():
            continue
        res = tts.generate_scene_tts(proj_dir, s.get("sceneId"), text)
        if res.get("status") == "completed":
            n += 1
        if on_event:
            on_event(f"S{s.get('sceneNumber')} TTS: {res.get('status')}")
    return {"generated": n}


def _h_plan_motion(proj_dir: Path, on_event=None) -> dict:
    data = scenes.load_scenes(proj_dir)
    n = 0
    for s in data["scenes"]:
        if not s.get("_layers"):
            continue
        if motion.motion_path(proj_dir, s.get("sceneId")).is_file():
            continue
        res = motion.plan_scene_motion(proj_dir, s.get("sceneNumber"))
        if "error" not in res:
            n += 1
        if on_event:
            on_event(f"S{s.get('sceneNumber')} 모션: {'완료' if 'error' not in res else res.get('error')}")
    return {"planned": n}


def _h_assemble(proj_dir: Path, on_event=None) -> dict:
    return manifest.build_manifest(proj_dir)


ACTION_HANDLERS = {
    "generate_missing_images": _h_generate_missing_images,
    "split_layers": _h_split_layers,
    "tts_all": _h_tts_all,
    "plan_motion": _h_plan_motion,
    "assemble": _h_assemble,
}

_CATALOG_DESC = (
    "- generate_missing_images: 이미지가 없는 씬에 씬 이미지를 생성한다.\n"
    "- split_layers: 이미지가 있고 레이어가 없는 씬을 캐릭터/움직임 기준으로 레이어 분리한다.\n"
    "- tts_all: 내레이션이 있는 모든 씬의 음성을 생성한다.\n"
    "- plan_motion: 레이어가 분리된 씬에 모션 플랜을 설계한다.\n"
    "- assemble: 매니페스트를 빌드해 AE 조립을 준비한다(보통 마지막).\n"
)


def project_status(proj_dir: Path) -> str:
    data = scenes.load_scenes(proj_dir)
    ss = data.get("scenes", [])
    img = sum(1 for s in ss if s.get("_image"))
    lay = sum(1 for s in ss if s.get("_layers"))
    aud = sum(1 for s in ss if s.get("_audio"))
    return f"총 {len(ss)}씬 / 이미지 {img} / 레이어 {lay} / TTS {aud}"


def plan_actions(proj_dir: Path, instruction: str, *, on_line=None) -> list:
    """codex로 NL 지시를 액션 목록으로. 실패 시 []."""
    from backend import edits
    recent = edits.recent_edits_text(proj_dir, limit=2, max_chars=1500)
    prompt = (
        "너는 영상 제작 파이프라인 비서다. 사용자의 지시를 아래 액션들의 순서 있는 목록으로 변환해라. "
        "목록 외 동작은 만들지 말고, 지시에 필요한 액션만 골라라. 보통 assemble은 마지막에 둔다.\n\n"
        f"## 가능한 액션\n{_CATALOG_DESC}\n## 현재 프로젝트 상태\n{project_status(proj_dir)}\n"
        + (f"\n{recent}\n" if recent else "")
        + f"\n## 사용자 지시\n{instruction}"
    )
    out = proj_dir / ".assistant_plan.json"
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_PLAN_SCHEMA), output_last=str(out), on_line=on_line)
    if res.get("returncode") != 0 or not out.is_file():
        return []
    try:
        return json.loads(out.read_text(encoding="utf-8")).get("actions", [])
    except Exception:
        return []


def run_assistant(proj_dir: Path, instruction: str, *,
                  planner=None, handlers=None, on_event=None) -> dict:
    """plan_actions로 계획 → 핸들러 순차 실행 → 결과 수집. planner/handlers 주입 가능(테스트)."""
    proj_dir = Path(proj_dir)
    planner = planner or plan_actions
    handlers = handlers if handlers is not None else ACTION_HANDLERS
    actions = planner(proj_dir, instruction, on_line=on_event) if _accepts_on_line(planner) else planner(proj_dir, instruction)
    results = []
    for a in actions:
        name = a.get("action")
        if on_event:
            on_event(f"▶ {name}: {a.get('reason', '')}")
        h = handlers.get(name)
        if h is None:
            results.append({"action": name, "reason": a.get("reason"), "result": {"status": "skipped"}})
            continue
        try:
            r = h(proj_dir, on_event=on_event)
        except TypeError:
            r = h(proj_dir)
        results.append({"action": name, "reason": a.get("reason"), "result": r})
    return {"plan": actions, "results": results}


def _accepts_on_line(fn) -> bool:
    try:
        import inspect
        return "on_line" in inspect.signature(fn).parameters
    except (ValueError, TypeError):
        return False
