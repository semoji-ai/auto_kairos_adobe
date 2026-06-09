"""scenes.json 조회/수정 — sceneId 기반 에셋, 미디어·레이어 enrich, 나레이션 편집(무삭제)."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path


def _path(proj_dir: Path) -> Path:
    return proj_dir / "scenes.json"


def _new_sid() -> str:
    return uuid.uuid4().hex[:8]


def _migrate_assets(proj_dir: Path, old_key, sid: str) -> None:
    """번호 기반 에셋(sb_{old}/bg_{old}/char_{old})을 sid 기반으로 복사(무삭제·멱등)."""
    sb, lay = proj_dir / "storyboard", proj_dir / "layers"
    if sb.is_dir():
        for p in list(sb.glob(f"sb_{old_key}.png")) + list(sb.glob(f"sb_{old_key}_v*.png")):
            tgt = sb / p.name.replace(f"sb_{old_key}", f"sb_{sid}", 1)
            if not tgt.exists():
                shutil.copy(p, tgt)
    if lay.is_dir():
        for nm in (f"bg_{old_key}.png", f"char_{old_key}.png"):
            src = lay / nm
            tgt = lay / nm.replace(f"_{old_key}.", f"_{sid}.", 1)
            if src.exists() and not tgt.exists():
                shutil.copy(src, tgt)


def ensure_scene_ids(proj_dir: Path) -> dict:
    """모든 씬에 sceneId 보장(없으면 발급). 신규 발급 시 번호 기반 에셋을 sid로 복사 마이그레이션.
    변경 시 scenes.json 저장. 멱등. 반환=data."""
    fp = _path(proj_dir)
    if not fp.is_file():
        return {"scenes": []}
    data = json.loads(fp.read_text(encoding="utf-8"))
    changed = False
    for s in data.get("scenes", []):
        if not s.get("sceneId"):
            sid = _new_sid()
            s["sceneId"] = sid
            _migrate_assets(proj_dir, s.get("sceneNumber"), sid)
            changed = True
    if changed:
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def scene_id_for(proj_dir: Path, scene_number) -> str | None:
    data = ensure_scene_ids(proj_dir)
    for s in data.get("scenes", []):
        if s.get("sceneNumber") == scene_number:
            return s.get("sceneId")
    return None


def _latest_image(sb_dir: Path, sid: str) -> str | None:
    """storyboard/sb_{sid}.png 및 버전(sb_{sid}_v2.png …) 중 최신(버전 번호 숫자 정렬)."""
    if not sb_dir.is_dir() or not sid:
        return None
    files: list[tuple[str, int]] = []
    if (sb_dir / f"sb_{sid}.png").exists():
        files.append((f"sb_{sid}.png", 0))
    for p in sb_dir.glob(f"sb_{sid}_v*.png"):
        try:
            files.append((p.name, int(p.name.split("_v")[1].split(".")[0])))
        except (IndexError, ValueError):
            pass
    if not files:
        return None
    files.sort(key=lambda x: x[1])
    return f"storyboard/{files[-1][0]}"


def load_scenes(proj_dir: Path) -> dict:
    """sceneId 보장 후 각 씬에 _image(최신)·_layers(sid 기반) 부여. dir=프로젝트 절대경로."""
    fp = _path(proj_dir)
    if not fp.is_file():
        return {"scenes": [], "dir": ""}
    data = ensure_scene_ids(proj_dir)
    sb_dir, lay_dir = proj_dir / "storyboard", proj_dir / "layers"
    for s in data.get("scenes", []):
        sid = s.get("sceneId")
        s["_image"] = _latest_image(sb_dir, sid)
        s["_layers"] = [f"layers/{nm}" for nm in (f"bg_{sid}.png", f"char_{sid}.png")
                        if (lay_dir / nm).exists()]
    data["dir"] = str(proj_dir)
    return data


def update_narration(proj_dir: Path, scene_number: int, narration: str) -> dict:
    """씬 나레이션 수정 + narration_dirty=True 저장. {ok, sceneNumber} 또는 {error}."""
    fp = _path(proj_dir)
    if not fp.is_file():
        return {"error": "scenes.json 없음"}
    data = json.loads(fp.read_text(encoding="utf-8"))
    for s in data.get("scenes", []):
        if s.get("sceneNumber") == scene_number:
            s["narration"] = narration
            s["narration_dirty"] = True
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"ok": True, "sceneNumber": scene_number}
    return {"error": f"scene {scene_number} 없음"}
