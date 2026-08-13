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
    """잘린 요소는 배경에 남아야 하므로 제거 목록에서 빠진다."""
    seen = {}
    monkeypatch.setattr(imagegen, "_run_fal_image",
                        lambda proj_dir, out, prompt, images=None, post=None:
                            (seen.__setitem__("prompt", prompt),
                             Path(out).write_bytes(b"\x89PNG"),
                             {"status": "completed", "path": str(out)})[2])
    monkeypatch.setattr(imagegen, "load_style", lambda: "STYLE")
    monkeypatch.setattr(imagegen, "_scene_size", lambda p: None)
    base = tmp_path / "layers"
    base.mkdir()
    imagegen.generate_background_layer(tmp_path, str(tmp_path / "s.png"), "ab",
                                       ["el0", "el1", "el2", "el3"], out_base=base)
    assert "el3" in seen["prompt"] and "el4" not in seen["prompt"]
