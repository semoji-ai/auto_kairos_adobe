"""인메모리 job 레지스트리 (스레드세이프) + SSE 이벤트 발행(잡 로그/완료 푸시)."""
from __future__ import annotations

import itertools
import queue
import threading


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._subs: list[queue.Queue] = []      # SSE 구독자(연결당 큐)

    # ---- SSE 구독/발행 ----
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def _emit(self, event: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except queue.Full:
                pass                            # 느린 구독자는 이벤트 유실 — 폴백(GET /api/jobs)으로 복구

    def create(self, skill_name: str, project_id: str) -> str:
        with self._lock:
            jid = f"job_{next(self._counter)}"
            self._jobs[jid] = {
                "job_id": jid,
                "skill_name": skill_name,
                "project_id": project_id,
                "status": "running",
                "logs": [],
                "artifact_paths": [],
                "error": None,
                "result": None,
            }
            return jid

    def append_log(self, job_id: str, line: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["logs"].append(line)
        self._emit({"type": "log", "job_id": job_id, "line": line})

    def set_status(self, job_id: str, status: str,
                   artifact_paths: list[str] | None = None,
                   error: str | None = None,
                   result: dict | None = None) -> None:
        with self._lock:
            j = self._jobs.get(job_id)
            if not j:
                return
            j["status"] = status
            if artifact_paths is not None:
                j["artifact_paths"] = artifact_paths
            if error is not None:
                j["error"] = error
            if result is not None:
                j["result"] = result
        if status != "running":                 # 종결 이벤트 푸시(결과는 GET /api/jobs로 1회 조회)
            self._emit({"type": "status", "job_id": job_id, "status": status, "error": error})

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            j = self._jobs.get(job_id)
            return dict(j) if j else None

def run_async(jobs: JobRegistry, job_id: str, fn) -> None:
    """fn을 데몬 스레드로 실행. 반환 dict → result/completed, 예외 → failed."""
    def _work():
        try:
            res = fn()
            jobs.set_status(job_id, "completed",
                            result=res if isinstance(res, dict) else {"value": res})
        except Exception as e:
            jobs.set_status(job_id, "failed", error=str(e)[:300])
    threading.Thread(target=_work, daemon=True).start()
