"""텍스트 파이프라인 순차 오케스트레이션."""
from __future__ import annotations

from pathlib import Path

from backend import skills_cfg, sessions, verify_voice
from backend.codex_runner import run_skill

PIPELINE = [
    "plan-explore", "deep-research", "draft-write",
    "target-research", "finalize-manuscript", "review-refine",
]


def apply_voice_gate(proj_dir: Path, on_line=None) -> dict:
    """review-refine 뒤 문체 게이트. 채널에 voice 팩이 있을 때만 채점.
    실패 시 위반 항목만 겨냥해 1회 재작성 후 재채점(그래도 실패면 리포트만)."""
    proj_dir = proj_dir.resolve()   # 상대 경로면 output_last가 codex cwd 기준으로 이중 결합됨
    plan = skills_cfg.parse_plan_fields(proj_dir)
    channel = plan.get("채널", "")
    if channel != "semoji":
        return {"gate": "skipped"}
    r = verify_voice.check_project(proj_dir)
    if on_line:
        on_line(f"[gate] 문체 채점: {'PASS' if r['ok'] else 'FAIL'} {r['metrics']}")
    if r["ok"]:
        return {"gate": "pass", "metrics": r["metrics"]}
    out = proj_dir / "final_manuscript.md"
    prompt = (
        "다음 원고는 세모지 채널 문체 게이트에서 탈락했다. 아래 위반 항목만 정확히 고쳐라. "
        "사실·수치·구성·메타라인은 그대로 유지하고 문체(어미·리듬·표기)만 수정한다.\n\n"
        "## 위반 항목\n" + "\n".join(f"- {v}" for v in r["violations"]) +
        "\n\n## 원고\n" + out.read_text(encoding="utf-8") +
        "\n\n수정된 원고 전문(마크다운)만 출력."
    )
    res = run_skill(prompt, proj_dir, session_id=sessions.load_session(proj_dir),
                    output_last=str(out), on_line=on_line)
    if res.get("session_id"):
        sessions.save_session(proj_dir, res["session_id"])
    r2 = verify_voice.check_project(proj_dir)
    if on_line:
        on_line(f"[gate] 재작성 후: {'PASS' if r2['ok'] else 'FAIL'} {r2['metrics']}")
    return {"gate": "pass" if r2["ok"] else "fail_after_rewrite",
            "metrics": r2["metrics"], "violations": r2["violations"]}


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
        result = {"status": "completed", "output": str(out)}
        if name == "review-refine":
            result.update(apply_voice_gate(proj_dir, on_line=on_line))
        return result
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
