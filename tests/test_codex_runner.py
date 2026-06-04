import sys
from backend.codex_runner import build_codex_cmd


def test_build_basic_with_schema_and_output():
    cmd = build_codex_cmd("PROMPT", output_schema="/p/s.json", output_last="/p/out.json")
    assert cmd[0:2] == ["codex", "exec"]
    assert "--skip-git-repo-check" in cmd
    assert "--json" in cmd
    assert cmd[cmd.index("--output-schema") + 1] == "/p/s.json"
    assert cmd[cmd.index("-o") + 1] == "/p/out.json"
    assert cmd[-1] == "PROMPT"


def test_build_resume_session():
    cmd = build_codex_cmd("FOLLOWUP", session_id="abc-123")
    assert cmd[1] == "exec"
    assert "resume" in cmd
    assert "abc-123" in cmd
    assert cmd[-1] == "FOLLOWUP"


def test_no_json_when_disabled():
    cmd = build_codex_cmd("P", json_events=False)
    assert "--json" not in cmd
