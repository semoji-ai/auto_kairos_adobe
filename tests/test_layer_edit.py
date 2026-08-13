"""레이어 낱개 삭제·재생성 — 사이드카 왕복, _prev 보존, 배경 재생성 대상."""
import json

import pytest

from backend import imagegen


def _layers_dir(tmp_path):
    d = tmp_path / "layers"
    d.mkdir(parents=True)
    return d


def _touch(d, name):
    (d / name).write_bytes(b"\x89PNG")
    return d / name


def test_write_and_load_element_specs(tmp_path):
    d = _layers_dir(tmp_path)
    specs = [{"layer": "ab__0_인물_char", "index": 0, "name": "왼쪽 인물",
              "location": "화면 좌측", "kind": "character"}]
    imagegen.write_element_specs(d, "ab", specs)
    assert (d / "ab__elements.json").is_file()
    assert imagegen.load_element_specs(d, "ab") == specs


def test_load_element_specs_recovers_from_filenames(tmp_path):
    """사이드카 없는 옛 프로젝트 — 파일명 + kinds.json으로 복원(location만 빈다)."""
    d = _layers_dir(tmp_path)
    _touch(d, "ab__0_왼쪽_인물_char.png")
    _touch(d, "ab__1_탁자.png")
    _touch(d, "ab__bg.png")                      # 배경은 요소가 아님
    (d / "ab__kinds.json").write_text(json.dumps({"ab__0_왼쪽_인물_char": "character"}),
                                      encoding="utf-8")
    specs = imagegen.load_element_specs(d, "ab")
    assert [s["index"] for s in specs] == [0, 1]
    assert specs[0]["kind"] == "character" and specs[1]["kind"] == "object"
    assert specs[0]["name"] == "왼쪽 인물" and specs[0]["location"] == ""


def test_is_background_layer():
    assert imagegen.is_background_layer("layers/ab__bg.png") is True
    assert imagegen.is_background_layer("ab__bg_v2") is True
    assert imagegen.is_background_layer("ab__0_인물.png") is False


def test_delete_layer_moves_to_prev_and_updates_sidecars(tmp_path):
    d = _layers_dir(tmp_path)
    _touch(d, "ab__0_인물.png")
    _touch(d, "ab__1_탁자.png")
    imagegen.write_element_specs(d, "ab", [
        {"layer": "ab__0_인물", "index": 0, "name": "인물", "location": "좌측", "kind": "character"},
        {"layer": "ab__1_탁자", "index": 1, "name": "탁자", "location": "중앙", "kind": "object"}])
    (d / "ab__kinds.json").write_text(json.dumps({"ab__0_인물": "character",
                                                  "ab__1_탁자": "object"}), encoding="utf-8")

    res = imagegen.delete_layer(tmp_path, "ab", "layers/ab__1_탁자.png")
    assert res["ok"] and res["removed"] == "ab__1_탁자"
    assert res["remaining_names"] == ["인물"]           # 배경 재생성에 쓸 목록
    assert not (d / "ab__1_탁자.png").exists()          # 활성 폴더에서 사라짐
    assert (d / "_prev" / "ab__1_탁자.png").is_file()   # 지우지 않고 보존
    assert [s["layer"] for s in imagegen.load_element_specs(d, "ab")] == ["ab__0_인물"]
    assert json.loads((d / "ab__kinds.json").read_text(encoding="utf-8")) == {"ab__0_인물": "character"}


def test_delete_layer_rejects_background_and_missing(tmp_path):
    d = _layers_dir(tmp_path)
    _touch(d, "ab__bg.png")
    assert "error" in imagegen.delete_layer(tmp_path, "ab", "ab__bg")
    assert (d / "ab__bg.png").is_file()                # 배경은 그대로
    assert "error" in imagegen.delete_layer(tmp_path, "ab", "ab__9_없음")


def test_regenerate_background_uses_remaining_names(tmp_path, monkeypatch):
    """요소를 지운 뒤 배경을 다시 만들면, 지운 요소는 제거 목록에서 빠져 배경에 남는다."""
    d = _layers_dir(tmp_path)
    _touch(d, "ab__bg.png")
    imagegen.write_element_specs(d, "ab", [
        {"layer": "ab__0_인물", "index": 0, "name": "인물", "location": "좌측", "kind": "character"}])
    seen = {}

    def _fake(proj_dir, out, prompt, images=None, post=None):
        seen["prompt"] = prompt
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(imagegen, "_run_fal_image", _fake)
    monkeypatch.setattr(imagegen, "load_style", lambda: "STYLE")
    monkeypatch.setattr(imagegen, "_scene_size", lambda p: None)

    res = imagegen.regenerate_layer(tmp_path, str(tmp_path / "scene.png"), "ab", "ab__bg")
    assert res["layer"]["status"] == "completed"
    assert "인물" in seen["prompt"]                     # 남은 요소는 계속 제거 대상
    assert "탁자" not in seen["prompt"]                 # 지운 요소는 배경에 남아야 하므로 빠짐
    assert (d / "_prev" / "ab__bg.png").is_file()       # 이전 배경은 보존


def test_regenerate_element_only_touches_that_layer(tmp_path, monkeypatch):
    from PIL import Image
    Image.new("RGB", (10, 10)).save(tmp_path / "scene.png")   # scene_key_color가 실제로 열 수 있어야 함
    d = _layers_dir(tmp_path)
    _touch(d, "ab__0_인물.png")
    _touch(d, "ab__1_탁자.png")
    _touch(d, "ab__bg.png")
    imagegen.write_element_specs(d, "ab", [
        {"layer": "ab__0_인물", "index": 0, "name": "인물", "location": "좌측", "kind": "object"},
        {"layer": "ab__1_탁자", "index": 1, "name": "탁자", "location": "중앙", "kind": "object"}])

    def _fake(proj_dir, out, prompt, images=None, post=None):
        out.write_bytes(b"\x89PNG")
        if post:
            post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(imagegen, "_run_fal_image", _fake)
    monkeypatch.setattr(imagegen, "load_style", lambda: "STYLE")
    monkeypatch.setattr(imagegen, "_scene_size", lambda p: None)
    monkeypatch.setattr(imagegen, "flatten_colors", lambda p: True)
    monkeypatch.setattr(imagegen, "chroma_key", lambda a, b, key=None: {"transparent_ratio": 0.5})
    monkeypatch.setattr(imagegen, "position_score", lambda a, b: 0.9)

    res = imagegen.regenerate_layer(tmp_path, str(tmp_path / "scene.png"), "ab", "ab__0_인물")
    assert res["layer"]["status"] == "completed"
    assert (d / "ab__1_탁자.png").is_file()             # 다른 요소는 그대로
    assert (d / "ab__bg.png").is_file()                 # 배경도 그대로


def test_regenerate_missing_spec_errors(tmp_path):
    _layers_dir(tmp_path)
    res = imagegen.regenerate_layer(tmp_path, str(tmp_path / "scene.png"), "ab", "ab__7_없음")
    assert "error" in res
