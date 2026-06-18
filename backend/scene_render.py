"""씬↔시트 첨부 렌더 (adobe 독립 Stage1-2 S2c) — scenes.json의 엔티티 ID를 entities.json의
시트로 해석해 씬 이미지를 시트 첨부로 일관 렌더. shot_relation=continue는 직전 씬도 첨부.
런타임 v3 의존 없음."""
from __future__ import annotations

import json
from pathlib import Path

from backend import imagegen
from backend import scenes as scenes_mod

_SUBDIR = "scenes"


def _entities_by_id(proj_dir: Path) -> dict:
    ep = proj_dir / "entities.json"
    if not ep.is_file():
        return {}
    try:
        ents = json.loads(ep.read_text(encoding="utf-8")).get("entities") or []
    except Exception:
        return {}
    return {e.get("id"): e for e in ents if e.get("id")}


def _sheet_rel(proj_dir: Path, ent) -> str:
    """엔티티의 sheet 경로(존재하는 파일만). 없으면 ''."""
    rel = str((ent or {}).get("sheet") or "").strip()
    if rel and (proj_dir / rel).is_file():
        return rel
    return ""


def resolve_scene_refs(scene, entities_by_id, proj_dir) -> dict:
    """씬의 character_ids/location_id/prop_ids → 존재하는 시트 rel(이름 동반).
    {character_sheets:[{rel,name}], location_sheet:{rel,name}|{}, prop_sheets:[{rel,name}]}."""
    proj_dir = Path(proj_dir)
    char_sheets = []
    for cid in (scene.get("character_ids") or []):
        ent = entities_by_id.get(cid)
        rel = _sheet_rel(proj_dir, ent)
        if rel:
            char_sheets.append({"rel": rel, "name": (ent or {}).get("name") or cid})
    location_sheet = {}
    lid = scene.get("location_id")
    if lid:
        ent = entities_by_id.get(lid)
        rel = _sheet_rel(proj_dir, ent)
        if rel:
            location_sheet = {"rel": rel, "name": (ent or {}).get("name") or lid}
    prop_sheets = []
    for pid in (scene.get("prop_ids") or []):
        ent = entities_by_id.get(pid)
        rel = _sheet_rel(proj_dir, ent)
        if rel:
            prop_sheets.append({"rel": rel, "name": (ent or {}).get("name") or pid})
    return {"character_sheets": char_sheets, "location_sheet": location_sheet,
            "prop_sheets": prop_sheets}


def build_scene_prompt(scene, descriptors, style_desc, rel_out, *, has_prev=False) -> str:
    """descriptors(첨부 순서와 일치)를 합쳐 씬 프롬프트 생성."""
    scene_desc = (scene.get("image_prompt") or scene.get("visual_summary")
                  or scene.get("narration") or "").strip()
    lines = "\n".join(f"- {d}" for d in descriptors)
    return (
        f"{style_desc}\n\n## 장면\n{scene_desc}\n\n"
        f"[첨부 이미지 — 순서대로]\n{lines}\n\n## 생성 지시\n"
        f"image_gen 도구로 위 아트스타일의 이미지 1장을 생성해 현재 폴더의 {rel_out} 로 저장.\n"
        f"첨부한 캐릭터·장소·소품 시트의 정체성을 그대로 유지(비율·형태를 새로 디자인하지 말 것). "
        f"비율을 텍스트로 새로 지정하지 말 것. 텍스트 없음. 저장되면 'OK'만 답해."
    )
