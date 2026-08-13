import json
from pathlib import Path

from backend import imagegen


def _els(n):
    return [{"name": f"el{i}", "location": "loc", "kind": "object", "reason": "r"} for i in range(n)]


def test_budget_keeps_first_four_in_priority_order():
    """분석 프롬프트가 이미 우선순위(캐릭터 > 가리는 전경 > 필요한 소품) 순으로 주므로 앞에서 자른다."""
    res = imagegen.apply_element_budget(_els(6))
    assert [e["name"] for e in res["elements"]] == ["el0", "el1", "el2", "el3"]
    assert [e["name"] for e in res["dropped"]] == ["el4", "el5"]
    assert imagegen.MAX_ELEMENTS == 4


def test_budget_passes_through_when_under_limit():
    res = imagegen.apply_element_budget(_els(3))
    assert len(res["elements"]) == 3 and res["dropped"] == []


def test_budget_handles_empty():
    res = imagegen.apply_element_budget([])
    assert res["elements"] == [] and res["dropped"] == []


def test_analyze_applies_budget(tmp_path, monkeypatch):
    """씬당 최대 5레이어 = 요소 4 + 배경 1."""
    out_json = tmp_path / ".layer_analysis.json"

    def _fake_run(prompt, proj_dir, **kw):
        out_json.write_text(json.dumps({"elements": _els(6)}), encoding="utf-8")
        return {"returncode": 0}

    monkeypatch.setattr(imagegen.llm, "run_orchestrator", _fake_run)
    res = imagegen.analyze_scene_layers(tmp_path, str(tmp_path / "scene.png"))
    assert len(res["elements"]) == 4
    assert len(res["dropped"]) == 2


def test_background_prompt_excludes_only_kept_elements(tmp_path, monkeypatch):
    """잘린 요소는 배경에 남아야 하므로 제거 목록에서 빠진다.
    split_scene_to_elements에 6개를 주면 4개 요소 레이어 + 1개 배경이 생기고,
    배경 프롬프트는 4개만 제거 대상으로 포함해야 한다(5번째·6번째는 배경에 유지)."""
    prompts = []
    monkeypatch.setattr(imagegen, "_run_fal_image",
                        lambda proj_dir, out, prompt, images=None, post=None:
                            (prompts.append(prompt),
                             Path(out).write_bytes(b"\x89PNG"),
                             {"status": "completed", "path": str(out)})[2])
    monkeypatch.setattr(imagegen, "load_style", lambda: "STYLE")
    monkeypatch.setattr(imagegen, "_scene_size", lambda p: None)
    monkeypatch.setattr(imagegen, "pick_key_color", lambda p: {"key": "magenta", "rgb": [255, 0, 255], "coverage": {"magenta": 0.1, "green": 0.2}})
    monkeypatch.setattr(imagegen, "chroma_key", lambda src, out, **kw: {"transparent_ratio": 0.7})

    # 씬 이미지 생성
    scene_img = tmp_path / "scene.png"
    scene_img.write_bytes(b"\x89PNG")

    # 6개 요소로 split 호출 — 4개만 채택되어야 함
    elements = _els(6)
    res = imagegen.split_scene_to_elements(tmp_path, str(scene_img), "ab", elements, subdir="layers")

    # 결과: 4개 요소 레이어 + 1개 배경 = 5개 총
    layers = res.get("layers", [])
    assert len(layers) == 5, f"Expected 5 layers (4 elements + 1 background), got {len(layers)}"

    # 배경 레이어는 마지막 (5번째)
    bg_layer = layers[-1]
    assert bg_layer.get("name") == "배경", f"Last layer should be background, got {bg_layer.get('name')}"

    # 배경 프롬프트: el0~el3만 포함, el4·el5는 제외
    bg_prompts = [p for p in prompts if "배경" in p and "제거" in p]
    assert bg_prompts, f"No background prompt found. Prompts: {prompts}"
    bg_prompt = bg_prompts[0]
    assert "el0" in bg_prompt and "el1" in bg_prompt and "el2" in bg_prompt and "el3" in bg_prompt, \
        f"Background prompt should contain el0-el3: {bg_prompt}"
    assert "el4" not in bg_prompt and "el5" not in bg_prompt, \
        f"Background prompt should NOT contain el4-el5: {bg_prompt}"
