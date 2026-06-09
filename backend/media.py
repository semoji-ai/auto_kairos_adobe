"""프로젝트 미디어 목록 + 갤러리→씬 이미지 적용(무삭제, 트래버설 방지)."""
from __future__ import annotations

import shutil
from pathlib import Path

from backend.imagegen import versioned_path

_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_VID_EXT = {".mp4", ".mov", ".webm", ".m4v"}
_MEDIA_DIRS = ["images", "images/search", "storyboard", "characters", "layers", "video_sources"]


def list_media(proj_dir: Path) -> list[dict]:
    """프로젝트 미디어 폴더의 이미지/비디오 파일 목록. [{name, rel, type, dir}]."""
    out: list[dict] = []
    for sub in _MEDIA_DIRS:
        d = proj_dir / sub
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            kind = "image" if ext in _IMG_EXT else ("video" if ext in _VID_EXT else None)
            if not kind:
                continue
            out.append({"name": f.name, "rel": f.relative_to(proj_dir).as_posix(),
                        "type": kind, "dir": str(proj_dir)})
    return out


def set_scene_image(proj_dir: Path, scene_number, src_rel: str) -> dict:
    """proj/src_rel 이미지를 storyboard/sb_{sceneId}.png 로 복사(무삭제 버전). 트래버설 방지."""
    from backend import scenes  # 지연 임포트(순환 방지)
    sid = scenes.scene_id_for(proj_dir, scene_number)
    if not sid:
        return {"status": "failed", "error": f"scene {scene_number} 없음"}
    src = (proj_dir / src_rel).resolve()
    if not src.is_relative_to(proj_dir.resolve()):
        return {"status": "failed", "error": "잘못된 경로"}
    if not src.is_file():
        return {"status": "failed", "error": f"소스 없음: {src_rel}"}
    sb = proj_dir / "storyboard"
    sb.mkdir(parents=True, exist_ok=True)
    dest = versioned_path(sb, f"sb_{sid}.png")
    shutil.copy(src, dest)
    return {"status": "completed", "path": str(dest),
            "rel": dest.relative_to(proj_dir).as_posix()}
