from backend.codex_runner import build_codex_cmd


def test_build_basic_with_schema_and_output():
    cmd = build_codex_cmd(output_schema="/p/s.json", output_last="/p/out.json")
    assert cmd[0:2] == ["codex", "exec"]
    assert "--skip-git-repo-check" in cmd
    assert "--json" in cmd
    assert cmd[cmd.index("--output-schema") + 1] == "/p/s.json"
    assert cmd[cmd.index("-o") + 1] == "/p/out.json"
    assert cmd[-1] == "-"  # 프롬프트는 stdin


def test_build_resume_session():
    cmd = build_codex_cmd(session_id="abc-123")
    assert cmd[1] == "exec"
    assert "resume" in cmd
    assert "abc-123" in cmd
    assert cmd[-1] == "-"


def test_no_json_when_disabled():
    cmd = build_codex_cmd(json_events=False)
    assert "--json" not in cmd


def test_build_cmd_with_sandbox():
    cmd = build_codex_cmd(sandbox="workspace-write")
    assert "-s" in cmd
    assert cmd[cmd.index("-s") + 1] == "workspace-write"


def test_build_cmd_no_sandbox_by_default():
    cmd = build_codex_cmd()
    assert "-s" not in cmd


def test_build_cmd_with_images():
    cmd = build_codex_cmd(images=["/a/scene.png"])
    assert "-i" in cmd
    assert cmd[cmd.index("-i") + 1] == "/a/scene.png"


def test_build_cmd_multiple_images():
    cmd = build_codex_cmd(images=["/a.png", "/b.png"])
    assert cmd.count("-i") == 2


# ===== codex strict 스키마 자동 변환/폴백 =====
def test_strictify_schema_sets_strict():
    from backend.codex_runner import strictify_schema
    src = {"type": "object", "additionalProperties": True,
           "required": ["a"],
           "properties": {"a": {"type": "string"},
                          "b": {"type": "array", "items": {
                              "type": "object", "additionalProperties": True,
                              "properties": {"x": {"type": "number"}}}}}}
    out = strictify_schema(src)
    assert out["additionalProperties"] is False and set(out["required"]) == {"a", "b"}
    inner = out["properties"]["b"]["items"]
    assert inner["additionalProperties"] is False and inner["required"] == ["x"]   # 중첩도 변환
    assert src["additionalProperties"] is True                                     # 원본 불변


def test_schema_strictifiable_detects_freeform_object():
    from backend.codex_runner import schema_strictifiable
    ok = {"type": "object", "properties": {"a": {"type": "string"}}}
    free = {"type": "object", "properties": {"m": {"type": "object", "additionalProperties": True}}}
    assert schema_strictifiable(ok) is True
    assert schema_strictifiable(free) is False        # 자유형 map → strict 불가


def test_strict_schema_file_returns_none_for_freeform(tmp_path):
    import json as _j
    from backend.codex_runner import _strict_schema_file
    p = tmp_path / "s.json"
    p.write_text(_j.dumps({"type": "object", "properties": {"m": {"type": "object"}}}), encoding="utf-8")
    path, tmp = _strict_schema_file(str(p))
    assert path is None and tmp is False               # 폴백 신호
