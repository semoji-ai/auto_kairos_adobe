import json
from pathlib import Path

from backend import manifest

SID = "abc123"


def _layers(tmp_path: Path, specs, files):
    lay = tmp_path / "layers"
    lay.mkdir(parents=True)
    for name in files:
        (lay / name).write_bytes(b"x")
    (lay / f"{SID}__elements.json").write_text(
        json.dumps(specs, ensure_ascii=False), encoding="utf-8")
    return [f"layers/{n}" for n in files if n.endswith(".png")]


def _spec(i, name, **kw):
    d = {"layer": f"{SID}__{i}_{name}", "index": i, "name": name, "name_en": name,
         "location": "", "kind": "object", "intent": "", "z": i + 1}
    d.update(kw)
    return d


def test_removed_layer_is_excluded(tmp_path):
    rels = _layers(tmp_path, [_spec(0, "car"), _spec(1, "tree", removed=True)],
                   [f"{SID}__bg.png", f"{SID}__0_car.png", f"{SID}__1_tree.png"])
    out = manifest._scene_layers(tmp_path, rels, SID)
    names = [e["name"] for e in out]
    assert f"{SID}__1_tree" not in names
    assert f"{SID}__0_car" in names


def test_hidden_layer_is_included(tmp_path):
    """hidden은 패널 미리보기 전용 — AE에는 그대로 들어간다."""
    rels = _layers(tmp_path, [_spec(0, "car", hidden=True)],
                   [f"{SID}__bg.png", f"{SID}__0_car.png"])
    out = manifest._scene_layers(tmp_path, rels, SID)
    assert f"{SID}__0_car" in [e["name"] for e in out]


def test_svg_preferred_when_present(tmp_path):
    rels = _layers(tmp_path, [_spec(0, "car")],
                   [f"{SID}__bg.png", f"{SID}__0_car.png", f"{SID}__0_car.svg"])
    out = manifest._scene_layers(tmp_path, rels, SID)
    car = next(e for e in out if e["name"] == f"{SID}__0_car")
    assert car["path"].endswith(".svg")
    assert car["vector"] is True


def test_png_used_when_no_svg(tmp_path):
    rels = _layers(tmp_path, [_spec(0, "car")], [f"{SID}__bg.png", f"{SID}__0_car.png"])
    out = manifest._scene_layers(tmp_path, rels, SID)
    car = next(e for e in out if e["name"] == f"{SID}__0_car")
    assert car["path"].endswith(".png")
    assert "vector" not in car


def test_background_svg_also_preferred(tmp_path):
    rels = _layers(tmp_path, [_spec(0, "car")],
                   [f"{SID}__bg.png", f"{SID}__bg.svg", f"{SID}__0_car.png"])
    out = manifest._scene_layers(tmp_path, rels, SID)
    bg = out[0]
    assert bg["kind"] == "bg"
    assert bg["path"].endswith(".svg")
    assert bg["vector"] is True


def test_removed_background_still_included(tmp_path):
    """배경에 removed가 잘못 기록돼도 배경은 빠지지 않는다 — 빠지면 합성이 무너진다."""
    rels = _layers(tmp_path, [_spec(0, "car"),
                              {"layer": f"{SID}__bg", "removed": True}],
                   [f"{SID}__bg.png", f"{SID}__0_car.png"])
    out = manifest._scene_layers(tmp_path, rels, SID)
    assert out[0]["kind"] == "bg"
