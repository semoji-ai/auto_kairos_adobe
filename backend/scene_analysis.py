"""씬 분석 (adobe 독립 Stage1-2 P4b) — final_manuscript.md를 마커로 분할하고
씬별 연출(LLM)을 붙여 adobe 네이티브 scenes.json 산출. 런타임 v3 의존 없음."""
from __future__ import annotations

import json
import re
from pathlib import Path

from backend import llm

_ROOT = Path(__file__).resolve().parents[1]
_SKILLS = _ROOT / "skills"
_SCHEMAS = Path(__file__).resolve().parent / "schemas"
_SCENE_SCHEMA = _SCHEMAS / "scene_specs.schema.json"
_REVIEW_SCHEMA = _SCHEMAS / "scene_review.schema.json"
_DECISION_SCHEMA = _SCHEMAS / "scene_layout_decision.schema.json"
_LAYOUTS = {"headline_only", "items_list", "metric_spotlight", "bar", "quote", "map", "cinematic"}
# 검토가 권고할 수 있고, 우리가 데이터를 채워 적용할 수 있는 '카드형' 레이아웃(map/cinematic은 대상 아님).
_DATA_LAYOUTS = {"headline_only", "items_list", "metric_spotlight", "quote", "bar"}
_REL = {"cut", "continue"}

_SCENE_RE = re.compile(r"(?m)^[ \t]*<!--\s*SCENE\s*-->[ \t]*$")
_CHARS_RE = re.compile(r"(?m)^[ \t]*<!--\s*CHARS:\s*(.*?)\s*-->[ \t]*$")


def _load_skill(name: str) -> str:
    md = _SKILLS / name / "SKILL.md"
    if not md.is_file():
        return f"skill: {name}"
    text = md.read_text(encoding="utf-8")
    if text.startswith("---"):              # YAML frontmatter 제거(프롬프트 노이즈 방지)
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:].lstrip("\n")
    return text


def _read(proj_dir: Path, name: str) -> str:
    p = proj_dir / name
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def split_manuscript(text: str) -> list:
    """<!--SCENE-->로 결정적 분할 → [{narration, characters}]. <!--CHARS-->는 추출·제거.
    마커 없으면 전체가 1씬. 빈 세그먼트는 버림."""
    segs: list = []
    for part in _SCENE_RE.split(text or ""):
        chars: list = []
        mm = _CHARS_RE.search(part)
        if mm:
            chars = [c.strip() for c in mm.group(1).split(",") if c.strip()]
            part = _CHARS_RE.sub("", part)
        narration = part.strip()
        if narration:
            segs.append({"narration": narration, "characters": chars})
    return segs


def _direct_scenes(proj_dir: Path, segments: list, *, on_event=None) -> list:
    """scene-analyze 스킬로 씬별 연출만 받음. 입력 순서 보존 리스트. 실패 시 []."""
    out = proj_dir / "scene_specs.json"
    narr = "\n\n".join(f"### 씬 {i + 1}\n{seg['narration']}" for i, seg in enumerate(segments))
    prompt = (
        _load_skill("scene-analyze")
        + "\n\n## editorial brief\n" + _read(proj_dir, "editorial_brief.json")
        + f"\n\n## 씬별 내레이션({len(segments)}개, 순서·개수 보존)\n{narr}\n\n"
        + "각 씬의 연출만 scene_specs JSON으로 출력(narration 미포함, 입력과 같은 개수·순서). "
        + f"project_id={proj_dir.name}."
    )
    if on_event:
        on_event(f"씬 연출 {len(segments)}개")
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_SCENE_SCHEMA),
                               output_last=str(out), on_line=on_event)
    if res.get("returncode") != 0 or not out.is_file():
        return []
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
        return list(data.get("scenes") or [])
    except Exception:
        return []


def analyze_scenes(proj_dir, *, enrich: bool = True, on_event=None) -> dict:
    """final_manuscript.md → 마커 분할 + 연출 + 실사/생성 분류 → adobe scenes.json.
    enrich=True면 search 씬에 실사 1장을 검색·다운로드해 imageRef에 채움.
    반환 {scenes, count, searched} 또는 {error}."""
    proj_dir = Path(proj_dir)
    man = proj_dir / "final_manuscript.md"
    if not man.is_file():
        return {"error": "final_manuscript.md 필요 (P4a 먼저)"}
    segments = split_manuscript(man.read_text(encoding="utf-8"))
    if not segments:
        return {"error": "원고가 비어 있음"}

    directions = _direct_scenes(proj_dir, segments, on_event=on_event)
    specs = []
    for i, seg in enumerate(segments):
        d = directions[i] if i < len(directions) and isinstance(directions[i], dict) else {}
        chars = seg["characters"] or list(d.get("characters") or [])
        src = d.get("asset_source") if d.get("asset_source") in ("generate", "search") else "generate"
        specs.append({
            "sceneNumber": i + 1,
            "narration": seg["narration"],
            "visual_summary": str(d.get("visual_summary") or seg["narration"][:60]),
            "image_prompt": str(d.get("image_prompt") or ""),
            "characters": chars,
            "layout": d.get("layout"),
            "asset_source": src,
            "search_query": str(d.get("search_query") or ""),
            "shot_relation": d.get("shot_relation") if d.get("shot_relation") in ("cut", "continue") else "cut",
            "location": str(d.get("location") or ""),
            "props": list(d.get("props") or []),
            # 카드형 레이아웃 데이터(다운스트림 jsx/manifest가 소비) — 해당 레이아웃 아니면 무시
            "headline": str(d.get("headline") or ""),
            "sub": str(d.get("sub") or ""),
            "values": list(d.get("values") or []),
            "labels": list(d.get("labels") or []),
            "unit": str(d.get("unit") or ""),
            "value": str(d.get("value") or ""),
            "label": str(d.get("label") or ""),
            "items": list(d.get("items") or []),
            "quote_text": str(d.get("quote_text") or ""),
            "quote_who": str(d.get("quote_who") or ""),
        })

    from backend.v3_import import _map_scene
    from backend import scenes as scenes_mod
    adobe = []
    for s in specs:
        m = _map_scene(s)
        if s.get("layout"):
            m["layout"] = s["layout"]
        m["asset_source"] = s["asset_source"]
        if s.get("search_query"):
            m["search_query"] = s["search_query"]
        m["shot_relation"] = s["shot_relation"]
        if s.get("location"):
            m["location"] = s["location"]
        if s.get("props"):
            m["props"] = s["props"]
        # 카드형 레이아웃 데이터 통과 + 결정적 안전장치:
        # scene-analyze가 레이아웃을 배정했지만 필수 데이터가 없으면 cinematic으로 다운그레이드
        # (빈 카드 렌더 방지). bar는 chart{} 구조로, 나머지는 jsx 필드명 그대로.
        lay = s.get("layout")
        if lay == "bar":
            vals = [x for x in s.get("values", []) if isinstance(x, (int, float))]
            labs = [str(x).strip() for x in s.get("labels", [])]
            if len(vals) >= 3 and len(labs) == len(vals):
                if s.get("headline"):
                    m["headline"] = s["headline"]
                m["chart"] = {"values": vals, "labels": labs, "unit": s.get("unit", "")}
            else:
                m["layout"] = "cinematic"          # 데이터 부족 → 이미지 씬으로
        elif lay in ("metric_spotlight", "items_list", "quote", "headline_only"):
            ok, fields = _valid_layout_payload(lay, s)
            if ok:
                m.update(fields)
            else:
                m["layout"] = "cinematic"          # 데이터 부족 → 이미지 씬으로(빈 카드 방지)
        adobe.append(m)
    (proj_dir / "scenes.json").write_text(
        json.dumps({"scenes": adobe}, ensure_ascii=False, indent=2), encoding="utf-8")
    scenes_mod.ensure_scene_ids(proj_dir)

    searched = _enrich_real_assets(proj_dir, specs, on_event=on_event) if enrich else 0
    if on_event:
        on_event(f"씬 분석 완료 — {len(specs)}씬 (실사 {searched})")
    return {"scenes": str(proj_dir / "scenes.json"), "count": len(specs), "searched": searched}


_PICK_SCHEMA = _SCHEMAS / "image_pick.schema.json"

# 적합성 검사 기준(비전 판정관용) — 명시적·일관된 판단을 위한 6개 축 + 규칙.
_IMG_CRITERIA = (
    "## 적합성 판정 기준(각 후보를 0~100점으로 평가)\n"
    "1) 내용 일치 (가중치 최상): 씬이 요구하는 '바로 그 실물/주제'를 실제로 담고 있는가. "
    "검색어의 특정 대상(그 특허 문서·그 인물·그 제품·그 장소)과 다른 것이면 크게 감점.\n"
    "2) 사실·시대 고증: 인물·복식·기술·건축이 내레이션의 시대/맥락과 맞는가. "
    "시대착오(과거 장면의 현대 물건 등)는 감점.\n"
    "3) 구도/프레이밍: 16:9 영상 컷으로 쓸 수 있는가. 과한 잘림·기울어짐·콜라주·여러 이미지 격자·"
    "지배적 여백은 감점(피사체가 명확·중심이면 가점).\n"
    "4) 화질: 선명하고 해상도가 충분한가. 흐림·픽셀 깨짐·심한 압축 아티팩트는 감점.\n"
    "5) 클린함: 워터마크·스톡 로고·큰 오버레이 텍스트·출처 배너가 없을수록 가점.\n"
    "6) 명확성: 주제가 한눈에 드러나는가. 관련 없는 배경/사물이 지배적이면 감점.\n"
    "## 선택 규칙\n"
    "- 최고점 후보가 60점 이상이면 그 번호를 best_index로. 60 미만(전부 부적합)이면 best_index=0.\n"
    "- 점수가 비슷하면 1)내용 일치 > 2)고증 > 3)구도 순으로 우선한다.\n"
    "- 의심스러우면 억지로 고르지 말고 0(부적합)으로 둔다 — 부적합보다 AI 생성 폴백이 낫다.\n"
    "- scores에 후보별 fit 점수와 짧은 근거(note)를 남기고, reason에 선택/기각 요약을 쓴다."
)


def _pick_suitable_image(proj_dir: Path, scene: dict, cands: list, *, on_event=None):
    """후보 이미지(로컬 다운로드된 것)를 codex 비전으로 적합성 판정 → 최적 후보 dict 또는 None.
    후보가 1개면 그대로, 비전 실패/후보 0개면 None(→ generate 폴백)."""
    usable = [c for c in cands if c.get("local")]
    if not usable:
        return None
    images = [c["local"] for c in usable]
    ctx = (f"제목: {scene.get('title', '')}\n요약: {scene.get('visual_summary', '')}\n"
           f"내레이션: {str(scene.get('narration') or '')[:300]}\n"
           f"검색어: {scene.get('search_query', '')}")
    listing = "\n".join(f"{i + 1}번: {c.get('title', '') or '(제목 없음)'}" for i, c in enumerate(usable))
    prompt = (
        "너는 다큐멘터리 자료조사관이다. 아래 씬에 쓸 '실사 자료 이미지'를 첨부한 후보들 중에서 고른다. "
        "첨부 순서 = 후보 번호(1번이 첫 이미지).\n\n"
        f"## 씬\n{ctx}\n\n## 후보 목록\n{listing}\n\n"
        f"{_IMG_CRITERIA}\n\nimage_pick JSON만 출력."
    )
    out = proj_dir / f".imgpick_{scene.get('sceneNumber')}.json"
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_PICK_SCHEMA),
                               output_last=str(out), images=images, on_line=on_event)
    if res.get("returncode") != 0 or not out.is_file():
        return None
    try:
        pick = json.loads(out.read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        bi = int(pick.get("best_index"))
    except (TypeError, ValueError):
        return None
    if bi < 1 or bi > len(usable):        # 0=전부 부적합 → generate 폴백
        if on_event:
            on_event(f"S{scene.get('sceneNumber')} 실사 부적합(전부 기각) → 생성 폴백: "
                     f"{str(pick.get('reason') or '')[:50]}")
        return None
    return usable[bi - 1]


def _enrich_real_assets(proj_dir: Path, specs: list, *, on_event=None) -> int:
    """asset_source=='search' 씬에 실사 1장 검색 → 적합성 검사(비전) → 최적 1장만 적용.
    전부 부적합이면 링크 안 함(→ 이후 씬렌더의 generate가 폴백). 붙은 수 반환."""
    from backend import search
    from backend import scenes as scenes_mod
    n = 0
    for s in specs:
        if (s.get("asset_source") or "generate") != "search":
            continue
        q = (s.get("search_query") or s.get("visual_summary") or "").strip()
        if not q:
            continue
        try:
            res = search.search_images(q, engine="serper")
            imgs = res.get("images") or []
            if not imgs:
                if on_event:
                    on_event(f"S{s['sceneNumber']} 실사 결과 없음: {q[:30]}")
                continue
            cands = search.download_candidates(proj_dir, imgs, s.get("sceneNumber"))
            chosen = _pick_suitable_image(proj_dir, s, cands, on_event=on_event)
            if not chosen:                 # 적합성 검사 통과 없음 → generate 폴백
                continue
            dl = search.save_image(proj_dir, chosen.get("url", ""), f"real_{s['sceneNumber']}.jpg")
            if dl.get("status") == "completed":
                scenes_mod.set_image_ref(proj_dir, s["sceneNumber"], dl["rel"])
                n += 1
                if on_event:
                    on_event(f"S{s['sceneNumber']} 실사 선택: {q[:30]}")
        except Exception as e:  # noqa: BLE001 — 검색/다운로드 오류 격리(generate 폴백)
            if on_event:
                on_event(f"S{s['sceneNumber']} 실사 실패: {e}")
    return n


def _scene_det_checks(proj_dir: Path, scenes: list) -> dict:
    """결정적 씬 검토(LLM 무관) — issues 리스트 + 카운트."""
    from backend import brief as brief_mod
    issues: list = []
    n = len(scenes)
    for s in scenes:
        sn = s.get("sceneNumber")
        if not str(s.get("visual_summary") or "").strip():
            issues.append(f"씬{sn}: visual_summary 비어 있음")
        if s.get("layout") and s.get("layout") not in _LAYOUTS:
            issues.append(f"씬{sn}: layout 비표준값 '{s.get('layout')}'")
        if s.get("shot_relation") and s.get("shot_relation") not in _REL:
            issues.append(f"씬{sn}: shot_relation 비표준값 '{s.get('shot_relation')}'")
    if scenes and scenes[0].get("shot_relation") == "continue":
        issues.append("씬1: 첫 씬은 cut이어야 함(continue로 표시됨)")
    per_min = None
    try:
        dur = brief_mod.parse_plan(proj_dir).get("duration", "")
        m = re.search(r"(\d+)", str(dur or ""))
        mins = int(m.group(1)) if m else 0
        if mins > 0:
            per_min = round(n / mins, 1)
            if per_min < 2:
                issues.append(f"분당 씬 수 {per_min}로 너무 적음(2 미만)")
            elif per_min > 12:
                issues.append(f"분당 씬 수 {per_min}로 너무 많음(12 초과)")
    except Exception:
        per_min = None
    man = re.sub(r"<!--.*?-->", "", _read(proj_dir, "final_manuscript.md"))
    coverage = all(str(s.get("narration") or "")[:30] in man for s in scenes) if scenes else False
    if scenes and not coverage:
        issues.append("narration 커버리지 불완전(일부 씬 narration이 원고에 없음)")
    return {"scenes": n, "per_minute": per_min, "narration_coverage": coverage, "issues": issues}


def _review_scenes_llm(proj_dir: Path, scenes: list, *, on_event=None) -> dict:
    """scene-review 스킬로 레이아웃/연결성/엔티티 검토. 실패 시 {scenes:[], flags:[]}."""
    out = proj_dir / "scene_review_llm.json"
    summary = "\n".join(
        f"씬{s.get('sceneNumber')}: layout={s.get('layout')} shot_relation={s.get('shot_relation')} "
        f"chars={s.get('characters')} loc={s.get('location', '')} | {str(s.get('narration') or '')[:60]}"
        for s in scenes)
    prompt = (
        _load_skill("scene-review")
        + "\n\n## editorial brief\n" + _read(proj_dir, "editorial_brief.json")
        + f"\n\n## 씬 목록({len(scenes)}개)\n{summary}\n\n"
        + "scene_review JSON만 출력(scenes 평가 + flags + overall). 권고이며 자동 수정 아님."
    )
    if on_event:
        on_event("씬 검토(LLM)")
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_REVIEW_SCHEMA),
                               output_last=str(out), on_line=on_event)
    if res.get("returncode") != 0 or not out.is_file():
        return {"scenes": [], "flags": []}
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
        return {"scenes": list(data.get("scenes") or []), "flags": list(data.get("flags") or []),
                "overall": str(data.get("overall") or "")}
    except Exception:
        return {"scenes": [], "flags": []}


def _valid_layout_payload(layout: str, dec: dict) -> tuple:
    """대상 레이아웃에 필요한 데이터가 결정적으로 유효한지 검증.
    반환 (ok, fields) — ok=False면 데이터 부족(적용 금지). jsx가 읽는 필드명과 정확히 일치.
    LLM 판단(apply=true)이라도 이 게이트를 통과 못하면 적용 안 함(빈 화면 렌더 방지)."""
    if layout == "metric_spotlight":
        v, lb = str(dec.get("value") or "").strip(), str(dec.get("label") or "").strip()
        return (bool(v and lb), {"value": v, "label": lb})
    if layout == "items_list":
        items = [str(x).strip() for x in (dec.get("items") or []) if str(x).strip()]
        hd = str(dec.get("headline") or "").strip()
        return (len(items) >= 2, {"headline": hd, "items": items})
    if layout == "quote":
        qt = str(dec.get("quote_text") or "").strip()
        return (bool(qt), {"quote_text": qt, "quote_who": str(dec.get("quote_who") or "").strip()})
    if layout == "headline_only":
        hd = str(dec.get("headline") or "").strip()
        return (bool(hd), {"headline": hd, "sub": str(dec.get("sub") or "").strip()})
    if layout == "bar":
        vals = [x for x in (dec.get("values") or []) if isinstance(x, (int, float))]
        labs = [str(x).strip() for x in (dec.get("labels") or [])]
        ok = len(vals) >= 3 and len(labs) == len(vals)
        return (ok, {"headline": str(dec.get("headline") or "").strip(),
                     "chart": {"values": vals, "labels": labs, "unit": str(dec.get("unit") or "").strip()}})
    return (False, {})


def _suggested_layout(text: str) -> str:
    """자유텍스트(검토 note/layout_fit)에서 카드형 레이아웃 권고명을 추출. 없으면 ''."""
    t = str(text or "")
    for lay in ("metric_spotlight", "items_list", "headline_only", "quote", "bar"):
        if lay in t:
            return lay
    return ""


def _layout_change_candidates(scenes: list, review_scenes: list) -> list:
    """검토가 현재와 '다른' 카드형 레이아웃을 권고한(또는 warn한) 씬을 후보로. [(sceneNumber, 현재, 권고|'')].
    검토 스키마는 layout_fit에 레이아웃명 또는 'ok'/'warn' 판정을 넣는다(둘 다 허용).
    - layout_fit이 카드형 레이아웃명이고 현재와 다르면 그 값을 권고로.
    - layout_fit이 'warn'이거나 note가 카드형을 언급하면 후보(권고는 note에서 추출, 없으면 ''→LLM이 결정)."""
    fit_by = {r.get("sceneNumber"): r for r in (review_scenes or [])}
    out = []
    for s in scenes:
        sn = s.get("sceneNumber")
        cur = s.get("layout") or "cinematic"
        r = fit_by.get(sn) or {}
        fit = str(r.get("layout_fit") or "").strip()
        note = str(r.get("note") or "")
        if fit in _DATA_LAYOUTS and fit != cur:
            out.append((sn, cur, fit))
        elif fit == "warn" or _suggested_layout(note) or _suggested_layout(fit):
            sug = _suggested_layout(note) or _suggested_layout(fit)
            if sug != cur:                          # 이미 그 레이아웃이면 후보 아님
                out.append((sn, cur, sug))
    return out


def apply_review_layouts(proj_dir, *, on_event=None) -> dict:
    """검토 권고 레이아웃을 '오케스트레이터 판단 + 결정적 데이터 게이트'로 선별 적용.
    억지 다양화 없음 — 검토가 플래그한 씬만, LLM이 apply=true로 판단하고 필수 데이터가
    유효할 때만 변경. scenes.json은 버전 백업 후 갱신(무삭제). 반환 {applied, kept, changed} 또는 {error}."""
    proj_dir = Path(proj_dir)
    sp = proj_dir / "scenes.json"
    rp = proj_dir / "scene_review.json"
    if not sp.is_file():
        return {"error": "scenes.json 필요 (씬 분석 먼저)"}
    if not rp.is_file():
        return {"error": "scene_review.json 필요 (씬 검토 먼저)"}
    try:
        doc = json.loads(sp.read_text(encoding="utf-8"))
        scenes = doc.get("scenes") or []
        review = json.loads(rp.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "scenes.json/scene_review.json 파싱 실패"}

    cands = _layout_change_candidates(scenes, review.get("scenes") or [])
    if not cands:
        if on_event:
            on_event("레이아웃 변경 권고 없음 — 현행 유지")
        return {"applied": [], "kept": [], "changed": 0}

    by_num = {s.get("sceneNumber"): s for s in scenes}
    note_by = {r.get("sceneNumber"): str(r.get("note") or "")
               for r in (review.get("scenes") or [])}
    lines = []
    for sn, cur, sug in cands:
        s = by_num.get(sn) or {}
        lines.append(
            f"### 씬 {sn} (현재 layout={cur}, 검토 권고={sug})\n"
            f"검토 노트: {note_by.get(sn, '')}\n"
            f"내레이션: {str(s.get('narration') or '')[:400]}")
    prompt = (
        "너는 영상 연출 오케스트레이터다. 아래 씬들은 씬검토가 현재 레이아웃 대신 다른 '카드형' "
        "레이아웃을 권고한 씬이다. 각 씬에 대해, 권고 레이아웃에 **필요한 데이터가 내레이션에 "
        "실제로 존재하는지** 판단해라. 존재하면 그 데이터를 정확히 채워 apply=true, 애매하거나 "
        "데이터가 없으면 apply=false(현행 유지)로 답해라. 억지로 바꾸지 마라 — 확실할 때만 바꾼다.\n\n"
        "레이아웃별 필수 데이터(정확히 이 필드로):\n"
        "- metric_spotlight: value(핵심 수치 한 개, 예 '340kg'), label(그 수치 설명 한 줄)\n"
        "- items_list: headline(제목), items(2~5개 항목 배열)\n"
        "- quote: quote_text(실제 인용문), quote_who(발언자)\n"
        "- headline_only: headline(핵심 한 줄), sub(선택 보조 한 줄)\n"
        "- bar: headline, values(숫자 3개+ 배열), labels(같은 개수), unit\n\n"
        "수치가 1개면 metric_spotlight, 3개+ 비교면 bar. 인용 부호가 있는 실제 발언만 quote.\n\n"
        + "\n\n".join(lines)
        + "\n\nscene_layout_decision JSON만 출력(각 씬 decisions 항목 1개)."
    )
    out = proj_dir / ".layout_decision.json"
    if on_event:
        on_event(f"레이아웃 판단(오케스트레이터) — 후보 {len(cands)}씬")
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_DECISION_SCHEMA),
                               output_last=str(out), on_line=on_event)
    if res.get("returncode") != 0 or not out.is_file():
        return {"error": "레이아웃 판단 실패"}
    try:
        decisions = json.loads(out.read_text(encoding="utf-8")).get("decisions") or []
    except Exception:
        return {"error": "레이아웃 판단 파싱 실패"}

    dec_by = {}
    for d in decisions:
        if not isinstance(d, dict):
            continue
        nd = dict(d)
        if isinstance(nd.get("data"), dict):     # LLM이 데이터를 data{}에 중첩하는 변형 흡수
            for k, v in nd["data"].items():
                nd.setdefault(k, v)
        sn = nd.get("sceneNumber", nd.get("scene"))   # sceneNumber/scene 둘 다 허용
        try:
            sn = int(sn)
        except (TypeError, ValueError):
            continue
        dec_by[sn] = nd
    applied, kept = [], []
    for sn, cur, sug in cands:
        d = dec_by.get(sn) or {}
        target = str(d.get("layout") or sug)
        if not d.get("apply") or target not in _DATA_LAYOUTS:
            kept.append({"scene": sn, "reason": str(d.get("reason") or "apply=false")})
            continue
        ok, fields = _valid_layout_payload(target, d)
        if not ok:
            kept.append({"scene": sn, "reason": f"{target} 데이터 부족 — 현행 유지"})
            continue
        sc = by_num.get(sn)
        if sc is None:
            continue
        sc["layout"] = target                       # 카드형은 이미지 대신 결정적 렌더 → asset_source 무관
        for k in ("value", "label", "headline", "sub", "items", "quote_text", "quote_who", "chart"):
            sc.pop(k, None)                          # 이전 레이아웃 잔여 데이터 제거(혼선 방지)
        sc.update(fields)
        applied.append({"scene": sn, "from": cur, "to": target})
        if on_event:
            on_event(f"씬{sn}: {cur} → {target} 적용")

    if applied:
        _version_backup(sp)                          # 무삭제 — scenes.v{n}.json 백업 후 갱신
        sp.write_text(json.dumps({"scenes": scenes}, ensure_ascii=False, indent=2), encoding="utf-8")
    for k in kept:
        if on_event:
            on_event(f"씬{k['scene']} 유지: {k['reason']}")
    return {"applied": applied, "kept": kept, "changed": len(applied)}


def _version_backup(path: Path) -> Path | None:
    """path를 path.v{n}.json 으로 백업(무삭제·멱등). 반환 백업 경로 또는 None."""
    if not path.is_file():
        return None
    stem = path.stem
    n = 1
    while (path.parent / f"{stem}.v{n}.json").exists():
        n += 1
    bak = path.parent / f"{stem}.v{n}.json"
    bak.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return bak


def review_scenes(proj_dir, *, on_event=None) -> dict:
    """scenes.json을 검토해 advisory 리포트 scene_review.json 산출(래칫 없음).
    반환 {report, flags, det_issues} 또는 {error}."""
    proj_dir = Path(proj_dir)
    sp = proj_dir / "scenes.json"
    if not sp.is_file():
        return {"error": "scenes.json 필요 (씬 분석 먼저)"}
    if not (proj_dir / "final_manuscript.md").is_file():
        return {"error": "final_manuscript.md 필요"}
    try:
        scenes = json.loads(sp.read_text(encoding="utf-8")).get("scenes") or []
    except Exception:
        return {"error": "scenes.json 파싱 실패"}
    det = _scene_det_checks(proj_dir, scenes)
    rv = _review_scenes_llm(proj_dir, scenes, on_event=on_event)
    report = {
        "overall": str(rv.get("overall") or ""),
        "deterministic": det,
        "scenes": list(rv.get("scenes") or []),
        "flags": list(rv.get("flags") or []),
    }
    (proj_dir / "scene_review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if on_event:
        on_event(f"씬 검토 — flags {len(report['flags'])}, det_issues {len(det['issues'])}")
    return {"report": str(proj_dir / "scene_review.json"),
            "flags": len(report["flags"]), "det_issues": len(det["issues"])}
