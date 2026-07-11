"""TTS 글자별 타임스탬프 → 연출 타이밍 큐. ElevenLabs with-timestamps로 확보한
tts_{sid}.timestamps.json(characters/starts/ends)에서 '특정 구절이 발화되는 초'를 찾아
텍스트·요소의 등장 타이밍을 내레이션에 정렬한다. 런타임 v3 의존 없음."""
from __future__ import annotations

import json
from pathlib import Path


def load_timestamps(proj_dir: Path, sid: str) -> dict | None:
    """audio/tts_{sid}.timestamps.json 로드. {characters, starts, ends} 또는 None."""
    fp = Path(proj_dir) / "audio" / f"tts_{sid}.timestamps.json"
    if not fp.is_file():
        return None
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None
    if d.get("characters") and d.get("starts"):
        return d
    return None


def _spoken_form(phrase: str) -> str:
    """표시 텍스트('96%')를 발화 형태('구십육퍼센트')로 — 타임스탬프는 전처리된 텍스트라 정합 필요."""
    try:
        from backend.tts import _clean_text
        return _clean_text(phrase)
    except Exception:
        return phrase


def _norm(s: str) -> str:
    """공백 제거(타임스탬프에는 공백 글자도 포함되므로 매칭 시 무시)."""
    return "".join(str(s or "").split())


def phrase_start_sec(ts: dict, phrase: str, *, preprocess: bool = True) -> float | None:
    """phrase가 발화되기 시작하는 초. 전처리 형태로 공백 무시 부분일치. 못 찾으면 None.
    preprocess=True면 phrase를 발화형태로 변환('96%'→'구십육퍼센트')해 매칭."""
    chars = ts.get("characters") or []
    starts = ts.get("starts") or []
    if not chars or len(chars) != len(starts):
        return None
    target = _norm(_spoken_form(phrase) if preprocess else phrase)
    if not target:
        return None
    # 공백을 뺀 글자 시퀀스와 그 원본 인덱스
    seq, idx = [], []
    for i, c in enumerate(chars):
        if str(c).strip():
            seq.append(str(c))
            idx.append(i)
    hay = "".join(seq)
    pos = hay.find(target)
    if pos < 0:
        # 숫자 등 완전일치 실패 시 앞부분(최대 6자)으로 재시도(단위·조사 흡수)
        if len(target) > 6:
            pos = hay.find(target[:6])
        if pos < 0:
            return None
    return float(starts[idx[pos]])


def scene_text_cue(proj_dir: Path, scene: dict, *, lead: float = 0.15) -> float | None:
    """레이아웃 씬의 '핵심 텍스트'가 발화되는 시각 - lead(살짝 앞서 등장). 없으면 None.
    metric=value, headline_only/items_list/bar=headline, quote=quote_text 기준."""
    sid = scene.get("sceneId")
    if not sid:
        return None
    ts = load_timestamps(proj_dir, sid)
    if not ts:
        return None
    layout = scene.get("layout")
    key = None
    if layout == "metric_spotlight":
        key = scene.get("value")
    elif layout in ("headline_only", "items_list", "bar"):
        key = scene.get("headline")
    elif layout == "quote":
        key = scene.get("quote_text")
    if not str(key or "").strip():
        return None
    t = phrase_start_sec(ts, str(key))
    if t is None:
        return None
    return round(max(0.0, t - lead), 2)
