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
