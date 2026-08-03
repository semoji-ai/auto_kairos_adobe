from pathlib import Path
from backend import verify_voice

GOOD = """스팸은 1937년 미국에서 태어났습니다.

무려 80년이 넘는 역사를 가진 통조림이죠.

그런데,
한국에서는 명절 선물세트로 팔리고 있습니다.

해외 언론들도 놀라워하며 기사를 쏟아냈다고 합니다.

하지만 서양에서는 싸구려 햄으로 취급받고 있는데요.

이것은 단순한 통조림이 아니었습니다.
전쟁과 함께 세계로 퍼져나간 음식이거든요.
"""

PLAIN = """스팸은 1937년 미국에서 태어났다.
80년이 넘는 역사를 가진 통조림이다.
한국에서는 선물세트로 팔리게 됐다.
해외 언론들도 기사를 쏟아냈다.
전쟁과 함께 세계로 퍼졌다.
"""


def test_good_passes():
    r = verify_voice.check(GOOD)
    assert r["ok"], r["violations"]


def test_plain_endings_fail():
    r = verify_voice.check(PLAIN)
    assert not r["ok"]
    assert any("평서체" in v for v in r["violations"])


def test_hangul_year_fails():
    r = verify_voice.check(GOOD.replace("1937년", "천구백삼십칠년"))
    assert not r["ok"]
    assert any("숫자" in v for v in r["violations"])


def test_uniform_lines_fail():
    txt = "\n".join(["스팸은 미국에서 태어난 음식입니다."] * 30)
    r = verify_voice.check(txt)
    assert not r["ok"]
    assert any("리듬" in v or "균일" in v for v in r["violations"])


def test_meta_lines_excluded():
    txt = GOOD + "\n[B-roll: 공장 전경]\n(연출: 줌인)\n"
    r = verify_voice.check(txt)
    assert r["ok"], r["violations"]


def test_gate_rewrites_once_on_fail(tmp_path, monkeypatch):
    """게이트 실패 → 위반 겨냥 재작성 1회 → 재채점."""
    from backend import pipeline
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "plan.md").write_text("# t\n\n채널: semoji\n분량: 5분\n", encoding="utf-8")
    (proj / "final_manuscript.md").write_text(PLAIN, encoding="utf-8")
    calls = []
    def fake_run_skill(prompt, proj_dir, **kw):
        calls.append(prompt)
        (proj / "final_manuscript.md").write_text(GOOD, encoding="utf-8")
        return {"returncode": 0, "session_id": None}
    monkeypatch.setattr(pipeline, "run_skill", fake_run_skill)
    r = pipeline.apply_voice_gate(proj)
    assert r["gate"] == "pass"
    assert len(calls) == 1 and "평서체" in calls[0]


def test_gate_skipped_for_other_channels(tmp_path):
    from backend import pipeline
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "plan.md").write_text("# t\n\n채널: iromism\n", encoding="utf-8")
    assert pipeline.apply_voice_gate(proj)["gate"] == "skipped"
