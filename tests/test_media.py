from backend import media


def test_list_media(tmp_path):
    p = tmp_path / "p"; p.mkdir()
    (p / "images").mkdir(); (p / "images" / "ref_1.png").write_bytes(b"\x89PNG")
    (p / "images" / "search").mkdir(); (p / "images" / "search" / "s.jpg").write_bytes(b"x")
    (p / "storyboard").mkdir(); (p / "storyboard" / "sb_1.png").write_bytes(b"x")
    (p / "video_sources").mkdir(); (p / "video_sources" / "v.mp4").write_bytes(b"x")
    items = media.list_media(p)
    rels = {i["rel"]: i["type"] for i in items}
    assert rels["images/ref_1.png"] == "image"
    assert rels["images/search/s.jpg"] == "image"
    assert rels["storyboard/sb_1.png"] == "image"
    assert rels["video_sources/v.mp4"] == "video"
    assert all(i["dir"] == str(p) for i in items)


def test_set_scene_image_copies_versioned(tmp_path):
    p = tmp_path / "p"; p.mkdir()
    (p / "scenes.json").write_text(
        '{"scenes":[{"sceneNumber":2,"sceneId":"sid22222","image_prompt":"x"}]}', encoding="utf-8")
    (p / "images").mkdir(); src = p / "images" / "pick.png"; src.write_bytes(b"\x89PNG")
    (p / "storyboard").mkdir(); (p / "storyboard" / "sb_sid22222.png").write_bytes(b"old")  # 기존
    res = media.set_scene_image(p, 2, "images/pick.png")
    assert res["status"] == "completed"
    assert res["rel"] == "storyboard/sb_sid22222_v2.png"   # sceneId 키 + 무삭제
    assert (p / "storyboard" / "sb_sid22222_v2.png").read_bytes() == b"\x89PNG"


def test_set_scene_image_rejects_traversal(tmp_path):
    p = tmp_path / "p"; p.mkdir()
    res = media.set_scene_image(p, 1, "../../etc/hosts")
    assert res["status"] == "failed"


def test_set_scene_image_missing_src(tmp_path):
    p = tmp_path / "p"; p.mkdir()
    res = media.set_scene_image(p, 1, "images/nope.png")
    assert res["status"] == "failed"
