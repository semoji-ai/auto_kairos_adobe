import json
import pytest
from backend import scene_analysis, llm


def _setup(tmp_path, scenes, manuscript=None, duration="1분"):
    (tmp_path / "scenes.json").write_text(json.dumps({"scenes": scenes}), encoding="utf-8")
    (tmp_path / "plan.md").write_text(f"# t\n채널: semoji\n분량: {duration}\n", encoding="utf-8")
    man = manuscript if manuscript is not None else " ".join(s.get("narration", "") for s in scenes)
    (tmp_path / "final_manuscript.md").write_text(man, encoding="utf-8")
    (tmp_path / "editorial_brief.json").write_text('{"real_topic":"x"}', encoding="utf-8")


def _good_scenes():
    return [{"sceneNumber": 1, "narration": "첫 씬 내용.", "visual_summary": "v1",
             "layout": "cinematic", "shot_relation": "cut", "characters": [], "location": ""},
            {"sceneNumber": 2, "narration": "둘째 씬 내용.", "visual_summary": "v2",
             "layout": "headline_only", "shot_relation": "cut", "characters": [], "location": ""}]


def test_review_merges_llm_flags(tmp_path, monkeypatch):
    _setup(tmp_path, _good_scenes())
    monkeypatch.setattr(scene_analysis, "_review_scenes_llm",
                        lambda pd, scenes, **k: {"scenes": [{"sceneNumber": 1, "layout_fit": "ok"}],
                                                 "flags": ["씬2: headline 적절"], "overall": "양호"})
    r = scene_analysis.review_scenes(tmp_path)
    assert r["flags"] == 1
    rep = json.loads((tmp_path / "scene_review.json").read_text(encoding="utf-8"))
    assert rep["overall"] == "양호" and rep["flags"] == ["씬2: headline 적절"]
    assert rep["deterministic"]["scenes"] == 2


def test_det_detects_first_scene_continue_and_bad_visual(tmp_path, monkeypatch):
    bad = _good_scenes()
    bad[0]["shot_relation"] = "continue"
    bad[1]["visual_summary"] = ""
    _setup(tmp_path, bad)
    monkeypatch.setattr(scene_analysis, "_review_scenes_llm", lambda *a, **k: {"scenes": [], "flags": []})
    r = scene_analysis.review_scenes(tmp_path)
    rep = json.loads((tmp_path / "scene_review.json").read_text(encoding="utf-8"))
    issues = " ".join(rep["deterministic"]["issues"])
    assert "첫 씬" in issues and "visual_summary" in issues
    assert r["det_issues"] >= 2


def test_det_detects_per_minute_too_many(tmp_path, monkeypatch):
    many = [{"sceneNumber": i + 1, "narration": f"씬{i}.", "visual_summary": "v",
             "layout": "cinematic", "shot_relation": "cut"} for i in range(20)]
    _setup(tmp_path, many, duration="1분")
    monkeypatch.setattr(scene_analysis, "_review_scenes_llm", lambda *a, **k: {"scenes": [], "flags": []})
    scene_analysis.review_scenes(tmp_path)
    rep = json.loads((tmp_path / "scene_review.json").read_text(encoding="utf-8"))
    assert any("분당 씬 수" in x for x in rep["deterministic"]["issues"])


def test_review_llm_failure_fallback(tmp_path, monkeypatch):
    _setup(tmp_path, _good_scenes())
    monkeypatch.setattr(llm, "run_orchestrator",
                        lambda *a, **k: {"returncode": 1, "output_last": k.get("output_last")})
    r = scene_analysis.review_scenes(tmp_path)
    assert r["flags"] == 0
    rep = json.loads((tmp_path / "scene_review.json").read_text(encoding="utf-8"))
    assert rep["scenes"] == [] and rep["deterministic"]["scenes"] == 2


def test_det_does_not_flag_bar_layout(tmp_path, monkeypatch):
    bar = [{"sceneNumber": 1, "narration": "연도별 매출 비교.", "visual_summary": "차트",
            "layout": "bar", "shot_relation": "cut", "characters": [], "location": "",
            "headline": "매출 추이", "chart": {"values": [1, 2, 3], "labels": ["a", "b", "c"], "unit": "%"}}]
    _setup(tmp_path, bar)
    monkeypatch.setattr(scene_analysis, "_review_scenes_llm", lambda *a, **k: {"scenes": [], "flags": []})
    scene_analysis.review_scenes(tmp_path)
    rep = json.loads((tmp_path / "scene_review.json").read_text(encoding="utf-8"))
    assert not any("비표준값" in x for x in rep["deterministic"]["issues"])


def test_review_no_scenes_errors(tmp_path):
    (tmp_path / "final_manuscript.md").write_text("x", encoding="utf-8")
    r = scene_analysis.review_scenes(tmp_path)
    assert r.get("error")


# ===== apply_review_layouts — 오케스트레이터 판단 + 결정적 데이터 게이트 =====
def _setup_review(tmp_path, scenes, review_scenes):
    (tmp_path / "scenes.json").write_text(json.dumps({"scenes": scenes}), encoding="utf-8")
    (tmp_path / "final_manuscript.md").write_text("x", encoding="utf-8")
    (tmp_path / "editorial_brief.json").write_text('{"real_topic":"x"}', encoding="utf-8")
    (tmp_path / "scene_review.json").write_text(
        json.dumps({"scenes": review_scenes, "flags": [], "deterministic": {}}), encoding="utf-8")


def _cine(sn, narr="내용"):
    return {"sceneNumber": sn, "narration": narr, "visual_summary": "v",
            "layout": "cinematic", "shot_relation": "cut", "characters": []}


def test_apply_no_candidates_keeps_all(tmp_path):
    # 검토가 현재와 같은 레이아웃을 권고 → 후보 없음
    _setup_review(tmp_path, [_cine(1)], [{"sceneNumber": 1, "layout_fit": "cinematic"}])
    r = scene_analysis.apply_review_layouts(tmp_path)
    assert r["changed"] == 0 and r["applied"] == []


def test_apply_metric_when_data_valid(tmp_path, monkeypatch):
    _setup_review(tmp_path, [_cine(1, "무게는 340kg에 달했다")],
                  [{"sceneNumber": 1, "layout_fit": "metric_spotlight", "note": "수치 강조"}])

    def fake(prompt, cwd, *, output_schema=None, output_last=None, on_line=None, **k):
        assert "metric_spotlight" in prompt
        json_path = output_last
        __import__("pathlib").Path(json_path).write_text(json.dumps({"decisions": [
            {"sceneNumber": 1, "apply": True, "layout": "metric_spotlight",
             "value": "340kg", "label": "최초 전자레인지 무게"}]}), encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    r = scene_analysis.apply_review_layouts(tmp_path)
    assert r["changed"] == 1 and r["applied"][0]["to"] == "metric_spotlight"
    doc = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
    s = doc["scenes"][0]
    assert s["layout"] == "metric_spotlight" and s["value"] == "340kg" and s["label"]
    assert list(tmp_path.glob("scenes.v*.json"))          # 무삭제 백업 생성


def test_apply_blocked_when_data_missing(tmp_path, monkeypatch):
    # LLM이 apply=true지만 value/label 누락 → 결정적 게이트가 차단(빈 렌더 방지)
    _setup_review(tmp_path, [_cine(1)],
                  [{"sceneNumber": 1, "layout_fit": "metric_spotlight"}])

    def fake(prompt, cwd, *, output_schema=None, output_last=None, on_line=None, **k):
        __import__("pathlib").Path(output_last).write_text(json.dumps({"decisions": [
            {"sceneNumber": 1, "apply": True, "layout": "metric_spotlight", "value": ""}]}),
            encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    r = scene_analysis.apply_review_layouts(tmp_path)
    assert r["changed"] == 0 and r["kept"]
    doc = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
    assert doc["scenes"][0]["layout"] == "cinematic"      # 변경 안 됨
    assert not list(tmp_path.glob("scenes.v*.json"))       # 변경 없으니 백업 없음


def test_apply_respects_llm_keep_decision(tmp_path, monkeypatch):
    _setup_review(tmp_path, [_cine(1)], [{"sceneNumber": 1, "layout_fit": "metric_spotlight"}])

    def fake(prompt, cwd, *, output_schema=None, output_last=None, on_line=None, **k):
        __import__("pathlib").Path(output_last).write_text(json.dumps({"decisions": [
            {"sceneNumber": 1, "apply": False, "reason": "오프닝 훅엔 cinematic이 적합"}]}),
            encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    r = scene_analysis.apply_review_layouts(tmp_path)
    assert r["changed"] == 0
    assert "cinematic" in r["kept"][0]["reason"] or "apply=false" in r["kept"][0]["reason"]


def test_apply_bar_requires_three_values(tmp_path, monkeypatch):
    _setup_review(tmp_path, [_cine(1)], [{"sceneNumber": 1, "layout_fit": "bar"}])

    def fake(prompt, cwd, *, output_schema=None, output_last=None, on_line=None, **k):
        __import__("pathlib").Path(output_last).write_text(json.dumps({"decisions": [
            {"sceneNumber": 1, "apply": True, "layout": "bar", "headline": "매출",
             "values": [10, 20], "labels": ["a", "b"]}]}), encoding="utf-8")  # 2개 < 3
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    r = scene_analysis.apply_review_layouts(tmp_path)
    assert r["changed"] == 0                               # 3개 미만 → 게이트 차단


def test_apply_detects_warn_plus_note_format(tmp_path, monkeypatch):
    # 실전 검토 형식: layout_fit='warn', 권고 레이아웃은 note 자유텍스트에 있음
    _setup_review(tmp_path, [_cine(1, "보유율은 96퍼센트에 달한다")],
                  [{"sceneNumber": 1, "layout_fit": "warn",
                    "note": "수치 1개를 각인시키려면 metric_spotlight 권장"}])

    def fake(prompt, cwd, *, output_schema=None, output_last=None, on_line=None, **k):
        assert "씬 1" in prompt and "metric_spotlight" in prompt
        __import__("pathlib").Path(output_last).write_text(json.dumps({"decisions": [
            {"sceneNumber": 1, "apply": True, "layout": "metric_spotlight",
             "value": "96%", "label": "국내 전자레인지 보유율"}]}), encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    r = scene_analysis.apply_review_layouts(tmp_path)
    assert r["changed"] == 1 and r["applied"][0]["to"] == "metric_spotlight"


def test_apply_ok_verdict_not_candidate(tmp_path, monkeypatch):
    # layout_fit='ok'이고 note가 cinematic 적절이라 하면 후보 아님(호출조차 없음)
    _setup_review(tmp_path, [_cine(1)],
                  [{"sceneNumber": 1, "layout_fit": "ok", "note": "서사 중심 cinematic 적절"}])
    called = {"n": 0}
    monkeypatch.setattr(llm, "run_orchestrator",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or {"returncode": 1})
    r = scene_analysis.apply_review_layouts(tmp_path)
    assert r["changed"] == 0 and called["n"] == 0          # 후보 없으니 LLM 호출 안 함


def test_apply_absorbs_nested_data_and_scene_key(tmp_path, monkeypatch):
    # 실전 LLM 변형: sceneNumber 대신 'scene', 데이터를 'data'{}에 중첩 — 둘 다 흡수해야 함
    _setup_review(tmp_path, [_cine(1, "보유율은 96퍼센트")],
                  [{"sceneNumber": 1, "layout_fit": "warn", "note": "metric_spotlight 권장"}])

    def fake(prompt, cwd, *, output_schema=None, output_last=None, on_line=None, **k):
        __import__("pathlib").Path(output_last).write_text(json.dumps({"decisions": [
            {"scene": 1, "apply": True, "layout": "metric_spotlight",
             "data": {"value": "96%", "label": "보유율"}}]}), encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    r = scene_analysis.apply_review_layouts(tmp_path)
    assert r["changed"] == 1, r
    doc = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
    assert doc["scenes"][0]["value"] == "96%" and doc["scenes"][0]["label"] == "보유율"
