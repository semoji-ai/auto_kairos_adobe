"""scenes.json 조회/수정 — 미디어·레이어 경로 enrich, 나레이션 편집(무삭제)."""
from __future__ import annotations

import json
from pathlib import Path


def _path(proj_dir: Path) -> Path:
    return proj_dir / "scenes.json"


def _latest_image(sb_dir: Path, n) -> str | None:
    """storyboard/sb_{n}.png 및 버전(sb_{n}_v2.png …) 중 최신.
    버전 번호로 숫자 정렬(사전식이면 v10이 v2보다 앞서는 버그)."""
    if not sb_dir.is_dir():
        return None
    files: list[tuple[str, int]] = []
    if (sb_dir / f"sb_{n}.png").exists():
        files.append((f"sb_{n}.png", 0))
    for p in sb_dir.glob(f"sb_{n}_v*.png"):
        try:
            files.append((p.name, int(p.name.split("_v")[1].split(".")[0])))
        except (IndexError, ValueError):
            pass
    if not files:
        return None
    files.sort(key=lambda x: x[1])
    return f"storyboard/{files[-1][0]}"


def load_scenes(proj_dir: Path) -> dict:
    """scenes.json 로드 + 각 씬에 _image(최신 씬 이미지)·_layers 부여. dir=프로젝트 절대경로."""
    fp = _path(proj_dir)
    if not fp.is_file():
        return {"scenes": [], "dir": ""}
    data = json.loads(fp.read_text(encoding="utf-8"))
    sb_dir, lay_dir = proj_dir / "storyboard", proj_dir / "layers"
    for s in data.get("scenes", []):
        n = s.get("sceneNumber")
        s["_image"] = _latest_image(sb_dir, n)
        s["_layers"] = [f"layers/{nm}" for nm in (f"bg_{n}.png", f"char_{n}.png")
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
