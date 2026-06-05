"""텍스트 파이프라인 순차 오케스트레이션."""
from __future__ import annotations

from pathlib import Path

from backend import skills_cfg, sessions
from backend.codex_runner import run_skill

PIPELINE = [
    "plan-explore", "deep-research", "draft-write",
    "target-research", "finalize-manuscript", "review-refine",
]


def run_one(skills_dir: Path, proj_dir: Path, name: str, on_line=None) -> dict:
    """단일 스킬 실행(세션 resume + 출력 캡처)."""
    cfg = skills_cfg.load_config(skills_dir, name)
    miss = skills_cfg.missing_inputs(cfg, proj_dir)
    if miss:
        return {"status": "failed", "error": f"입력 누락: {miss}"}
    prompt = skills_cfg.build_prompt(skills_dir, name, cfg, proj_dir)
    out = proj_dir / cfg["output"]
    out.parent.mkdir(parents=True, exist_ok=True)
    schema = (skills_dir / name / cfg["schema"]) if cfg.get("schema") else None
    sid = sessions.load_session(proj_dir)
    res = run_skill(
        prompt, proj_dir, session_id=sid,
        output_schema=str(schema) if schema else None,
        output_last=str(out), on_line=on_line,
    )
    if res.get("session_id"):
        sessions.save_session(proj_dir, res["session_id"])
    if res["returncode"] == 0 and out.exists():
        return {"status": "completed", "output": str(out)}
    return {"status": "failed", "error": f"rc={res['returncode']}", "stage": name}


def run_pipeline(skills_dir: Path, proj_dir: Path, on_line=None) -> dict:
    """PIPELINE 순차 실행. 한 단계 실패 시 중단."""
    done = []
    for name in PIPELINE:
        if on_line:
            on_line(f"[stage] {name}")
        r = run_one(skills_dir, proj_dir, name, on_line=on_line)
        if r["status"] != "completed":
            return {"status": "failed", "stage": name, "error": r.get("error"),
                    "completed": done}
        done.append(name)
    return {"status": "completed", "completed": done,
            "final": str(proj_dir / "final_manuscript.md")}
