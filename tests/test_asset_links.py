from pathlib import Path
from backend import asset_links


def test_assets_root_from_env(monkeypatch, tmp_path):
    nas = tmp_path / "nas"
    monkeypatch.setenv("AK_ASSETS_DIR", str(nas))
    root = asset_links.assets_root()
    assert root == nas and nas.is_dir()


def test_assets_root_unavailable(monkeypatch):
    # 쓰기 불가 경로 → None(로컬 유지)
    monkeypatch.setenv("AK_ASSETS_DIR", "/proc/nonexistent_ak_assets_xyz")
    assert asset_links.assets_root() is None


def test_link_project_assets_migrates_and_links(monkeypatch, tmp_path):
    nas = tmp_path / "nas"; monkeypatch.setenv("AK_ASSETS_DIR", str(nas))
    proj = tmp_path / "projects" / "p1"; (proj / "images").mkdir(parents=True)
    (proj / "images" / "a.png").write_bytes(b"\x89PNG")     # 기존 로컬 에셋
    (proj / "plan.md").write_text("# t", encoding="utf-8")  # 메타데이터는 로컬 유지

    res = asset_links.link_project_assets(proj, "p1")
    assert "images" in res["linked"]
    # images는 이제 심링크, 내용은 NAS로 이동되어 심링크 통해 읽힘
    assert (proj / "images").is_symlink()
    assert (proj / "images" / "a.png").read_bytes() == b"\x89PNG"
    assert (nas / "p1" / "images" / "a.png").exists()
    # plan.md는 로컬 그대로
    assert (proj / "plan.md").is_file() and not (proj / "plan.md").is_symlink()


def test_link_project_assets_idempotent(monkeypatch, tmp_path):
    nas = tmp_path / "nas"; monkeypatch.setenv("AK_ASSETS_DIR", str(nas))
    proj = tmp_path / "p2"; proj.mkdir()
    asset_links.link_project_assets(proj, "p2")
    first = (proj / "images").resolve()
    res2 = asset_links.link_project_assets(proj, "p2")   # 두 번째 호출
    assert res2["linked"] == []                          # 이미 링크됨 → no-op
    assert (proj / "images").resolve() == first


def test_link_project_assets_noop_when_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("AK_ASSETS_DIR", "/proc/nonexistent_ak_assets_xyz")
    proj = tmp_path / "p3"; (proj / "images").mkdir(parents=True)
    res = asset_links.link_project_assets(proj, "p3")
    assert res["linked"] == [] and "skipped" in res
    assert (proj / "images").is_dir() and not (proj / "images").is_symlink()  # 로컬 유지
