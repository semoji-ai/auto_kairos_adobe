from pathlib import Path
from backend import imagegen


def test_versioned_path_first(tmp_path):
    p = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p.name == "ref_1.png"


def test_versioned_path_no_overwrite(tmp_path):
    (tmp_path / "ref_1.png").write_text("x", encoding="utf-8")
    p = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p.name == "ref_1_v2.png"
    (tmp_path / "ref_1_v2.png").write_text("x", encoding="utf-8")
    p2 = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p2.name == "ref_1_v3.png"


def test_is_rate_limited():
    assert imagegen.is_rate_limited("image_gen rate limit으로 실패") is True
    assert imagegen.is_rate_limited("OK 저장 완료") is False


def test_build_image_prompt():
    pr = imagegen.build_image_prompt("전기차 한 대", "STYLE_DESC", "images/ref_1.png")
    assert "STYLE_DESC" in pr
    assert "전기차 한 대" in pr
    assert "images/ref_1.png" in pr
    assert "image_gen" in pr


def test_versioned_path_in_subdir_concept(tmp_path):
    sb = tmp_path / "storyboard"; sb.mkdir()
    p = imagegen.versioned_path(sb, "sb_1.png")
    assert p.parent.name == "storyboard"
    assert p.name == "sb_1.png"


def test_generate_many_runs_all(tmp_path, monkeypatch):
    from backend import imagegen as ig
    calls = []

    def fake_one(proj_dir, rel_out, image_prompt, *, subdir="images", **kw):
        calls.append(rel_out)
        out = proj_dir / subdir / rel_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "generate_one", fake_one)
    items = [("a.png", "p1"), ("b.png", "p2"), ("c.png", "p3")]
    results = ig.generate_many(tmp_path, items, subdir="storyboard", concurrency=3)
    assert len(results) == 3
    assert all(r["status"] == "completed" for r in results.values())
    assert set(calls) == {"a.png", "b.png", "c.png"}


def test_generate_many_concurrency_min_one(tmp_path, monkeypatch):
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "generate_one",
                        lambda proj_dir, rel_out, p, **kw: {"status": "completed", "path": rel_out})
    results = ig.generate_many(tmp_path, [("a.png", "p")], concurrency=0)
    assert len(results) == 1


def test_chroma_key_magenta(tmp_path):
    from PIL import Image
    from backend import imagegen
    im = Image.new("RGBA", (4, 2), (255, 0, 255, 255))
    for y in range(2):
        im.putpixel((2, y), (30, 60, 200, 255))
        im.putpixel((3, y), (30, 60, 200, 255))
    src = tmp_path / "m.png"; im.save(src)
    out = tmp_path / "t.png"
    res = imagegen.chroma_key_magenta(src, out)
    from PIL import Image as I
    r = I.open(out).convert("RGBA")
    assert r.getpixel((0, 0))[3] == 0
    assert r.getpixel((3, 0))[3] == 255
    assert res["transparent_ratio"] > 0.4
