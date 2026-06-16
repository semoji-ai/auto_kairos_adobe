"""리서치 오케스트레이션 — 브리프→쿼리→레인(P1)+웹 fan-out→종합 research_report.
run_research는 Task 4. 여기는 유틸·상수."""
from __future__ import annotations

import json
import re
from pathlib import Path

_SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
_REPORT_SCHEMA = _SCHEMAS / "research_report.schema.json"


def _explorer_count(duration: str) -> int:
    """분량(예 '1분','10분')에 따른 웹리서치 에이전트 수. v3 스케일."""
    m = re.search(r"(\d+)", str(duration or ""))
    mins = int(m.group(1)) if m else 0
    if mins <= 1:
        return 3
    if mins <= 3:
        return 4
    if mins <= 5:
        return 5
    return 6


def _digest(sources: list, web_notes: list) -> dict:
    """결정적 통계(LLM 무관). 소스/노트 카운트 + lane/tier 분포."""
    lanes: dict[str, int] = {}
    tiers: dict[str, int] = {}
    for s in sources:
        lanes[s.get("lane", "")] = lanes.get(s.get("lane", ""), 0) + 1
        tiers[s.get("tier_hint", "")] = tiers.get(s.get("tier_hint", ""), 0) + 1
    return {
        "source_count": len(sources),
        "web_note_count": len([n for n in web_notes if n]),
        "lanes": lanes,
        "tiers": tiers,
    }


def _load_sources(proj_dir: Path) -> list[dict]:
    """research/manifests/**/sources.jsonl 의 모든 소스 dict 로드."""
    out: list[dict] = []
    base = Path(proj_dir) / "research" / "manifests"
    if not base.is_dir():
        return out
    for jsonl in base.rglob("sources.jsonl"):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out
