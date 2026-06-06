import pytest
from pathlib import Path
from backend import skills_cfg

SKILLS = Path(__file__).resolve().parents[1] / "skills"


def test_load_config():
    c = skills_cfg.load_config(SKILLS, "scene-decompose")
    assert c["output"] == "scenes.json"
    assert c["inputs"] == ["final_manuscript.md"]
    assert c["output_kind"] == "json"


def test_build_prompt_includes_skill_and_inputs(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "final_manuscript.md").write_text("원고내용ABC", encoding="utf-8")
    c = skills_cfg.load_config(SKILLS, "scene-decompose")
    prompt = skills_cfg.build_prompt(SKILLS, "scene-decompose", c, proj)
    assert "원고내용ABC" in prompt
    assert "scene-decompose" in prompt
    assert "scenes.json" in prompt


def test_missing_inputs(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    c = skills_cfg.load_config(SKILLS, "scene-decompose")
    missing = skills_cfg.missing_inputs(c, proj)
    assert "final_manuscript.md" in missing


def test_reference_list_config():
    c = skills_cfg.load_config(SKILLS, "reference-list")
    assert c["output"] == "references.json"
    assert c["schema"] == "references.schema.json"
    assert c["inputs"] == ["final_manuscript.md"]


PIPELINE = ["plan-explore", "deep-research", "draft-write",
            "target-research", "finalize-manuscript", "review-refine"]


@pytest.mark.parametrize("name", PIPELINE)
def test_pipeline_skill_configs_load(name):
    c = skills_cfg.load_config(SKILLS, name)
    assert c["name"] == name
    assert c["output"]
    assert (SKILLS / name / "SKILL.md").exists()
