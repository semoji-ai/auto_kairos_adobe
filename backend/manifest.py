"""scenes.json + 에셋 → AE build_scene.jsx 용 manifest.json(레이어 스택 포함)."""
from __future__ import annotations

import json
from pathlib import Path

from backend import scenes, tts

W, H, FPS = 1920, 1080, 30
DEFAULT_DUR = 3.0


def _abs(proj_dir: Path, rel: str) -> str:
    return str((proj_dir / rel).resolve())


def _img_size(path: Path):
    """이미지 픽셀 크기 (w, h). 실패 시 None."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.width, im.height
    except Exception:
        return None


def _scene_layers(proj_dir: Path, layer_rels: list) -> list:
    """[{name, path(abs), kind, foot?}] — 배경(__bg)을 맨 앞(AE 최하단)으로.
    레이어는 풀프레임(요소가 제 위치에 그려진 투명 PNG) — 컴프 크기를 이미지에 맞추면 1:1·중앙으로 정확히 겹침.
    foot = 알파(불투명) 영역의 하단 중앙 [x, y] — 까딱 모션의 피벗(전신=발, 상반신=절단점)."""
    out = []
    bg = [r for r in layer_rels if "__bg" in Path(r).name]
    el = [r for r in layer_rels if "__bg" not in Path(r).name]
    for r in bg + el:
        entry = {"name": Path(r).stem, "path": _abs(proj_dir, r),
                 "kind": "bg" if "__bg" in Path(r).name else "element"}
        if entry["kind"] == "element":
            foot = _alpha_foot(proj_dir / r)
            if foot:
                entry["foot"] = foot
        out.append(entry)
    return out


def _alpha_foot(path: Path) -> list | None:
    """불투명 영역 bbox의 하단 중앙 [x, y](레이어=컴프 좌표). 전부 투명/실패 시 None."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            bbox = im.convert("RGBA").getchannel("A").getbbox()
        if not bbox:
            return None
        l, t, r, b = bbox
        return [round((l + r) / 2, 1), float(b)]
    except Exception:
        return None


def build_manifest(proj_dir: Path, only_scene: int | None = None) -> dict:
    """manifest.json 생성. only_scene 지정 시 그 씬만(manifest_scene_{n}.json). 반환 {path, scenes}."""
    proj_dir = Path(proj_dir)
    data = scenes.load_scenes(proj_dir)
    out_scenes = []
    for s in data.get("scenes", []):
        if only_scene is not None and s.get("sceneNumber") != only_scene:
            continue
        sid = s.get("sceneId")
        audio = _abs(proj_dir, s["_audio"]) if s.get("_audio") else None
        if audio:
            dur = tts.audio_duration(proj_dir / s["_audio"]) or DEFAULT_DUR
        else:
            dur = float(s.get("duration_estimate_sec") or DEFAULT_DUR)
        # 씬 컴프 크기 = 씬 이미지 크기 → 풀프레임 레이어가 1:1·중앙으로 정확히 겹침(위치 보존)
        size = _img_size(proj_dir / s["_image"]) if s.get("_image") else None
        sw, sh = size if size else (W, H)
        layers = _scene_layers(proj_dir, s.get("_layers") or [])
        cam = None
        mp = proj_dir / f"motion_{sid}.json"
        if mp.is_file():
            try:
                mo = json.loads(mp.read_text(encoding="utf-8"))
                moves_by = {L.get("layer"): L.get("moves", []) for L in mo.get("layers", [])}
                for entry in layers:
                    mv = moves_by.get(entry["name"])
                    if mv:
                        entry["moves"] = mv
                c = mo.get("camera") or {}
                if c.get("type") and c["type"] != "none":
                    cam = c
            except Exception:
                cam = None
        out_scenes.append({
            "ae_comp_name": f"S{s.get('sceneNumber'):02d}_{sid}",
            "width": sw, "height": sh,
            "image": _abs(proj_dir, s["_image"]) if s.get("_image") else None,
            "layers": layers,
            "audio": audio,
            "subtitle": s.get("narration", "") or "",
            "duration": dur,
            **({"camera": cam} if cam else {}),
        })
    mf = {"width": W, "height": H, "fps": FPS, "scenes": out_scenes}
    out = proj_dir / (f"manifest_scene_{only_scene}.json" if only_scene is not None else "manifest.json")
    out.write_text(json.dumps(mf, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(out), "scenes": len(out_scenes)}
