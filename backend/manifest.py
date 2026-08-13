"""scenes.json + 에셋 → AE build_scene.jsx 용 manifest.json(레이어 스택 포함)."""
from __future__ import annotations

import json
from pathlib import Path

from backend import scene_layouts, scenes, themes, timeline

W, H, FPS = 1920, 1080, 30
DEFAULT_DUR = timeline.DEFAULT_DUR      # 길이 규칙은 timeline이 단일 기준


def _key(n):
    """씬 번호 비교용 — 삽입 씬의 소수 번호(25.25)를 int로 자르면 서로 다른 씬이 섞인다."""
    try:
        return float(n)
    except (TypeError, ValueError):
        return None


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


def build_manifest(proj_dir: Path, only_scene: int | None = None,
                   only_scenes: list | None = None) -> dict:
    """manifest.json 생성. 반환 {path, scenes}.

    only_scene = 한 씬(manifest_scene_{n}.json), only_scenes = 여러 씬(manifest_subset.json).
    둘 다 없으면 전체(manifest.json). 부분 빌드는 Final 컴프를 만들지 않는다(skipFinal)."""
    proj_dir = Path(proj_dir)
    data = scenes.load_scenes(proj_dir)
    picked = None
    if only_scenes:
        picked = {_key(x) for x in only_scenes}
    elif only_scene is not None:
        picked = {_key(only_scene)}
    out_scenes = []
    for s in data.get("scenes", []):
        if picked is not None and _key(s.get("sceneNumber")) not in picked:
            continue
        sid = s.get("sceneId")
        audio = _abs(proj_dir, s["_audio"]) if s.get("_audio") else None
        dur = timeline.scene_duration(proj_dir, s)   # 컴프·자막·타임라인 공통 계산
        layout = s.get("layout") or "cinematic"
        layout = scene_layouts.resolve_layout(layout)   # 별칭·미지원 이름 → 그릴 수 있는 이름
        # 지도 씬 — 패널(MapLibre)이 렌더한 지도 이미지가 링크되면 일반 이미지 씬으로 취급
        is_map = layout == "map"
        if is_map and s.get("_image"):
            layout = "cinematic"
        is_layout_scene = layout != "cinematic"
        # 씬 컴프 크기 = 씬 이미지 크기 → 풀프레임 레이어가 1:1·중앙으로 정확히 겹침(위치 보존)
        # 레이아웃 씬(비이미지)은 이미지/레이어를 쓰지 않음 — 기본 1920×1080 컴프
        size = None if is_layout_scene else (_img_size(proj_dir / s["_image"]) if s.get("_image") else None)
        sw, sh = size if size else (W, H)
        layers = [] if is_layout_scene else _scene_layers(proj_dir, s.get("_layers") or [])
        cam = None
        mp = proj_dir / f"motion_{sid}.json"
        if mp.is_file():
            try:
                mo = json.loads(mp.read_text(encoding="utf-8"))
                moves_by = {L.get("layer"): L.get("moves", []) for L in mo.get("layers", [])}
                for entry in layers:
                    mv = moves_by.get(entry["name"])
                    if mv:
                        # 캐릭터는 오퍼시티 키프레임 금지 — fade류 제거, slide는 noFade 플래그
                        if "_char" in entry["name"]:
                            mv = [m for m in mv if m.get("type") not in ("fade_in", "exit_fade")]
                            for m in mv:
                                m["noFade"] = True
                        if mv:
                            entry["moves"] = mv
                c = mo.get("camera") or {}
                if c.get("type") and c["type"] != "none":
                    cam = c
            except Exception:
                cam = None
        if is_map and cam is None:
            cam = {"type": "slow_zoom_in", "amount": 6}   # 지도 씬 기본 — 천천히 푸시인
        # 차트 명세서 사이드카(chart_{sid}.spec.json) — chartagent 패턴/모티프 토큰을 jsx bar에 전달
        chart_spec = None
        csp = proj_dir / f"chart_{sid}.spec.json"
        if layout == "bar" and csp.is_file():
            try:
                chart_spec = json.loads(csp.read_text(encoding="utf-8"))
            except Exception:
                chart_spec = None
        # 지도 geo 사이드카({이미지}.geo.json) — 마커/경로 픽셀 좌표를 jsx에 전달(AE 네이티브 레이어)
        map_geo = None
        if is_map and s.get("_image"):
            gp = proj_dir / f"{s['_image']}.geo.json"
            if gp.is_file():
                try:
                    map_geo = json.loads(gp.read_text(encoding="utf-8"))
                except Exception:
                    map_geo = None
        # 결정적 규칙: 캐릭터 레이어(_char 접미사 또는 kinds 사이드카)는 LLM 플랜 없이도
        # 항상 발밑 피벗 bob(까딱임) — 모션 버튼은 부가 연출(fade_in/camera)용 옵션
        kinds = {}
        kp = proj_dir / "layers" / f"{sid}__kinds.json"
        if kp.is_file():
            try:
                kinds = json.loads(kp.read_text(encoding="utf-8"))
            except Exception:
                kinds = {}
        for entry in layers:
            if entry["kind"] != "element" or entry.get("moves") or not entry.get("foot"):
                continue
            is_char = "_char" in entry["name"] or kinds.get(entry["name"]) == "character"
            if is_char:
                entry["moves"] = [{"type": "bob", "start": 0, "duration": dur}]
        # 레이아웃 데이터 — v3 공통 계약으로 정규화해서 넘긴다(jsx는 정규 이름만 안다)
        data_fields = scene_layouts.normalize_fields(s)
        out_scenes.append({
            "ae_comp_name": timeline.comp_name(s),
            "width": sw, "height": sh,
            "image": _abs(proj_dir, s["_image"]) if s.get("_image") else None,
            "layers": layers,
            "audio": audio,
            "subtitle": scenes.subtitle_text(s),   # 화면 표시용(TTS 발음 텍스트 아님)
            "duration": dur,
            "layout": layout,
            **data_fields,
            **({"camera": cam} if cam else {}),
            **({"mapGeo": map_geo} if map_geo else {}),
            **({"chartSpec": chart_spec} if chart_spec else {}),
        })
    mf = {"width": W, "height": H, "fps": FPS, "scenes": out_scenes}
    if picked is not None:
        mf["skipFinal"] = True   # 부분 빌드 — Final은 전체 컴프 때만(jsx가 스킵)
    tokens_path = Path(__file__).resolve().parents[1] / "data" / "artstyle" / "ae_tokens.json"
    if tokens_path.is_file():
        mf["ae_tokens"] = str(tokens_path)
    proj_theme = themes.resolve_theme(proj_dir, None)
    if proj_theme.get("colors"):
        mf["themeColors"] = proj_theme["colors"]   # jsx가 ae_tokens.colors 위에 오버라이드
    if only_scenes:
        name = "manifest_subset.json"
    elif only_scene is not None:
        name = f"manifest_scene_{only_scene}.json"
    else:
        name = "manifest.json"
    out = proj_dir / name
    out.write_text(json.dumps(mf, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(out), "scenes": len(out_scenes)}
