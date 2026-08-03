"""세모지 문체 검증 게이트 — 코퍼스 실측 밴드(semoji-voice-bands.json) 기반 규칙 채점.

나레이션 라인만 평가한다(메타라인 `[...]`, `(...)`, 헤딩 제외).
gn-voice verify_style 방법론: 하한선 포함 — '너무 매끈한'(균일 리듬) 원고도 탈락.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

BANDS_FILE = Path(__file__).resolve().parents[1] / "data" / "artstyle" / "semoji-voice-bands.json"

POLITE = re.compile(r"(습니다|입니다|합니다|됩니다|집니다|겁니다)[.?!…\"”』)]*\s*$")
COLLOQ = re.compile(r"(거죠|이죠|었죠|았죠|잖아요|거든요|는데요|인데요|네요|까요)[.?!…\"”』)]*\s*$")
PLAIN = re.compile(r"(했다|됐다|되었다|였다|이다)[.]?\s*$")
HANGUL_NUM = re.compile(r"(일|이|삼|사|오|육|칠|팔|구|십|백|천)(천|백|십)?(구백|팔십)?[일이삼사오육칠팔구십백천]*년|[일이삼사오육칠팔구]십[일이삼사오육칠팔구]?\s*(골|년|살|개)")
META = re.compile(r"^\s*([\[(#]|<출처>)")


def narration_lines(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines()
            if l.strip() and not META.match(l.strip())]


def check(text: str) -> dict:
    """{ok, violations[], metrics{}} — 위반 문구는 재작성 지시문에 그대로 쓸 수 있게 서술형."""
    lines = narration_lines(text)
    enders = [l for l in lines if re.search(r"[.?!…\"”]\s*$", l)
              or POLITE.search(l) or COLLOQ.search(l) or PLAIN.search(l)]
    ne = max(1, len(enders))
    polite = sum(1 for l in enders if POLITE.search(l)) / ne
    colloq = sum(1 for l in enders if COLLOQ.search(l)) / ne
    plain = sum(1 for l in enders if PLAIN.search(l)) / ne
    lens = [len(l) for l in lines]
    len_std = statistics.pstdev(lens) if len(lens) > 1 else 0.0
    hangul_years = HANGUL_NUM.findall(text)

    v = []
    if plain > 0.05:
        bad = [l for l in enders if PLAIN.search(l)][:3]
        v.append(f"평서체 종결(~했다/됐다/이다)이 {plain:.0%} — 세모지는 존댓말 기본, 전부 '~습니다/~죠'로 바꿀 것. 예: {bad}")
    if polite + colloq < 0.5:
        v.append(f"존댓말+구어체 종결이 {polite+colloq:.0%}뿐 — 실측 밴드(합계 61~93%)에 못 미침. '~습니다' 기본, 공감 지점 '~거죠/~거든요' 혼용.")
    if len(lines) >= 10 and len_std < 4.0:
        v.append(f"줄 길이 표준편차 {len_std:.1f} — 실측 하한(≈6.9)보다 균일. 짧은 문장 연타와 긴 호흡을 섞어 리듬을 만들 것(너무 매끈한 원고 금지).")
    if hangul_years:
        v.append("숫자를 한글로 풀어씀 — 세모지는 아라비아 숫자 표기(예: 2022년, 672골).")
    return {"ok": not v, "violations": v,
            "metrics": {"polite": round(polite, 3), "colloq": round(colloq, 3),
                        "plain": round(plain, 3), "line_len_std": round(len_std, 2),
                        "enders": ne}}


def check_project(proj_dir: Path) -> dict:
    fp = proj_dir / "final_manuscript.md"
    if not fp.exists():
        return {"ok": False, "violations": ["final_manuscript.md 없음"], "metrics": {}}
    return check(fp.read_text(encoding="utf-8"))
