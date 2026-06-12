"""인메모리 job 레지스트리 (스레드세이프)."""
from __future__ import annotations

import itertools
import threading


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._counter = itertools.count(1)

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
