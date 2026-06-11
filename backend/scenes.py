"""scenes.json 조회/수정 — sceneId 기반 에셋, 미디어·레이어 enrich, 나레이션 편집(무삭제)."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path


def _path(proj_dir: Path) -> Path:
    return proj_dir / "scenes.json"


def _new_sid() -> str:
    return uuid.uuid4().hex[:8]


def _migrate_assets(proj_dir: Path, old_key, sid: str) -> None:
    """번호 기반 에셋(sb_{old}/bg_{old}/char_{old})을 sid 기반으로 복사(무삭제·멱등)."""
    sb, lay = proj_dir / "storyboard", proj_dir / "layers"
    if sb.is_dir():
        for p in list(sb.glob(f"sb_{old_key}.png")) + list(sb.glob(f"sb_{old_key}_v*.png")):
            tgt = sb / p.name.replace(f"sb_{old_key}", f"sb_{sid}", 1)
            if not tgt.exists():
                shutil.copy(p, tgt)
    if lay.is_dir():
        for nm in (f"bg_{old_key}.png", f"char_{old_key}.png"):
            src = lay / nm
            tgt = lay / nm.replace(f"_{old_key}.", f"_{sid}.", 1)
            if src.exists() and not tgt.exists():
                shutil.copy(src, tgt)


def ensure_scene_ids(proj_dir: Path) -> dict:
    """모든 씬에 sceneId 보장(없으면 발급). 신규 발급 시 번호 기반 에셋을 sid로 복사 마이그레이션.
    변경 시 scenes.json 저장. 멱등. 반환=data."""
    fp = _path(proj_dir)
    if not fp.is_file():
        return {"scenes": []}
    data = json.loads(fp.read_text(encoding="utf-8"))
    changed = False
    for s in data.get("scenes", []):
        if not s.get("sceneId"):
            sid = _new_sid()
            s["sceneId"] = sid
            _migrate_assets(proj_dir, s.get("sceneNumber"), sid)
            changed = True
        if "imageRef" not in s:                       # 최초 1회 백필
            latest = _latest_image(proj_dir / "storyboard", s.get("sceneId"))
            s["imageRef"] = latest or ""
            changed = True
    if changed:
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def scene_id_for(proj_dir: Path, scene_number) -> str | None:
    data = ensure_scene_ids(proj_dir)
    for s in data.get("scenes", []):
        if s.get("sceneNumber") == scene_number:
            return s.get("sceneId")
    return None


def _latest_image(sb_dir: Path, sid: str) -> str | None:
    """storyboard/sb_{sid}.png 및 버전(sb_{sid}_v2.png …) 중 최신(버전 번호 숫자 정렬)."""
    if not sb_dir.is_dir() or not sid:
        return None
    files: list[tuple[str, int]] = []
    if (sb_dir / f"sb_{sid}.png").exists():
        files.append((f"sb_{sid}.png", 0))
    for p in sb_dir.glob(f"sb_{sid}_v*.png"):
        try:
            files.append((p.name, int(p.name.split("_v")[1].split(".")[0])))
        except (IndexError, ValueError):
            pass
    if not files:
        return None
    files.sort(key=lambda x: x[1])
    return f"storyboard/{files[-1][0]}"


def load_scenes(proj_dir: Path) -> dict:
    """sceneId 보장 후 각 씬에 _image(최신)·_layers(sid 기반) 부여. dir=프로젝트 절대경로."""
    fp = _path(proj_dir)
    if not fp.is_file():
        return {"scenes": [], "dir": ""}
    data = ensure_scene_ids(proj_dir)
    lay_dir = proj_dir / "layers"
    for s in data.get("scenes", []):
        sid = s.get("sceneId")
        ref = s.get("imageRef") or ""
        s["_image"] = ref if (ref and (proj_dir / ref).is_file()) else None
        s["_layers"] = (sorted(f"layers/{p.name}" for p in lay_dir.glob(f"*{sid}*.png"))
                        if sid and lay_dir.is_dir() else [])
        aud_dir = proj_dir / "audio"
        auds = list(aud_dir.glob(f"tts_{sid}.*")) if sid and aud_dir.is_dir() else []
        s["_audio"] = (f"audio/{max(auds, key=lambda p: p.stat().st_mtime).name}"
                       if auds else None)      # 최신(mp3/wav 공존 시 방금 생성분)
        aud = proj_dir / "audio"
        s["_status"] = {
            "narration": bool((s.get("narration") or "").strip()),
            "image": s["_image"] is not None,
            "layers": len(s["_layers"]) > 0,
            "tts": bool(sid and aud.is_dir() and any(aud.glob(f"*{sid}*"))),
        }
    data["dir"] = str(proj_dir)
    return data


def update_narration(proj_dir: Path, scene_number: int, narration: str) -> dict:
    """씬 나레이션 수정 + narration_dirty=True 저장. {ok, sceneNumber} 또는 {error}."""
    fp = _path(proj_dir)
    if not fp.is_file():
        return {"error": "scenes.json 없음"}
    data = json.loads(fp.read_text(encoding="utf-8"))
    for s in data.get("scenes", []):
        if s.get("sceneNumber") == scene_number:
            s["narration"] = narration
            s["narration_dirty"] = True
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"ok": True, "sceneNumber": scene_number}
    return {"error": f"scene {scene_number} 없음"}


def new_scene_image_name(sid: str) -> str:
    """생성 씬 이미지의 고유 파일명(여러 번 생성해도 충돌·덮어쓰기 없음)."""
    return f"scene_{sid}_{uuid.uuid4().hex[:6]}.png"


def set_image_ref(proj_dir: Path, scene_number, image_rel) -> dict:
    """씬의 imageRef 설정(링크) 또는 빈 문자열로 해제. 경로는 프로젝트 내부 + 존재 검증."""
    fp = _path(proj_dir)
    if not fp.is_file():
        return {"error": "scenes.json 없음"}
    rel = (image_rel or "").strip()
    if rel:
        target = (proj_dir / rel).resolve()
        if not target.is_relative_to(proj_dir.resolve()):
            return {"error": "잘못된 경로"}
        if not target.is_file():
            return {"error": f"파일 없음: {rel}"}
    data = json.loads(fp.read_text(encoding="utf-8"))
    for s in data.get("scenes", []):
        if s.get("sceneNumber") == scene_number:
            s["imageRef"] = rel
            fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"ok": True, "sceneNumber": scene_number, "imageRef": rel}
    return {"error": f"scene {scene_number} 없음"}


def _save(proj_dir: Path, data: dict) -> dict:
    _path(proj_dir).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _renumber(data: dict) -> dict:
    for i, s in enumerate(data.get("scenes", []), start=1):
        s["sceneNumber"] = i
    return data


def _split_text(text: str) -> tuple[str, str]:
    """문장 단위로 가운데 분할. 문장 경계 없으면 (전체, '')."""
    import re
    t = (text or "").strip()
    if not t:
        return "", ""
    parts = re.split(r"(?<=[.!?。])\s+", t)
    if len(parts) < 2:
        return t, ""
    mid = (len(parts) + 1) // 2
    return " ".join(parts[:mid]).strip(), " ".join(parts[mid:]).strip()


def _blank_scene(sid: str, narration: str = "", title: str = "") -> dict:
    return {"sceneNumber": 0, "sceneId": sid, "title": title, "narration": narration,
            "visual_summary": "", "image_prompt": "", "characters": [], "imageRef": ""}


def add_scene(proj_dir: Path, after_number: int | None = None,
              narration: str = "", title: str = "") -> dict:
    """after_number 다음에 새 씬 삽입(없으면 끝). 새 sceneId 발급. 재번호 후 저장. 반환=load_scenes."""
    data = ensure_scene_ids(proj_dir)
    ss = data.setdefault("scenes", [])
    new = _blank_scene(_new_sid(), narration, title)
    idx = len(ss)
    if after_number is not None:
        for i, s in enumerate(ss):
            if s.get("sceneNumber") == after_number:
                idx = i + 1
                break
    ss.insert(idx, new)
    _save(proj_dir, _renumber(data))
    return load_scenes(proj_dir)


def remove_scene(proj_dir: Path, scene_number: int) -> dict:
    """배열에서 씬 제거(파일 무삭제). 재번호 후 저장. 반환=load_scenes."""
    data = ensure_scene_ids(proj_dir)
    ss = data.get("scenes", [])
    data["scenes"] = [s for s in ss if s.get("sceneNumber") != scene_number]
    _save(proj_dir, _renumber(data))
    return load_scenes(proj_dir)


def split_scene(proj_dir: Path, scene_number: int,
                first: str | None = None, second: str | None = None) -> dict:
    """씬을 둘로 분할. 첫 씬=기존 sceneId+imageRef 유지, 둘째=새 sceneId+빈 imageRef.
    first/second 미지정 시 나레이션 문장 단위 분할. 반환=load_scenes."""
    data = ensure_scene_ids(proj_dir)
    ss = data.get("scenes", [])
    for i, s in enumerate(ss):
        if s.get("sceneNumber") == scene_number:
            if first is None and second is None:
                first, second = _split_text(s.get("narration", ""))
            s["narration"] = first or ""
            nxt = _blank_scene(_new_sid(), second or "", s.get("title", ""))
            nxt["visual_summary"] = s.get("visual_summary", "")
            ss.insert(i + 1, nxt)
            break
    _save(proj_dir, _renumber(data))
    return load_scenes(proj_dir)


def merge_scenes(proj_dir: Path, scene_number: int) -> dict:
    """scene_number 와 그 다음 씬을 병합. 첫 씬 sceneId+imageRef 유지, 나레이션 연결.
    둘째 씬 에셋은 디스크에 남김(무삭제). 다음 씬 없으면 no-op. 반환=load_scenes."""
    data = ensure_scene_ids(proj_dir)
    ss = data.get("scenes", [])
    for i, s in enumerate(ss):
        if s.get("sceneNumber") == scene_number and i + 1 < len(ss):
            nxt = ss[i + 1]
            a, b = (s.get("narration") or "").strip(), (nxt.get("narration") or "").strip()
            s["narration"] = (a + "\n" + b).strip()
            del ss[i + 1]
            break
    _save(proj_dir, _renumber(data))
    return load_scenes(proj_dir)
