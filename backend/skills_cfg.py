"""스킬 설정(skill.json) 로드 + codex 프롬프트 빌드 (순수)."""
from __future__ import annotations

import json
from pathlib import Path


def load_config(skills_dir: Path, name: str) -> dict:
    cfg = skills_dir / name / "skill.json"
    data = json.loads(cfg.read_text(encoding="utf-8"))
    data.setdefault("inputs", [])
    data.setdefault("output_kind", "md")
    data.setdefault("schema", None)
    return data


def missing_inputs(config: dict, proj_dir: Path) -> list[str]:
    return [f for f in config.get("inputs", []) if not (proj_dir / f).exists()]


def build_prompt(skills_dir: Path, name: str, config: dict, proj_dir: Path) -> str:
    skill_md = skills_dir / name / "SKILL.md"
    parts = [skill_md.read_text(encoding="utf-8") if skill_md.exists() else f"skill: {name}"]
    for fname in config.get("inputs", []):
        fp = proj_dir / fname
        if fp.exists():
            parts.append(f"\n\n## 입력: {fname}\n{fp.read_text(encoding='utf-8')}")
    out = config["output"]
    if config.get("output_kind") == "json":
        parts.append(f"\n\nproject_id={proj_dir.name}. {out} 내용(JSON)만 출력.")
    else:
        parts.append(f"\n\nproject_id={proj_dir.name}. {out} 에 들어갈 본문(마크다운)만 출력.")
    return "".join(parts)
