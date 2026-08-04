"""텍스트 파이프라인 순차 오케스트레이션."""
from __future__ import annotations

import json
import re

from pathlib import Path

from backend import skills_cfg, sessions, verify_voice
from backend.codex_runner import run_skill

PIPELINE = [
    "plan-explore", "deep-research", "draft-write",
    "target-research", "finalize-manuscript", "review-refine",
]


def build_judge_prompt(text: str) -> str:
    """이해도 심사 프롬프트 — regex가 못 재는 자연스러움·흐름을 LLM이 채점."""
    return (
        "다음 영상 나레이션 원고를 심사하라. 기준은 하나 — **중학생이 한 번 듣고 이해되고 편안하게 읽히는가**.\n"
        "구체 점검: 조사·어미가 자연스러운가 / 문장이 뚝뚝 끊기지 않고 이어지는가 / "
        "숫자·사실이 나열만 되지 않고 의미 부여가 따라오는가 / 시간 순서가 역행하지 않는가 / "
        "지표를 맞추려 억지로 넣은 듯한 문장(어색한 ~잖아요/~거든요 등)이 없는가.\n\n"
        "## 원고\n" + text + "\n\n"
        '결과를 JSON 한 줄로만 출력: {"pass": true|false, "issues": ["어색한 문장을 그대로 인용 + 무엇이 문제인지", ...]}\n'
        "사소한 취향 문제는 issues에 넣지 말 것 — 중학생 이해·흐름을 실제로 해치는 것만."
    )


def build_rewrite_prompt(text: str, metric_violations: list, flow_issues: list) -> str:
    """재작성 프롬프트 — 우선순위: 자연스러운 흐름 > 지표. 지표 스터핑 금지."""
    return (
        "다음 원고를 세모지 문체로 다듬어라.\n\n"
        "## 최우선 원칙\n"
        "- **자연스럽게 읽히는 흐름이 항상 우선이다.** 중학생이 한 번 듣고 이해되는 쉬운 문장, "
        "한 문장에 정보 1개, 숫자 나열 뒤 의미 부여, 시간 순서 유지.\n"
        "- 아래 지표는 그 안에서 충족하라. **지표를 맞추려 억지 문장을 끼워 넣는 것은 최악의 실패다** "
        "— 구어체(~거죠/~거든요)는 공감 지점에서 자연스러울 때만.\n"
        "- 분량을 줄여야 하면 문장을 토막 내지 말고 **덜 중요한 에피소드를 통째로 덜어내라.**\n"
        "- 사실·수치·모션그래픽 메타라인([B-roll], (연출:))은 유지한다.\n\n"
        + ("## 문체 지표 위반\n" + "\n".join(f"- {v}" for v in metric_violations) + "\n\n" if metric_violations else "")
        + ("## 흐름·이해도 문제(심사관 지적)\n" + "\n".join(f"- {v}" for v in flow_issues) + "\n\n" if flow_issues else "")
        + "## 원고\n" + text + "\n\n수정된 원고 전문(마크다운)만 출력."
    )


def _run_judge(proj_dir: Path, text: str, on_line=None) -> dict:
    """이해도 심사 실행 → {"pass": bool, "issues": [...]}. 파싱 실패 시 pass 처리(게이트 무한루프 방지)."""
    out = proj_dir / ".voice_judge.json"
    res = run_skill(build_judge_prompt(text), proj_dir, output_last=str(out), on_line=on_line)
    try:
        m = re.search(r"\{.*\}", out.read_text(encoding="utf-8"), re.S)
        v = json.loads(m.group(0))
        return {"pass": bool(v.get("pass")), "issues": list(v.get("issues", []))}
    except Exception:
        return {"pass": True, "issues": []}


def apply_voice_gate(proj_dir: Path, on_line=None) -> dict:
    """review-refine 뒤 문체 게이트. 채널에 voice 팩이 있을 때만 채점.
    실패 시 위반 항목만 겨냥해 1회 재작성 후 재채점(그래도 실패면 리포트만)."""
    proj_dir = proj_dir.resolve()   # 상대 경로면 output_last가 codex cwd 기준으로 이중 결합됨
    plan = skills_cfg.parse_plan_fields(proj_dir)
    channel = plan.get("채널", "")
    if channel != "semoji":
        return {"gate": "skipped"}
    out = proj_dir / "final_manuscript.md"
    max_rewrites = 3
    r = judge = None
    for rnd in range(max_rewrites + 1):
        r = verify_voice.check_project(proj_dir)
        judge = _run_judge(proj_dir, out.read_text(encoding="utf-8"), on_line=on_line)
        if on_line:
            on_line(f"[gate] 라운드 {rnd} — 지표: {'PASS' if r['ok'] else 'FAIL'} {r['metrics']} · "
                    f"이해도 심사: {'PASS' if judge['pass'] else 'FAIL'} {judge['issues'][:2]}")
        if r["ok"] and judge["pass"]:
            return {"gate": "pass", "metrics": r["metrics"], "rounds": rnd}
        if rnd == max_rewrites:
            break
        prompt = build_rewrite_prompt(out.read_text(encoding="utf-8"),
                                      r["violations"], judge["issues"])
        res = run_skill(prompt, proj_dir, session_id=sessions.load_session(proj_dir),
                        output_last=str(out), on_line=on_line)
        if res.get("session_id"):
            sessions.save_session(proj_dir, res["session_id"])
    return {"gate": "fail_after_rewrite", "metrics": r["metrics"],
            "rounds": max_rewrites, "violations": r["violations"] + judge["issues"]}


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
