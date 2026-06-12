import json
from pathlib import Path
from backend import v3_import


def _mk_v3(tmp_path, scenes, manuscript="원고 본문"):
    v3 = tmp_path / "uuid1234_slug"; v3.mkdir()
    (v3 / "scene_specs.json").write_text(json.dumps({"scenes": scenes}, ensure_ascii=False), encoding="utf-8")
    (v3 / "final_manuscript.md").write_text(manuscript, encoding="utf-8")
    return v3


def test_import_v3_flat_schema(tmp_path):
    root = tmp_path / "projects"; root.mkdir()
    v3 = _mk_v3(tmp_path, [{
        "sceneNumber": 1, "title": "기원", "narration": "내레이션",
        "narration_tts": "발음 교정본", "durationFrames": 150,
        "headline": "헤드라인", "imageAsset": {"source": "generate", "prompt": "전기차 작업실"}}])
    res = v3_import.import_v3(root, v3)
    pid = res["project_id"]
    d = root / pid
    sc = json.loads((d / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]
    assert sc["narration"] == "내레이션" and sc["narration_tts"] == "발음 교정본"
    assert sc["image_prompt"] == "전기차 작업실"
    assert sc["duration_estimate_sec"] == 5.0          # 150/30
    assert sc["sceneId"]                               # ensure_scene_ids 적용
    assert (d / "final_manuscript.md").read_text(encoding="utf-8") == "원고 본문"
    assert res["scenes"] == 1


def test_import_v3_nested_creative(tmp_path):
    root = tmp_path / "projects"; root.mkdir()
    v3 = _mk_v3(tmp_path, [{
        "sceneNumber": 1, "title": "t", "narration": "n",
        "visualization": {"creative": {"concept": "콘셉트 요약"}},
        "imageAsset": {"source": "search", "query": "tesla factory"}}])
    res = v3_import.import_v3(root, v3)
    sc = json.loads((root / res["project_id"] / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]
    assert sc["visual_summary"] == "콘셉트 요약"
    assert sc["image_prompt"] == "tesla factory"        # search query도 프롬프트로


def test_import_v3_missing_specs(tmp_path):
    root = tmp_path / "projects"; root.mkdir()
    empty = tmp_path / "none"; empty.mkdir()
    res = v3_import.import_v3(root, empty)
    assert "error" in res


def test_import_v3_reuses_images(tmp_path):
    root = tmp_path / "projects"; root.mkdir()
    v3 = _mk_v3(tmp_path, [{"sceneNumber": 1, "title": "t", "narration": "n"}])
    img_dir = v3 / "images"; img_dir.mkdir()
    # 최소 유효 PNG 생성
    import struct, zlib
    raw = b"\x00\xff\x00\x00"
    png = (b"\x89PNG\r\n\x1a\n"
           + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    import binascii
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    chunks = b"\x89PNG\r\n\x1a\n"
    for tag, payload in ((b"IHDR", ihdr), (b"IDAT", zlib.compress(raw)), (b"IEND", b"")):
        chunks += struct.pack(">I", len(payload)) + tag + payload
        chunks += struct.pack(">I", binascii.crc32(tag + payload) & 0xFFFFFFFF)
    (img_dir / "scene_001.png").write_bytes(chunks)
    res = v3_import.import_v3(root, v3)
    assert res["images"] == 1
    d = root / res["project_id"]
    sc = json.loads((d / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]
    assert sc["imageRef"].startswith("storyboard/sb_")
    assert (d / sc["imageRef"]).is_file()
