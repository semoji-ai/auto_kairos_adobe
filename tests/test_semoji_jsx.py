from pathlib import Path

PANEL = Path(__file__).resolve().parents[1] / "cep" / "com.autokairos.pd"
JSX = PANEL / "jsx" / "build_scene.jsx"


def _src():
    return JSX.read_text(encoding="utf-8")


def test_stamp_branch():
    src = _src()
    assert 'mv.type === "stamp"' in src
    # 5프레임 내리찍기 — 스케일 시작 배율은 amount(기본 300)
    assert "300" in src


def test_wiggle_branch():
    src = _src()
    assert 'mv.type === "wiggle"' in src
    assert "wiggle(" in src


def test_source_caption_function():
    src = _src()
    assert "function addSourceCaption" in src
    assert '"출처"' in src and '"출처판"' in src


def test_source_caption_not_parented_to_guide():
    """출처 자막은 카메라 줌에 딸려가면 안 된다 — 가이드 미페어런팅.
    addSourceCaption 함수 본문에 guide/parent 참조가 없어야 한다."""
    src = _src()
    body = src.split("function addSourceCaption")[1].split("\n    function ")[0]
    assert "parent = guide" not in body
    assert ".parent =" not in body or "textL.parent = plate" in body


def test_source_caption_called_in_build():
    src = _src()
    assert "addSourceCaption(comp, s" in src


def test_es5_only():
    src = _src()
    assert "=>" not in src and "const " not in src and "let " not in src and "`" not in src
