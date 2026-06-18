from pathlib import Path
from backend import sheets


def test_looks_from_visual_joins_fields():
    looks = sheets._looks_from_visual({"hair": "갈색 단발", "outfit": "노란 셔츠", "appearance": "둥근 얼굴"})
    assert "갈색 단발" in looks and "노란 셔츠" in looks
    assert sheets._looks_from_visual({}) == "원본 그대로"


def test_character_prompt_keeps_layout_and_name():
    p = sheets.build_character_sheet_prompt("하루", {"hair": "검은 머리", "expressions": ["미소", "놀람"]}, "references/characters/char-1.png")
    assert "하루" in p
    assert "유지" in p and "헤어" in p
    assert "references/characters/char-1.png" in p
    assert "미소" in p


def test_location_prompt_six_panels_no_person():
    p = sheets.build_location_sheet_prompt("거실", {"space": "아파트 거실", "mood": "따뜻함", "lighting": "오후"}, "references/locations/loc-1.png")
    assert "6패널" in p or "6" in p
    assert "인물" in p  # 인물 금지 문구
    assert "거실" in p


def test_prop_prompt_four_views_no_person():
    p = sheets.build_prop_sheet_prompt("포스트잇", {"form": "사각 메모지", "material": "종이", "color": "노랑"}, "references/props/prop-1.png")
    assert "4" in p
    assert "인물" in p
    assert "포스트잇" in p


def test_base_sheet_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(sheets, "_BASE_SHEET", tmp_path / "nope.png")
    assert sheets.base_sheet() is None
    (tmp_path / "yes.png").write_bytes(b"x")
    monkeypatch.setattr(sheets, "_BASE_SHEET", tmp_path / "yes.png")
    assert sheets.base_sheet() == tmp_path / "yes.png"
