import json
from pathlib import Path

import numpy as np
from PIL import Image

from backend import imagegen


def _solid(tmp_path, name, rgb, size=(40, 40)):
    p = tmp_path / name
    Image.new("RGB", size, rgb).save(p)
    return p


def test_pick_key_color_avoids_dominant_magenta(tmp_path):
    """씬이 마젠타로 가득하면 마젠타로 키잉할 수 없다 — 그린을 골라야 한다."""
    p = _solid(tmp_path, "m.png", (250, 10, 250))
    res = imagegen.pick_key_color(p)
    assert res["key"] == "green"
    assert res["rgb"] == [0, 255, 0]


def test_pick_key_color_avoids_dominant_green(tmp_path):
    p = _solid(tmp_path, "g.png", (10, 250, 10))
    assert imagegen.pick_key_color(p)["key"] == "magenta"


def test_pick_key_color_defaults_to_magenta(tmp_path):
    """둘 다 없으면 기존 기본값(마젠타)을 유지한다."""
    p = _solid(tmp_path, "b.png", (120, 120, 120))
    res = imagegen.pick_key_color(p)
    assert res["key"] == "magenta"
    assert res["coverage"]["magenta"] == 0.0


def test_scene_key_color_is_sticky(tmp_path):
    """요소·배경·재생성이 같은 색을 써야 한다 — 한 번 정하면 사이드카에 고정."""
    base = tmp_path / "layers"
    base.mkdir()
    p = _solid(tmp_path, "m.png", (250, 10, 250))
    first = imagegen.scene_key_color(base, "ab", p)
    assert first["key"] == "green"
    assert (base / "ab__keycolor.json").is_file()
    # 씬 이미지를 바꿔도 이미 정해진 값을 그대로 쓴다
    p2 = _solid(tmp_path, "g.png", (10, 250, 10))
    assert imagegen.scene_key_color(base, "ab", p2)["key"] == "green"


def test_chroma_key_green_makes_background_transparent(tmp_path):
    """그린 키잉이 마젠타와 같은 기준으로 알파를 만든다."""
    src = tmp_path / "src.png"
    a = np.zeros((10, 10, 3), dtype="uint8")
    a[:, :5] = (0, 255, 0)          # 왼쪽 절반 그린 = 빼낼 배경
    a[:, 5:] = (200, 30, 40)        # 오른쪽 절반 요소
    Image.fromarray(a, "RGB").save(src)
    out = tmp_path / "out.png"
    res = imagegen.chroma_key(src, out, key="green")
    alpha = np.array(Image.open(out).convert("RGBA"))[:, :, 3]
    assert alpha[:, :5].max() == 0            # 그린은 완전 투명
    assert alpha[:, 7:].min() == 255          # 요소는 불투명
    assert 0.4 < res["transparent_ratio"] < 0.6


def test_chroma_key_magenta_alias_still_works(tmp_path):
    src = tmp_path / "src.png"
    a = np.zeros((10, 10, 3), dtype="uint8")
    a[:, :5] = (255, 0, 255)
    a[:, 5:] = (30, 200, 40)
    Image.fromarray(a, "RGB").save(src)
    out = tmp_path / "out.png"
    res = imagegen.chroma_key_magenta(src, out)
    alpha = np.array(Image.open(out).convert("RGBA"))[:, :, 3]
    assert alpha[:, :5].max() == 0
    assert 0.4 < res["transparent_ratio"] < 0.6


def test_element_prompt_uses_selected_key_color():
    p_m = imagegen.build_element_layer_prompt("인물", "좌측", "STYLE", "layers/a.png")
    assert "#FF00FF" in p_m and "마젠타" in p_m
    p_g = imagegen.build_element_layer_prompt("인물", "좌측", "STYLE", "layers/a.png", key="green")
    assert "#00FF00" in p_g and "그린" in p_g
    assert "#FF00FF" not in p_g


def test_element_prompt_exclusion_uses_key_color():
    p = imagegen.build_element_layer_prompt("인물", "좌측", "STYLE", "layers/a.png",
                                            others=["탁자"], key="green")
    assert "탁자" in p and "그린" in p


def test_run_fal_image_writes_output_and_runs_post(tmp_path, monkeypatch):
    from backend import fal_api
    out = tmp_path / "layers" / "x.png"
    called = {}
    monkeypatch.setattr(fal_api, "edit_image",
                        lambda prompt, imgs, **k: called.setdefault("prompt", prompt) and b"PNGDATA")
    monkeypatch.setattr(imagegen, "fal_api", fal_api)
    res = imagegen._run_fal_image(tmp_path, out, "프롬프트",
                                  images=[tmp_path / "scene.png"],
                                  post=lambda o: called.setdefault("post", str(o)))
    assert res["status"] == "completed"
    assert out.read_bytes() == b"PNGDATA"
    assert called["prompt"] == "프롬프트"
    assert called["post"] == str(out)


def test_run_fal_image_failure_returns_failed(tmp_path, monkeypatch):
    from backend import fal_api

    def _boom(*a, **k):
        raise fal_api.FalError("FAL_KEY 없음")

    monkeypatch.setattr(fal_api, "edit_image", _boom)
    res = imagegen._run_fal_image(tmp_path, tmp_path / "y.png", "p", images=[])
    assert res["status"] == "failed" and "FAL_KEY" in res["error"]


def test_element_prompt_and_chroma_key_agree_on_color(tmp_path, monkeypatch):
    """씬이 마젠타 지배적이면 그린이 선택된다 — 프롬프트도 그린을, chroma_key도 key="green"을 써야 한다.
    Finding 1 회귀 방지: _qc_feedback이 하드코딩된 마젠타를 재시도 프롬프트에 섞어 넣지 않는지도 함께 확인."""
    out_base = tmp_path / "layers"
    out_base.mkdir()
    scene_img = _solid(tmp_path, "scene.png", (250, 10, 250))   # 마젠타 지배적 → green 선택

    captured = {"prompts": [], "chroma_keys": []}

    def _fake_run_fal(proj_dir, out, prompt, images=None, post=None):
        captured["prompts"].append(prompt)
        Path(out).write_bytes(b"\x89PNG")
        if post:
            post(Path(out))
        return {"status": "completed", "path": str(out)}

    def _fake_chroma_key(src, out, key="magenta"):
        captured["chroma_keys"].append(key)
        return {"transparent_ratio": 0.5}

    monkeypatch.setattr(imagegen, "_run_fal_image", _fake_run_fal)
    monkeypatch.setattr(imagegen, "chroma_key", _fake_chroma_key)
    monkeypatch.setattr(imagegen, "flatten_colors", lambda p, colors=None: False)
    monkeypatch.setattr(imagegen, "position_score", lambda *a, **k: 1.0)
    monkeypatch.setattr(imagegen, "_aspect_mismatch", lambda *a, **k: False)
    monkeypatch.setattr(imagegen, "normalize_layer_size", lambda *a, **k: False)

    spec = {"name": "인물", "location": "좌측", "kind": "character"}
    r = imagegen.generate_element_layer(tmp_path, str(scene_img), "ab", 0, spec, [],
                                        out_base=out_base, scene_size=(40, 40), style="STYLE")

    assert r["status"] == "completed"
    assert captured["prompts"], "no prompt captured"
    assert "그린" in captured["prompts"][0]
    assert "마젠타" not in captured["prompts"][0]
    assert all(k == "green" for k in captured["chroma_keys"])


def test_qc_feedback_uses_matching_key_label():
    assert "그린" in imagegen._qc_feedback(0.0, None, key="green")
    assert "마젠타" not in imagegen._qc_feedback(0.0, None, key="green")
    assert "마젠타" in imagegen._qc_feedback(0.0, None)
    assert "마젠타" in imagegen._qc_feedback(1.0, None)


def test_background_prompt_has_no_codex_boilerplate(tmp_path, monkeypatch):
    """Finding 2: fal은 codex 전용 image_gen 도구/저장/응답 지시문을 받지 않아야 한다."""
    prompts = []

    def _fake_run_fal(proj_dir, out, prompt, images=None, post=None):
        prompts.append(prompt)
        Path(out).write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(imagegen, "_run_fal_image", _fake_run_fal)
    out_base = tmp_path / "layers"
    out_base.mkdir()
    scene_img = _solid(tmp_path, "scene.png", (120, 120, 120))
    imagegen.generate_background_layer(tmp_path, str(scene_img), "ab", ["요소1"],
                                       out_base=out_base, scene_size=None, style="STYLE")
    assert prompts
    assert "image_gen" not in prompts[0]
    assert "저장되면 OK" not in prompts[0]


def test_scene_key_color_falls_back_on_unreadable_image(tmp_path):
    """Finding 4: 씬 이미지가 읽을 수 없으면 마젠타 기본값으로 degrade하고 사이드카는 쓰지 않는다."""
    out_base = tmp_path / "layers"
    out_base.mkdir()
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    res = imagegen.scene_key_color(out_base, "ab", bad)
    assert res == {"key": "magenta", "rgb": [255, 0, 255], "coverage": {}}
    assert not (out_base / "ab__keycolor.json").is_file()
