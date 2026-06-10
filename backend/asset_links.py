"""프로젝트의 무거운 에셋 폴더(이미지/오디오/비디오 등)를 NAS로 심링크.

코드/깃/메타데이터(scenes.json·plan.md 등)는 로컬 유지, 생성 에셋만 NAS에 둔다.
심링크라 백엔드 쓰기·패널 file:// 미리보기 모두 투명하게 동작한다.
NAS 미마운트/쓰기 불가 시 graceful no-op(로컬 유지) — 작업 중단 없음.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

# NAS로 분리할 무거운 에셋 서브폴더(텍스트/메타데이터는 제외)
ASSET_SUBDIRS = ["images", "storyboard", "characters", "layers", "audio", "video_sources"]
DEFAULT_ROOT = "/Volumes/kairos/auto_kairos_adobe_assets"


def assets_root() -> Path | None:
    """에셋 NAS 루트. env AK_ASSETS_DIR 우선, 없으면 DEFAULT_ROOT.
    생성·쓰기 가능하면 Path, 불가(미마운트 등)면 None."""
    p = Path(os.environ.get("AK_ASSETS_DIR", DEFAULT_ROOT)).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
        t = p / ".ak_write_test"
        t.touch()
        t.unlink()
        return p
    except Exception:
        return None


def link_project_assets(proj_dir: Path, project_id: str | None = None) -> dict:
    """proj_dir의 에셋 서브폴더를 NAS로 심링크. 기존 로컬 내용은 NAS로 이동(무삭제).
    NAS 불가 시 {linked:[], skipped:...}. 멱등."""
    root = assets_root()
    if root is None:
        return {"linked": [], "skipped": "assets_root 사용 불가 — 로컬 유지"}
    pid = project_id or proj_dir.name
    base = root / pid
    base.mkdir(parents=True, exist_ok=True)
    linked = []
    for sub in ASSET_SUBDIRS:
        local = proj_dir / sub
        target = base / sub
        target.mkdir(parents=True, exist_ok=True)
        if local.is_symlink():
            continue                       # 이미 링크됨(멱등)
        if local.is_dir():
            for item in list(local.iterdir()):   # 기존 내용 NAS로 이동
                dest = target / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            shutil.rmtree(local)
        local.symlink_to(target, target_is_directory=True)
        linked.append(sub)
    return {"linked": linked, "root": str(base)}
