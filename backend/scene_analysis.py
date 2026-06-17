"""씬 분석 (adobe 독립 Stage1-2 P4b) — final_manuscript.md를 마커로 분할하고
씬별 연출(LLM)을 붙여 adobe 네이티브 scenes.json 산출. 런타임 v3 의존 없음."""
from __future__ import annotations

import json
import re
from pathlib import Path

from backend import llm

_ROOT = Path(__file__).resolve().parents[1]
_SKILLS = _ROOT / "skills"
_SCHEMAS = Path(__file__).resolve().parent / "schemas"
_SCENE_SCHEMA = _SCHEMAS / "scene_specs.schema.json"

_SCENE_RE = re.compile(r"(?m)^[ \t]*<!--\s*SCENE\s*-->[ \t]*$")
_CHARS_RE = re.compile(r"(?m)^[ \t]*<!--\s*CHARS:\s*(.*?)\s*-->[ \t]*$")


def _load_skill(name: str) -> str:
    md = _SKILLS / name / "SKILL.md"
    if not md.is_file():
        return f"skill: {name}"
    text = md.read_text(encoding="utf-8")
    if text.startswith("---"):              # YAML frontmatter 제거(프롬프트 노이즈 방지)
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:].lstrip("\n")
    return text


def _read(proj_dir: Path, name: str) -> str:
    p = proj_dir / name
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def split_manuscript(text: str) -> list:
    """<!--SCENE-->로 결정적 분할 → [{narration, characters}]. <!--CHARS-->는 추출·제거.
    마커 없으면 전체가 1씬. 빈 세그먼트는 버림."""
    segs: list = []
    for part in _SCENE_RE.split(text or ""):
        chars: list = []
        mm = _CHARS_RE.search(part)
        if mm:
            chars = [c.strip() for c in mm.group(1).split(",") if c.strip()]
            part = _CHARS_RE.sub("", part)
        narration = part.strip()
        if narration:
            segs.append({"narration": narration, "characters": chars})
    return segs
