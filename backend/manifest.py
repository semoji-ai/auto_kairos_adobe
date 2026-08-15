"""scenes.json + 에셋 → AE build_scene.jsx 용 manifest.json(레이어 스택 포함)."""
from __future__ import annotations

import json
import re
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


def fit_transform(sw, sh, comp_w: int = W, comp_h: int = H):
    """세로 기준 배율과 좌우 중앙 정렬 오프셋 (f, ox).

    f = 컴프높이 / 이미지높이 — 위아래를 자르지 않는다. 폭이 남으면 좌우에 여백이
    생기고(ox 양수), 16:9보다 가로로 길면 좌우로 넘친다(ox 음수).
    크기를 못 읽었거나 비정상이면 (1.0, 0.0)으로 물러선다."""
    try:
        sw = float(sw)
        sh = float(sh)
    except (TypeError, ValueError):
        return (1.0, 0.0)
    if sw <= 0 or sh <= 0:
        return (1.0, 0.0)
    f = comp_h / sh
    return (f, (comp_w - sw * f) / 2)


def _scene_layers(proj_dir: Path, layer_rels: list, sid: str = "", scene_width: int | None = None,
                  *, prefix: str = "", f: float = 1.0, ox: float = 0.0,
                  scene_height: int | None = None) -> list:
    """[{name, aeName, path, kind, position, scale, foot?}] — 배경(__bg)을 맨 앞(최하단)으로.

    좌표는 **컴프 공간**이다. layerize 레이어는 요소 크기로 크롭돼 오므로 사이드카 bbox로
    씬 이미지 좌표를 되살린 뒤, 세로 기준 배율 f와 좌우 오프셋 ox를 곱해 컴프 좌표로 굽는다.
    jsx는 이 숫자를 그대로 찍는다 — 계산하지 않는다.

    bbox가 없는 레이어(배경판·레거시 풀프레임)도 좌표를 싣는다. 씬 사각형을 채우도록
    자기 PNG 폭 기준으로 배율을 낸다."""
    from backend import imagegen
    specs = {s.get("layer"): s for s in imagegen.load_element_specs(proj_dir / "layers", sid)} if sid else {}
    bg = [r for r in layer_rels if "__bg" in Path(r).name]
    el = [r for r in layer_rels if "__bg" not in Path(r).name]
    # 프로젝트에서 제거한 요소는 내보내지 않는다. hidden은 패널 미리보기 전용이라 무시한다.
    el = [r for r in el if not (specs.get(Path(r).stem) or {}).get("removed")]
    el.sort(key=lambda r: (specs.get(Path(r).stem, {}).get("z") is None,
                           specs.get(Path(r).stem, {}).get("z") or 0,
                           Path(r).name))
    sw = float(scene_width or W)
    sh = float(scene_height or H)
    scale_factor = 1.0
    if scene_width and bg:
        plate_size = _img_size(proj_dir / bg[0])
        if plate_size and plate_size[0]:
            scale_factor = scene_width / plate_size[0]
    out = []
    idx = 0
    for r in bg + el:
        stem = Path(r).stem
        is_bg = "__bg" in Path(r).name
        # 벡터화한 레이어는 SVG로 내보낸다 — AE에서 연속 래스터화를 켜면 확대해도 깨지지 않는다.
        # 크기 계산은 PNG 기준을 그대로 쓴다. PIL은 SVG를 읽지 못한다.
        svg_rel = str(Path(r).with_suffix(".svg"))
        has_svg = (proj_dir / svg_rel).is_file()
        if is_bg:
            ae_name = prefix + "배경"
        else:
            idx += 1
            nm = (specs.get(stem) or {}).get("name") or stem
            ae_name = "%s%02d_%s" % (prefix, idx, re.sub(r"\s+", "", str(nm)))
        entry = {"name": stem, "aeName": ae_name,
                 "path": _abs(proj_dir, svg_rel if has_svg else r),
                 "kind": "bg" if is_bg else "element"}
        if has_svg:
            entry["vector"] = True
        placed = False
        if not is_bg:
            bbox = (specs.get(stem) or {}).get("bbox")
            if bbox and len(bbox) == 4:
                try:
                    l, t, rr, b = [float(v) * scale_factor for v in bbox]
                except (TypeError, ValueError):
                    l = rr = None      # 비정상(비수치) bbox — bbox 없는 것으로 취급
                if l is not None and (rr - l) > 0:
                    size = _img_size(proj_dir / r)
                    if size and size[0]:
                        entry["position"] = [(l + rr) / 2 * f + ox, (t + b) / 2 * f]
                        entry["scale"] = (rr - l) / size[0] * 100 * f
                        entry["foot"] = [(l + rr) / 2 * f + ox, b * f]
                        placed = True
        if not placed:
            # 풀프레임(배경판·bbox 없는 레거시) — 씬 사각형을 채운다
            size = _img_size(proj_dir / r) or (sw, sh)
            pw = float(size[0] or sw)
            entry["position"] = [sw * f / 2 + ox, sh * f / 2]
            entry["scale"] = sw * f / pw * 100
            if not is_bg:
                foot = _alpha_foot(proj_dir / r)
                if foot:
                    entry["foot"] = [foot[0] * f + ox, foot[1] * f]
        out.append(entry)
    return out


def _alpha_foot(path: Path) -> list | None:
    """불투명 영역 bbox의 하단 중앙 [x, y](레이어=컴프 좌표). 전부 투명/실패 시 None.
    bbox 사이드카가 없는 기존(풀프레임) 레이어의 까딱 모션 피벗 폴백."""
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
    둘 다 없으면 전체(manifest.json). 평면 구조에서는 Final이 유일한 컴프이므로 부분
    빌드도 같은 컴프에 들어간다 — 각 씬은 자기 start(전체 타임라인 기준)를 그대로 낸다."""
    proj_dir = Path(proj_dir)
    data = scenes.load_scenes(proj_dir)
    starts = {}
    for s_t, start_t, _dur_t in timeline.scene_timings(proj_dir, data):
        starts[_key(s_t.get("sceneNumber"))] = start_t
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
        # width/height는 씬 이미지 원본 크기(fit 계산 기준) — 컴프 좌표는 fit_transform으로 굽는다.
        # 레이아웃 씬(비이미지)은 이미지/레이어를 쓰지 않음 — 기본 1920×1080 기준
        size = None if is_layout_scene else (_img_size(proj_dir / s["_image"]) if s.get("_image") else None)
        sw, sh = size if size else (W, H)
        f, ox = fit_transform(sw, sh)
        prefix = "S%s_" % timeline.comp_num(s.get("sceneNumber"))
        layers = [] if is_layout_scene else _scene_layers(
            proj_dir, s.get("_layers") or [], sid, sw,
            prefix=prefix, f=f, ox=ox, scene_height=sh)
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
            "start": starts.get(_key(s.get("sceneNumber")), 0.0),
            "prefix": prefix,
            "fit": {"f": f, "ox": ox, "w": sw, "h": sh},
            "bgFill": (sw * f) < (W - 1),
            **({"imageFit": {"position": [sw * f / 2 + ox, sh * f / 2],
                             "scale": sw * f / float((_img_size(proj_dir / s["_image"]) or (sw, sh))[0] or sw) * 100}}
               if s.get("_image") else {}),
            "layout": layout,
            **data_fields,
            **({"camera": cam} if cam else {}),
            **({"mapGeo": map_geo} if map_geo else {}),
            **({"chartSpec": chart_spec} if chart_spec else {}),
        })
    mf = {"width": W, "height": H, "fps": FPS, "scenes": out_scenes}
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
