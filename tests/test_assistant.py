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
    actions = assistant.plan_actions(d, "음성 입혀서 합쳐줘")
    assert [a["action"] for a in actions] == ["tts_all", "assemble"]


def test_plan_actions_failure_returns_empty(tmp_path, monkeypatch):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a"}])
    monkeypatch.setattr(assistant.llm, "run_orchestrator",
                        lambda *a, **k: {"returncode": 1, "output_last": k.get("output_last")})
    assert assistant.plan_actions(d, "뭐든") == []


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
