"""v3 프로젝트(output/{uuid}_{slug}) → adobe 프로젝트 가져오기.
scene_specs 구(visualization.creative 중첩)/신(플랫) 스키마 양쪽 허용. 무삭제 — v3 원본은 읽기만."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from backend import scenes

FPS = 30


def _visual_summary(s: dict) -> str:
    viz = s.get("visualization") or {}
    cre = viz.get("creative") or {}
    return (s.get("visual_summary") or cre.get("concept") or s.get("headline")
            or viz.get("concept") or "")


def _image_prompt(s: dict) -> str:
    ia = s.get("imageAsset") or {}
    return (ia.get("prompt") or ia.get("query") or s.get("image_prompt") or "")


def _map_scene(s: dict) -> dict:
    out = {
        "sceneNumber": s.get("sceneNumber"),
        "title": s.get("title", "") or "",
        "narration": s.get("narration", "") or "",
        "visual_summary": _visual_summary(s),
        "image_prompt": _image_prompt(s),
        "characters": s.get("characters") or [],
        "imageRef": "",
    }
    if s.get("narration_tts"):
        out["narration_tts"] = s["narration_tts"]
    if s.get("durationFrames"):
        out["duration_estimate_sec"] = round(float(s["durationFrames"]) / FPS, 2)
    elif s.get("duration_estimate_sec"):
        out["duration_estimate_sec"] = s["duration_estimate_sec"]
    return out


def import_v3(root: Path, v3_dir, title: str | None = None) -> dict:
    """v3 출력 폴더에서 adobe 프로젝트 생성. 반환 {project_id, scenes, images} 또는 {error}."""
    v3 = Path(v3_dir)
    specs = v3 / "scene_specs.json"
    if not specs.is_file():
        return {"error": f"scene_specs.json 없음: {v3}"}
    try:
        data = json.loads(specs.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"scene_specs 파싱 실패: {e}"}
    src_scenes = data.get("scenes") or []
    if not src_scenes:
        return {"error": "scenes 비어있음"}

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    pid = uuid.uuid4().hex[:8]
    d = root / pid
    d.mkdir(parents=True, exist_ok=False)
    name = title or data.get("topic") or v3.name.split("_", 1)[-1]
    (d / "plan.md").write_text(f"# {name}\n\n(v3 가져오기: {v3.name})\n", encoding="utf-8")

    mapped = [_map_scene(s) for s in src_scenes]
    (d / "scenes.json").write_text(json.dumps({"scenes": mapped}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    scenes.ensure_scene_ids(d)          # sceneId 발급 + imageRef 백필

    man = v3 / "final_manuscript.md"
    if man.is_file():
        shutil.copy(man, d / "final_manuscript.md")

    # 기존 씬 이미지 복사(있으면): v3 images/scene_{n:03d}.* → storyboard/ + imageRef
    copied = 0
    img_dir = v3 / "images"
    if img_dir.is_dir():
        cur = scenes.load_scenes(d)
        for s in cur["scenes"]:
            n = s.get("sceneNumber")
            if not isinstance(n, int):
                continue
            for ext in ("png", "jpg", "jpeg", "webp"):
                src = img_dir / f"scene_{n:03d}.{ext}"
                if src.is_file():
                    sb = d / "storyboard"; sb.mkdir(exist_ok=True)
                    dst = sb / f"sb_{s['sceneId']}.png"
                    if ext == "png":
                        shutil.copy(src, dst)
                    else:
                        from PIL import Image
                        Image.open(src).convert("RGB").save(dst)
                    scenes.set_image_ref(d, n, f"storyboard/{dst.name}")
                    copied += 1
                    break
    return {"project_id": pid, "title": name, "scenes": len(mapped), "images": copied}
