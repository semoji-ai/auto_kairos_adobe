"""scenes.json + 에셋 → AE build_scene.jsx 용 manifest.json(레이어 스택 포함)."""
from __future__ import annotations

import json
from pathlib import Path

from backend import scenes, tts

W, H, FPS = 1920, 1080, 30
DEFAULT_DUR = 3.0


def _abs(proj_dir: Path, rel: str) -> str:
    return str((proj_dir / rel).resolve())


def _scene_layers(proj_dir: Path, layer_rels: list) -> list:
    """[{name, path(abs), kind}] — 배경(__bg)을 맨 앞(AE 최하단)으로."""
    out = []
    bg = [r for r in layer_rels if "__bg" in Path(r).name]
    el = [r for r in layer_rels if "__bg" not in Path(r).name]
    for r in bg + el:
        out.append({"name": Path(r).stem, "path": _abs(proj_dir, r),
                    "kind": "bg" if "__bg" in Path(r).name else "element"})
    return out


def build_manifest(proj_dir: Path) -> dict:
    """manifest.json 생성. 반환 {path, scenes}."""
    proj_dir = Path(proj_dir)
    data = scenes.load_scenes(proj_dir)
    out_scenes = []
    for s in data.get("scenes", []):
        sid = s.get("sceneId")
        layers = _scene_layers(proj_dir, s.get("_layers") or [])
        audio = _abs(proj_dir, s["_audio"]) if s.get("_audio") else None
        if audio:
            dur = tts.audio_duration(proj_dir / s["_audio"]) or DEFAULT_DUR
        else:
            dur = float(s.get("duration_estimate_sec") or DEFAULT_DUR)
        out_scenes.append({
            "ae_comp_name": f"S{s.get('sceneNumber'):02d}_{sid}",
            "image": _abs(proj_dir, s["_image"]) if s.get("_image") else None,
            "layers": layers,
            "audio": audio,
            "subtitle": s.get("narration", "") or "",
            "duration": dur,
        })
    mf = {"width": W, "height": H, "fps": FPS, "scenes": out_scenes}
    out = proj_dir / "manifest.json"
    out.write_text(json.dumps(mf, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(out), "scenes": len(out_scenes)}
