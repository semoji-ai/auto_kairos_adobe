"""원고 파이프라인 (adobe 독립 Stage1-2 P4a) — 초안→타겟리서치→적용→래칫.
v3 draft-writer/script-director/script-reviewer 프롬프트를 adobe 스킬로 이식,
llm.run_orchestrator(claude)로 호출, P3 web_agent로 타겟 웹리서치. 런타임 v3 의존 없음."""
from __future__ import annotations

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from backend import llm
from backend.research import web_agent

_ROOT = Path(__file__).resolve().parents[1]
_SKILLS = _ROOT / "skills"
_SCHEMAS = Path(__file__).resolve().parent / "schemas"
_DRAFT_SCHEMA = _SCHEMAS / "manuscript_draft.schema.json"
_REVIEW_SCHEMA = _SCHEMAS / "manuscript_review.schema.json"


def _load_skill(name: str) -> str:
    md = _SKILLS / name / "SKILL.md"
    return md.read_text(encoding="utf-8") if md.is_file() else f"skill: {name}"


def _read(proj_dir: Path, name: str) -> str:
    p = proj_dir / name
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def generate_draft(proj_dir, *, on_event=None):
    """manuscript-draft 스킬 → draft.md + research_questions.json. 반환 (draft_path|None, questions)."""
    proj_dir = Path(proj_dir)
    out = proj_dir / "manuscript_draft.json"
    prompt = (
        _load_skill("manuscript-draft")
        + "\n\n## 리서치 리포트\n" + _read(proj_dir, "research_report.json")
        + "\n\n## editorial brief\n" + _read(proj_dir, "editorial_brief.json")
        + f"\n\nmanuscript_draft JSON({{draft_markdown, questions}})만 출력. project_id={proj_dir.name}."
    )
    if on_event:
        on_event("원고 초안")
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_DRAFT_SCHEMA),
                               output_last=str(out), on_line=on_event)
    if res.get("returncode") != 0 or not out.is_file():
        return None, []
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        return None, []
    draft_path = proj_dir / "draft.md"
    draft_path.write_text(str(data.get("draft_markdown") or ""), encoding="utf-8")
    questions = [str(q) for q in (data.get("questions") or []) if str(q).strip()]
    (proj_dir / "research_questions.json").write_text(
        json.dumps({"questions": questions}, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft_path, questions


def targeted_research(proj_dir, questions, *, max_workers: int = 3, on_event=None) -> list:
    """각 타겟 질문을 web_agent로 병렬 웹리서치 → targeted_claims.json. 빈 결과 격리."""
    proj_dir = Path(proj_dir)
    qs = [str(q).strip() for q in (questions or []) if str(q).strip()]
    if not qs:
        return []

    def _one(q):
        prompt = (
            f"너는 리서치 탐색가다. 다음 질문을 웹 검색·열람으로 해결하라: '{q}'. "
            f"WebSearch/WebFetch를 사용하고, 검증된 답을 출처 URL과 함께 1~3문장으로 보고하라.")
        note = web_agent.run_web_research(proj_dir, prompt, on_line=on_event)
        return {"question": q, "claim": note} if note else None

    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as ex:
        results = list(ex.map(_one, qs))
    claims = [c for c in results if c]
    (proj_dir / "targeted_claims.json").write_text(
        json.dumps(claims, ensure_ascii=False, indent=2), encoding="utf-8")
    if on_event:
        on_event(f"타겟 리서치 {len(claims)}/{len(qs)}")
    return claims
