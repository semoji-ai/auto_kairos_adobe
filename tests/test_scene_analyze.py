import json
from pathlib import Path
from backend import scene_analysis, llm

_SPECS_SCHEMA = Path(__file__).resolve().parents[1] / "backend/schemas/scene_specs.schema.json"


def test_scene_specs_schema_has_bar_and_chart_fields():
    props = json.loads(_SPECS_SCHEMA.read_text(encoding="utf-8"))[
        "properties"]["scenes"]["items"]["properties"]
    assert "bar" in props["layout"]["enum"]
    for f in ("headline", "values", "labels", "unit"):
        assert f in props, f


def _setup(tmp_path, manuscript):
    (tmp_path / "final_manuscript.md").write_text(manuscript, encoding="utf-8")
    (tmp_path / "editorial_brief.json").write_text('{"real_topic":"유한양행"}', encoding="utf-8")


def _patch_direct(monkeypatch, scenes):
    def fake_orch(prompt, cwd, *, output_schema=None, output_last=None, **k):
        Path(output_last).write_text(json.dumps({"scenes": scenes}), encoding="utf-8")
        return {"returncode": 0, "output_last": output_last}
    monkeypatch.setattr(llm, "run_orchestrator", fake_orch)


def test_analyze_scenes_builds_scenes_json(tmp_path, monkeypatch):
    _setup(tmp_path, "첫 씬.\n<!--SCENE-->\n둘째 씬.")
    _patch_direct(monkeypatch, [
        {"visual_summary": "공장 외경", "image_prompt": "1933 공장", "characters": []},
        {"visual_summary": "창업자 클로즈업", "image_prompt": "유일한 박사", "characters": ["유일한"]}])
    r = scene_analysis.analyze_scenes(tmp_path)
    assert r["count"] == 2
    data = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
    s = data["scenes"]
    assert s[0]["narration"] == "첫 씬." and s[0]["visual_summary"] == "공장 외경"
    assert s[1]["narration"] == "둘째 씬." and s[1]["sceneNumber"] == 2
    assert all(sc.get("sceneId") for sc in s)
    assert s[1]["characters"] == ["유일한"]


def test_analyze_scenes_marker_chars_win(tmp_path, monkeypatch):
    _setup(tmp_path, "씬.\n<!--CHARS: 소년-->\n본문.")
    _patch_direct(monkeypatch, [{"visual_summary": "v", "image_prompt": "p", "characters": ["딴사람"]}])
    scene_analysis.analyze_scenes(tmp_path)
    data = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
    assert data["scenes"][0]["characters"] == ["소년"]


def test_analyze_scenes_direction_count_mismatch(tmp_path, monkeypatch):
    _setup(tmp_path, "씬1.\n<!--SCENE-->\n씬2.\n<!--SCENE-->\n씬3.")
    _patch_direct(monkeypatch, [{"visual_summary": "v1", "image_prompt": "p1"}])
    r = scene_analysis.analyze_scenes(tmp_path)
    assert r["count"] == 3
    data = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
    assert data["scenes"][0]["visual_summary"] == "v1"
    assert data["scenes"][2]["narration"] == "씬3."


def test_analyze_scenes_llm_failure_fallback(tmp_path, monkeypatch):
    _setup(tmp_path, "씬1.\n<!--SCENE-->\n씬2.")
    monkeypatch.setattr(llm, "run_orchestrator",
                        lambda *a, **k: {"returncode": 1, "output_last": k.get("output_last")})
    r = scene_analysis.analyze_scenes(tmp_path)
    assert r["count"] == 2
    data = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))
    assert data["scenes"][0]["narration"] == "씬1."


def test_analyze_scenes_no_manuscript_errors(tmp_path):
    r = scene_analysis.analyze_scenes(tmp_path)
    assert r.get("error")


def test_analyze_scenes_bar_layout_passthrough(tmp_path, monkeypatch):
    _setup(tmp_path, "매출이 3년간 늘었습니다.")
    _patch_direct(monkeypatch, [
        {"visual_summary": "연도별 매출", "image_prompt": "", "characters": [],
         "layout": "bar", "headline": "연도별 매출 추이",
         "values": [120, 340, 580], "labels": ["2020", "2021", "2022"], "unit": "억원"}])
    scene_analysis.analyze_scenes(tmp_path, enrich=False)
    s = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]
    assert s["layout"] == "bar"
    assert s["headline"] == "연도별 매출 추이"
    # 다운스트림(jsx/manifest/storyboard) 계약: chart{values,labels,unit}
    assert s["chart"] == {"values": [120, 340, 580], "labels": ["2020", "2021", "2022"], "unit": "억원"}


def test_analyze_scenes_nonbar_has_no_chart(tmp_path, monkeypatch):
    _setup(tmp_path, "도입부.")
    _patch_direct(monkeypatch, [
        {"visual_summary": "도입", "image_prompt": "p", "characters": [], "layout": "cinematic"}])
    scene_analysis.analyze_scenes(tmp_path, enrich=False)
    s = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]
    assert "chart" not in s and "headline" not in s


def test_analyze_passes_metric_data_when_present(tmp_path, monkeypatch):
    """scene-analyze가 metric_spotlight를 데이터와 함께 내면 scenes.json에 value/label 통과."""
    _setup(tmp_path, "보유율 96%.")
    _patch_direct(monkeypatch, [
        {"visual_summary": "v", "layout": "metric_spotlight",
         "value": "96%", "label": "보유율"}])
    scene_analysis.analyze_scenes(tmp_path)
    s = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]
    assert s["layout"] == "metric_spotlight" and s["value"] == "96%" and s["label"] == "보유율"


def test_analyze_downgrades_dataless_layout_to_cinematic(tmp_path, monkeypatch):
    """레이아웃만 배정하고 데이터가 없으면 cinematic으로 다운그레이드(빈 카드 렌더 방지)."""
    _setup(tmp_path, "씬1.\n<!--SCENE-->\n씬2.\n<!--SCENE-->\n씬3.")
    _patch_direct(monkeypatch, [
        {"visual_summary": "v1", "layout": "metric_spotlight"},          # value/label 없음
        {"visual_summary": "v2", "layout": "quote"},                     # quote_text 없음
        {"visual_summary": "v3", "layout": "quote", "quote_text": "필요는 발명의 어머니"}])
    scene_analysis.analyze_scenes(tmp_path)
    s = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))["scenes"]
    assert s[0]["layout"] == "cinematic"        # 데이터 없는 metric → 다운그레이드
    assert s[1]["layout"] == "cinematic"        # 데이터 없는 quote → 다운그레이드
    assert s[2]["layout"] == "quote" and s[2]["quote_text"] == "필요는 발명의 어머니"


def test_analyze_downgrades_bar_without_enough_values(tmp_path, monkeypatch):
    _setup(tmp_path, "매출.")
    _patch_direct(monkeypatch, [
        {"visual_summary": "v", "layout": "bar", "headline": "매출",
         "values": [10, 20], "labels": ["a", "b"]}])       # 3개 미만
    scene_analysis.analyze_scenes(tmp_path)
    s = json.loads((tmp_path / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]
    assert s["layout"] == "cinematic"           # bar 데이터 부족 → 다운그레이드


# ===== Serper 실사 검색 + 멀티모달 적합성 검사 =====
def test_pick_suitable_returns_chosen(tmp_path, monkeypatch):
    scene = {"sceneNumber": 1, "visual_summary": "특허 문서", "search_query": "US 3691140 patent"}
    (tmp_path / "c1.jpg").write_bytes(b"x"); (tmp_path / "c2.jpg").write_bytes(b"y")
    cands = [{"url": "u1", "title": "특허", "local": str(tmp_path / "c1.jpg")},
             {"url": "u2", "title": "딴것", "local": str(tmp_path / "c2.jpg")}]

    def fake(prompt, cwd, *, output_schema=None, output_last=None, images=None, on_line=None, **k):
        assert "적합성 판정 기준" in prompt and len(images) == 2   # 기준·이미지 전달
        Path(output_last).write_text(json.dumps({"best_index": 1, "reason": "내용 일치"}), encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    chosen = scene_analysis._pick_suitable_image(tmp_path, scene, cands)
    assert chosen and chosen["url"] == "u1"


def test_pick_suitable_rejects_all(tmp_path, monkeypatch):
    scene = {"sceneNumber": 1, "visual_summary": "특허"}
    (tmp_path / "c1.jpg").write_bytes(b"x")
    cands = [{"url": "u1", "local": str(tmp_path / "c1.jpg")}]

    def fake(prompt, cwd, *, output_schema=None, output_last=None, images=None, on_line=None, **k):
        Path(output_last).write_text(json.dumps({"best_index": 0, "reason": "전부 부적합"}), encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(llm, "run_orchestrator", fake)
    assert scene_analysis._pick_suitable_image(tmp_path, scene, cands) is None   # → generate 폴백


def test_pick_suitable_no_local_none(tmp_path):
    cands = [{"url": "u1", "local": None}]
    assert scene_analysis._pick_suitable_image(tmp_path, {"sceneNumber": 1}, cands) is None


def test_enrich_applies_only_suitable(tmp_path, monkeypatch):
    from backend import search, scenes as scenes_mod
    (tmp_path / "scenes.json").write_text(json.dumps({"scenes": [
        {"sceneNumber": 1, "sceneId": "s1", "asset_source": "search", "search_query": "특허", "imageRef": ""}]}),
        encoding="utf-8")
    specs = [{"sceneNumber": 1, "asset_source": "search", "search_query": "특허", "visual_summary": "특허"}]
    monkeypatch.setattr(search, "search_images", lambda q, **k: {"images": [{"url": "u1", "thumb": "t1"}]})
    monkeypatch.setattr(search, "download_candidates",
                        lambda pd, imgs, sid, **k: [{"url": "u1", "local": str(tmp_path / "c.jpg")}])
    (tmp_path / "c.jpg").write_bytes(b"x")
    monkeypatch.setattr(scene_analysis, "_pick_suitable_image",
                        lambda pd, s, cands, **k: {"url": "u1"})
    monkeypatch.setattr(search, "save_image", lambda pd, url, name, **k: {"status": "completed", "rel": "images/search/real_1.jpg"})
    applied = {}
    monkeypatch.setattr(scenes_mod, "set_image_ref", lambda pd, n, rel: applied.update({n: rel}))
    got = scene_analysis._enrich_real_assets(tmp_path, specs)
    assert got == 1 and applied == {1: "images/search/real_1.jpg"}


def test_enrich_skips_when_unsuitable(tmp_path, monkeypatch):
    from backend import search, scenes as scenes_mod
    specs = [{"sceneNumber": 1, "asset_source": "search", "search_query": "특허"}]
    monkeypatch.setattr(search, "search_images", lambda q, **k: {"images": [{"url": "u1"}]})
    monkeypatch.setattr(search, "download_candidates", lambda pd, imgs, sid, **k: [{"url": "u1", "local": "x"}])
    monkeypatch.setattr(scene_analysis, "_pick_suitable_image", lambda pd, s, cands, **k: None)  # 전부 부적합
    called = {"save": 0}
    monkeypatch.setattr(search, "save_image", lambda *a, **k: called.__setitem__("save", 1) or {"status": "completed"})
    got = scene_analysis._enrich_real_assets(tmp_path, specs)
    assert got == 0 and called["save"] == 0   # 부적합이면 다운로드·적용 안 함
