"""일관성 시트 생성 (adobe 독립 Stage1-2 S2b) — entities.json의 엔티티별 멀티패널 시트를
codex로 1장씩 생성하고 references/에 저장, entities.json에 sheet 경로 역기록.
캐릭터는 세모지 베이스 시트를 리스타일(레이아웃·정체성 단일 소스), 장소·소품은 단일샷 멀티패널.
런타임 v3 의존 없음."""
from __future__ import annotations

import json
from pathlib import Path

from backend import imagegen

_ROOT = Path(__file__).resolve().parents[1]
_BASE_SHEET = _ROOT / "data" / "artstyle" / "semoji_base_sheet.png"


def base_sheet():
    """세모지 기준 캐릭터 시트(턴어라운드+표정 레이아웃) 경로. 없으면 None."""
    return _BASE_SHEET if _BASE_SHEET.exists() else None


def _looks_from_visual(visual: dict) -> str:
    """character visual {appearance,hair,outfit} → looks 문자열."""
    v = visual or {}
    parts = [str(v[k]).strip() for k in ("hair", "outfit", "appearance")
             if str(v.get(k) or "").strip()]
    return ", ".join(parts) if parts else "원본 그대로"


def build_character_sheet_prompt(name: str, visual: dict, rel_out: str) -> str:
    """베이스 캐릭터 시트(첨부 1번)를 리스타일 — 레이아웃·포즈·표정·비율 유지, 헤어·의상만 변경."""
    looks = _looks_from_visual(visual)
    exprs = ", ".join(str(e) for e in (visual or {}).get("expressions") or []) or "기본 표정들"
    return (
        f"첨부된 1번 이미지는 캐릭터 기준 시트(전신 턴어라운드 + 얼굴 클로즈업 + 표정 5컷)다.\n"
        f"이 시트의 캐릭터를 '{name}'(이)라는 캐릭터로 변경해서 같은 레이아웃으로 새로 그려줘.\n"
        f"- 패널 구성·포즈·표정 칸 배치·신체 비율·체형·얼굴 구조·그림체는 1번 시트 그대로 유지.\n"
        f"- 헤어와 의상만 변경: {looks}\n"
        f"- 표정 칸은 다음 정서를 반영: {exprs}\n"
        f"비율을 텍스트로 새로 지정하지 말 것. 글자·로고 없음. "
        f"image_gen으로 생성 후 현재 폴더의 {rel_out} 로 저장. 저장되면 'OK'만 답해."
    )


def build_location_sheet_prompt(name: str, visual: dict, rel_out: str) -> str:
    """장소 6패널 단일샷 — 인물 없음, 세모지 그림체."""
    v = visual or {}
    space = str(v.get("space") or "").strip()
    mood = str(v.get("mood") or "").strip()
    lighting = str(v.get("lighting") or "").strip()
    return (
        f"{imagegen.load_style()}\n\n## 장소 위치 시트(인물 없음)\n"
        f"'{name}' 장소를 한 이미지 안 6패널 그리드(2열 3행)로 그려줘:\n"
        f"1) 항공 와이드  2) 다른 각도 항공  3) 지상 아이레벨  "
        f"4) 랜드마크 디테일  5) 수면/원경 와이드  6) 야경.\n"
        f"- 공간: {space}\n- 분위기: {mood}\n- 조명: {lighting}\n"
        f"[첨부 이미지]는 그림체·색감 참고용 — 인물(사람)·캐릭터는 절대 그리지 말 것. 배경/장소만.\n"
        f"image_gen으로 1장 생성해 현재 폴더의 {rel_out} 로 저장. "
        f"비율을 텍스트로 새로 지정하지 말 것. 글자 없음. 저장되면 'OK'만 답해."
    )


def build_prop_sheet_prompt(name: str, visual: dict, rel_out: str) -> str:
    """소품 4뷰 단일샷 — 인물 없음, 세모지 그림체."""
    v = visual or {}
    form = str(v.get("form") or "").strip()
    material = str(v.get("material") or "").strip()
    color = str(v.get("color") or "").strip()
    return (
        f"{imagegen.load_style()}\n\n## 소품 시트(인물 없음)\n"
        f"'{name}' 소품을 한 이미지 안 4뷰(2x2)로 그려줘: 정면, 측면, 디테일 클로즈업, 인컨텍스트.\n"
        f"- 형태: {form}\n- 재질: {material}\n- 색: {color}\n"
        f"[첨부 이미지]는 그림체·색감 참고용 — 인물(사람)·캐릭터는 절대 그리지 말 것. 사물만.\n"
        f"image_gen으로 1장 생성해 현재 폴더의 {rel_out} 로 저장. "
        f"비율을 텍스트로 새로 지정하지 말 것. 글자 없음. 저장되면 'OK'만 답해."
    )
