"""editorial brief 생성 + 평가·개선 래칫 (adobe 독립 Stage1-2 P2).
v3 brief-interviewer-auto/brief-reviewer 프롬프트를 adobe 스킬로 이식, llm.run_orchestrator로 호출.
런타임 v3 의존 없음."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from backend import llm

_ROOT = Path(__file__).resolve().parents[1]
_SKILLS = _ROOT / "skills"
_SCHEMAS = Path(__file__).resolve().parent / "schemas"
_BRIEF_SCHEMA = _SCHEMAS / "editorial_brief.schema.json"
_REVIEW_SCHEMA = _SCHEMAS / "brief_review.schema.json"


def parse_plan(proj_dir) -> dict:
    """plan.md → {topic, writing_style, duration, tone}. 제목은 첫 '# ' 헤더 또는 '제목:'.
    채널 없으면 writing_style='semoji'."""
    plan = Path(proj_dir) / "plan.md"
    if not plan.is_file():
        raise FileNotFoundError(f"plan.md 필요: {plan}")
    text = plan.read_text(encoding="utf-8")
    topic = ""
    fields = {"채널": "", "분량": "", "톤": ""}
    for line in text.splitlines():
        s = line.strip()
        if not topic and s.startswith("# "):
            topic = s[2:].strip()
        if not topic and s.startswith("제목:"):
            topic = s.split(":", 1)[1].strip()
        for key in fields:
            if s.startswith(key + ":"):
                fields[key] = s.split(":", 1)[1].strip()
    return {
        "topic": topic,
        "writing_style": fields["채널"] or "semoji",
        "duration": fields["분량"],
        "tone": fields["톤"],
    }


def _load_skill(name: str) -> str:
    md = _SKILLS / name / "SKILL.md"
    return md.read_text(encoding="utf-8") if md.is_file() else f"skill: {name}"


def _dna_text() -> str:
    p = _ROOT / "data" / "brief-dna.md"
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def generate_brief(proj_dir, *, version: int, prev_brief=None, revisions=None,
                   on_event=None) -> Path | None:
    """brief-interview 스킬로 editorial_brief.v{version}.json 생성. 실패 시 None."""
    proj_dir = Path(proj_dir)
    plan = parse_plan(proj_dir)
    out = proj_dir / f"editorial_brief.v{version}.json"
    parts = [
        _load_skill("brief-interview"),
        "\n\n## DNA 레버 정의\n" + _dna_text(),
        f"\n\n## 기획 입력\ntopic: {plan['topic']}\nwriting_style: {plan['writing_style']}\n"
        f"duration: {plan['duration']}\ntone: {plan['tone']}\n",
    ]
    if prev_brief and Path(prev_brief).is_file():
        parts.append("\n\n## 직전 brief(개선 대상)\n" + Path(prev_brief).read_text(encoding="utf-8"))
    if revisions:
        parts.append("\n\n## REVISE 지시(반드시 반영)\n" + "\n".join(f"- {r}" for r in revisions))
    parts.append(f"\n\neditorial_brief JSON만 출력. project_id={proj_dir.name}.")
    prompt = "".join(parts)
    if on_event:
        on_event(f"브리프 생성 v{version}")
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_BRIEF_SCHEMA),
                               output_last=str(out), on_line=on_event)
    if res.get("returncode") == 0 and out.is_file():
        return out
    return None
