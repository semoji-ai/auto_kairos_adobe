import json
from pathlib import Path
from backend import assistant


def _proj(tmp_path, scenes_arr):
    d = tmp_path / "p"; d.mkdir()
    (d / "scenes.json").write_text(json.dumps({"scenes": scenes_arr}, ensure_ascii=False), encoding="utf-8")
    return d


def test_catalog_names():
    assert set(assistant.ACTION_HANDLERS) == {
        "generate_missing_images", "split_layers", "tts_all", "plan_motion", "assemble"}


def test_plan_motion_handler(tmp_path, monkeypatch):
    d = _proj(tmp_path, [
        {"sceneNumber": 1, "sceneId": "pa", "narration": "n"},          # 레이어 없음 → 스킵
        {"sceneNumber": 2, "sceneId": "pb", "narration": "n"},          # 레이어 있음 → 대상
        {"sceneNumber": 3, "sceneId": "pc", "narration": "n"},          # 모션 파일 이미 있음 → 스킵
    ])
    lay = d / "layers"; lay.mkdir()
    (lay / "pb__0_a.png").write_bytes(b"x")
    (lay / "pc__0_a.png").write_bytes(b"x")
    (d / "motion_pc.json").write_text("{}", encoding="utf-8")
    calls = []
    monkeypatch.setattr(assistant.motion, "plan_scene_motion",
                        lambda proj_dir, sn, **kw: (calls.append(sn) or {"layers": [], "camera": {"type": "none"}}))
    res = assistant._h_plan_motion(d)
    assert calls == [2] and res == {"planned": 1}


def test_project_status_summary(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a", "narration": "n",
                          "imageRef": "storyboard/sb_a.png"}])
    (d / "storyboard").mkdir(); (d / "storyboard" / "sb_a.png").write_bytes(b"\x89PNG")
    st = assistant.project_status(d)
    assert "1" in st and "이미지" in st


def test_plan_actions_parses(tmp_path, monkeypatch):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a"}])

    def fake_run(prompt, cwd, *, output_schema=None, output_last=None, images=None, on_line=None, **kw):
        Path(output_last).write_text('{"actions":[{"action":"tts_all","reason":"음성"},'
                                     '{"action":"assemble","reason":"합치기"}]}', encoding="utf-8")
        return {"returncode": 0, "output_last": output_last}

    monkeypatch.setattr(assistant.llm, "run_orchestrator", fake_run)
    planned = assistant.plan_actions(d, "음성 입혀서 합쳐줘")
    assert [a["action"] for a in planned["actions"]] == ["tts_all", "assemble"]
    assert planned["reply"] is None


def test_plan_actions_failure_returns_empty(tmp_path, monkeypatch):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a"}])
    monkeypatch.setattr(assistant.llm, "run_orchestrator",
                        lambda *a, **k: {"returncode": 1, "output_last": k.get("output_last")})
    assert assistant.plan_actions(d, "뭐든") == {"actions": [], "reply": None}


def test_run_assistant_dispatches_in_order(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a"}])
    calls = []
    handlers = {
        "tts_all": lambda proj_dir, on_event=None: calls.append("tts") or {"done": 1},
        "assemble": lambda proj_dir, on_event=None: calls.append("asm") or {"path": "m.json"},
    }
    out = assistant.run_assistant(
        d, "x",
        planner=lambda proj_dir, instr, on_line=None: [
            {"action": "tts_all", "reason": "r1"}, {"action": "assemble", "reason": "r2"}],
        handlers=handlers)
    assert calls == ["tts", "asm"]
    assert [r["action"] for r in out["results"]] == ["tts_all", "assemble"]
    assert out["results"][0]["result"] == {"done": 1}


def test_run_assistant_unknown_action_skipped(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a"}])
    out = assistant.run_assistant(
        d, "x",
        planner=lambda proj_dir, instr, on_line=None: [{"action": "nope", "reason": "?"}],
        handlers={})
    assert out["results"][0]["result"]["status"] == "skipped"


def test_generate_missing_images_only_missing(tmp_path, monkeypatch):
    from backend import imagegen, scenes as sc
    d = _proj(tmp_path, [
        {"sceneNumber": 1, "sceneId": "a", "image_prompt": "그림1", "imageRef": "storyboard/sb_a.png"},
        {"sceneNumber": 2, "sceneId": "b", "image_prompt": "그림2", "imageRef": ""}])
    (d / "storyboard").mkdir(); (d / "storyboard" / "sb_a.png").write_bytes(b"\x89PNG")
    gen = []

    def fake_gen(proj_dir, rel_out, prompt, *, subdir="images", **kw):
        gen.append(prompt)
        (proj_dir / subdir).mkdir(parents=True, exist_ok=True)
        (proj_dir / subdir / rel_out).write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(proj_dir / subdir / rel_out)}

    monkeypatch.setattr(imagegen, "generate_one", fake_gen)
    res = assistant.ACTION_HANDLERS["generate_missing_images"](d)
    assert gen == ["그림2"] and res["generated"] == 1     # 씬2만(씬1은 이미 이미지 있음)


def test_tts_all_handler(tmp_path, monkeypatch):
    from backend import tts as _tts
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a", "narration": "안녕"},
                         {"sceneNumber": 2, "sceneId": "b", "narration": ""}])
    monkeypatch.setattr(_tts, "generate_scene_tts",
                        lambda proj_dir, sid, text, voice=None: {"status": "completed"})
    res = assistant.ACTION_HANDLERS["tts_all"](d)
    assert res["generated"] == 1                          # 내레이션 있는 씬만


def test_assemble_handler(tmp_path, monkeypatch):
    from backend import manifest
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a"}])
    monkeypatch.setattr(manifest, "build_manifest", lambda proj_dir: {"path": "m.json", "scenes": 1})
    assert assistant.ACTION_HANDLERS["assemble"](d)["scenes"] == 1


def test_tts_all_handler_prefers_narration_tts(tmp_path, monkeypatch):
    from backend import tts as _tts
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a", "narration": "원문",
                          "narration_tts": "교정본"}])
    seen = []
    monkeypatch.setattr(_tts, "generate_scene_tts",
                        lambda proj_dir, sid, text, voice=None: seen.append(text) or
                        {"status": "completed"})
    res = assistant.ACTION_HANDLERS["tts_all"](d)
    assert res["generated"] == 1 and seen == ["교정본"]


def test_plan_actions_question_returns_reply(tmp_path, monkeypatch):
    """질문이면 actions 비우고 reply 답변 — 비서가 상담 모드로 응답."""
    d = _proj(tmp_path, [{"sceneNumber": 2, "sceneId": "q1", "narration": "씬 둘"}])
    cap = {}

    def fake_run(prompt, cwd, *, output_schema=None, output_last=None, images=None, on_line=None, **kw):
        cap["prompt"] = prompt
        Path(output_last).write_text(
            '{"actions":[],"reply":"씬 2는 인물 2명 + 전경 책상 1 + 강조 사물 1로 4개 분리를 권합니다."}',
            encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(assistant.llm, "run_orchestrator", fake_run)
    out = assistant.run_assistant(d, "2번 씬은 레이어 몇 개로 나누면 좋을까?")
    assert out["reply"].startswith("씬 2는")
    assert out["plan"] == [] and out["results"] == []
    assert "질문" in cap["prompt"] and "씬2" in cap["prompt"].replace(" ", "")   # 씬별 상태 제공


def test_run_assistant_legacy_list_planner_compat(tmp_path):
    """구형(list 반환) 주입 플래너 호환 유지."""
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a"}])
    out = assistant.run_assistant(
        d, "x",
        planner=lambda proj_dir, instr, on_line=None: [{"action": "assemble", "reason": "r"}],
        handlers={"assemble": lambda proj_dir, on_event=None: {"scenes": 0}})
    assert out["plan"][0]["action"] == "assemble" and out["reply"] is None


def test_history_roundtrip_and_prompt_inclusion(tmp_path, monkeypatch):
    """대화 이력이 저장되고 다음 플래닝 프롬프트에 포함 — 이어지는 상의 가능."""
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "h1", "narration": "n"}])
    cap = {}

    def fake_run(prompt, cwd, **kw):
        cap["prompt"] = prompt
        Path(kw["output_last"]).write_text('{"actions":[],"reply":"씬 1부터 보시죠."}', encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(assistant.llm, "run_orchestrator", fake_run)
    assistant.run_assistant(d, "어떤 씬부터 작업할까?")
    out2 = assistant.run_assistant(d, "그럼 그 다음은?")
    assert "어떤 씬부터 작업할까?" in cap["prompt"]       # 이전 사용자 발화 포함
    assert "씬 1부터 보시죠." in cap["prompt"]            # 이전 비서 답변 포함
    assert "최근 대화" in cap["prompt"]
    assert out2["reply"] == "씬 1부터 보시죠."


def test_prompt_defaults_to_consult(tmp_path, monkeypatch):
    """프롬프트가 상담 기본 + 명확한 명령만 실행 원칙을 명시."""
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "c2"}])
    cap = {}

    def fake_run(prompt, cwd, **kw):
        cap["prompt"] = prompt
        Path(kw["output_last"]).write_text('{"actions":[],"reply":"r"}', encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(assistant.llm, "run_orchestrator", fake_run)
    assistant.plan_actions(d, "음")
    assert "기본은 '대화'" in cap["prompt"]
    assert "명확하게 실행을 지시" in cap["prompt"]
    assert "실행할까요?" in cap["prompt"]                  # 모호하면 제안만
