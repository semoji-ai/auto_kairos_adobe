from pathlib import Path
from backend import llm


def test_default_orchestrator_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_CFG", tmp_path / "llm_config.json")
    monkeypatch.delenv("AK_ORCHESTRATOR", raising=False)
    assert llm.get_orchestrator() == "claude"


def test_set_get_orchestrator(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_CFG", tmp_path / "llm_config.json")
    llm.set_orchestrator("codex")
    assert llm.get_orchestrator() == "codex"
    llm.set_orchestrator("이상한값")          # 검증 → claude로
    assert llm.get_orchestrator() == "claude"


def test_run_orchestrator_routes_text_to_claude(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_CFG", tmp_path / "c.json"); llm.set_orchestrator("claude")
    seen = {}
    monkeypatch.setattr(llm.claude_runner, "run_claude", lambda *a, **k: seen.update(engine="claude") or {"returncode": 0})
    monkeypatch.setattr(llm.codex_runner, "run_skill", lambda *a, **k: seen.update(engine="codex") or {"returncode": 0})
    llm.run_orchestrator("p", tmp_path)                       # 텍스트 → claude
    assert seen["engine"] == "claude"


def test_run_orchestrator_forces_codex_for_images(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_CFG", tmp_path / "c.json"); llm.set_orchestrator("claude")
    seen = {}
    monkeypatch.setattr(llm.claude_runner, "run_claude", lambda *a, **k: seen.update(engine="claude") or {"returncode": 0})
    monkeypatch.setattr(llm.codex_runner, "run_skill", lambda *a, **k: seen.update(engine="codex") or {"returncode": 0})
    llm.run_orchestrator("p", tmp_path, images=["/x.png"])    # 멀티모달 → codex 강제
    assert seen["engine"] == "codex"


def test_run_orchestrator_codex_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "_CFG", tmp_path / "c.json"); llm.set_orchestrator("codex")
    seen = {}
    monkeypatch.setattr(llm.codex_runner, "run_skill", lambda *a, **k: seen.update(engine="codex") or {"returncode": 0})
    llm.run_orchestrator("p", tmp_path)
    assert seen["engine"] == "codex"
