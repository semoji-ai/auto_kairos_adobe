"""codex imagegen(빌트인 image_gen, 단일 인증) 호출 — workspace-write 저장 + 재시도 + 버전."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from backend.codex_runner import run_skill

STYLE_FILE = Path(__file__).resolve().parents[1] / "data" / "artstyle" / "semoji.md"


def load_style() -> str:
    return STYLE_FILE.read_text(encoding="utf-8") if STYLE_FILE.exists() else ""


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


def build_image_prompt(image_prompt: str, style_desc: str, rel_out: str) -> str:
    return (
        f"{style_desc}\n\n## 생성 지시\n"
        f"image_gen 도구로 위 아트스타일을 적용한 이미지 1장을 생성해 "
        f"현재 폴더의 {rel_out} 로 저장해줘.\n내용: {image_prompt}\n"
        f"텍스트 없음. 저장되면 'OK'만 답해."
    )


def generate_one(proj_dir: Path, rel_out: str, image_prompt: str,
                 *, subdir: str = "images", retries: int = 2, on_line=None) -> dict:
    """레퍼런스/스토리보드 1장 생성. subdir로 출력 폴더 분리(images|storyboard). rate limit 백오프."""
    out_base = proj_dir / subdir
    out_base.mkdir(parents=True, exist_ok=True)
    out = versioned_path(out_base, Path(rel_out).name)
    rel = out.relative_to(proj_dir).as_posix()
    prompt = build_image_prompt(image_prompt, load_style(), rel)
    last = ""
    for attempt in range(retries + 1):
        captured = []
        res = run_skill(
            prompt, proj_dir, sandbox="workspace-write",
            output_last=str(proj_dir / ".imagegen_last.txt"),
            on_line=lambda ln: (captured.append(ln), on_line and on_line(ln)),
        )
        last = "\n".join(captured)
        if res["returncode"] == 0 and out.exists():
            return {"status": "completed", "path": str(out)}
        if is_rate_limited(last) and attempt < retries:
            time.sleep(20 * (attempt + 1))
            continue
        break
    return {"status": "failed", "error": "rate_limit_or_no_file", "log_tail": last[-200:]}


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
                  concurrency: int = 4, on_event=None) -> dict:
    """items=[(rel_out, image_prompt), ...] 를 동시에 생성. 각자 generate_one(백오프 내장).
    반환: {rel_out: result_dict}. concurrency는 최소 1."""
    workers = max(1, int(concurrency))
    results = {}

    def _work(item):
        rel, prompt = item
        res = generate_one(proj_dir, rel, prompt, subdir=subdir)
        if on_event:
            on_event(rel, res)
        return rel, res

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for rel, res in ex.map(_work, items):
            results[rel] = res
    return results
