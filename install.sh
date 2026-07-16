#!/bin/bash
# auto_kairos Adobe — 통합 부트스트랩(멱등).
#   클론 → ./install.sh → (키 채우기) → 실행.
# 자동: venv + pip + .env + 헬스체크.  체크만: codex/claude CLI(자동설치는 인증/라이선스라 안내만).
#   --cep       CEP 패널을 AE 확장 폴더에 링크(macOS, Adobe 시스템 설정 변경 — 옵트인).
#   --upscayl   이미지 업스케일 엔진(upscayl-bin + 모델)을 ~/.local/share/upscayl에 설치(옵트인).
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
GREEN=$'\033[32m'; YEL=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; NC=$'\033[0m'
ok(){ echo "  ${GREEN}✓${NC} $1"; }
warn(){ echo "  ${YEL}!${NC} $1"; }
bad(){ echo "  ${RED}✗${NC} $1"; }
has_flag(){ for a in "$@"; do :; done; for a in $FLAGS; do [ "$a" = "$1" ] && return 0; done; return 1; }
FLAGS="$*"

echo "== auto_kairos Adobe 설치 =="

# 1) Python venv (3.10+ 권장)
PY="$(command -v python3.12 || command -v python3.11 || command -v python3.10 || command -v python3 || true)"
if [ -z "$PY" ]; then bad "python3 없음 — 먼저 Python 3.10+ 설치"; exit 1; fi
PYVER="$($PY -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
echo "== 1) venv (.venv, python $PYVER) =="
case "$PYVER" in 3.9|3.8|3.7) warn "python $PYVER 감지 — 3.10+ 권장(구버전은 일부 타입힌트 이슈 가능)";; esac
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
./.venv/bin/pip -q install --upgrade pip >/dev/null 2>&1 || true
./.venv/bin/pip -q install -r requirements.txt && ok "requirements 설치(.venv)" || { bad "pip 설치 실패"; exit 1; }

# 2) .env
echo "== 2) .env =="
if [ -f .env ]; then ok ".env 존재(그대로 둠)"; else cp .env.example .env && ok ".env 생성(.env.example 복사) — 키를 채우세요"; fi

# 3) 외부 CLI 도구 확인(자동설치 안 함 — 인증 필요)
echo "== 3) 외부 도구(체크만) =="
if command -v codex >/dev/null 2>&1; then
  [ -f "$HOME/.codex/auth.json" ] && ok "codex 설치·인증됨(이미지·비전 엔진)" || warn "codex 설치됨·미인증 → 'codex login'"
else warn "codex 없음 → 설치 후 로그인(이미지 생성 필수). https://github.com/openai/codex"; fi
if command -v claude >/dev/null 2>&1; then ok "claude CLI 있음(기본 LLM 오케스트레이터)"
else warn "claude CLI 없음 → 설치(LLM 추론에 필요). https://docs.anthropic.com/claude-code"; fi

# 4) CEP 패널(옵트인)
echo "== 4) CEP 패널(AE 확장) =="
if has_flag --cep; then
  bash "$ROOT/scripts/setup_cep_dev.sh" && ok "CEP 패널 링크됨"
else
  echo "  ${DIM}건너뜀 — 링크하려면: ./install.sh --cep  (macOS, AE 확장 폴더에 심링크)${NC}"
fi

# 4b) 업스케일 엔진(옵트인) — upscayl-bin + 모델을 ~/.local/share/upscayl에
echo "== 4b) 업스케일 엔진(Upscayl) =="
UPS_DIR="$HOME/.local/share/upscayl"
if has_flag --upscayl; then
  if [ -x "$UPS_DIR/bin/upscayl-bin" ] && ls "$UPS_DIR/models/"*.param >/dev/null 2>&1; then
    ok "이미 설치됨($UPS_DIR)"
  else
    mkdir -p "$UPS_DIR/bin" "$UPS_DIR/models"
    OS="$(uname -s)"; ASSET="macos"; case "$OS" in Linux) ASSET="linux";; esac
    URL="$(curl -sL https://api.github.com/repos/upscayl/upscayl-ncnn/releases/latest \
           | grep browser_download_url | grep "$ASSET" | head -1 | cut -d'"' -f4)"
    if [ -n "$URL" ]; then
      TMP="$(mktemp -d)"; curl -sL "$URL" -o "$TMP/u.zip" && unzip -q -o "$TMP/u.zip" -d "$TMP"
      BINP="$(find "$TMP" -name upscayl-bin -type f | head -1)"
      [ -n "$BINP" ] && cp "$BINP" "$UPS_DIR/bin/upscayl-bin" && chmod +x "$UPS_DIR/bin/upscayl-bin"
      for m in digital-art-4x upscayl-standard-4x remacri-4x; do
        for e in param bin; do
          curl -sL "https://github.com/upscayl/upscayl/raw/main/resources/models/$m.$e" \
               -o "$UPS_DIR/models/$m.$e"
        done
      done
      rm -rf "$TMP"
      [ -x "$UPS_DIR/bin/upscayl-bin" ] && ok "업스케일 설치됨(모델: digital-art/standard/remacri)" \
        || bad "업스케일 바이너리 설치 실패"
    else
      bad "릴리스 URL 조회 실패 — 수동 설치 필요"
    fi
  fi
else
  echo "  ${DIM}건너뜀 — 설치하려면: ./install.sh --upscayl  (4K 업스케일, 로컬 GPU·키 불필요)${NC}"
fi

# 5) 헬스체크 — 모듈 임포트 + 데이터 자산
echo "== 5) 헬스체크 =="
./.venv/bin/python - <<'PY'
import sys
try:
    from backend import router, imagegen, tts, scene_analysis, manifest, sheets, scene_render, search, cues, video, upscale
    print("  \033[32m✓\033[0m backend 모듈 임포트 OK (v3/v4 런타임 의존 없음)")
except Exception as e:
    print("  \033[31m✗\033[0m 모듈 임포트 실패:", e); sys.exit(1)
from pathlib import Path
d = Path("data/artstyle")
need = ["semoji_base.jpg", "semoji_base_sheet.png", "semoji.md", "voices.json"]
miss = [n for n in need if not (d/n).is_file()]
print("  \033[32m✓\033[0m 데이터 자산 완비" if not miss else "  \033[31m✗\033[0m 누락 자산: "+", ".join(miss))
PY

echo ""
echo "완료. 다음:"
echo "  1) .env에 키 채우기(ELEVENLABS/SERPER 등 — 선택)"
echo "  2) 백엔드 실행:  ./.venv/bin/python backend/app.py"
echo "  3) CEP 패널 링크(미실행 시):  ./install.sh --cep  → AE에서 Window > Extensions"
