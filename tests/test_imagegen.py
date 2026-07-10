from pathlib import Path
from backend import imagegen


def test_versioned_path_first(tmp_path):
    p = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p.name == "ref_1.png"


def test_versioned_path_no_overwrite(tmp_path):
    (tmp_path / "ref_1.png").write_text("x", encoding="utf-8")
    p = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p.name == "ref_1_v2.png"
    (tmp_path / "ref_1_v2.png").write_text("x", encoding="utf-8")
    p2 = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p2.name == "ref_1_v3.png"


def test_is_rate_limited():
    assert imagegen.is_rate_limited("image_gen rate limit으로 실패") is True
    assert imagegen.is_rate_limited("OK 저장 완료") is False


def test_build_image_prompt():
    pr = imagegen.build_image_prompt("전기차 한 대", "STYLE_DESC", "images/ref_1.png")
    assert "STYLE_DESC" in pr
    assert "전기차 한 대" in pr
    assert "images/ref_1.png" in pr
    assert "image_gen" in pr


def test_build_image_prompt_nochar_forbids_base_person():
    pr = imagegen.build_image_prompt("전기차 충전 장면", "STYLE", "images/s1.png")
    # 공냥 긍정형 — 무캐릭터는 '배경과 사물만/무인 장면'으로(부정문 없이)
    assert "배경과 사물만" in pr and "무인" in pr
    assert "캐릭터 시트" not in pr
    for neg in ("말 것", "금지", "없음"):        # 네거티브 0개
        assert neg not in pr, neg


def test_build_image_prompt_character_branch():
    pr = imagegen.build_image_prompt("지오가 차를 가리킴", "STYLE", "images/s1.png",
                                     has_character_ref=True)
    assert "1번 캐릭터 시트" in pr and "100% 동일" in pr
    assert "세모지 베이스" in pr


def test_build_character_prompt_restyle():
    pr = imagegen.build_character_prompt("지오", "갈색 머리, 크림 셔츠", "characters/char_지오.png")
    assert "1번 이미지의 캐릭터를 '지오'" in pr
    assert "그대로 유지" in pr and "헤어와 의상만" in pr
    assert "characters/char_지오.png" in pr
    # 비율은 첨부 이미지가 정한다(긍정형 — "지정하지 말 것" 부정문 대신)
    assert "비율은 첨부한 1번 이미지가 정한다" in pr


def test_generate_one_attaches_base(tmp_path, monkeypatch):
    """character_ref 없으면 베이스만 첨부, has_character_ref=False로 빌드."""
    from backend import imagegen as ig
    seen = {}

    def fake_run(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        seen["images"] = images
        seen["prompt"] = prompt
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run)
    monkeypatch.setattr(ig, "base_img", lambda: tmp_path / "semoji_base.jpg")
    res = ig.generate_one(tmp_path, "ref_1.png", "전기차")
    assert res["status"] == "completed"
    assert seen["images"] == [str(tmp_path / "semoji_base.jpg")]
    assert "배경과 사물만" in seen["prompt"]        # 무캐릭터 긍정형 분기


def test_generate_one_with_character_ref_order(tmp_path, monkeypatch):
    """character_ref 주면 [캐릭터, 베이스] 순서로 첨부 + 캐릭터 분기."""
    from backend import imagegen as ig
    seen = {}

    def fake_run(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        seen["images"] = images
        seen["prompt"] = prompt
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run)
    monkeypatch.setattr(ig, "base_img", lambda: tmp_path / "base.jpg")
    res = ig.generate_one(tmp_path, "s1.png", "지오가 차를 가리킴",
                          character_ref=str(tmp_path / "char_지오.png"))
    assert res["status"] == "completed"
    assert seen["images"] == [str(tmp_path / "char_지오.png"), str(tmp_path / "base.jpg")]
    assert "1번 캐릭터 시트" in seen["prompt"]


def test_generate_character_needs_base(tmp_path, monkeypatch):
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "base_img", lambda: None)
    res = ig.generate_character(tmp_path, "지오", "갈색 머리")
    assert res["status"] == "failed" and "semoji_base" in res["error"]


def test_generate_character_attaches_base(tmp_path, monkeypatch):
    from backend import imagegen as ig
    seen = {}

    def fake_run(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        seen["images"] = images
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run)
    monkeypatch.setattr(ig, "base_img", lambda: tmp_path / "base.jpg")
    res = ig.generate_character(tmp_path, "지오", "갈색 머리, 크림 셔츠")
    assert res["status"] == "completed"
    assert seen["images"] == [str(tmp_path / "base.jpg")]
    assert (tmp_path / "characters" / "char_지오.png").exists()


def test_versioned_path_in_subdir_concept(tmp_path):
    sb = tmp_path / "storyboard"; sb.mkdir()
    p = imagegen.versioned_path(sb, "sb_1.png")
    assert p.parent.name == "storyboard"
    assert p.name == "sb_1.png"


def test_build_layer_prompt_character():
    p = imagegen.build_layer_prompt("character", "STYLE", "char_1.png")
    # built-in 엔진 — 크로마키 그린(#00FF00), rel_out은 프롬프트에 넣지 않음(회수 방식)
    assert "인물" in p and "#00FF00" in p and "STYLE" in p


def test_build_layer_prompt_background():
    p = imagegen.build_layer_prompt("background", "STYLE", "bg_1.png")
    assert "배경" in p and "STYLE" in p
    assert "마젠타" not in p and "#00FF00" not in p     # 배경 레이어는 크로마 채움 없음


def test_generate_many_runs_all(tmp_path, monkeypatch):
    from backend import imagegen as ig
    calls = []

    def fake_one(proj_dir, rel_out, image_prompt, *, subdir="images", **kw):
        calls.append(rel_out)
        out = proj_dir / subdir / rel_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "generate_one", fake_one)
    items = [("a.png", "p1"), ("b.png", "p2"), ("c.png", "p3")]
    results = ig.generate_many(tmp_path, items, subdir="storyboard", concurrency=3)
    assert len(results) == 3
    assert all(r["status"] == "completed" for r in results.values())
    assert set(calls) == {"a.png", "b.png", "c.png"}


def test_generate_many_concurrency_min_one(tmp_path, monkeypatch):
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "generate_one",
                        lambda proj_dir, rel_out, p, **kw: {"status": "completed", "path": rel_out})
    results = ig.generate_many(tmp_path, [("a.png", "p")], concurrency=0)
    assert len(results) == 1


def test_build_element_layer_prompt():
    p = imagegen.build_element_layer_prompt("왼쪽 전기차", "프레임 왼쪽", "STYLE", "layers/x.png")
    # built-in 엔진 — 크로마키 그린(#00FF00), rel_out은 프롬프트에 넣지 않음(회수 방식)
    assert "왼쪽 전기차" in p and "#00FF00" in p and "STYLE" in p
    assert "얹혀" in p          # 위에 얹힌 것 함께 그림(베이스 포함)


def test_build_element_layer_prompt_excludes_others():
    # 다른 선택 요소(문서)는 별도 레이어이므로 책상 레이어에서 제외
    p = imagegen.build_element_layer_prompt("책상", "중앙", "STYLE", "layers/d.png", others=["문서", "책상"])
    assert "별도 레이어" in p and "문서" in p
    # 자기 자신(책상)은 제외 목록에 안 들어감
    assert p.count("책상") >= 1


def test_analyze_scene_layers_parses(tmp_path, monkeypatch):
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir(); img = proj / "storyboard" / "s.png"; img.write_bytes(b"\x89PNG")

    def fake_run(prompt, cwd, *, output_schema=None, output_last=None, images=None, on_line=None, **kw):
        from pathlib import Path as _P
        _P(output_last).write_text('{"elements":[{"name":"전기차","location":"왼쪽"},'
                                   '{"name":"인물","location":"오른쪽"}]}', encoding="utf-8")
        return {"returncode": 0, "output_last": output_last}

    monkeypatch.setattr(ig.llm, "run_orchestrator", fake_run)
    res = ig.analyze_scene_layers(proj, str(img))
    assert [e["name"] for e in res["elements"]] == ["전기차", "인물"]


def test_analyze_scene_layers_prompt_uses_narration(tmp_path, monkeypatch):
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir(); img = proj / "storyboard" / "s.png"; img.write_bytes(b"\x89PNG")
    cap = {}

    def fake_run(prompt, cwd, *, output_schema=None, output_last=None, images=None, on_line=None, **kw):
        cap["prompt"] = prompt
        from pathlib import Path as _P
        _P(output_last).write_text('{"elements":[]}', encoding="utf-8")
        return {"returncode": 0, "output_last": output_last}

    monkeypatch.setattr(ig.llm, "run_orchestrator", fake_run)
    ig.analyze_scene_layers(proj, str(img), narration="아이가 전기차를 향해 달려간다", context="제목: 의미")
    assert "아이가 전기차를 향해 달려간다" in cap["prompt"]   # 내레이션 주입
    assert "캐릭터" in cap["prompt"]                          # 1순위: 캐릭터 전원
    assert "가리는" in cap["prompt"]                           # 2순위: 전경 가림
    assert "우선순위" in cap["prompt"]                         # 기준이 우선순위로 명시


def _green_stub(ratio):
    """chroma_key_green(현행 파이프라인이 호출) 대역 — 위치 QC용 키잉본(투명)을 실제로 써서
    position_score 경로를 태우고 transparent_ratio를 통제한다.
    ratio가 콜러블이면 매 호출 값을 뽑는다(재시도별 다른 값)."""
    from PIL import Image

    def _f(src, out):
        try:
            size = Image.open(src).size
        except Exception:
            size = (100, 100)
        Image.new("RGBA", size, (0, 0, 0, 0)).save(out)     # QC 키잉본(투명) 기록
        return {"transparent_ratio": ratio() if callable(ratio) else ratio}
    return _f


def test_split_scene_to_elements(tmp_path, monkeypatch):
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir(); img = proj / "storyboard" / "s.png"; img.write_bytes(b"\x89PNG")
    made = []

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        out.write_bytes(b"\x89PNG"); made.append(out.name)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    res = ig.split_scene_to_elements(proj, str(img), "sid9",
                                     [{"name": "전기차", "location": "왼쪽"},
                                      {"name": "인물", "location": "오른쪽"}], concurrency=2)
    names = [r["rel"] for r in res["layers"]]
    # 요소 2개 + 배경 1개
    assert any("sid9__0" in n for n in names) and any("sid9__1" in n for n in names)
    assert any("sid9__bg" in n for n in names)


def test_chroma_key_magenta(tmp_path):
    from PIL import Image
    from backend import imagegen
    im = Image.new("RGBA", (4, 2), (255, 0, 255, 255))
    for y in range(2):
        im.putpixel((2, y), (30, 60, 200, 255))
        im.putpixel((3, y), (30, 60, 200, 255))
    src = tmp_path / "m.png"; im.save(src)
    out = tmp_path / "t.png"
    res = imagegen.chroma_key_magenta(src, out)
    from PIL import Image as I
    r = I.open(out).convert("RGBA")
    assert r.getpixel((0, 0))[3] == 0
    assert r.getpixel((3, 0))[3] == 255
    assert res["transparent_ratio"] > 0.4


def test_archive_prev_layers_moves_not_deletes(tmp_path):
    from backend import imagegen as ig
    lay = tmp_path / "layers"; lay.mkdir()
    (lay / "sid9__0_old.png").write_bytes(b"\x89PNG")
    (lay / "sid9__bg.png").write_bytes(b"\x89PNG")
    (lay / "other__0_x.png").write_bytes(b"\x89PNG")     # 다른 씬 — 유지
    moved = ig._archive_prev_layers(lay, "sid9")
    assert moved == 2
    assert not (lay / "sid9__0_old.png").exists()        # 활성 폴더에서 빠짐
    assert (lay / "_prev" / "sid9__0_old.png").exists()  # 보존됨(무삭제)
    assert (lay / "other__0_x.png").exists()             # 다른 씬 그대로


def test_normalize_layer_size_resizes(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = tmp_path / "L.png"
    Image.new("RGBA", (1672, 941), (255, 0, 0, 255)).save(p)   # codex 변칙 크기
    changed = ig.normalize_layer_size(p, (1536, 1024))
    assert changed is True
    assert Image.open(p).size == (1536, 1024)


def test_normalize_layer_size_noop_when_match(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = tmp_path / "L.png"
    Image.new("RGBA", (1536, 1024)).save(p)
    assert ig.normalize_layer_size(p, (1536, 1024)) is False    # 이미 일치 → 무변경


def test_split_normalizes_to_scene_size(tmp_path, monkeypatch):
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"
    Image.new("RGB", (1536, 1024)).save(scene)                  # 씬 = 1536x1024

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", (1672, 941), (0, 255, 0, 255)).save(out)   # 변칙 크기로 생성
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    res = ig.split_scene_to_elements(proj, str(scene), "sz1",
                                     [{"name": "차", "location": "왼쪽"}], concurrency=1)
    for r in res["layers"]:
        assert Image.open(proj / r["rel"]).size == (1536, 1024)  # 요소+배경 모두 씬 크기


def _mk_magenta_test_img(tmp_path):
    """중앙 빨강 사각형 + 마젠타 배경 + 경계 혼합색 1px 띠."""
    from PIL import Image
    im = Image.new("RGB", (100, 100), (255, 0, 255))          # 순수 마젠타
    for y in range(30, 70):
        for x in range(30, 70):
            im.putpixel((x, y), (200, 30, 40))                # 요소(빨강)
    for x in range(29, 71):                                    # 경계 혼합(반쯤 마젠타)
        im.putpixel((x, 29), (228, 15, 148)); im.putpixel((x, 70), (228, 15, 148))
    p = tmp_path / "m.png"; im.save(p)
    return p


def test_soft_chroma_core_kept_bg_removed(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = _mk_magenta_test_img(tmp_path)
    r = ig.chroma_key_magenta(p, p)
    out = Image.open(p).convert("RGBA")
    assert out.getpixel((50, 50))[3] == 255                   # 요소 중심 불투명
    assert out.getpixel((5, 5))[3] == 0                       # 마젠타 배경 완전 투명
    assert 0.5 < r["transparent_ratio"] < 0.95                # 비율 신호 유지


def test_soft_chroma_edge_soft_alpha(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = _mk_magenta_test_img(tmp_path)
    ig.chroma_key_magenta(p, p)
    out = Image.open(p).convert("RGBA")
    a = out.getpixel((50, 29))[3]                              # 혼합 경계 픽셀
    assert a < 255                                             # 이진(255)이 아니라 소프트


class _Proc:
    """subprocess.run 반환 대역 — codex built-in 엔진은 stdout(JSONL)만 파싱한다."""
    def __init__(self, stdout="", stderr="", returncode=0):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _mk_gen_png(gen_dir, tid, name="ig_1.png", data=b"\x89PNG-generated"):
    """가짜 codex 산출물 — _GEN_DIR/<thread_id>/<name> 생성(회수 대상)."""
    d = gen_dir / tid
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_bytes(data)
    return p


def test_run_codex_image_builtin_success(tmp_path, monkeypatch):
    """성공: stdout에 thread_id → _GEN_DIR/<tid>/*.png 회수 → out 복사."""
    from backend import imagegen as ig
    gen = tmp_path / "generated_images"
    monkeypatch.setattr(ig, "_GEN_DIR", gen)
    tid = "0199aaaa-bbbb-cccc-dddd"

    def fake_run(cmd, input=None, env=None, **k):
        _mk_gen_png(gen, tid)
        return _Proc(stdout='{"thread_id":"%s"}\n' % tid)

    monkeypatch.setattr(ig.subprocess, "run", fake_run)
    out = tmp_path / "o.png"
    res = ig._run_codex_image(tmp_path, out, "전기차", retries=0)
    assert res["status"] == "completed" and out.exists()
    assert out.read_bytes() == b"\x89PNG-generated"


def test_run_codex_image_no_thread_id(tmp_path, monkeypatch):
    """stdout에 thread_id 없음 → no_file(회수 불가)."""
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "_GEN_DIR", tmp_path / "generated_images")
    monkeypatch.setattr(ig.subprocess, "run",
                        lambda *a, **k: _Proc(stdout="done, no id here"))
    res = ig._run_codex_image(tmp_path, tmp_path / "x.png", "p", retries=0)
    assert res["status"] == "failed" and res["error"] == "no_file"


def test_run_codex_image_thread_no_png(tmp_path, monkeypatch):
    """thread 폴더는 있으나 png 없음 → no_file."""
    from backend import imagegen as ig
    gen = tmp_path / "generated_images"
    tid = "0199-empty-thread"
    (gen / tid).mkdir(parents=True)
    monkeypatch.setattr(ig, "_GEN_DIR", gen)
    monkeypatch.setattr(ig.subprocess, "run",
                        lambda *a, **k: _Proc(stdout='{"thread_id":"%s"}' % tid))
    res = ig._run_codex_image(tmp_path, tmp_path / "x.png", "p", retries=0)
    assert res["status"] == "failed" and res["error"] == "no_file"


def test_run_codex_image_copy_guard(tmp_path, monkeypatch):
    """회수 파일 md5 == 첨부 md5 → 복사(생성 아님) → failed."""
    from backend import imagegen as ig
    gen = tmp_path / "generated_images"
    monkeypatch.setattr(ig, "_GEN_DIR", gen)
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"IDENTICAL-BYTES")
    tid = "0199-copy-guard"

    def fake_run(cmd, input=None, env=None, **k):
        _mk_gen_png(gen, tid, data=b"IDENTICAL-BYTES")   # 첨부와 동일 = 복사
        return _Proc(stdout='{"thread_id":"%s"}' % tid)

    monkeypatch.setattr(ig.subprocess, "run", fake_run)
    out = tmp_path / "o.png"
    res = ig._run_codex_image(tmp_path, out, "p", images=[str(ref)], retries=0)
    assert res["status"] == "failed"


def test_run_codex_image_classifies_rate_limit(tmp_path, monkeypatch):
    """rate limit 문자열 감지 → error=='rate_limit'(백오프 재시도 후 실패)."""
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "_GEN_DIR", tmp_path / "generated_images")
    monkeypatch.setattr(ig.time, "sleep", lambda s: None)
    monkeypatch.setattr(ig.subprocess, "run",
                        lambda *a, **k: _Proc(stdout="openai rate limit exceeded (429)"))
    res = ig._run_codex_image(tmp_path, tmp_path / "x.png", "p", retries=1)
    assert res["status"] == "failed" and res["error"] == "rate_limit"


def test_run_codex_image_strips_openai_key_from_env(tmp_path, monkeypatch):
    """API 금지 계약: subprocess.run에 전달되는 env에 OPENAI_API_KEY가 없어야 함."""
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "_GEN_DIR", tmp_path / "generated_images")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-pass")
    seen = {}

    def fake_run(cmd, input=None, env=None, **k):
        seen["env"] = env
        return _Proc(stdout="no id")

    monkeypatch.setattr(ig.subprocess, "run", fake_run)
    ig._run_codex_image(tmp_path, tmp_path / "x.png", "p", retries=0)
    assert "OPENAI_API_KEY" not in seen["env"]     # codex 환경에 키 미전달


def test_run_codex_image_attaches_refs_and_imagegen_stdin(tmp_path, monkeypatch):
    """참조 첨부: images → cmd에 '-i <path>', 엔진 플래그, stdin은 '/imagegen ' 시작."""
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "_GEN_DIR", tmp_path / "generated_images")
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"REF")
    seen = {}

    def fake_run(cmd, input=None, env=None, **k):
        seen["cmd"] = cmd
        seen["input"] = input
        return _Proc(stdout="no id")

    monkeypatch.setattr(ig.subprocess, "run", fake_run)
    ig._run_codex_image(tmp_path, tmp_path / "x.png", "p", images=[str(ref)], retries=0)
    assert "-i" in seen["cmd"]
    i = seen["cmd"].index("-i")
    assert seen["cmd"][i + 1] == str(ref)          # 참조가 -i 인자로
    assert "image_generation" in seen["cmd"]       # built-in 엔진 활성화 플래그
    assert seen["input"].startswith("/imagegen ")  # stdin은 /imagegen 프롬프트
    assert "정확히 1장" in seen["input"]           # 후보 낭비 완화 긍정형 지시


def test_split_qc_retries_on_bad_ratio(tmp_path, monkeypatch):
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)
    calls = {"n": 0}

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        calls["n"] += 1
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    # 1차: ratio 0.01(불량 — 전체를 그림), 2차: 0.6(정상)
    ratios = iter([0.01, 0.6])
    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(lambda: next(ratios)))
    res = ig.split_scene_to_elements(proj, str(scene), "qc1",
                                     [{"name": "차", "location": "왼쪽"}], concurrency=1)
    el = res["layers"][0]
    assert calls["n"] >= 3                       # 요소 1차+재시도 + 배경 1
    assert el["status"] == "completed" and el.get("qc") == "retried_ok"


def test_split_qc_marks_lowq_after_retry(tmp_path, monkeypatch):
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.005))  # 항상 불량
    res = ig.split_scene_to_elements(proj, str(scene), "qc2",
                                     [{"name": "차", "location": "왼쪽"}], concurrency=1)
    el = res["layers"][0]
    assert el["status"] == "completed_lowq"      # 보존하되 저품질 표시(무삭제)


def _scene_with_red_box(tmp_path):
    """원본: 회색 바탕 + (30,30)-(70,70) 빨강 사각형."""
    from PIL import Image
    im = Image.new("RGB", (100, 100), (90, 90, 90))
    for y in range(30, 70):
        for x in range(30, 70):
            im.putpixel((x, y), (200, 30, 40))
    p = tmp_path / "scene.png"; im.save(p)
    return p


def _layer_box(tmp_path, name, x0, y0):
    """레이어: 투명 바탕 + (x0,y0)부터 40px 빨강 사각형(불투명)."""
    from PIL import Image
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for y in range(y0, y0 + 40):
        for x in range(x0, x0 + 40):
            im.putpixel((x, y), (200, 30, 40, 255))
    p = tmp_path / name; im.save(p)
    return p


def test_position_score_high_when_in_place(tmp_path):
    from backend import imagegen as ig
    scene = _scene_with_red_box(tmp_path)
    layer = _layer_box(tmp_path, "ok.png", 30, 30)      # 원위치
    assert ig.position_score(layer, scene) > 0.9


def test_position_score_low_when_displaced(tmp_path):
    from backend import imagegen as ig
    scene = _scene_with_red_box(tmp_path)
    layer = _layer_box(tmp_path, "off.png", 0, 55)      # 어긋난 위치(회색 영역 위)
    assert ig.position_score(layer, scene) < 0.5


def test_split_qc_retries_on_bad_position(tmp_path, monkeypatch):
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"
    Image.new("RGB", (100, 100)).save(scene)
    calls = {"n": 0}

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        calls["n"] += 1
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    pos_seq = iter([0.2, 0.9])                           # 1차 어긋남 → 재시도 정상
    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    monkeypatch.setattr(ig, "position_score", lambda L, S: next(pos_seq, 0.9))
    res = ig.split_scene_to_elements(proj, str(scene), "pq1",
                                     [{"name": "차", "location": "왼쪽"}], concurrency=1)
    el = res["layers"][0]
    assert el["status"] == "completed" and el["qc"] == "retried_ok"
    assert calls["n"] >= 3                               # 요소 2회 + 배경 1회


def test_split_retry_uses_new_file_path(tmp_path, monkeypatch):
    """E2E 발견 버그 회귀: 재시도는 1차본을 덮어쓰지 말고 새 버전 파일(out2)로 출력해야 한다.
    built-in 엔진은 rel_out을 프롬프트에 싣지 않으므로(회수 방식) 출력 대상은 _run_codex_image의 out 인자로 확인."""
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)
    outs = []

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        outs.append(Path(out).name)
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    pos_seq = iter([0.2, 0.9])                          # 1차 어긋남 → 재시도 OK
    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    monkeypatch.setattr(ig, "position_score", lambda L, S: next(pos_seq, 0.9))
    res = ig.split_scene_to_elements(proj, str(scene), "rp1",
                                     [{"name": "차", "location": "왼쪽"}], concurrency=1)
    el = res["layers"][0]
    assert el["qc"] == "retried_ok" and el["pos_score"] == 0.9     # 최종 pos 보고
    assert outs[0] == "rp1__0_차.png"                   # 1차는 원본 경로
    assert outs[1] == "rp1__0_차_v2.png"                # 재시도는 새 버전 파일(1차 덮어쓰기 방지)
    assert el["rel"].endswith("_v2.png")


def test_split_lowq_keeps_green_raw_single_keying(tmp_path, monkeypatch):
    """현행: lowq 확정 시 그린 출력은 raw 그대로 유지(AE에서 키잉) — 최종본 재키잉 없음.
    QC 키잉본은 각 시도 파일에 1회씩만(최종 1차본 재적용 없음)."""
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)
    keyed = []

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    def fake_green(a, b):
        keyed.append(Path(a).name)
        Image.new("RGBA", (100, 100), (0, 0, 0, 0)).save(b)   # QC 키잉본 기록(위치 QC 경로 유지)
        return {"transparent_ratio": 0.5}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", fake_green)
    monkeypatch.setattr(ig, "position_score", lambda L, S: 0.1)    # 항상 어긋남 → lowq
    res = ig.split_scene_to_elements(proj, str(scene), "lq1",
                                     [{"name": "차", "location": "왼쪽"}], concurrency=1)
    el = res["layers"][0]
    assert el["status"] == "completed_lowq"
    first = Path(el["rel"]).name
    assert keyed.count(first) == 1                       # 최종(1차)본은 QC용 1회만(재키잉 없음)


def test_split_retry_retires_loser_no_duplicates(tmp_path, monkeypatch):
    """재시도 성공 시 탈락 1차본이 _prev로 이동 — 활성 폴더에 같은 요소 1장만(중복 방지)."""
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    pos_seq = iter([0.2, 0.9])                          # 1차 탈락 → 재시도 합격
    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    monkeypatch.setattr(ig, "position_score", lambda L, S: next(pos_seq, 0.9))
    ig.split_scene_to_elements(proj, str(scene), "dd1",
                               [{"name": "차", "location": "왼쪽"}], concurrency=1)
    active = [p.name for p in (proj / "layers").glob("dd1__0*.png")]
    assert active == ["dd1__0_차_v2.png"]               # 활성엔 합격본 1장만
    assert (proj / "layers" / "_prev" / "dd1__0_차.png").exists()   # 탈락본 보존


def test_split_lowq_retires_retry_file(tmp_path, monkeypatch):
    """재시도도 탈락(lowq) 시 재시도본이 _prev로 — 활성엔 1차본만."""
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    monkeypatch.setattr(ig, "position_score", lambda L, S: 0.1)     # 둘 다 탈락
    res = ig.split_scene_to_elements(proj, str(scene), "dd2",
                                     [{"name": "차", "location": "왼쪽"}], concurrency=1)
    active = [p.name for p in (proj / "layers").glob("dd2__0*.png")]
    assert active == ["dd2__0_차.png"]                  # 활성엔 1차본(lowq)만
    assert res["layers"][0]["status"] == "completed_lowq"


def test_split_writes_kinds_sidecar(tmp_path, monkeypatch):
    from PIL import Image
    from backend import imagegen as ig
    import json as _j
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    monkeypatch.setattr(ig, "position_score", lambda L, S: 0.9)
    ig.split_scene_to_elements(proj, str(scene), "kd",
                               [{"name": "남자", "location": "좌", "kind": "character"},
                                {"name": "책상", "location": "중앙", "kind": "object"}], concurrency=1)
    kinds = _j.loads((proj / "layers" / "kd__kinds.json").read_text(encoding="utf-8"))
    assert kinds == {"kd__0_남자_char": "character", "kd__1_책상": "object"}


def test_gen_semaphore_limits_concurrency(tmp_path, monkeypatch):
    """전역 세마포어 — 동시 codex 이미지 실행이 상한을 넘지 않음(초과분 대기)."""
    import threading, time
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "_GEN_DIR", tmp_path / "generated_images")
    monkeypatch.setattr(ig, "_GEN_SEMA", threading.BoundedSemaphore(2))
    state = {"cur": 0, "peak": 0}
    lock = threading.Lock()

    def fake_run(cmd, input=None, env=None, **kw):
        with lock:
            state["cur"] += 1
            state["peak"] = max(state["peak"], state["cur"])
        time.sleep(0.05)
        with lock:
            state["cur"] -= 1
        return _Proc(stdout="no thread id")               # 회수 불가 → no_file 경로

    monkeypatch.setattr(ig.subprocess, "run", fake_run)
    outs = [tmp_path / f"o{i}.png" for i in range(6)]
    ts = [threading.Thread(target=lambda o=o: ig._run_codex_image(tmp_path, o, "p", retries=0))
          for o in outs]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert state["peak"] <= 2                              # 상한 준수


def test_aspect_mismatch_detection(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = tmp_path / "a.png"
    Image.new("RGBA", (1024, 1536)).save(p)               # 세로형
    assert ig._aspect_mismatch(p, (1536, 1024)) is True
    Image.new("RGBA", (1530, 1020)).save(p)               # 같은 비율, 약간 작음
    assert ig._aspect_mismatch(p, (1536, 1024)) is False


def test_split_aspect_mismatch_triggers_retry_not_stretch(tmp_path, monkeypatch):
    """비율 다른 출력은 늘리지 않고(찌그러짐 방지) QC 재시도로 보냄."""
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (1536, 1024)).save(scene)
    sizes = iter([(1024, 1536), (1536, 1024)])            # 1차 세로형(불량) → 재시도 정상

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", next(sizes, (1536, 1024))).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    monkeypatch.setattr(ig, "position_score", lambda L, S: 0.9)
    res = ig.split_scene_to_elements(proj, str(scene), "ar1",
                                     [{"name": "차", "location": "좌", "kind": "object"}], concurrency=1)
    el = res["layers"][0]
    assert el["qc"] == "retried_ok"                       # 재시도로 회복
    assert Image.open(proj / el["rel"]).size == (1536, 1024)


def test_bg_retries_once_on_failure(tmp_path, monkeypatch):
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)
    calls = {"el": 0, "bg": 0}

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        if "__bg" in out.name:
            calls["bg"] += 1
            if calls["bg"] == 1:
                return {"status": "failed", "error": "rate_limit"}     # 1차 실패
        else:
            calls["el"] += 1
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    monkeypatch.setattr(ig, "position_score", lambda L, S: 0.9)
    res = ig.split_scene_to_elements(proj, str(scene), "bgr",
                                     [{"name": "차", "location": "좌", "kind": "object"}], concurrency=1)
    bg = res["layers"][-1]
    assert calls["bg"] == 2 and bg["status"] == "completed"           # 재시도로 생성


def test_split_names_character_layers_with_char_suffix(tmp_path, monkeypatch):
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"; Image.new("RGB", (100, 100)).save(scene)

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", (100, 100)).save(out)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_green", _green_stub(0.5))
    monkeypatch.setattr(ig, "position_score", lambda L, S: 0.9)
    res = ig.split_scene_to_elements(proj, str(scene), "cs",
                                     [{"name": "남자", "location": "좌", "kind": "character"},
                                      {"name": "책상", "location": "중앙", "kind": "object"}], concurrency=1)
    rels = [r["rel"] for r in res["layers"]]
    assert any(r.endswith("cs__0_남자_char.png") for r in rels)       # 캐릭터 → _char
    assert any(r.endswith("cs__1_책상.png") for r in rels)            # 사물 → 접미사 없음


def test_style_is_positive_smooth_no_negatives():
    """스타일 명세 — 공냥 긍정형: 매끄러운 플랫 표면을 '긍정'으로 명시하고,
    네거티브 트리거 어휘(grain/noise/halftone 등 '빼려는 대상')는 언급하지 않는다
    (gpt-image가 언급된 부정 대상을 오히려 렌더하는 문제 회피)."""
    from backend import imagegen
    style = imagegen.load_style().lower()
    # 긍정 평면 서술이 있어야
    assert "smooth" in style and "flat" in style and "uniform" in style
    # '빼려는 대상' 단어를 본문에 두지 않음(부정문 없이 긍정으로만 통제)
    for neg in ("no ", "grain", "halftone", "noise"):
        assert neg not in style, neg


def test_flatten_colors_quantizes(tmp_path):
    """flatten_colors — 그라데이션(얼룩)을 적은 색으로 평탄화(디더 없음)."""
    from PIL import Image
    from backend import imagegen
    im = Image.new("RGB", (60, 60))
    px = im.load()
    for x in range(60):
        for y in range(60):
            px[x, y] = (40 + x, 66, 80)        # 60단계 그라데이션
    p = tmp_path / "t.png"; im.save(p)
    before = len(Image.open(p).convert("RGB").getcolors(99999))
    assert imagegen.flatten_colors(p, colors=8) is True
    after = len(Image.open(p).convert("RGB").getcolors(99999))
    assert after <= 8 and after < before


def test_flatten_colors_disabled(tmp_path, monkeypatch):
    """AK_FLATTEN_COLORS=0 이면 비활성(원본 유지)."""
    from PIL import Image
    from backend import imagegen
    monkeypatch.setenv("AK_FLATTEN_COLORS", "0")
    im = Image.new("RGB", (20, 20), (10, 20, 30)); p = tmp_path / "t.png"; im.save(p)
    assert imagegen.flatten_colors(p) is False


def test_normalize_scene_image_cover_crop(tmp_path):
    from PIL import Image as _Im
    p = tmp_path / "s.png"
    _Im.new("RGB", (1659, 948), (10, 20, 30)).save(p)
    assert imagegen.normalize_scene_image(p) is True
    assert _Im.open(p).size == (1920, 1080)
    # 이미 타깃이면 no-op
    assert imagegen.normalize_scene_image(p) is False
