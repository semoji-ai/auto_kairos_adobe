import json
from pathlib import Path
from backend.router import handle_request
from backend.jobs import JobRegistry

ROOT = Path(__file__).resolve().parents[1] / "projects"


def _ctx():
    return {"root": ROOT, "jobs": JobRegistry()}


def test_health():
    code, body = handle_request("GET", "/health", {}, None, _ctx())
    assert code == 200
    assert body["backend_status"] == "connected"


def test_projects_list():
    code, body = handle_request("GET", "/api/projects", {}, None, _ctx())
    assert code == 200
    assert any(p["project_id"] == "demo01" for p in body["projects"])


def test_project_load():
    code, body = handle_request("POST", "/api/projects/load", {},
                                {"project_id": "demo01"}, _ctx())
    assert code == 200
    assert body["project_id"] == "demo01"


def test_unknown_404():
    code, body = handle_request("GET", "/nope", {}, None, _ctx())
    assert code == 404


def test_skills_run_returns_job_id(monkeypatch, tmp_path):
    import backend.router as r
    proj = tmp_path / "demoX"
    proj.mkdir()
    (proj / "final_manuscript.md").write_text("원고 텍스트.", encoding="utf-8")

    def fake_run(prompt, cwd, **kw):
        out = kw.get("output_last")
        if out:
            from pathlib import Path as _P
            _P(out).write_text(
                '{"version":"adobe-0.1","project_id":"demoX","total_scenes":0,"scenes":[]}',
                encoding="utf-8")
        return {"returncode": 0, "session_id": "sess-1", "output_last": out}

    monkeypatch.setattr(r, "run_skill", fake_run)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/skills/run", {},
                                {"project_id": "demoX", "skill_name": "scene-decompose"}, ctx)
    assert code == 200
    jid = body["job_id"]
    code2, jbody = handle_request("GET", f"/api/jobs/{jid}", {}, None, ctx)
    assert code2 == 200
    assert jbody["status"] == "completed"
    assert any("scenes.json" in a for a in jbody["artifact_paths"])


def test_skills_run_missing_manuscript_422(tmp_path):
    proj = tmp_path / "noman"
    proj.mkdir()
    (proj / "plan.md").write_text("# 제목", encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/skills/run", {},
                                {"project_id": "noman", "skill_name": "scene-decompose"}, ctx)
    assert code == 422
    assert "final_manuscript.md" in body["error"]


def test_projects_file_returns_manuscript():
    ctx = _ctx()
    code, body = handle_request("GET", "/api/projects/file",
                                {"project_id": "demo01", "name": "final_manuscript.md"}, None, ctx)
    assert code == 200
    assert body["name"] == "final_manuscript.md"
    assert "카지노" in body["content"]


def test_projects_file_rejects_traversal():
    ctx = _ctx()
    code, body = handle_request("GET", "/api/projects/file",
                                {"project_id": "demo01", "name": "../../backend/app.py"}, None, ctx)
    assert code == 400


def test_projects_file_404_missing():
    ctx = _ctx()
    code, body = handle_request("GET", "/api/projects/file",
                                {"project_id": "demo01", "name": "nope.md"}, None, ctx)
    assert code == 404


def test_projects_file_rejects_absolute(tmp_path):
    proj = tmp_path / "p1"; proj.mkdir()
    (proj / "final_manuscript.md").write_text("원고", encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/projects/file",
                                {"project_id": "p1", "name": "/etc/hosts"}, None, ctx)
    assert code == 400


def test_images_generate_from_references(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "references.json").write_text(
        '{"project_id":"p","references":[{"id":"ref_1","subject":"차","image_prompt":"전기차"}]}',
        encoding="utf-8")

    def fake_gen(proj_dir, rel_out, image_prompt, **kw):
        out = proj_dir / "images" / rel_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(r.imagegen, "generate_one", fake_gen)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/images/generate", {},
                                {"project_id": "p"}, ctx)
    assert code == 200
    assert body["generated"] == 1


def test_characters_generate(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()

    def fake_char(proj_dir, name, looks, **kw):
        out = proj_dir / "characters" / f"char_{name}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(r.imagegen, "generate_character", fake_char)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/characters/generate", {},
                                {"project_id": "p", "name": "지오", "looks": "갈색 머리"}, ctx)
    assert code == 200
    assert body["character"]["status"] == "completed"
    assert (proj / "characters" / "char_지오.png").exists()


def test_characters_generate_requires_fields(tmp_path):
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/characters/generate", {},
                                {"project_id": "p", "name": "지오"}, ctx)
    assert code == 400


def test_characters_list(tmp_path):
    proj = tmp_path / "p"; (proj / "characters").mkdir(parents=True)
    (proj / "characters" / "char_지오.png").write_bytes(b"\x89PNG")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/characters/list",
                                {"project_id": "p"}, None, ctx)
    assert code == 200
    assert "char_지오.png" in body["images"]


def test_storyboard_passes_character_ref(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text(
        '{"scenes":[{"sceneNumber":1,"image_prompt":"장면1"}]}', encoding="utf-8")
    (proj / "characters").mkdir()
    (proj / "characters" / "char_지오.png").write_bytes(b"\x89PNG")
    seen = {}

    def fake_many(proj_dir, items, *, subdir="images", concurrency=4, on_event=None, character_ref=None):
        seen["character_ref"] = character_ref
        return {rel: {"status": "completed"} for rel, _ in items}

    monkeypatch.setattr(r.imagegen, "generate_many", fake_many)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/storyboard/generate", {},
                                {"project_id": "p", "character": "지오"}, ctx)
    assert code == 200
    assert seen["character_ref"] == str(proj / "characters" / "char_지오.png")


def test_images_list(tmp_path):
    proj = tmp_path / "p"; (proj / "images").mkdir(parents=True)
    (proj / "images" / "ref_1.png").write_bytes(b"\x89PNG")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/images/list",
                                {"project_id": "p"}, None, ctx)
    assert code == 200
    assert "ref_1.png" in body["images"]


def test_storyboard_generate_from_scenes(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text(
        '{"project_id":"p","total_scenes":2,"scenes":['
        '{"sceneNumber":1,"title":"A","narration":"가","image_prompt":"장면1"},'
        '{"sceneNumber":2,"title":"B","narration":"나","image_prompt":"장면2"}]}',
        encoding="utf-8")

    def fake_gen(proj_dir, rel_out, image_prompt, **kw):
        assert kw.get("subdir") == "storyboard"
        out = proj_dir / "storyboard" / rel_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(r.imagegen, "generate_one", fake_gen)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/storyboard/generate", {},
                                {"project_id": "p"}, ctx)
    assert code == 200
    assert body["generated"] == 2


def test_storyboard_generate_requires_scenes(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/storyboard/generate", {},
                                {"project_id": "p"}, ctx)
    assert code == 422


def test_storyboard_list(tmp_path):
    proj = tmp_path / "p"; (proj / "storyboard").mkdir(parents=True)
    (proj / "storyboard" / "sb_1.png").write_bytes(b"\x89PNG")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/storyboard/list",
                                {"project_id": "p"}, None, ctx)
    assert code == 200
    assert "sb_1.png" in body["images"]


def test_layers_generate(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; (proj / "storyboard").mkdir(parents=True)
    (proj / "storyboard" / "sb_1.png").write_bytes(b"\x89PNG")
    (proj / "scenes.json").write_text(
        '{"project_id":"p","total_scenes":1,"scenes":[{"sceneNumber":1,"title":"A","narration":"가"}]}',
        encoding="utf-8")

    def fake_layers(proj_dir, items, **kw):
        out = {}
        for n, img in items:
            ld = proj_dir / "layers"; ld.mkdir(parents=True, exist_ok=True)
            (ld / f"bg_{n}.png").write_bytes(b"\x89PNG")
            (ld / f"char_{n}.png").write_bytes(b"\x89PNG")
            out[n] = {"background": {"status": "completed"}, "character": {"status": "completed"}}
        return out

    monkeypatch.setattr(r.imagegen, "generate_scene_layers", fake_layers)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/layers/generate", {}, {"project_id": "p"}, ctx)
    assert code == 200
    assert body["scenes"] == 1


def test_layers_generate_requires_storyboard(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text('{"scenes":[{"sceneNumber":1}]}', encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/layers/generate", {}, {"project_id": "p"}, ctx)
    assert code == 422


def test_projects_create(tmp_path):
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/projects/create", {},
                                {"title": "새 영상", "channel": "semoji", "duration": "1분"}, ctx)
    assert code == 200
    pid = body["project_id"]
    assert (tmp_path / pid / "plan.md").exists()


def test_projects_create_requires_title(tmp_path):
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/projects/create", {}, {"title": ""}, ctx)
    assert code == 400


def test_projects_files_list(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "plan.md").write_text("기획", encoding="utf-8")
    (proj / "final_manuscript.md").write_text("원고", encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/projects/files",
                                {"project_id": "p"}, None, ctx)
    assert code == 200
    labels = [g["label"] for g in body["groups"]]
    assert "기획" in labels and "원고" in labels


def test_projects_files_missing_project(tmp_path):
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/projects/files",
                                {"project_id": "nope"}, None, ctx)
    assert code == 200
    assert body["groups"] == []


def test_scenes_get(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text(
        '{"project_id":"p","scenes":[{"sceneNumber":1,"title":"A","narration":"가","image_prompt":"장면1"}]}',
        encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/scenes", {"project_id": "p"}, None, ctx)
    assert code == 200
    assert body["scenes"][0]["sceneNumber"] == 1
    assert body["dir"] == str(proj)


def test_scenes_update_narration(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text(
        '{"scenes":[{"sceneNumber":1,"narration":"옛","image_prompt":"x"}]}', encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/scenes/narration", {},
                                {"project_id": "p", "sceneNumber": 1, "narration": "새"}, ctx)
    assert code == 200 and body["ok"] is True
    import json as _j
    assert _j.loads((proj / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]["narration"] == "새"


def test_scenes_image_single(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text(
        '{"scenes":[{"sceneNumber":3,"sceneId":"sid33333","image_prompt":"전기차 공장"}]}', encoding="utf-8")
    seen = {}

    def fake_one(proj_dir, rel_out, image_prompt, *, subdir="images", character_ref=None, **kw):
        seen.update(rel_out=rel_out, subdir=subdir, prompt=image_prompt, character_ref=character_ref)
        return {"status": "completed", "path": str(proj_dir / subdir / rel_out)}

    monkeypatch.setattr(r.imagegen, "generate_one", fake_one)
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/scenes/image", {},
                                {"project_id": "p", "sceneNumber": 3, "character": "지오"}, ctx)
    assert code == 200 and body["result"]["status"] == "completed"
    assert seen["rel_out"] == "sb_sid33333.png" and seen["subdir"] == "storyboard"
    assert seen["prompt"] == "전기차 공장"
    # 캐릭터 시트가 없으면 character_ref=None (파일 미존재)
    assert seen["character_ref"] is None


def test_scenes_image_unknown_scene(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "scenes.json").write_text('{"scenes":[]}', encoding="utf-8")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/scenes/image", {},
                                {"project_id": "p", "sceneNumber": 9}, ctx)
    assert code == 404


def test_media_list(tmp_path):
    proj = tmp_path / "p"; (proj / "images").mkdir(parents=True)
    (proj / "images" / "a.png").write_bytes(b"\x89PNG")
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/media", {"project_id": "p"}, None, ctx)
    assert code == 200
    assert body["items"][0]["rel"] == "images/a.png"


def test_search_images_endpoint(tmp_path, monkeypatch):
    import backend.router as r
    monkeypatch.setattr(r.search, "search_images",
                        lambda q, engine="serper", count=12: {"images": [{"url": "u", "thumb": "t", "title": "x", "source": engine}]})
    proj = tmp_path / "p"; proj.mkdir()
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/search-images",
                                {"project_id": "p", "q": "전기차", "engine": "serper"}, None, ctx)
    assert code == 200 and body["images"][0]["url"] == "u"


def test_search_images_requires_query(tmp_path):
    proj = tmp_path / "p"; proj.mkdir()
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("GET", "/api/search-images",
                                {"project_id": "p", "q": ""}, None, ctx)
    assert code == 400


def test_search_save_endpoint(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()
    monkeypatch.setattr(r.search, "save_image",
                        lambda proj_dir, url, name, **kw: {"status": "completed", "rel": "images/search/x.jpg"})
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/search-images/save", {},
                                {"project_id": "p", "url": "http://x/a.jpg", "name": "x.jpg"}, ctx)
    assert code == 200 and body["result"]["status"] == "completed"


def test_scene_set_image_endpoint(tmp_path, monkeypatch):
    import backend.router as r
    proj = tmp_path / "p"; proj.mkdir()
    monkeypatch.setattr(r.media, "set_scene_image",
                        lambda proj_dir, n, src: {"status": "completed", "rel": f"storyboard/sb_{n}.png"})
    ctx = {"root": tmp_path, "jobs": JobRegistry()}
    code, body = handle_request("POST", "/api/scenes/set-image", {},
                                {"project_id": "p", "sceneNumber": 2, "src": "images/a.png"}, ctx)
    assert code == 200 and body["result"]["rel"] == "storyboard/sb_2.png"
