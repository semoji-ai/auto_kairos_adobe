"""이미지→비디오(i2v) 변환 — Higgsfield CLI 연동. 씬 이미지를 start-image로 두고
모델별 파라미터 + LLM이 모델에 맞춰 생성한 프롬프트로 영상 생성. 힉스필드 인증 필요.
런타임 v3 의존 없음. 이미지 생성(codex $imagegen)과 별개 경로."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

from backend import llm

HF = os.environ.get("HIGGSFIELD_BIN", "higgsfield")

# i2v에 쓸 씬→비디오 모델(업스케일·립싱크 등 제외). label은 패널 표시용.
CURATED_MODELS = [
    ("seedance_2_0", "Seedance 2.0"),
    ("seedance_2_0_mini", "Seedance 2.0 Mini"),
    ("seedance1_5", "Seedance 1.5 Pro"),
    ("kling3_0", "Kling 3.0"),
    ("kling3_0_turbo", "Kling 3.0 Turbo"),
]

# 모델별 프롬프트 포맷 힌트(LLM에 주입) — 카메라를 강요하지 않는다(카메라 판단은 아래 문법이 담당).
_MODEL_PROMPT_STYLE = {
    "seedance": ("Seedance 계열 — 한 문단 서술. 피사체의 자연스러운 미세 동작 → (필요 시) 카메라 → "
                 "빛·분위기 순. 부드럽고 절제된 톤."),
    "kling": ("Kling 계열 — 간결·동적 한두 문장. 무엇이 어떻게 움직이는지 또렷하게."),
}

# 내러티브 카메라 문법 — 내용이 카메라 무브를 '동기'할 때만 넣는다(기계적 푸시인 방지).
_CAMERA_GRAMMAR = (
    "## 카메라 판단(중요 — 내용이 요구할 때만 카메라를 움직인다)\n"
    "- 반전·발견·특정 대상 주목(예: '이름이 ~가 아니다', 숨은 디테일) → 그 대상으로 느린 푸시인.\n"
    "- 규모·전경·웅장함이 드러남 → 느린 풀백 또는 와이드.\n"
    "- 시간 경과·이동·여정 → 완만한 팬/트래킹.\n"
    "- 설명·나열·정적 인물/정물/문서 → 카메라 고정. 피사체의 미세 동작(숨·시선·손짓)만.\n"
    "- 확신이 없으면 카메라를 고정한다. 매 클립 푸시인을 넣지 말 것 — 정지도 좋은 선택이다."
)

_CACHE: dict = {}
_LOCK = threading.Lock()


def _run(args: list, *, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run([HF, *args], capture_output=True, text=True, timeout=timeout)


def higgsfield_status() -> dict:
    """CLI 설치 + 인증 여부(토큰 값은 노출 안 함). {installed, authed}."""
    if shutil.which(HF) is None:
        return {"installed": False, "authed": False, "hint": "higgsfield CLI 미설치"}
    try:
        p = _run(["auth", "token"], timeout=15)
        authed = p.returncode == 0 and bool((p.stdout or "").strip())
    except Exception:
        authed = False
    return {"installed": True, "authed": authed,
            "hint": "" if authed else "higgsfield auth login 필요"}


def _model_params(model: str) -> list:
    """higgsfield model get <m> --json → 파라미터 목록(캐시). 실패 시 []."""
    with _LOCK:
        if model in _CACHE:
            return _CACHE[model]
    params = []
    try:
        p = _run(["model", "get", model, "--json"], timeout=20)
        if p.returncode == 0:
            data = json.loads(p.stdout or "{}")
            for pr in data.get("params", []):
                # 미디어/배열 파라미터는 패널 옵션에서 제외(경로는 우리가 start-image로 주입)
                if pr.get("type") == "array" or pr.get("name") in (
                        "start_image", "end_image", "image_references",
                        "video_references", "audio_references"):
                    continue
                params.append({"name": pr.get("name"), "type": pr.get("type"),
                               "enum": pr.get("enum") or [], "default": pr.get("default"),
                               "required": bool(pr.get("required"))})
    except Exception:
        params = []
    with _LOCK:
        _CACHE[model] = params
    return params


def list_models() -> dict:
    """패널용 모델 레지스트리 + 힉스필드 상태. {status, models:[{id,label,params:[...]}]}."""
    st = higgsfield_status()
    models = []
    if st["installed"]:
        for mid, label in CURATED_MODELS:
            params = _model_params(mid)
            if params:                    # 조회 성공한 모델만(구버전 CLI에 없는 모델 스킵)
                models.append({"id": mid, "label": label, "params": params})
    return {"status": st, "models": models}


def _style_key(model: str) -> str:
    return "kling" if model.startswith("kling") else "seedance"


def build_video_prompt(proj_dir: Path, scene: dict, model: str, *, on_event=None) -> dict:
    """씬(내레이션·요약)으로 모델에 맞는 i2v 프롬프트를 LLM이 생성. {prompt} 또는 {error}.
    씬 이미지가 있으면 첨부해 화면 내용을 반영(멀티모달→codex)."""
    proj_dir = Path(proj_dir)
    style = _MODEL_PROMPT_STYLE[_style_key(model)]
    ctx = (f"제목: {scene.get('title', '')}\n요약: {scene.get('visual_summary', '')}\n"
           f"내레이션: {str(scene.get('narration') or '')[:400]}")
    img = scene.get("_image") or scene.get("imageRef") or ""
    imgs = [str(proj_dir / img)] if img and (proj_dir / img).is_file() else None
    prompt = (
        "너는 i2v(이미지→비디오) 프롬프트 작가다. 첨부/설명된 씬 이미지를 시작 프레임으로 하는 "
        "짧은 영상 클립의 영어 프롬프트를 1개 만든다.\n"
        f"## 대상 모델 스타일\n{style}\n\n{_CAMERA_GRAMMAR}\n\n## 씬\n{ctx}\n\n"
        "규칙: 시작 프레임(이미지)의 구도를 유지하며 '움직임'을 서술. 새 인물·장면 추가 금지. "
        "카메라는 위 문법에 따라 판단(내용이 요구할 때만, 없으면 고정). 영어로, 프롬프트 텍스트만 출력."
    )
    out = proj_dir / f".vprompt_{scene.get('sceneNumber')}.txt"
    res = llm.run_orchestrator(prompt, proj_dir, output_last=str(out), images=imgs, on_line=on_event)
    if res.get("returncode") != 0 or not out.is_file():
        return {"error": "프롬프트 생성 실패"}
    text = out.read_text(encoding="utf-8").strip().strip('"').strip()
    return {"prompt": text} if text else {"error": "빈 프롬프트"}


def _download(url: str, dest: Path, timeout: int = 120) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            dest.write_bytes(r.read())
        return True
    except Exception:
        return False


def generate_video(proj_dir: Path, scene_image: str, model: str, params: dict, prompt: str,
                   *, out_name: str, subdir: str = "video", on_event=None,
                   wait_timeout: str = "20m") -> dict:
    """씬 이미지를 start-image로 i2v 생성 → subdir/out_name.mp4. {status, path}|{status:failed, error}.
    params는 모델 파라미터(예: {resolution:'1080p', mode:'std', duration:5}). 힉스필드 인증 필요."""
    proj_dir = Path(proj_dir)
    if shutil.which(HF) is None:
        return {"status": "failed", "error": "higgsfield CLI 미설치"}
    if not str(prompt or "").strip():
        return {"status": "failed", "error": "prompt 필요"}
    img = Path(scene_image)
    if not img.is_file():
        return {"status": "failed", "error": f"씬 이미지 없음: {scene_image}"}
    out_dir = proj_dir / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    from backend.imagegen import versioned_path
    out = versioned_path(out_dir, Path(out_name).name if out_name.endswith(".mp4") else out_name + ".mp4")

    cmd = ["generate", "create", model, "--start-image", str(img), "--prompt", prompt]
    for k, v in (params or {}).items():
        if v is None or v == "":
            continue
        cmd += [f"--{k}", str(v)]
    cmd += ["--wait", "--wait-timeout", wait_timeout, "--json"]
    if on_event:
        on_event(f"힉스필드 {model} 생성 시작 (씬 이미지 i2v)")
    try:
        p = subprocess.run([HF, *cmd], capture_output=True, text=True, timeout=_to_sec(wait_timeout) + 120)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": "생성 타임아웃"}
    log = (p.stdout or "") + "\n" + (p.stderr or "")
    if on_event:
        for ln in log.splitlines():
            if ln.strip():
                on_event(ln[:200])
    url = _result_url(p.stdout or "")
    if not url:
        return {"status": "failed", "error": "결과 URL 없음", "log_tail": log[-300:]}
    if not _download(url, out):
        return {"status": "failed", "error": f"다운로드 실패: {url}"}
    return {"status": "completed", "path": str(out),
            "rel": out.relative_to(proj_dir).as_posix(), "url": url}


def _result_url(stdout: str) -> str:
    """--wait --json 출력에서 결과 mp4 URL 추출."""
    try:
        for blob in re.findall(r"\{.*\}", stdout, re.DOTALL):
            try:
                d = json.loads(blob)
            except Exception:
                continue
            u = _find_url(d)
            if u:
                return u
    except Exception:
        pass
    m = re.search(r"https?://\S+\.mp4", stdout)   # 폴백: 평문 URL
    return m.group(0) if m else ""


def _find_url(obj) -> str:
    """중첩 dict/list에서 첫 mp4/영상 url 탐색."""
    if isinstance(obj, str):
        return obj if obj.startswith("http") and (".mp4" in obj or "/video" in obj) else ""
    if isinstance(obj, dict):
        for k in ("url", "video_url", "output_url", "result_url", "download_url"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for v in obj.values():
            u = _find_url(v)
            if u:
                return u
    if isinstance(obj, list):
        for v in obj:
            u = _find_url(v)
            if u:
                return u
    return ""


def _to_sec(t: str) -> int:
    """'20m'/'90s'/'1h' → 초. 기본 1200."""
    m = re.match(r"(\d+)\s*([smh]?)", str(t or "").strip())
    if not m:
        return 1200
    n = int(m.group(1))
    return n * {"s": 1, "m": 60, "h": 3600, "": 60}[m.group(2)]
