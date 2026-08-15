from pathlib import Path

PANEL = Path(__file__).resolve().parents[1] / "cep" / "com.autokairos.pd"
JSX = PANEL / "jsx" / "build_scene.jsx"


def _src():
    return JSX.read_text(encoding="utf-8")


def test_no_per_scene_comp():
    """씬마다 컴프를 만들지 않는다 — 평면 컴프 하나."""
    src = _src()
    assert "proj.items.addComp" in src            # Final은 만든다
    assert src.count("proj.items.addComp") == 1   # 그 한 번뿐


def test_flat_helpers_exist():
    src = _src()
    for fn in ("function akFindOrMakeComp", "function akRemoveSceneGroup",
               "function akGroupAnchor", "function buildSceneGroup"):
        assert fn in src


def test_guide_null_created_and_named():
    src = _src()
    assert 's.prefix + "가이드"' in src
    assert "addNull" in src


def test_camera_targets_guide():
    """카메라는 가이드 널을 잡는다 — 씬 컴프 레이어가 아니다."""
    src = _src()
    assert "applyCamera(guide" in src
    assert "fc.layers.add(comps[" not in src


def test_layers_use_baked_coords_only():
    """jsx가 채움 스케일을 계산하지 않는다 — 좌표는 매니페스트가 굽는다."""
    src = _src()
    assert "Math.max(W / sw, H / sh)" not in src
    assert "layer.position" in src and "layer.scale" in src


def test_scene_time_applied():
    src = _src()
    assert "inPoint" in src and "outPoint" in src
    assert "startTime" in src            # 오디오


def test_bob_null_stays_in_group():
    """까딱까딱 널은 이름에 접두사가 붙고 레이어 바로 아래로 옮겨진다."""
    src = _src()
    assert "moveAfter" in src
    assert '"_피벗"' in src


def test_target_comp_is_final():
    src = _src()
    assert '"Final"' in src
    assert "app.project.activeItem" not in src


def test_no_skip_final():
    assert "skipFinal" not in _src()


def test_es5_only():
    src = _src()
    assert "=>" not in src
    assert "const " not in src and "let " not in src
    assert "`" not in src
