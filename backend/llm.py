"""오케스트레이터(추론) LLM 선택·디스패치. claude(기본) 또는 codex.
규칙: images(멀티모달) 있으면 무조건 codex(claude 헤드리스 비전 미지원). 이미지 생성은 별도(항상 codex)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from backend import codex_runner, claude_runner

_CFG = Path(__file__).resolve().parents[1] / "data" / "llm_config.json"
VALID = ("claude", "codex")
DEFAULT = "claude"


def get_orchestrator() -> str:
    try:
        v = json.loads(_CFG.read_text(encoding="utf-8")).get("orchestrator")
        if v in VALID:
            return v
    except Exception:
        pass
    v = os.environ.get("AK_ORCHESTRATOR")
    return v if v in VALID else DEFAULT


def set_orchestrator(name: str) -> str:
    name = name if name in VALID else DEFAULT
    _CFG.parent.mkdir(parents=True, exist_ok=True)
    _CFG.write_text(json.dumps({"orchestrator": name}, ensure_ascii=False, indent=2), encoding="utf-8")
    return name


def run_orchestrator(prompt, cwd, *, session_id=None, output_schema=None, output_last=None,
                     sandbox=None, images=None, model=None, on_line=None) -> dict:
    """선택 오케스트레이터로 추론 실행. images 있으면 codex 강제."""
    engine = get_orchestrator()
    if images or engine == "codex":
        return codex_runner.run_skill(prompt, cwd, session_id=session_id, output_schema=output_schema,
                                      output_last=output_last, sandbox=sandbox, images=images, on_line=on_line)
    return claude_runner.run_claude(prompt, cwd, session_id=session_id, output_schema=output_schema,
                                    output_last=output_last, sandbox=sandbox, images=images, model=model,
                                    on_line=on_line)
