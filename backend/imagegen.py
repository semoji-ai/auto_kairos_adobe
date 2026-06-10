"""codex imagegen(빌트인 image_gen, 단일 인증) 호출 — workspace-write 저장 + 재시도 + 버전."""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

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
    return {"status": "failed", "error": "rate_limit_or_no_file", "log_tail": last[-200:]}


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
        "아래 내레이션과 연출 맥락을 읽고, 실제로 움직임/애니메이션이 필요한 주요 요소만 골라라.\n\n"
        f"## 내레이션\n{narration or '(없음)'}\n\n## 맥락\n{context or '(없음)'}\n\n"
        "## 원칙\n"
        "1) 등장하는 캐릭터(사람·인물·생명체)는 항상 각각 개별 레이어로 분리한다.\n"
        "2) 캐릭터가 아닌 사물·오브젝트는 내레이션상 움직이거나 강조·등장하는 경우에만 분리한다.\n"
        "3) 움직임이 없는 장식·소품·고정 배경 요소는 분리하지 말고 배경에 남긴다(목록에서 제외).\n"
        "4) 불필요하게 모든 요소를 쪼개지 말 것 — 보통 2~6개가 적당하다.\n\n"
        "각 요소: name(짧은 한국어 이름), location(화면 내 위치), "
        "kind('character' 또는 'object'), reason(왜 이 레이어를 분리·애니메이션하는지 한 줄)."
    )
    out_json = proj_dir / ".layer_analysis.json"
    res = run_skill(prompt, proj_dir, output_schema=str(_LAYER_SCHEMA),
                    output_last=str(out_json), images=[scene_image], on_line=on_line)
    if res.get("returncode") != 0 or not out_json.is_file():
        return {"error": "분석 실패", "elements": []}
    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "분석 결과 파싱 실패", "elements": []}
    return {"elements": data.get("elements", [])}


def build_element_layer_prompt(name: str, location: str, style_desc: str, rel_out: str) -> str:
    return (
        f"{style_desc}\n\n## 레이어 분리 — 단일 요소\n첨부한 씬 이미지를 레퍼런스로 사용한다.\n"
        f"이 씬에서 '{name}'({location})만 동일한 위치·크기·외형으로 다시 그리고, "
        f"그 외 전 영역은 순수 마젠타 단색(#FF00FF)으로 채운다.\n"
        f"image_gen 도구로 생성해 현재 폴더의 {rel_out} 로 저장. 텍스트 없음. 저장되면 OK만 답해."
    )


def _layer_slug(name: str) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣]+", "_", name).strip("_")
    return s[:24] or "el"


def split_scene_to_elements(proj_dir: Path, scene_image: str, sid: str, elements: list,
                            *, subdir: str = "layers", concurrency: int = 4, on_event=None) -> dict:
    """요소별 투명 레이어({sid}__{i}_{slug}.png) + 배경 레이어({sid}__bg.png) 생성.
    요소는 마젠타→투명 후처리. 무삭제(versioned)."""
    out_base = proj_dir / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    style = load_style()

    def _element(i_el):
        i, el = i_el
        name, loc = el.get("name", f"el{i}"), el.get("location", "")
        out = versioned_path(out_base, f"{sid}__{i}_{_layer_slug(name)}.png")
        rel = out.relative_to(proj_dir).as_posix()
        prompt = build_element_layer_prompt(name, loc, style, rel)
        res = _run_codex_image(proj_dir, out, prompt, images=[scene_image],
                               post=lambda o: chroma_key_magenta(o, o))
        r = {"name": name, "rel": rel, "status": res.get("status")}
        if on_event:
            on_event(r)
        return r

    def _bg():
        names = ", ".join(e.get("name", "") for e in elements)
        out = versioned_path(out_base, f"{sid}__bg.png")
        rel = out.relative_to(proj_dir).as_posix()
        prompt = (f"{style}\n\n## 레이어 분리 — 배경\n첨부한 씬 이미지를 레퍼런스로 사용한다.\n"
                  f"다음 피사체들을 모두 제거하고({names}) 배경·환경만 자연스럽게 채워서 그린다.\n"
                  f"image_gen 도구로 생성해 현재 폴더의 {rel} 로 저장. 텍스트 없음. 저장되면 OK만 답해.")
        res = _run_codex_image(proj_dir, out, prompt, images=[scene_image])
        r = {"name": "배경", "rel": rel, "status": res.get("status")}
        if on_event:
            on_event(r)
        return r

    layers = []
    tasks = list(enumerate(elements))
    with ThreadPoolExecutor(max_workers=max(1, int(concurrency))) as ex:
        layers = list(ex.map(_element, tasks))
    layers.append(_bg())
    return {"layers": layers}


def chroma_key_magenta(src_png: Path, out_png: Path) -> dict:
    """마젠타(#FF00FF) 근방을 투명으로. 가장자리 디스필(마젠타 성분 감쇠)."""
    im = Image.open(src_png).convert("RGBA")
    a = np.array(im).astype(int)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mask = (r > 150) & (g < 110) & (b > 150)
    a[mask, 3] = 0
    keep = ~mask
    over = keep & (g < np.minimum(r, b) - 40)
    a[over, 0] = np.minimum(a[over, 0], a[over, 1] + 40)
    a[over, 2] = np.minimum(a[over, 2], a[over, 1] + 40)
    out = Image.fromarray(a.astype("uint8"), "RGBA")
    out.save(out_png)
    return {"transparent_ratio": float(mask.sum()) / mask.size}


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
