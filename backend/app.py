"""auto_kairos Adobe PD Assistant — 최소 백엔드 (PoC).

의존성 0 (Python 표준 라이브러리만). CEP 패널이 /health 로 연결을 확인한다.
codex 상태(바이너리 + 로그인 인증)도 함께 보고한다.

실행:  python3 backend/app.py   (기본 포트 8765)
"""
from __future__ import annotations

import json
import os
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VERSION = "0.1.0-poc"
PORT = int(os.environ.get("AK_BACKEND_PORT", "8765"))


def codex_status() -> str:
    """codex CLI 설치 + 로그인 인증 여부."""
    if shutil.which("codex") is None:
        return "not_installed"
    if (Path.home() / ".codex" / "auth.json").exists():
        return "ready"
    return "not_authenticated"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        # CEP 패널(file://)에서의 fetch 허용
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._send(200, {
                "backend_status": "connected",
                "codex_status": codex_status(),
                "auto_kairos_root": str(Path.home() / "LocalProjects"),
                "version": VERSION,
            })
        else:
            self._send(404, {"error": "not found", "path": self.path})

    def log_message(self, fmt, *args):  # 조용히
        pass


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"[auto_kairos backend] http://127.0.0.1:{PORT}/health  (codex={codex_status()})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
