"""레이어 분석 — 연출 의도 기반 판단(프롬프트 조립·스키마·사이드카)."""
import json
from pathlib import Path

from backend import imagegen, motion

SCHEMA = Path(__file__).resolve().parents[1] / "backend" / "schemas" / "layer_elements.schema.json"


def test_motion_vocabulary_is_public():
    """분석과 모션 플랜이 같은 어휘 목록을 써야 한다 — 출처는 motion 한 곳."""
    assert isinstance(motion.PRESET_GUIDE, str)
    for name in ("slide_in", "fade_in", "pop", "drift", "bob", "shake",
                 "zoom_emphasis", "exit_fade"):
        assert name in motion.PRESET_GUIDE, name
    for cam in ("slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right"):
        assert cam in motion.CAMERA_GUIDE, cam
    assert motion._PRESET_GUIDE is motion.PRESET_GUIDE      # 기존 사용처 보존


def test_schema_requires_intent_and_english_name():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    item = schema["properties"]["elements"]["items"]
    assert set(item["required"]) == {"name", "name_en", "location", "kind", "reason", "intent"}
    assert item["properties"]["name_en"]["type"] == "string"
    assert item["properties"]["intent"]["type"] == "string"
    assert item["additionalProperties"] is False


def test_prompt_carries_direction_inputs():
    """씬 이미지를 만든 프롬프트가 연출 의도의 원본 — 반드시 전달돼야 한다."""
    p = imagegen.build_layer_analysis_prompt(
        narration="당시 전기차는 느리다는 이미지가 강했다.",
        context="제목: 속도 / 요약: 이미지를 깨는 순간",
        image_prompt="어두운 도로 위를 강하게 가속하며 출발하는 빨간 전기 스포츠카, 속도감 있는 빛의 궤적",
        neighbors="앞 씬(continue): 창업 — 2003년 설립\n뒤 씬(cut): 위기 — 파산 직전",
        briefing="테슬라 창업 서사. 인물 중심, 담백한 톤.")
    assert "빛의 궤적" in p                      # image_prompt 본문
    assert "당시 전기차는" in p                  # narration
    assert "앞 씬(continue)" in p                # 앞뒤 씬
    assert "담백한 톤" in p                      # 브리핑
    for name in ("slide_in", "bob", "zoom_emphasis", "exit_fade"):
        assert name in p, name                   # 실행 가능한 모션 어휘
    assert "slow_zoom_in" in p                   # 카메라 어휘


def test_prompt_demands_minimality_and_intent():
    """연출로 물으면 없는 움직임을 지어내기 쉽다 — 최소성과 intent를 프롬프트가 강제해야 한다."""
    p = imagegen.build_layer_analysis_prompt()
    assert "인물 1장 + 배경 1장" in p            # 최소 구성 반례
    assert "intent" in p
    assert "배경에 남긴다" in p                  # intent를 못 대면 분리하지 않는다
    assert "name_en" in p                        # 영어 이름 요구
    assert str(imagegen.MAX_ELEMENTS) in p       # 상한 명시


def test_prompt_handles_empty_inputs():
    p = imagegen.build_layer_analysis_prompt()
    assert "(없음)" in p and len(p) > 200


def test_analyze_passes_new_context_through(tmp_path, monkeypatch):
    seen = {}

    def _fake(prompt, proj_dir, **kw):
        seen["prompt"] = prompt
        (tmp_path / ".layer_analysis.json").write_text(json.dumps({"elements": [
            {"name": "차량", "name_en": "red sports car", "location": "중앙",
             "kind": "object", "reason": "가속을 표현", "intent": "slide_in 좌→우"}]}),
            encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(imagegen.llm, "run_orchestrator", _fake)
    res = imagegen.analyze_scene_layers(tmp_path, str(tmp_path / "s.png"),
                                        image_prompt="빛의 궤적", briefing="브리핑")
    assert "빛의 궤적" in seen["prompt"] and "브리핑" in seen["prompt"]
    assert res["elements"][0]["intent"] == "slide_in 좌→우"
    assert res["elements"][0]["name_en"] == "red sports car"


def test_neighbor_context_builds_both_sides():
    from backend import router
    ss = [{"sceneNumber": 1, "title": "창업", "narration": "2003년 설립됐다."},
          {"sceneNumber": 2, "title": "속도", "narration": "로드스터가 등장했다.",
           "shot_relation": "continue"},
          {"sceneNumber": 3, "title": "위기", "narration": "파산 직전까지 갔다.",
           "shot_relation": "cut"}]
    ctx = router._neighbor_context(ss, 2)
    assert "창업" in ctx and "위기" in ctx
    assert "continue" in ctx                      # 이 씬이 앞 씬과 이어지는지
    assert router._neighbor_context(ss, 1).startswith("앞 씬: (없음)")
    assert "뒤 씬: (없음)" in router._neighbor_context(ss, 3)
    assert router._neighbor_context([], 1)        # 빈 목록도 문자열 반환


def test_analyze_endpoint_passes_direction_context(tmp_path, monkeypatch):
    import backend.router as r
    from backend.jobs import JobRegistry
    proj = tmp_path / "p"
    (proj / "storyboard").mkdir(parents=True)
    (proj / "storyboard" / "sb_a.png").write_bytes(b"\x89PNG")
    (proj / "scenes.json").write_text(json.dumps({"scenes": [
        {"sceneNumber": 1, "sceneId": "a", "title": "속도", "narration": "빠르다.",
         "visual_summary": "가속 순간", "image_prompt": "빛의 궤적이 있는 빨간 스포츠카",
         "imageRef": "storyboard/sb_a.png"},
        {"sceneNumber": 2, "sceneId": "b", "title": "위기", "narration": "위험했다."}]}),
        encoding="utf-8")
    seen = {}

    def _fake(proj_dir, scene_image, **kw):
        seen.update(kw)
        return {"elements": [], "dropped": []}

    monkeypatch.setattr(r.imagegen, "analyze_scene_layers", _fake)
    monkeypatch.setattr(r.vault, "read_context", lambda d: "프로젝트 브리핑 요약")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, _ = r.handle_request("POST", "/api/scenes/analyze-layers", {},
                               {"project_id": "p", "sceneNumber": 1}, ctx)
    assert code == 200
    assert seen["image_prompt"] == "빛의 궤적이 있는 빨간 스포츠카"
    assert "위기" in seen["neighbors"]
    assert seen["briefing"] == "프로젝트 브리핑 요약"
    assert "속도" in seen["context"]


def test_specs_sidecar_keeps_intent(tmp_path, monkeypatch):
    """분리 시점의 연출 의도가 남아야 모션 플랜이 이어받을 수 있다."""
    monkeypatch.setattr(imagegen, "_run_fal_image",
                        lambda proj_dir, out, prompt, images=None, post=None:
                            (Path(out).write_bytes(b"\x89PNG"),
                             {"status": "completed", "path": str(out)})[1])
    monkeypatch.setattr(imagegen, "load_style", lambda: "STYLE")
    monkeypatch.setattr(imagegen, "_scene_size", lambda p: None)
    monkeypatch.setattr(imagegen, "chroma_key", lambda a, b, key=None: {"transparent_ratio": 0.5})
    monkeypatch.setattr(imagegen, "position_score", lambda a, b: 0.9)
    monkeypatch.setattr(imagegen, "flatten_colors", lambda p: True)
    from PIL import Image
    Image.new("RGB", (8, 8)).save(tmp_path / "s.png")

    imagegen.split_scene_to_elements(tmp_path, str(tmp_path / "s.png"), "ab", [
        {"name": "차량", "name_en": "red car", "location": "중앙", "kind": "object",
         "reason": "가속 표현", "intent": "slide_in 좌→우"}])
    specs = imagegen.load_element_specs(tmp_path / "layers", "ab")
    assert specs[0]["intent"] == "slide_in 좌→우"
    assert specs[0]["name_en"] == "red car"


def test_motion_prompt_includes_intent(tmp_path, monkeypatch):
    from backend import motion as m
    seen = {}

    def _fake(prompt, proj_dir, **kw):
        seen["prompt"] = prompt
        return {"returncode": 1}

    (tmp_path / "layers").mkdir()
    (tmp_path / "layers" / "ab__0_인물_char.png").write_bytes(b"\x89PNG")
    (tmp_path / "scenes.json").write_text(json.dumps({"scenes": [
        {"sceneNumber": 1, "sceneId": "ab", "narration": "말한다."}]}), encoding="utf-8")
    (tmp_path / "layers" / "ab__kinds.json").write_text(
        json.dumps({"ab__0_인물_char": "character"}), encoding="utf-8")
    imagegen.write_element_specs(tmp_path / "layers", "ab", [
        {"layer": "ab__0_인물_char", "index": 0, "name": "인물", "name_en": "person",
         "location": "좌측", "kind": "character", "intent": "bob으로 생동감"}])
    monkeypatch.setattr(m.llm, "run_orchestrator", _fake)
    m.plan_scene_motion(tmp_path, 1)
    assert "bob으로 생동감" in seen["prompt"]
