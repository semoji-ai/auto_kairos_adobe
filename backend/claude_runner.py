"""claude CLI(헤드리스) 어댑터 — 텍스트 추론용. CLAUDECODE 등 중첩 변수 pop, --json-schema 구조화 출력.
프롬프트는 stdin. 멀티모달(이미지)은 헤드리스에서 행이 걸려 미지원 → 비전은 codex가 담당."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

_NEST_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")


def _clean_env() -> dict:
    e = dict(os.environ)
    for k in _NEST_ENV:
        e.pop(k, None)          # 중첩 세션 방지(안 하면 claude -p 가 행)
    return e


def run_claude(prompt: str, cwd, *, session_id=None, output_schema=None, output_last=None,
               sandbox=None, images=None, model=None, on_line=None) -> dict:
    """codex run_skill과 동일 시그니처/반환. images/sandbox/session_id는 무시(헤드리스 텍스트 전용)."""
    if shutil.which("claude") is None:
        return {"returncode": 127, "session_id": None, "output_last": output_last}
    cmd = ["claude", "-p", "--output-format", "json"]
    if output_schema:
        cmd += ["--json-schema", str(output_schema)]
    if model:
        cmd += ["--model", str(model)]
    try:
        r = subprocess.run(cmd, input=prompt, cwd=str(cwd), env=_clean_env(),
                           capture_output=True, text=True, timeout=1200)
    except Exception:
        return {"returncode": 1, "session_id": None, "output_last": output_last}
    if on_line and r.stdout:
        on_line(r.stdout[:500])
    result_text = r.stdout
    try:                        # --output-format json 엔벨로프면 result 추출
        env = json.loads(r.stdout)
        if isinstance(env, dict) and "result" in env:
            result_text = env["result"]
    except Exception:
        pass
    if output_last and result_text:
        Path(output_last).write_text(result_text, encoding="utf-8")
    return {"returncode": r.returncode, "session_id": None, "output_last": output_last}
