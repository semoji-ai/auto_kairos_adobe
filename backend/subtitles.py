"""말자막 — TTS 타임스탬프 기반 줄 분할·타이밍 → subtitles.srt + subtitles.json(전역).
씬 오프셋은 manifest와 동일한 duration 로직(오디오 길이→estimate→3.0)으로 누적."""
from __future__ import annotations

import json
from pathlib import Path

from backend import scenes, tts

MAX_LINE = 20      # 자막 한 줄 최대 글자(어절 경계 분할)
DEFAULT_DUR = 3.0


def split_lines(text: str, max_len: int = MAX_LINE) -> list:
    """어절(공백) 경계로 max_len 이하 줄들로 분할."""
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_len:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def _load_ts(proj_dir: Path, sid: str) -> dict | None:
    fp = Path(proj_dir) / "audio" / f"tts_{sid}.timestamps.json"
    if not fp.is_file():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def line_cues(ts: dict, max_len: int = MAX_LINE) -> list:
    """타임스탬프 dict → [{text, start, end}] (씬 로컬 시간).
    alignment characters를 줄 텍스트와 순서대로 소비하며 각 줄의 [첫글자 start, 끝글자 end]."""
    text = ts.get("text", "")
    chars, starts, ends = ts.get("characters", []), ts.get("starts", []), ts.get("ends", [])
    lines = split_lines(text, max_len)
    cues, ci = [], 0
    for line in lines:
        # 줄의 첫 비공백 글자부터 매칭(공백은 건너뜀)
        first_idx = last_idx = None
        for chx in line:
            while ci < len(chars) and chars[ci] != chx:
                ci += 1
            if ci < len(chars):
                if first_idx is None:
                    first_idx = ci
                last_idx = ci
                ci += 1
        if first_idx is None or last_idx is None:
            continue
        try:
            cues.append({"text": line,
                         "start": float(starts[first_idx]),
                         "end": float(ends[last_idx])})
        except (IndexError, ValueError, TypeError):
            continue
    return cues


def _scene_durations(proj_dir: Path, data: dict) -> list:
    """manifest와 동일 로직의 씬 길이 목록(Final 배치 오프셋용)."""
    out = []
    for s in data.get("scenes", []):
        if s.get("_audio"):
            d = tts.audio_duration(Path(proj_dir) / s["_audio"]) or DEFAULT_DUR
        else:
            d = float(s.get("duration_estimate_sec") or DEFAULT_DUR)
        out.append(d)
    return out


def _fmt_srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_subtitles(proj_dir: Path) -> dict:
    """전 씬 자막 빌드 → subtitles.json([{start,end,text}] 전역) + subtitles.srt.
    타임스탬프 없는 씬은 균등 분배 폴백. 반환 {json, srt, lines, scenes_no_ts}."""
    proj_dir = Path(proj_dir)
    data = scenes.load_scenes(proj_dir)
    durs = _scene_durations(proj_dir, data)
    cues_all, no_ts = [], []
    offset = 0.0
    for s, dur in zip(data.get("scenes", []), durs):
        sid = s.get("sceneId")
        ts = _load_ts(proj_dir, sid) if sid else None
        if ts and ts.get("characters"):
            for c in line_cues(ts):
                cues_all.append({"start": round(offset + c["start"], 3),
                                 "end": round(offset + c["end"], 3), "text": c["text"]})
        else:
            text = (s.get("narration_tts") or s.get("narration") or "").strip()
            if text:
                no_ts.append(s.get("sceneNumber"))
                lines = split_lines(text)
                step = dur / max(1, len(lines))
                for i, line in enumerate(lines):       # 균등 분배 폴백
                    cues_all.append({"start": round(offset + i * step, 3),
                                     "end": round(offset + (i + 1) * step - 0.05, 3), "text": line})
        offset += dur
    jpath = proj_dir / "subtitles.json"
    jpath.write_text(json.dumps({"cues": cues_all}, ensure_ascii=False, indent=2), encoding="utf-8")
    srt = []
    for i, c in enumerate(cues_all, 1):
        srt.append(f"{i}\n{_fmt_srt_time(c['start'])} --> {_fmt_srt_time(c['end'])}\n{c['text']}\n")
    spath = proj_dir / "subtitles.srt"
    spath.write_text("\n".join(srt), encoding="utf-8")
    return {"json": str(jpath), "srt": str(spath), "lines": len(cues_all), "scenes_no_ts": no_ts}
