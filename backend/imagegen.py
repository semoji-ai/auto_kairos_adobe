"""이미지 생성 — codex CLI image_gen.py(실 gpt-image) 호출 + 재시도 + 복사가드 + 버전.
⚠️ 헤드리스 codex exec의 built-in image_gen은 실제 생성을 안 함(stale 복사/코드드로잉) → CLI만 사용.
참조 메모리 [[feedback_codex_image_generation_cli_rule]]."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from backend import env
from backend import fal_api
from backend import llm
from backend.codex_runner import run_skill  # noqa: F401 — 하위 호환 재export

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
    t = (text or "").lower()
    return ("rate limit" in t or "rate_limit" in t or "too many requests" in t
            or "429" in t)


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


# 전역 동시 이미지 생성 상한 — codex CLI 동시 폭주(rate limit) 방지 큐잉
_GEN_SEMA = threading.BoundedSemaphore(max(1, int(os.environ.get("AK_GEN_CONCURRENCY", "3"))))

# codex CLI image_gen.py 경로(환경변수로 재정의 가능)
_CLI_SCRIPT = Path(os.environ.get("AK_IMAGEGEN_CLI")
                   or (Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
                       / "skills" / ".system" / "imagegen" / "scripts" / "image_gen.py"))
# 코덱스 exec용 잔존 지시문(저장/‘OK’ 응답 등)을 CLI 프롬프트에서 제거하는 패턴
_BOILERPLATE_RE = re.compile(
    r"(##\s*생성 지시.*$)|(image_gen[^\n]*저장[^\n]*\.?)|(현재 폴더의[^\n]*저장[^\n]*\.?)"
    r"|(저장되면\s*['\"]?OK['\"]?만[^\n]*\.?)",
    re.MULTILINE | re.DOTALL)


def _image_python() -> str:
    """image_gen.py를 돌릴 파이썬(openai 설치 필요). AK_IMAGE_PYTHON > 현재 인터프리터."""
    return os.environ.get("AK_IMAGE_PYTHON") or sys.executable


def _clean_image_prompt(prompt: str) -> str:
    """codex exec 시절 프롬프트의 도구·저장 지시문 제거(CLI는 출력 경로를 인자로 받음)."""
    cleaned = _BOILERPLATE_RE.sub("", prompt or "").strip()
    return cleaned or (prompt or "").strip()


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _run_codex_image(proj_dir: Path, out: Path, prompt: str, *,
                     images=None, retries: int = 2, on_line=None, post=None,
                     size: str = "auto") -> dict:
    """codex CLI image_gen.py로 실제 gpt-image 생성. images 있으면 edit, 없으면 generate.
    출력이 첨부 이미지와 동일(복사)이면 실패 처리(헤드리스 built-in image_gen의 가짜 생성 방지).
    전역 세마포어로 동시 실행 제한."""
    key = env.get_key("OPENAI_API_KEY")
    if not key:
        return {"status": "failed", "error": "OPENAI_API_KEY 없음(auto_kairos .env)"}
    if not _CLI_SCRIPT.is_file():
        return {"status": "failed", "error": f"image_gen CLI 없음: {_CLI_SCRIPT}"}
    out.parent.mkdir(parents=True, exist_ok=True)
    img_list = [str(i) for i in (images or []) if Path(i).is_file()]
    in_md5 = {_md5(Path(i)) for i in img_list}
    clean = _clean_image_prompt(prompt)
    cmd = [_image_python(), str(_CLI_SCRIPT)]
    if img_list:
        cmd += ["edit", "--prompt", clean, "--out", str(out), "--size", size, "--force"]
        for img in img_list:
            cmd += ["--image", img]
    else:
        cmd += ["generate", "--prompt", clean, "--out", str(out), "--size", size, "--force"]
    cenv = dict(os.environ)
    cenv["OPENAI_API_KEY"] = key
    last = ""
    for attempt in range(retries + 1):
        with _GEN_SEMA:
            proc = subprocess.run(cmd, env=cenv, capture_output=True, text=True)
        last = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if on_line:
            for ln in last.splitlines():
                if ln.strip():
                    on_line(ln)
        if proc.returncode == 0 and out.exists():
            if in_md5 and _md5(out) in in_md5:
                last += "\n[copy-guard] 출력이 첨부 이미지와 동일(복사) — 실패 처리"
            else:
                if post:
                    post(out)
                return {"status": "completed", "path": str(out)}
        if is_rate_limited(last) and attempt < retries:
            time.sleep(20 * (attempt + 1))
            continue
        if attempt < retries:
            continue
        break
    reason = "rate_limit" if is_rate_limited(last) else "no_file"
    return {"status": "failed", "error": reason, "log_tail": last[-300:]}


def _run_fal_image(proj_dir: Path, out: Path, prompt: str, *, images=None, post=None) -> dict:
    """fal 편집 API로 이미지 1장 생성 → out에 저장. _run_codex_image와 같은 계약.
    레이어 분리 전용 경로(CLAUDE.md 예외). 실패는 {"status": "failed", "error": ...}."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = fal_api.edit_image(prompt, list(images or []))
        out.write_bytes(data)
        if post:
            post(out)
    except (fal_api.FalError, OSError) as e:
        return {"status": "failed", "error": str(e)[:200], "path": str(out)}
    return {"status": "completed", "path": str(out)}


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


MAX_ELEMENTS = 4        # 씬당 요소 레이어 상한. 배경 1장을 더해 최대 5레이어.


def apply_element_budget(elements: list) -> dict:
    """요소를 MAX_ELEMENTS개로 자른다. 분석 프롬프트는 요소를 뒤→앞(z-order)으로 주므로,
    이 절단은 우선순위가 아니라 가장 앞쪽(전경) 요소부터 잘라낸다. 이는 받아들일 만하다 —
    최소성 원칙 때문에 5개 이상 응답 자체가 드물고, 잘린 요소는 배경에 그대로 남기 때문이다.
    잘린 것은 dropped로 함께 돌려준다 — 패널이 '예산 초과로 제외'를 보여주고,
    배경 프롬프트는 채택된 것만 제거 대상으로 삼는다(잘린 요소는 배경에 남아야 한다)."""
    els = list(elements or [])
    return {"elements": els[:MAX_ELEMENTS], "dropped": els[MAX_ELEMENTS:]}


def build_layer_analysis_prompt(*, narration: str = "", context: str = "",
                                image_prompt: str = "", neighbors: str = "",
                                briefing: str = "") -> str:
    """레이어 분석 프롬프트 — 사물 분류가 아니라 '이 장면을 어떻게 움직일 것인가'에서 역산한다.

    씬 이미지는 image_prompt로 생성됐고 그 프롬프트는 나레이션을 표현하려고 쓰였다.
    즉 연출 의도가 거기 이미 적혀 있으므로, 그것을 판단의 출발점으로 삼는다."""
    from backend import motion
    return (
        "너는 모션그래픽 연출가다. 첨부한 씬 이미지를 레이어로 분리하려 한다.\n"
        "분류가 목적이 아니다 — **이 장면을 효과적으로 연출하려면 무엇이 따로 떨어져 있어야 하는가**를 판단해라.\n\n"
        f"## 이 그림을 만든 연출 의도(이미지 생성 프롬프트)\n{image_prompt or '(없음)'}\n\n"
        f"## 내레이션\n{narration or '(없음)'}\n\n"
        f"## 씬 맥락\n{context or '(없음)'}\n\n"
        f"## 앞뒤 씬\n{neighbors or '(없음)'}\n\n"
        f"## 프로젝트 브리핑\n{briefing or '(없음)'}\n\n"
        "## 판단 순서\n"
        "1) 이 씬의 연출 의도는 무엇인가 — 위 이미지 생성 프롬프트가 노린 것.\n"
        "2) 그 의도를 살리려면 무엇이 움직이거나 깊이(앞뒤)를 가져야 하는가.\n"
        "3) 그 움직임을 만들려면 어떤 요소가 따로 떨어져 있어야 하는가. 그것만 목록에 넣는다.\n\n"
        f"## 사용 가능한 레이어 모션\n{motion.PRESET_GUIDE}\n"
        f"## 사용 가능한 카메라\n{motion.CAMERA_GUIDE}\n"
        "여기 없는 동작은 구현할 수 없다. 목록 안에서만 연출을 구상해라.\n"
        "**현재 실제로 적용되는 것은 제한적이다:** 인물 레이어는 bob(까딱임)과 필요 시 fade_in만 받는다. "
        "사물 레이어에는 지금 개별 모션이 붙지 않는다 — 사물이 따로 떨어질 이유는 카메라 무브와 앞뒤 가림(겹침)뿐이다. "
        "따라서 사물을 분리하려면 '카메라가 밀 때 앞뒤로 분리돼야 한다' 또는 '인물을 가린다' 같은 근거가 있어야 하고, "
        "움직임을 지어내서는 안 된다.\n\n"
        "## 최소성(중요)\n"
        f"요소는 최대 {MAX_ELEMENTS}개지만 그것은 상한이지 목표가 아니다. "
        "연출에 필요한 최소로 나눈다. **인물 한 명이 말하는 씬은 인물 1장 + 배경 1장이면 충분하다.** "
        "더 쪼개도 연출이 나아지지 않으면 쪼개지 않는다. 요소 1~2개가 가장 흔한 정답이다.\n"
        "각 요소에 intent(그 레이어로 무엇을 할 것인가)를 쓸 수 없다면 분리 근거가 없는 것이므로 "
        "목록에서 빼고 배경에 남긴다.\n\n"
        "## 항상 지키는 규칙\n"
        "- 인물(사람·캐릭터·생명체)은 움직일 것이 없어 보여도 각각 분리한다 — 까딱임(bob)으로 화면이 죽지 않게 한다. "
        "다른 것에 가려져 일부만 보여도 포함한다.\n"
        "- 인물을 앞에서 가리는 전경은 분리해야 앞뒤 겹침이 유지된다.\n"
        "- 내레이션이 강조하거나 이름을 부르는 사물은 그 강조를 화면으로 받아야 하므로 분리 후보다 — "
        "단 그 사물로 할 동작(intent)을 쓸 수 있을 때만이다.\n"
        "- 정적인 배경·장식은 분리하지 않고 배경에 남긴다.\n"
        "- 앞 씬과 이어지는 샷(continue)이면 레이어 구성을 앞 씬과 맞춰 연결이 끊기지 않게 한다.\n"
        "- 요소는 '가장 뒤'에서 '가장 앞' 순서로 나열한다(뒤→앞). 가리는 사물은 가려지는 인물보다 앞에 온다.\n\n"
        "## 각 요소에 쓸 것\n"
        "- name: 짧은 한국어 이름\n"
        "- name_en: 짧은 영어 이름(레이어 분리 모델 프롬프트에 쓴다)\n"
        "- location: 화면 내 위치\n"
        "- kind: 'character' 또는 'object'\n"
        "- reason: 왜 이것이 따로 떨어져야 하는가 — 연출 관점으로 한 줄\n"
        "- intent: 이 레이어로 무엇을 할 것인가 — 위 어휘와 위 제약 안에서. 예: '인물 — bob로 idle', "
        "'앞쪽 책상 — 카메라 푸시인 때 앞뒤 분리'"
    )


def analyze_scene_layers(proj_dir: Path, scene_image: str, *,
                         narration: str = "", context: str = "", image_prompt: str = "",
                         neighbors: str = "", briefing: str = "", on_line=None) -> dict:
    """씬 이미지+연출 맥락을 분석해 '연출에 필요한' 레이어만 선별.
    {elements:[{name,name_en,location,kind,reason,intent}], dropped:[...]} 또는 error."""
    prompt = build_layer_analysis_prompt(narration=narration, context=context,
                                         image_prompt=image_prompt, neighbors=neighbors,
                                         briefing=briefing)
    out_json = proj_dir / ".layer_analysis.json"
    res = llm.run_orchestrator(prompt, proj_dir, output_schema=str(_LAYER_SCHEMA),
                               output_last=str(out_json), images=[scene_image], on_line=on_line)
    if res.get("returncode") != 0 or not out_json.is_file():
        return {"error": "분석 실패", "elements": [], "dropped": []}
    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "분석 결과 파싱 실패", "elements": [], "dropped": []}
    return {**apply_element_budget(data.get("elements", []))}


def build_element_layer_prompt(name: str, location: str, style_desc: str, rel_out: str,
                               others: list | None = None, key: str = "magenta") -> str:
    """단일 요소 레이어 프롬프트. others=별도 레이어로 분리되는 다른 요소들(이 레이어에서 제외).
    이 요소 위에 얹힌/붙은 것(others 제외)은 함께 그려 한 덩어리로 유지.
    key=빼낼 배경으로 채울 키 색(씬마다 scene_key_color가 정한다)."""
    others = [o for o in (others or []) if o and o != name]
    kl, kh = KEY_LABEL[key], KEY_HEX[key]
    excl = (f"단, 다음은 별도 레이어이므로 포함하지 말고 {kl}로 채운다: {', '.join(others)}.\n"
            if others else "")
    return (
        f"{style_desc}\n\n## 레이어 분리 — 단일 요소\n첨부한 씬 이미지를 레퍼런스로 사용한다.\n"
        f"이 씬에서 '{name}'({location})를 다시 그린다. "
        f"가장 중요한 규칙: 원본 씬에서 이 요소가 차지하는 **정확히 같은 좌표와 같은 크기** 그대로 그려라 — "
        f"절대 확대하지 말고, 중앙으로 옮기지 말고, 화면을 채우지 말 것. "
        f"이 레이어를 원본 위에 겹치면 픽셀이 일치해야 한다.\n"
        f"이 요소 위에 얹혀 있거나 붙어 있는 것(예: 위에 놓인 문서·물건)도 함께 그려 한 덩어리로 유지한다.\n"
        f"{excl}"
        f"그 외 전 영역(다른 인물·사물·배경)은 순수 {kl} 단색({kh})으로 채운다.\n"
        f"텍스트 없음."
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


def _aspect_mismatch(png_path: Path, target_size: tuple, tol: float = 0.03) -> bool:
    """가로세로 비율이 목표와 3% 이상 다르면 True — 이 경우 리사이즈는 찌그러짐을 만든다."""
    try:
        with Image.open(png_path) as im:
            a = im.width / im.height
        t = target_size[0] / target_size[1]
        return abs(a - t) / t > tol
    except Exception:
        return False


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


QC_MIN, QC_MAX = 0.05, 0.98     # transparent_ratio 정상 범위(요소 레이어만)
QC_POS_MIN = 0.5                # position_score 하한 — 미만이면 확대/이동돼 그려진 것

ELEMENTS_SIDECAR = "{sid}__elements.json"
KINDS_SIDECAR = "{sid}__kinds.json"


def _scene_size(scene_image: str):
    """씬 크기 — 모든 레이어를 이 크기로 정규화(겹침 보장). 실패 시 None."""
    try:
        return Image.open(scene_image).size
    except Exception:
        return None


def _qc_feedback(ratio, pos, key: str = "magenta"):
    """QC 불합격 사유 → 재시도 피드백 한 줄. 합격이면 None."""
    kl = KEY_LABEL[key]
    if ratio is not None and ratio < QC_MIN:
        return f"이전 시도에서 {kl} 채움이 거의 없었다(전체를 그렸다). 요소 외 전 영역을 반드시 {kl}로."
    if ratio is not None and ratio > QC_MAX:
        return f"이전 시도에서 요소가 거의 그려지지 않았다(전부 {kl}). 요소를 분명히 그려라."
    if pos is not None and pos < QC_POS_MIN:
        return ("이전 시도에서 요소가 원본과 다른 위치/크기로 그려졌다. "
                "원본 씬에서 이 요소가 차지하는 정확히 같은 좌표·같은 크기로 그려라 — "
                "확대하거나 중앙으로 옮기지 말 것.")
    return None


def _gen_element_once(proj_dir: Path, scene_image: str, out: Path, prompt: str, scene_size,
                      key: str = "magenta"):
    """요소 레이어 1회 생성 + 후처리 → (res, transparent_ratio, position_score)."""
    ratio_box = {}

    def _post(o):
        # raw(chroma 전) 보존 — 텍스처/화질 검수용. layers/_raw/{name}(무삭제·덮어쓰기)
        raw_dir = o.parent / "_raw"
        raw_dir.mkdir(exist_ok=True)
        shutil.copy(o, raw_dir / o.name)
        flatten_colors(o)                       # 구름 얼룩 제거(색 양자화) → 그 후 키잉
        ratio_box.update(chroma_key(o, o, key=key))

    res = _run_fal_image(proj_dir, out, prompt, images=[scene_image], post=_post)
    pos = None
    if res.get("status") == "completed":
        if scene_size and _aspect_mismatch(out, scene_size):
            # 비율 자체가 다르면 늘리면 찌그러짐 → 리사이즈하지 않고 QC 불합격(pos=0)으로 재시도 유도
            return res, ratio_box.get("transparent_ratio"), 0.0
        if scene_size:
            normalize_layer_size(out, scene_size)   # 같은 비율의 크기 변칙만 보정
        pos = position_score(out, scene_image)      # 원위치 충실도
    return res, ratio_box.get("transparent_ratio"), pos


def generate_element_layer(proj_dir: Path, scene_image: str, sid: str, index: int, spec: dict,
                           others: list, *, out_base: Path, scene_size=None,
                           style: str | None = None, on_event=None) -> dict:
    """요소 레이어 1개 생성(QC 불합격 시 1회 재시도, 탈락본은 _prev로).
    전체 분리·낱개 재생성이 공유한다. 반환 {name, rel, status, qc, pos_score}."""
    style = load_style() if style is None else style
    scene_size = scene_size if scene_size is not None else _scene_size(scene_image)
    name, loc = spec.get("name", f"el{index}"), spec.get("location", "")
    # 캐릭터 레이어는 _char 접미사 — AE 레이어명에 노출 + 결정적 모션 규칙의 앵커
    tag = "_char" if spec.get("kind") == "character" else ""
    base_name = f"{sid}__{index}_{_layer_slug(name)}{tag}.png"
    out = versioned_path(out_base, base_name)
    rel = out.relative_to(proj_dir).as_posix()
    key = scene_key_color(out_base, sid, scene_image)["key"]
    prompt = build_element_layer_prompt(name, loc, style, rel, others=others, key=key)
    res, ratio, pos = _gen_element_once(proj_dir, scene_image, out, prompt, scene_size, key=key)
    qc = None
    fb = _qc_feedback(ratio, pos, key=key) if res.get("status") == "completed" else None
    if fb:
        out2 = versioned_path(out_base, base_name)              # 새 파일(무삭제)
        rel2 = out2.relative_to(proj_dir).as_posix()
        # 재시도 프롬프트는 반드시 새 파일 경로로 다시 빌드 — 1차 경로가 들어가면
        # codex가 1차본을 raw로 덮어쓰고 out2는 미생성(E2E에서 발견된 버그)
        prompt2 = build_element_layer_prompt(name, loc, style, rel2, others=others, key=key)
        res2, ratio2, pos2 = _gen_element_once(proj_dir, scene_image, out2,
                                               prompt2 + "\n[재시도 피드백] " + fb, scene_size,
                                               key=key)
        if res2.get("status") == "completed" and _qc_feedback(ratio2, pos2, key=key) is None:
            _retire_layer(out_base, out)            # 탈락한 1차본 → _prev (중복 방지·무삭제)
            out, rel, res, qc, pos = out2, rel2, res2, "retried_ok", pos2
        else:
            # 1차본 유지 + 저품질 표시. 최종 파일이 키잉 안 된 raw일 가능성 가드:
            # 키 색이 그대로면(투명비 ~0) chroma 재적용(멱등 — 이미 키잉된 파일엔 무해)
            try:
                if out.exists():
                    rr = chroma_key(out, out, key=key)
                    if scene_size:
                        normalize_layer_size(out, scene_size)
                    ratio = rr.get("transparent_ratio", ratio)
            except Exception:
                pass
            _retire_layer(out_base, out2)           # 재시도본도 탈락 → _prev (중복 방지)
            res = {"status": "completed_lowq", "path": str(out)}
    r = {"name": name, "rel": rel, "status": res.get("status"), "qc": qc,
         "pos_score": pos}                                          # 풀프레임 레이어(크롭 안 함)
    if res.get("error"):
        r["error"] = res.get("error")
    if on_event:
        on_event(r)
    return r


def generate_background_layer(proj_dir: Path, scene_image: str, sid: str, names: list, *,
                              out_base: Path, scene_size=None, style: str | None = None,
                              on_event=None) -> dict:
    """배경 레이어 생성 — names의 요소들을 지운 배경. 실패 시 1회 재시도(배경은 필수).
    요소를 삭제하면 그 요소는 배경에 남아야 하므로 남은 이름들로 다시 부른다."""
    style = load_style() if style is None else style
    scene_size = scene_size if scene_size is not None else _scene_size(scene_image)
    joined = ", ".join(n for n in names if n)
    res, out, rel = None, None, None
    for bg_try in range(2):                          # 배경은 필수 — 실패 시 1회 재시도
        out = versioned_path(out_base, f"{sid}__bg.png")
        rel = out.relative_to(proj_dir).as_posix()
        prompt = (f"{style}\n\n## 레이어 분리 — 배경\n첨부한 씬 이미지를 레퍼런스로 사용한다.\n"
                  f"다음 요소들과 '그 위에 얹혀 있거나 붙어 있는 것'까지 함께 제거한다: {joined}.\n"
                  f"제거한 자리는 그 뒤에 있을 법한 내용(벽·바닥·뒤쪽 사물 등)으로 자연스럽게 메운다.\n"
                  f"위 목록과 무관한 다른 인물·사물·환경은 원본과 똑같이 그대로 둔다. 임의로 지우거나 추가하지 않는다.\n"
                  f"텍스트 없음.")
        res = _run_fal_image(proj_dir, out, prompt, images=[scene_image])
        if res.get("status") == "completed":
            if scene_size:
                normalize_layer_size(out, scene_size)   # 배경도 동일 크기 보장
            break
        if on_event:
            on_event({"name": "배경", "status": "재시도", "try": bg_try + 1})
    r = {"name": "배경", "rel": rel, "status": res.get("status")}
    if res.get("error"):
        r["error"] = res.get("error")
    if on_event:
        on_event(r)
    return r


def write_element_specs(out_base: Path, sid: str, specs: list) -> None:
    """요소 명세 사이드카 저장(실패해도 분리 자체는 유효 — 낱개 재생성만 품질이 떨어진다)."""
    try:
        (Path(out_base) / ELEMENTS_SIDECAR.format(sid=sid)).write_text(
            json.dumps(specs, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _specs_from_filenames(out_base: Path, sid: str) -> list:
    """사이드카가 없는 옛 프로젝트 복원 — 파일명 {sid}__{i}_{슬러그}[_char] + kinds.json.
    location은 복원할 수 없어 빈 문자열(프롬프트 품질만 조금 떨어진다)."""
    kinds = {}
    kp = Path(out_base) / KINDS_SIDECAR.format(sid=sid)
    if kp.is_file():
        try:
            kinds = json.loads(kp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            kinds = {}
    specs = []
    for path in sorted(Path(out_base).glob(f"{sid}__*.png")):
        stem = path.stem
        tail = stem[len(sid) + 2:]                  # "{i}_{슬러그}[_char]" 또는 "bg"
        if tail == "bg" or not tail:
            continue
        num, _, rest = tail.partition("_")
        if not num.isdigit():
            continue
        rest = re.sub(r"_v\d+$", "", rest)          # versioned_path 접미사 제거
        kind = kinds.get(stem) or ("character" if rest.endswith("_char") else "object")
        name = rest[:-5] if rest.endswith("_char") else rest
        specs.append({"layer": stem, "index": int(num), "name": name.replace("_", " ").strip(),
                      "location": "", "kind": kind})
    return specs


def load_element_specs(out_base: Path, sid: str) -> list:
    """요소 명세 목록. 사이드카 우선, 없으면 파일명에서 복원."""
    fp = Path(out_base) / ELEMENTS_SIDECAR.format(sid=sid)
    if fp.is_file():
        try:
            specs = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(specs, list) and specs:
                return specs
        except (json.JSONDecodeError, OSError):
            pass
    return _specs_from_filenames(out_base, sid)


def _stem_of(layer: str) -> str:
    """'layers/ab__0_x.png' | 'ab__0_x.png' | 'ab__0_x' → 'ab__0_x'."""
    return Path(str(layer)).stem


def is_background_layer(layer: str) -> bool:
    return _stem_of(layer).endswith("__bg") or "__bg_v" in _stem_of(layer)


def delete_layer(proj_dir: Path, sid: str, layer: str, *, subdir: str = "layers") -> dict:
    """요소 레이어 1개를 _prev로 치우고 사이드카에서 제거. 배경은 삭제 대상이 아니다.
    반환 {ok, removed, remaining_names} 또는 {error}. 배경 재생성은 호출자(잡)가 한다."""
    out_base = Path(proj_dir) / subdir
    stem = _stem_of(layer)
    if is_background_layer(stem):
        return {"error": "배경 레이어는 삭제할 수 없습니다 — 재생성만 가능합니다"}
    target = None
    for p in out_base.glob(f"{stem}.png"):
        target = p
        break
    if target is None or not target.is_file():
        return {"error": f"레이어 없음: {stem}"}
    specs = [s for s in load_element_specs(out_base, sid) if s.get("layer") != stem]
    _retire_layer(out_base, target)
    write_element_specs(out_base, sid, specs)
    kp = out_base / KINDS_SIDECAR.format(sid=sid)
    if kp.is_file():
        try:
            kinds = json.loads(kp.read_text(encoding="utf-8"))
            kinds.pop(stem, None)
            kp.write_text(json.dumps(kinds, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass
    return {"ok": True, "removed": stem,
            "remaining_names": [s.get("name", "") for s in specs]}


def regenerate_layer(proj_dir: Path, scene_image: str, sid: str, layer: str, *,
                     subdir: str = "layers", on_event=None) -> dict:
    """레이어 1개만 다시 생성. 배경이면 남은 요소 기준으로 배경을, 아니면 그 요소만.
    이전 파일은 _prev로 치운다(무삭제)."""
    out_base = Path(proj_dir) / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    specs = load_element_specs(out_base, sid)
    style = load_style()
    scene_size = _scene_size(scene_image)
    stem = _stem_of(layer)
    if is_background_layer(stem):
        for p in out_base.glob(f"{sid}__bg*.png"):
            _retire_layer(out_base, p)
        r = generate_background_layer(proj_dir, scene_image, sid,
                                      [s.get("name", "") for s in specs],
                                      out_base=out_base, scene_size=scene_size,
                                      style=style, on_event=on_event)
        return {"layer": r}
    spec = next((s for s in specs if s.get("layer") == stem), None)
    if spec is None:
        return {"error": f"요소 명세 없음: {stem}"}
    old = out_base / f"{stem}.png"
    others = [s.get("name", "") for s in specs if s.get("layer") != stem]
    r = generate_element_layer(proj_dir, scene_image, sid, int(spec.get("index") or 0), spec,
                               others, out_base=out_base, scene_size=scene_size,
                               style=style, on_event=on_event)
    if r.get("status", "").startswith("completed") and old.is_file() \
            and Path(r["rel"]).stem != stem:
        _retire_layer(out_base, old)                # 새 버전이 생겼으면 이전 판은 치운다
        specs = [dict(s, layer=Path(r["rel"]).stem) if s.get("layer") == stem else s for s in specs]
        write_element_specs(out_base, sid, specs)
    return {"layer": r}


def split_scene_to_elements(proj_dir: Path, scene_image: str, sid: str, elements: list,
                            *, subdir: str = "layers", concurrency: int = 1, on_event=None) -> dict:
    """씬 이미지를 layerize로 분리해 투명 PNG 여러 장을 저장한다.

    모델이 프롬프트에 적은 이름대로 오려내므로 다시 그리지 않는다 — 원위치가 어긋날 수 없다.
    z_index 0은 요소가 지워지고 메워진 배경판이라 그대로 배경 레이어로 쓴다.
    concurrency는 호출 1회 구조라 쓰지 않으며, 기존 호출부 호환을 위해 남긴다."""
    out_base = Path(proj_dir) / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    _archive_prev_layers(out_base, sid)     # 재분리 시 기존 레이어 누적 방지(무삭제)
    picked = apply_element_budget(elements)["elements"]
    names = [(e.get("name_en") or "").strip() for e in picked]
    names = [n for n in names if n]
    layers = fal_api.layerize(scene_image, names)

    by_name = {}
    for i, el in enumerate(picked):
        key = (el.get("name_en") or "").strip()
        if key:
            by_name[key] = (i, el)

    results, specs, kinds, unexpected = [], [], {}, []
    for L in layers:
        nm = L.get("name")
        if nm is None:                       # z0 — 인페인팅된 배경판
            out = versioned_path(out_base, f"{sid}__bg.png")
            out.write_bytes(L["data"])
            results.append({"name": "배경", "rel": out.relative_to(proj_dir).as_posix(),
                            "status": "completed", "z": L["z"], "bbox": None})
            if on_event:
                on_event(results[-1])
            continue
        hit = by_name.get(nm.strip())
        if hit is None:
            unexpected.append(nm)
            if on_event:
                on_event({"name": nm, "status": "unexpected"})
            continue
        i, el = hit
        tag = "_char" if el.get("kind") == "character" else ""
        out = versioned_path(out_base, f"{sid}__{i}_{_layer_slug(nm)}{tag}.png")
        out.write_bytes(L["data"])
        stem = out.stem
        kinds[stem] = el.get("kind", "object")
        specs.append({"layer": stem, "index": i, "name": el.get("name", ""),
                      "name_en": nm, "location": el.get("location", ""),
                      "kind": el.get("kind", "object"), "intent": el.get("intent", ""),
                      "bbox": L.get("bbox"), "z": L.get("z")})
        results.append({"name": el.get("name", nm), "rel": out.relative_to(proj_dir).as_posix(),
                        "status": "completed", "z": L.get("z"), "bbox": L.get("bbox")})
        if on_event:
            on_event(results[-1])

    (out_base / KINDS_SIDECAR.format(sid=sid)).write_text(
        json.dumps(kinds, ensure_ascii=False, indent=2), encoding="utf-8")
    write_element_specs(out_base, sid, specs)
    return {"layers": results, "unexpected": unexpected}


def flatten_colors(png_path: Path, colors: int | None = None) -> bool:
    """codex가 평면 일러스트에 넣는 구름 얼룩(불균일 저주파 음영)을 제거 — 색 양자화로 flat화.
    디더 없음(디더=노이즈). 접힘 음영/디테일은 보존(색 경계가 뚜렷한 영역은 유지).
    AK_FLATTEN_COLORS=0 이면 비활성. 마젠타 전 적용 권장(마젠타도 묶여 chroma 정확)."""
    n = colors if colors is not None else int(os.environ.get("AK_FLATTEN_COLORS", "40"))
    if n <= 0:
        return False
    try:
        im = Image.open(png_path).convert("RGB")
        q = im.quantize(colors=n, method=Image.FASTOCTREE, dither=Image.NONE)
        q.convert("RGB").save(png_path)
        return True
    except Exception:
        return False


KEY_COLORS = {"magenta": (255, 0, 255), "green": (0, 255, 0)}
KEY_HEX = {"magenta": "#FF00FF", "green": "#00FF00"}
KEY_LABEL = {"magenta": "마젠타", "green": "그린"}
_COVER_DIST = 0.25          # 이 거리 안이면 '그 색과 겹친다'고 본다


def _key_distance(a: "np.ndarray", key: str) -> "np.ndarray":
    """픽셀별 키 색 거리(0=순수 키 색, 1=정반대). a는 RGB float 배열."""
    kr, kg, kb = KEY_COLORS[key]
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return np.sqrt((kr - r) ** 2 + (kg - g) ** 2 + (kb - b) ** 2) / 441.673


def color_coverage(scene_image, key: str) -> float:
    """씬 이미지에서 그 키 색과 겹치는 픽셀 비율(0~1). 작을수록 키 컬러로 쓰기 좋다."""
    with Image.open(scene_image) as im:
        small = im.convert("RGB").resize((64, 64), Image.BILINEAR)
    a = np.array(small).astype(float)
    return float((_key_distance(a, key) < _COVER_DIST).mean())


def pick_key_color(scene_image) -> dict:
    """이미지에 덜 걸치는 키 색을 고른다. 동률이면 마젠타(기존 기본값)."""
    cov = {k: color_coverage(scene_image, k) for k in KEY_COLORS}
    key = "magenta" if cov["magenta"] <= cov["green"] else "green"
    return {"key": key, "rgb": list(KEY_COLORS[key]), "coverage": cov}


def scene_key_color(out_base: Path, sid: str, scene_image) -> dict:
    """씬의 키 색을 사이드카에 고정해 재사용. 요소·배경·재생성이 반드시 같은 색을 써야 한다."""
    fp = Path(out_base) / f"{sid}__keycolor.json"
    if fp.is_file():
        try:
            saved = json.loads(fp.read_text(encoding="utf-8"))
            if saved.get("key") in KEY_COLORS:
                return saved
        except (json.JSONDecodeError, OSError):
            pass
    try:
        res = pick_key_color(scene_image)
    except Exception:
        return {"key": "magenta", "rgb": list(KEY_COLORS["magenta"]), "coverage": {}}
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return res


def chroma_key(src_png: Path, out_png: Path, key: str = "magenta") -> dict:
    """키 색 거리 기반 소프트 알파 + 가장자리 수축·페더 + 디스필.
    반환 {"transparent_ratio": float} — QC 게이트 신호로 사용."""
    im = Image.open(src_png).convert("RGBA")
    a = np.array(im).astype(float)
    dist = _key_distance(a, key)
    alpha = np.clip((dist - 0.18) / 0.22, 0.0, 1.0)           # 0.18 이하=투명, 0.40 이상=불투명
    # 가장자리 수축(erode 1px) — 키 색 프린지 제거
    core = alpha >= 0.999
    er = core.copy()
    er[1:, :] &= core[:-1, :]; er[:-1, :] &= core[1:, :]
    er[:, 1:] &= core[:, :-1]; er[:, :-1] &= core[:, 1:]
    edge = core & ~er
    alpha[edge] *= 0.8                                        # 경계 페더
    # 디스필: 남은 픽셀의 키 색 성분 감쇠
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    keep = alpha > 0
    if key == "magenta":
        over = keep & (g < np.minimum(r, b) - 40)
        a[over, 0] = np.minimum(a[over, 0], a[over, 1] + 40)
        a[over, 2] = np.minimum(a[over, 2], a[over, 1] + 40)
    else:                                                     # green
        over = keep & (g > np.maximum(r, b) + 40)
        a[over, 1] = np.minimum(a[over, 1], np.maximum(a[over, 0], a[over, 2]) + 40)
    a[:, :, 3] = alpha * 255
    Image.fromarray(a.astype("uint8"), "RGBA").save(out_png)
    return {"transparent_ratio": float((alpha < 0.5).sum()) / alpha.size}


def chroma_key_magenta(src_png: Path, out_png: Path) -> dict:
    """기존 호출부·테스트 보존용 별칭."""
    return chroma_key(src_png, out_png, key="magenta")


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
