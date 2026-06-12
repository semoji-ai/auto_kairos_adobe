"""codex imagegen(빌트인 image_gen, 단일 인증) 호출 — workspace-write 저장 + 재시도 + 버전."""
from __future__ import annotations

import json
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from backend import llm
from backend.codex_runner import run_skill

STYLE_FILE = Path(__file__).resolve().parents[1] / "data" / "artstyle" / "semoji.md"
BASE_IMG = Path(__file__).resolve().parents[1] / "data" / "artstyle" / "semoji_base.jpg"


def load_style() -> str:
    return STYLE_FILE.read_text(encoding="utf-8") if STYLE_FILE.exists() else ""


def base_img() -> Path | None:
    """세모지 베이스 이미지 경로(있으면). scene-image/character-sheet 규칙의 스타일·비율 앵커."""
    return BASE_IMG if BASE_IMG.exists() else None


def versioned_path(images_dir: Path, name: str) -> Path:
    """name이 이미 있으면 _v2,_v3... 으로 (무삭제)."""
    base = images_dir / name
    if not base.exists():
        return base
    stem, ext = name.rsplit(".", 1)
    n = 2
    while (images_dir / f"{stem}_v{n}.{ext}").exists():
        n += 1
    return images_dir / f"{stem}_v{n}.{ext}"


def is_rate_limited(text: str) -> bool:
    return "rate limit" in (text or "").lower()


def build_image_prompt(image_prompt: str, style_desc: str, rel_out: str,
                       *, has_character_ref: bool = False) -> str:
    """씬 이미지 프롬프트. 세모지 베이스가 항상 첨부된다는 전제(scene-image 규칙).
    has_character_ref=True → 캐릭터 시트(1번)+베이스(2번) / False → 베이스만(인물 사용 금지)."""
    if has_character_ref:
        explainer = (
            "[첨부 이미지]\n"
            "- 1번 캐릭터 시트: 이 인물을 그대로 사용 — 신체 비율·체형·얼굴·헤어·의상을 "
            "100% 동일하게 유지하고, 비율을 바꾸거나 새로 디자인하지 말 것.\n"
            "- 2번(마지막) 세모지 베이스: 이미지 전체의 그림체·색감 기준(베이스 인물 정체성 복사 금지)."
        )
    else:
        explainer = (
            "[첨부 이미지]\n"
            "- 첨부 이미지(세모지 베이스)는 그림체·색감 참고용이다 — "
            "베이스의 인물(사람)은 사용하거나 포함하지 말 것."
        )
    return (
        f"{style_desc}\n\n## 장면\n{image_prompt}\n\n{explainer}\n\n## 생성 지시\n"
        f"image_gen 도구로 위 아트스타일을 적용한 이미지 1장을 생성해 현재 폴더의 {rel_out} 로 저장.\n"
        f"비율을 텍스트로 새로 지정하지 말 것(비율은 첨부 이미지가 정함). "
        f"텍스트 없음. 저장되면 'OK'만 답해."
    )


def build_character_prompt(name: str, looks: str, rel_out: str) -> str:
    """기준 캐릭터 시트 — 세모지 베이스(1번 첨부)를 리스타일(character-sheet 규칙).
    비율·체형·얼굴 구조는 베이스가 정함 — 텍스트로 비율을 지시하지 않는다."""
    return (
        f"첨부된 1번 이미지의 캐릭터를 '{name}'(이)라는 캐릭터로 변경해서 새로 그려줘.\n"
        f"- 신체 비율·체형·얼굴 구조·그림체·포즈·배경은 1번 이미지 그대로 유지.\n"
        f"- 헤어와 의상만 변경: {looks}\n"
        f"비율을 텍스트로 새로 지정하지 말 것. 글자·로고 없음. "
        f"image_gen으로 생성 후 현재 폴더의 {rel_out} 로 저장. 저장되면 'OK'만 답해."
    )


def _run_codex_image(proj_dir: Path, out: Path, prompt: str, *,
                     images=None, retries: int = 2, on_line=None, post=None) -> dict:
    """codex image_gen 실행 + rate limit 백오프. out 생성 확인 후 post(out) 후처리(선택)."""
    last = ""
    for attempt in range(retries + 1):
        captured = []
        res = run_skill(
            prompt, proj_dir, sandbox="workspace-write",
            images=images or None,
            output_last=str(proj_dir / ".imagegen_last.txt"),
            on_line=lambda ln: (captured.append(ln), on_line and on_line(ln)),
        )
        last = "\n".join(captured)
        if res["returncode"] == 0 and out.exists():
            if post:
                post(out)
            return {"status": "completed", "path": str(out)}
        if is_rate_limited(last) and attempt < retries:
            time.sleep(20 * (attempt + 1))
            continue
        break
    reason = "rate_limit" if is_rate_limited(last) else "no_file"
    return {"status": "failed", "error": reason, "log_tail": last[-200:]}


def generate_one(proj_dir: Path, rel_out: str, image_prompt: str,
                 *, subdir: str = "images", retries: int = 2, on_line=None,
                 character_ref=None) -> dict:
    """씬/레퍼런스 1장 생성. 세모지 베이스를 항상 첨부(있으면).
    character_ref를 주면 캐릭터 분기(시트+베이스), 없으면 무캐릭터 분기(베이스만, 인물 금지)."""
    out_base = proj_dir / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    out = versioned_path(out_base, Path(rel_out).name)
    rel = out.relative_to(proj_dir).as_posix()
    images = []
    if character_ref:
        images.append(str(character_ref))
    base = base_img()
    if base:
        images.append(str(base))
    prompt = build_image_prompt(image_prompt, load_style(), rel,
                                has_character_ref=bool(character_ref))
    return _run_codex_image(proj_dir, out, prompt, images=images,
                            retries=retries, on_line=on_line)


def generate_character(proj_dir: Path, name: str, looks: str,
                       *, rel_out: str | None = None, subdir: str = "characters",
                       retries: int = 2, on_line=None) -> dict:
    """기준 캐릭터 시트 생성 — 세모지 베이스를 1번으로 첨부해 리스타일(character-sheet 규칙).
    looks = '갈색 헝클 머리, 크림 오버셔츠+청록 티, 베이지 바지, 흰 운동화, 살짝 미소' 형태."""
    base = base_img()
    if not base:
        return {"status": "failed", "error": "semoji_base.jpg 없음 — 캐릭터 리스타일 불가"}
    out_base = proj_dir / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    out = versioned_path(out_base, Path(rel_out or f"char_{name}.png").name)
    rel = out.relative_to(proj_dir).as_posix()
    prompt = build_character_prompt(name, looks, rel)
    return _run_codex_image(proj_dir, out, prompt, images=[str(base)],
                            retries=retries, on_line=on_line)


def build_asset_prompt(image_prompt: str, style_desc: str, rel_out: str,
                       *, has_char_ref: bool = False) -> str:
    """배경/소품 — 첨부 이미지는 그림체 참고용, 인물(사람)·캐릭터는 그리지 않음."""
    refs = "세모지 베이스" + ("와 기준 캐릭터 시트" if has_char_ref else "")
    return (
        f"{style_desc}\n\n## 장면(인물 없음)\n{image_prompt}\n\n"
        f"[첨부 이미지]\n- 첨부 이미지({refs})는 그림체·색감 참고용이다 — "
        f"인물(사람)·캐릭터는 절대 그리지 말 것. 사물/배경만 그린다.\n\n## 생성 지시\n"
        f"image_gen 도구로 위 아트스타일을 적용한 이미지 1장을 생성해 현재 폴더의 {rel_out} 로 저장.\n"
        f"비율을 텍스트로 새로 지정하지 말 것. 텍스트 없음. 저장되면 'OK'만 답해."
    )


def generate_asset(proj_dir: Path, rel_out: str, image_prompt: str,
                   *, char_ref=None, subdir: str = "images",
                   retries: int = 2, on_line=None) -> dict:
    """배경/소품 생성 — 세모지 베이스(+선택 캐릭터 시트)를 스타일 참고로 첨부, 인물은 안 그림."""
    out_base = proj_dir / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    out = versioned_path(out_base, Path(rel_out).name)
    rel = out.relative_to(proj_dir).as_posix()
    images = []
    base = base_img()
    if base:
        images.append(str(base))
    if char_ref:
        images.append(str(char_ref))
    prompt = build_asset_prompt(image_prompt, load_style(), rel, has_char_ref=bool(char_ref))
    return _run_codex_image(proj_dir, out, prompt, images=images or None,
                            retries=retries, on_line=on_line)


_LAYER_SCHEMA = Path(__file__).resolve().parent / "schemas" / "layer_elements.schema.json"


def analyze_scene_layers(proj_dir: Path, scene_image: str, *,
                         narration: str = "", context: str = "", on_line=None) -> dict:
    """codex 멀티모달로 씬 이미지+내레이션을 분석해 '움직임이 필요한' 레이어만 선별.
    캐릭터는 항상 분리, 사물은 내레이션상 움직일 때만. {elements:[{name,location,kind,reason}]}|{error}."""
    prompt = (
        "첨부한 씬 이미지를 모션그래픽 레이어로 분리하려 한다. "
        "분리한 요소들과 배경을 다시 겹쳤을 때 원본 씬이 그대로 복원되도록 빠짐없이 식별하는 게 핵심이다. "
        "아래 내레이션과 맥락도 참고한다.\n\n"
        f"## 내레이션\n{narration or '(없음)'}\n\n## 맥락\n{context or '(없음)'}\n\n"
        "## 분리 원칙\n"
        "1) 화면에 보이는 사람·인물·캐릭터·생명체는 한 명도 빠짐없이 각각 개별 레이어로 분리한다 "
        "(다른 것에 가려져 일부만 보여도 반드시 포함).\n"
        "2) 인물이나 주요 피사체를 '앞에서 가리는' 전경 사물(책상·기둥·난간·소품 등)은 반드시 개별 레이어로 분리한다 "
        "— 그래야 앞뒤 겹침(가림)이 유지된다.\n"
        "3) 내레이션상 움직이거나 강조·등장하는 사물도 분리한다.\n"
        "4) 그 외 정적인 배경·장식 요소는 분리하지 말고 배경에 남긴다(목록에서 제외).\n"
        "5) 요소는 '가장 뒤'에서 '가장 앞' 순서로 나열한다(뒤→앞). 가리는 사물은 가려지는 인물보다 앞에 온다.\n\n"
        "각 요소: name(짧은 한국어 이름), location(화면 내 위치), kind('character' 또는 'object'), "
        "reason(왜 분리하는지 — 특히 전경에서 무엇을 가리는지 한 줄)."
    )
    out_json = proj_dir / ".layer_analysis.json"
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_LAYER_SCHEMA),
                               output_last=str(out_json), images=[scene_image], on_line=on_line)
    if res.get("returncode") != 0 or not out_json.is_file():
        return {"error": "분석 실패", "elements": []}
    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "분석 결과 파싱 실패", "elements": []}
    return {"elements": data.get("elements", [])}


def build_element_layer_prompt(name: str, location: str, style_desc: str, rel_out: str,
                               others: list | None = None) -> str:
    """단일 요소 레이어 프롬프트. others=별도 레이어로 분리되는 다른 요소들(이 레이어에서 제외).
    이 요소 위에 얹힌/붙은 것(others 제외)은 함께 그려 한 덩어리로 유지."""
    others = [o for o in (others or []) if o and o != name]
    excl = (f"단, 다음은 별도 레이어이므로 포함하지 말고 마젠타로 채운다: {', '.join(others)}.\n"
            if others else "")
    return (
        f"{style_desc}\n\n## 레이어 분리 — 단일 요소\n첨부한 씬 이미지를 레퍼런스로 사용한다.\n"
        f"이 씬에서 '{name}'({location})를 다시 그린다. "
        f"가장 중요한 규칙: 원본 씬에서 이 요소가 차지하는 **정확히 같은 좌표와 같은 크기** 그대로 그려라 — "
        f"절대 확대하지 말고, 중앙으로 옮기지 말고, 화면을 채우지 말 것. "
        f"이 레이어를 원본 위에 겹치면 픽셀이 일치해야 한다.\n"
        f"이 요소 위에 얹혀 있거나 붙어 있는 것(예: 위에 놓인 문서·물건)도 함께 그려 한 덩어리로 유지한다.\n"
        f"{excl}"
        f"그 외 전 영역(다른 인물·사물·배경)은 순수 마젠타 단색(#FF00FF)으로 채운다.\n"
        f"image_gen 도구로 생성해 현재 폴더의 {rel_out} 로 저장. 텍스트 없음. 저장되면 OK만 답해."
    )


def position_score(layer_png: Path, scene_image) -> float | None:
    """요소 레이어가 원본 씬의 '같은 자리'에 그려졌는지 점수(0~1).
    불투명 영역의 픽셀이 원본과 ±40 이내로 일치하는 비율 — 원위치 재드로잉이면 높고,
    확대·이동돼 그려졌으면 낮다(실측: 제자리 0.57~0.98, 어긋남 0.14~0.46)."""
    try:
        im = Image.open(layer_png).convert("RGBA")
        orig = Image.open(scene_image).convert("RGB")
        if im.size != orig.size:
            im = im.resize(orig.size)
        a = np.array(im).astype(int)
        o = np.array(orig).astype(int)
        mask = a[:, :, 3] > 128
        if mask.sum() == 0:
            return None
        diff = np.abs(a[:, :, :3] - o).max(axis=2)
        return float((diff[mask] < 40).mean())
    except Exception:
        return None


def normalize_layer_size(png_path: Path, target_size: tuple) -> bool:
    """레이어 크기를 씬 크기로 강제(codex image_gen이 가끔 다른 크기로 출력 — 예: 1672×941).
    리사이즈했으면 True. 크기가 다르면 풀프레임 겹침이 어긋나므로 생성 직후 호출."""
    try:
        im = Image.open(png_path)
        if im.size == tuple(target_size):
            return False
        im.convert("RGBA").resize(tuple(target_size), Image.LANCZOS).save(png_path)
        return True
    except Exception:
        return False


def _layer_slug(name: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "_", name).strip("_")
    return s[:24] or "el"


def _archive_prev_layers(out_base: Path, sid: str) -> int:
    """재분리 전, 같은 sid의 기존 레이어를 layers/_prev/ 로 이동(무삭제). 옮긴 개수 반환.
    load_scenes의 _layers glob(layers/*{sid}*.png, 비재귀)은 _prev/ 를 보지 않는다."""
    if not sid:
        return 0
    existing = [p for p in out_base.glob(f"*{sid}*.png") if p.is_file()]
    if not existing:
        return 0
    prev = out_base / "_prev"
    prev.mkdir(exist_ok=True)
    for p in existing:
        dest = prev / p.name
        n = 2
        while dest.exists():
            dest = prev / f"{p.stem}_p{n}{p.suffix}"
            n += 1
        shutil.move(str(p), str(dest))
    return len(existing)


def _retire_layer(out_base: Path, path: Path) -> None:
    """QC에서 탈락한 시도 파일을 layers/_prev/ 로 이동(무삭제).
    활성 폴더에 한 시도만 남겨 _layers glob 중복(같은 요소 2장)을 방지."""
    try:
        if not path or not Path(path).is_file():
            return
        prev = out_base / "_prev"
        prev.mkdir(exist_ok=True)
        dest = prev / Path(path).name
        n = 2
        while dest.exists():
            dest = prev / f"{Path(path).stem}_p{n}{Path(path).suffix}"
            n += 1
        shutil.move(str(path), str(dest))
    except Exception:
        pass


def split_scene_to_elements(proj_dir: Path, scene_image: str, sid: str, elements: list,
                            *, subdir: str = "layers", concurrency: int = 4, on_event=None) -> dict:
    """요소별 투명 레이어({sid}__{i}_{slug}.png) + 배경 레이어({sid}__bg.png) 생성.
    요소는 마젠타→투명 후처리. 무삭제(versioned)."""
    out_base = proj_dir / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    _archive_prev_layers(out_base, sid)     # 재분리 시 기존 레이어 누적 방지(무삭제: _prev로 이동)
    style = load_style()
    try:                                    # 씬 크기 — 모든 레이어를 이 크기로 정규화(겹침 보장)
        scene_size = Image.open(scene_image).size
    except Exception:
        scene_size = None

    all_names = [e.get("name", "") for e in elements]
    QC_MIN, QC_MAX = 0.05, 0.98     # transparent_ratio 정상 범위(요소 레이어만)
    QC_POS_MIN = 0.5                # position_score 하한 — 미만이면 확대/이동돼 그려진 것

    def _gen_element_once(out, prompt):
        ratio_box = {}

        def _post(o):
            ratio_box.update(chroma_key_magenta(o, o))

        res = _run_codex_image(proj_dir, out, prompt, images=[scene_image], post=_post)
        pos = None
        if res.get("status") == "completed":
            if scene_size:
                normalize_layer_size(out, scene_size)   # 크기 변칙 가드
            pos = position_score(out, scene_image)      # 원위치 충실도
        return res, ratio_box.get("transparent_ratio"), pos

    def _qc_feedback(ratio, pos):
        """QC 불합격 사유 → 재시도 피드백 한 줄. 합격이면 None."""
        if ratio is not None and ratio < QC_MIN:
            return "이전 시도에서 마젠타 채움이 거의 없었다(전체를 그렸다). 요소 외 전 영역을 반드시 마젠타로."
        if ratio is not None and ratio > QC_MAX:
            return "이전 시도에서 요소가 거의 그려지지 않았다(전부 마젠타). 요소를 분명히 그려라."
        if pos is not None and pos < QC_POS_MIN:
            return ("이전 시도에서 요소가 원본과 다른 위치/크기로 그려졌다. "
                    "원본 씬에서 이 요소가 차지하는 정확히 같은 좌표·같은 크기로 그려라 — "
                    "확대하거나 중앙으로 옮기지 말 것.")
        return None

    def _element(i_el):
        i, el = i_el
        name, loc = el.get("name", f"el{i}"), el.get("location", "")
        out = versioned_path(out_base, f"{sid}__{i}_{_layer_slug(name)}.png")
        rel = out.relative_to(proj_dir).as_posix()
        others = [nm for j, nm in enumerate(all_names) if j != i]   # 다른 선택 요소는 제외
        prompt = build_element_layer_prompt(name, loc, style, rel, others=others)
        res, ratio, pos = _gen_element_once(out, prompt)
        qc = None
        fb = _qc_feedback(ratio, pos) if res.get("status") == "completed" else None
        if fb:
            out2 = versioned_path(out_base, f"{sid}__{i}_{_layer_slug(name)}.png")  # 새 파일(무삭제)
            rel2 = out2.relative_to(proj_dir).as_posix()
            # 재시도 프롬프트는 반드시 새 파일 경로로 다시 빌드 — 1차 경로가 들어가면
            # codex가 1차본을 raw로 덮어쓰고 out2는 미생성(E2E에서 발견된 버그)
            prompt2 = build_element_layer_prompt(name, loc, style, rel2, others=others)
            res2, ratio2, pos2 = _gen_element_once(out2, prompt2 + "\n[재시도 피드백] " + fb)
            if res2.get("status") == "completed" and _qc_feedback(ratio2, pos2) is None:
                _retire_layer(out_base, out)            # 탈락한 1차본 → _prev (중복 방지·무삭제)
                out, rel, res, qc, pos = out2, rel2, res2, "retried_ok", pos2
            else:
                # 1차본 유지 + 저품질 표시. 최종 파일이 키잉 안 된 raw일 가능성 가드:
                # 마젠타가 그대로면(투명비 ~0) chroma 재적용(멱등 — 이미 키잉된 파일엔 무해)
                try:
                    if out.exists():
                        rr = chroma_key_magenta(out, out)
                        if scene_size:
                            normalize_layer_size(out, scene_size)
                        ratio = rr.get("transparent_ratio", ratio)
                except Exception:
                    pass
                _retire_layer(out_base, out2)           # 재시도본도 탈락 → _prev (중복 방지)
                res = {"status": "completed_lowq", "path": str(out)}
        r = {"name": name, "rel": rel, "status": res.get("status"), "qc": qc,
             "pos_score": pos}                                          # 풀프레임 레이어(크롭 안 함)
        if on_event:
            on_event(r)
        return r

    def _bg():
        names = ", ".join(e.get("name", "") for e in elements)
        out = versioned_path(out_base, f"{sid}__bg.png")
        rel = out.relative_to(proj_dir).as_posix()
        prompt = (f"{style}\n\n## 레이어 분리 — 배경\n첨부한 씬 이미지를 레퍼런스로 사용한다.\n"
                  f"다음 요소들과 '그 위에 얹혀 있거나 붙어 있는 것'까지 함께 제거한다: {names}.\n"
                  f"제거한 자리는 그 뒤에 있을 법한 내용(벽·바닥·뒤쪽 사물 등)으로 자연스럽게 메운다.\n"
                  f"위 목록과 무관한 다른 인물·사물·환경은 원본과 똑같이 그대로 둔다. 임의로 지우거나 추가하지 않는다.\n"
                  f"image_gen 도구로 생성해 현재 폴더의 {rel} 로 저장. 텍스트 없음. 저장되면 OK만 답해.")
        res = _run_codex_image(proj_dir, out, prompt, images=[scene_image])
        if res.get("status") == "completed" and scene_size:
            normalize_layer_size(out, scene_size)       # 배경도 동일 크기 보장
        r = {"name": "배경", "rel": rel, "status": res.get("status")}
        if on_event:
            on_event(r)
        return r

    layers = []
    tasks = list(enumerate(elements))
    with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as ex:
        layers = list(ex.map(_element, tasks))
    layers.append(_bg())
    # 레이어별 kind(인물/사물) 사이드카 — 모션 규칙(캐릭터만 bob)에 사용
    kinds = {}
    for i, el in enumerate(elements):
        match = [r for r in layers if r.get("rel", "").split("/")[-1].startswith(f"{sid}__{i}_")]
        if match:
            kinds[Path(match[0]["rel"]).stem] = el.get("kind", "object")
    (out_base / f"{sid}__kinds.json").write_text(
        json.dumps(kinds, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"layers": layers}


def chroma_key_magenta(src_png: Path, out_png: Path) -> dict:
    """마젠타(#FF00FF) 거리 기반 소프트 알파 + 가장자리 수축·페더.
    반환 {"transparent_ratio": float} — QC 게이트 신호로 사용."""
    im = Image.open(src_png).convert("RGBA")
    a = np.array(im).astype(float)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    # 마젠타 유사도: r·b 높고 g 낮을수록 마젠타. dist 0=순수 마젠타.
    dist = np.sqrt((255 - r) ** 2 + g ** 2 + (255 - b) ** 2) / 441.673
    alpha = np.clip((dist - 0.18) / 0.22, 0.0, 1.0)           # 0.18 이하=투명, 0.40 이상=불투명
    # 가장자리 수축(erode 1px) — 마젠타 프린지 제거
    core = alpha >= 0.999
    er = core.copy()
    er[1:, :] &= core[:-1, :]; er[:-1, :] &= core[1:, :]
    er[:, 1:] &= core[:, :-1]; er[:, :-1] &= core[:, 1:]
    edge = core & ~er
    alpha[edge] *= 0.8                                        # 경계 페더
    # 디스필: 남은 픽셀의 마젠타 성분 감쇠(기존 로직 유지)
    keep = alpha > 0
    over = keep & (g < np.minimum(r, b) - 40)
    a[over, 0] = np.minimum(a[over, 0], a[over, 1] + 40)
    a[over, 2] = np.minimum(a[over, 2], a[over, 1] + 40)
    a[:, :, 3] = alpha * 255
    Image.fromarray(a.astype("uint8"), "RGBA").save(out_png)
    return {"transparent_ratio": float((alpha < 0.5).sum()) / alpha.size}


def build_layer_prompt(layer_kind: str, style_desc: str, rel_out: str) -> str:
    head = f"{style_desc}\n\n## 레이어 분리 지시\n첨부한 scene 이미지를 레퍼런스로 사용한다."
    if layer_kind == "character":
        body = ("등장 인물(캐릭터)들만 동일한 포즈·외형·위치로 다시 그리고, "
                "인물 외 모든 영역은 순수 마젠타 단색(#FF00FF)으로 채운다.")
    else:  # background
        body = ("인물(캐릭터)을 모두 제거하고, 배경·환경·공간만 자연스럽게 채워서 그린다. "
                "인물이 있던 자리는 배경으로 메운다.")
    return (f"{head} {body}\nimage_gen 도구로 생성해 현재 폴더의 {rel_out} 로 저장. "
            f"텍스트 없음. 저장되면 OK만 답해.")


def generate_layer(proj_dir, scene_image, rel_out: str, layer_kind: str,
                   *, subdir: str = "layers", retries: int = 2, on_line=None) -> dict:
    """씬 레퍼런스(-i) + layer_kind로 레이어 재생성. character는 마젠타→투명 후처리."""
    out_base = proj_dir / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    raw = versioned_path(out_base, Path(rel_out).name)
    rel = raw.relative_to(proj_dir).as_posix()
    prompt = build_layer_prompt(layer_kind, load_style(), rel)
    last = ""
    for attempt in range(retries + 1):
        captured = []
        res = run_skill(
            prompt, proj_dir, sandbox="workspace-write",
            images=[str(scene_image)],
            output_last=str(proj_dir / ".imagegen_last.txt"),
            on_line=lambda ln: (captured.append(ln), on_line and on_line(ln)),
        )
        last = "\n".join(captured)
        if res["returncode"] == 0 and raw.exists():
            if layer_kind == "character":
                chroma_key_magenta(raw, raw)
            return {"status": "completed", "path": str(raw), "layer": layer_kind}
        if is_rate_limited(last) and attempt < retries:
            time.sleep(20 * (attempt + 1))
            continue
        break
    return {"status": "failed", "error": "rate_limit_or_no_file", "layer": layer_kind}


def generate_scene_layers(proj_dir, scenes_with_images, *, concurrency=4, on_event=None):
    """scenes_with_images=[(sceneNumber, scene_image_path)]. 씬당 background+character 레이어 병렬 생성.
    반환: {sceneNumber: {background:res, character:res}}."""
    tasks = []
    for n, img in scenes_with_images:
        tasks.append((n, "background", f"bg_{n}.png", img))
        tasks.append((n, "character", f"char_{n}.png", img))

    def _work(t):
        n, kind, rel, img = t
        res = generate_layer(proj_dir, img, rel, kind)
        if on_event:
            on_event(n, kind, res)
        return (n, kind, res)

    out = {}
    with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as ex:
        for n, kind, res in ex.map(_work, tasks):
            out.setdefault(n, {})[kind] = res
    return out


def generate_many(proj_dir: Path, items: list, *, subdir: str = "images",
                  concurrency: int = 4, on_event=None, character_ref=None) -> dict:
    """items=[(rel_out, image_prompt), ...] 를 동시에 생성. 각자 generate_one(백오프 내장).
    character_ref를 주면 모든 항목을 캐릭터 분기로(시트+베이스) 생성.
    반환: {rel_out: result_dict}. concurrency는 최소 1."""
    workers = max(1, int(concurrency))
    results = {}

    def _work(item):
        rel, prompt = item
        res = generate_one(proj_dir, rel, prompt, subdir=subdir, character_ref=character_ref)
        if on_event:
            on_event(rel, res)
        return rel, res

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for rel, res in ex.map(_work, items):
            results[rel] = res
    return results
