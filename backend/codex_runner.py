"""codex exec 래퍼 — 커맨드 빌드(순수) + 스킬 실행(subprocess, stdin 프롬프트 + 스트리밍).
codex의 --output-schema는 OpenAI strict 규격(모든 object에 additionalProperties:false +
모든 properties가 required)을 요구 → claude용 관대한 스키마를 호출 시점에 자동 변환한다."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def strictify_schema(obj):
    """JSON 스키마를 OpenAI strict 규격으로(재귀). object마다 additionalProperties=False +
    properties 전부 required. 원본은 그대로 두고 새 dict 반환."""
    if isinstance(obj, list):
        return [strictify_schema(v) for v in obj]
    if not isinstance(obj, dict):
        return obj
    out = {k: strictify_schema(v) for k, v in obj.items()}
    props = out.get("properties")
    if isinstance(props, dict):
        out["additionalProperties"] = False
        out["required"] = list(props.keys())          # strict: 모든 속성 required
    return out


def schema_strictifiable(obj) -> bool:
    """strict 변환이 가능한 스키마인가. OpenAI strict는 '자유형 object'(properties 없는 object)를
    지원하지 않으므로, 그런 노드가 하나라도 있으면 False(→ 스키마 없이 프롬프트+추출로 폴백)."""
    if isinstance(obj, list):
        return all(schema_strictifiable(v) for v in obj)
    if not isinstance(obj, dict):
        return True
    t = obj.get("type")
    is_obj = t == "object" or (isinstance(t, list) and "object" in t)
    if is_obj and not isinstance(obj.get("properties"), dict):
        return False                                   # 자유형 map → strict 불가
    is_arr = t == "array" or (isinstance(t, list) and "array" in t)
    if is_arr and "items" not in obj:
        return False                                   # items 없는 배열 → strict 불가
    return all(schema_strictifiable(v) for v in obj.values())


def _strict_schema_file(schema_path: str):
    """스키마를 strict 변환해 임시 파일로. 반환 (경로|None, 임시여부).
    변환 불가(자유형 object 포함)면 (None, False) — 호출부가 스키마 없이 실행 후 JSON 추출."""
    try:
        data = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    except Exception:
        return None, False
    if not schema_strictifiable(data):
        return None, False
    try:
        fd, tmp = tempfile.mkstemp(prefix="akschema_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(strictify_schema(data), f, ensure_ascii=False)
        return tmp, True
    except Exception:
        return None, False


def build_codex_cmd(
    *,
    session_id: str | None = None,
    output_schema: str | None = None,
    output_last: str | None = None,
    json_events: bool = True,
    skip_git: bool = True,
    sandbox: str | None = None,
    images: list | None = None,
) -> list[str]:
    """codex exec 커맨드 리스트. 프롬프트는 stdin으로 넘기므로 positional은 '-'.
    session_id 있으면 resume."""
    cmd = ["codex", "exec"]
    if session_id:
        cmd += ["resume", session_id]
    if sandbox:
        cmd += ["-s", sandbox]
    if images:
        for img in images:
            cmd += ["-i", img]
    if skip_git:
        cmd += ["--skip-git-repo-check"]
    if json_events:
        cmd += ["--json"]
    if output_schema:
        cmd += ["--output-schema", output_schema]
    if output_last:
        cmd += ["-o", output_last]
    cmd += ["-"]  # 프롬프트는 stdin (긴/'--'로 시작하는 프롬프트 안전)
    return cmd


def _extract_session_id(json_line: str) -> str | None:
    try:
        evt = json.loads(json_line)
    except ValueError:
        return None
    if isinstance(evt, dict):
        for key in ("session_id", "sessionId", "conversation_id", "thread_id"):
            if evt.get(key):
                return str(evt[key])
    return None


def run_skill(
    prompt: str,
    cwd: Path,
    *,
    session_id: str | None = None,
    output_schema: str | None = None,
    output_last: str | None = None,
    sandbox: str | None = None,
    images: list | None = None,
    on_line=None,
) -> dict:
    """codex exec 실행. 프롬프트는 stdin으로 전달. 각 stdout 라인을 on_line(line)으로 흘림.
    반환: {returncode, session_id, output_last}."""
    # codex는 strict 스키마만 받으므로(관대한 claude용 스키마는 invalid_json_schema로 거부)
    # 호출 시점에 변환본을 만들어 전달하고, 끝나면 임시파일 정리.
    schema_arg, schema_tmp = (None, False)
    if output_schema:
        schema_arg, schema_tmp = _strict_schema_file(output_schema)
    cmd = build_codex_cmd(
        session_id=session_id, output_schema=schema_arg,
        output_last=output_last, sandbox=sandbox, images=images,
    )
    proc = subprocess.Popen(
        cmd, cwd=str(cwd),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", bufsize=1,
    )
    try:
        if proc.stdin is not None:
            proc.stdin.write(prompt)
            proc.stdin.close()
    except BrokenPipeError:
        pass
    found_session = session_id
    if proc.stdout is not None:
        for line in proc.stdout:
            line = line.rstrip("\n")
            if on_line:
                on_line(line)
            if found_session is None:
                sid = _extract_session_id(line)
                if sid:
                    found_session = sid
    proc.wait()
    if schema_tmp and schema_arg:
        try:
            os.unlink(schema_arg)          # strict 변환 임시 스키마 정리
        except OSError:
            pass
    # 스키마를 못 쓴 경우(자유형 object) — claude 경로와 동일하게 결과에서 JSON만 추출
    if output_schema and not schema_arg and output_last:
        try:
            from backend.claude_runner import _extract_json
            fp = Path(output_last)
            if fp.is_file():
                fp.write_text(_extract_json(fp.read_text(encoding="utf-8")), encoding="utf-8")
        except Exception:
            pass
    return {
        "returncode": proc.returncode,
        "session_id": found_session,
        "output_last": output_last,
    }
