from pathlib import Path

PANEL = Path(__file__).resolve().parents[1] / "cep" / "com.autokairos.pd"
HTML = PANEL / "index.html"
NAV = PANEL / "js" / "nav.js"
MAIN = PANEL / "js" / "main.js"


def test_index_has_two_views():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="view-list"' in html
    assert 'id="view-detail"' in html
    # 상세 뷰는 초기 숨김
    assert 'id="view-detail" hidden' in html or 'id="view-detail"  hidden' in html


def test_index_has_detail_header_and_back():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="detailTitle"' in html
    assert 'id="btnBackToList"' in html


def test_index_has_tabs():
    html = HTML.read_text(encoding="utf-8")
    for el in ['id="btnTabPlanning"', 'id="btnTabStoryboard"',
               'id="tab-planning"', 'id="tab-storyboard"']:
        assert el in html, el


def test_index_has_chat_dock():
    html = HTML.read_text(encoding="utf-8")
    for el in ['id="chat-dock"', 'id="chatInput"', 'id="btnChatSend"']:
        assert el in html, el


def test_index_has_taskbar():
    assert 'id="task-bar"' in HTML.read_text(encoding="utf-8")


def test_index_has_responsive_media_query():
    assert "@media" in HTML.read_text(encoding="utf-8")


def test_existing_controls_present_in_detail():
    # 기존 버튼 ID 보존(바인딩 깨짐 방지)
    html = HTML.read_text(encoding="utf-8")
    for bid in ['id="btnDecompose"', 'id="btnGenCharacter"',
                'id="btnRefList"', 'id="btnGenStoryboard"', 'id="btnGenLayers"',
                'id="btnBuild"', 'id="btnCreate"', 'id="btnProjects"']:
        assert bid in html, bid


def test_nav_defines_functions():
    nav = NAV.read_text(encoding="utf-8")
    for fn in ["function enterProject", "function exitProject", "function switchTab"]:
        assert fn in nav, fn


def test_main_calls_enterProject():
    assert "enterProject(" in MAIN.read_text(encoding="utf-8")


def test_existing_result_boxes_wired():
    # checkBackend/buildComp가 쓰는 박스가 실제 존재 + main.js 참조 일치(레거시 #status 잔존 금지)
    html = HTML.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    # 백엔드 상태등(초록/빨강 점) + 연결 버튼 + AE 결과 박스
    assert 'id="healthDot"' in html and 'id="healthText"' in html and 'id="btnReconnect"' in html
    assert 'id="aeresult"' in html
    assert '$("status")' not in main   # 레거시 #status 잔존 금지


def test_planning_tab_has_file_viewer():
    html = HTML.read_text(encoding="utf-8")
    for el in ['id="btnReloadFiles"', 'id="planFiles"', 'id="planEdit"']:
        assert el in html, el
    # 임시 원고보기 버튼/박스는 제거됨
    assert 'id="btnManuscript"' not in html
    assert 'id="manuscript"' not in html


def test_index_loads_planning_js():
    assert 'src="js/planning.js"' in HTML.read_text(encoding="utf-8")


def test_storyboard_tab_has_sheet():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="sheet"' in html and 'id="btnLoadSheet"' in html
    assert 'src="js/storyboard.js"' in html


def test_storyboard_js_defines_loadSheet():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function loadSheet" in js


def test_gallery_panel_present():
    html = HTML.read_text(encoding="utf-8")
    for el in ['id="gallery-panel"', 'id="galSearch"', 'id="galEngine"',
               'id="btnGalSearch"', 'id="btnGalRefresh"', 'src="js/gallery.js"']:
        assert el in html, el


def test_storyboard_js_has_drop_handler():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function dropOnScene" in js and "set-image" in js


def test_storyboard_js_has_unlink():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function unlinkScene" in js and "unlink-image" in js


def test_storyboard_2pane():
    html = HTML.read_text(encoding="utf-8")
    for el in ['id="sb-2pane"', 'id="sb-left"', 'id="sb-right"', 'id="sb-toolbar"', 'id="btnOpenGenModal"']:
        assert el in html, el


def test_storyboard_preserves_legacy_ids():
    html = HTML.read_text(encoding="utf-8")
    for bid in ['id="btnDecompose"', 'id="btnRefList"', 'id="btnGenStoryboard"',
                'id="btnGenLayers"', 'id="btnBuild"', 'id="btnGenCharacter"',
                'id="btnRefreshCharacters"', 'id="btnGalRefresh"', 'id="btnGalSearch"',
                'id="sheet"', 'id="gallery-panel"', 'id="scenes"', 'id="aeresult"']:
        assert bid in html, bid


def test_storyboard_js_has_layer_analysis():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function analyzeLayers" in js and "analyze-layers" in js and "split-layers" in js


def test_genmodal_present():
    html = HTML.read_text(encoding="utf-8")
    for el in ['id="genModal"', 'id="genCategory"', 'id="genPrompt"', 'id="genSubmit"',
               'id="genScene"', 'src="js/genmodal.js"']:
        assert el in html, el


def test_storyboard_js_has_scene_ops():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function sceneOp" in js and "sa-split" in js and "sa-merge" in js   # 도구상자
    assert "work-dots" in js     # 진행 점(뱃지 대체)


def test_build_scene_jsx_handles_layers():
    jsx = (PANEL / "jsx" / "build_scene.jsx").read_text(encoding="utf-8")
    assert "s.layers" in jsx and "addLayerObj" in jsx and "position" in jsx


def test_storyboard_js_has_tts():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function genTts" in js and "/api/scenes/tts" in js


def test_main_js_assembly_uses_manifest():
    js = (PANEL / "js" / "main.js").read_text(encoding="utf-8")
    assert "/api/assembly/manifest" in js and "akBuildScene" in js


def test_assistant_js_wired():
    js = (PANEL / "js" / "assistant.js").read_text(encoding="utf-8")
    assert "function sendChat" in js and "/api/assistant" in js


def test_index_loads_assistant_js():
    html = (PANEL / "index.html").read_text(encoding="utf-8")
    assert "js/assistant.js" in html and 'id="chatInput"' in html
    assert "disabled" not in html.split('id="chatInput"')[1].split(">")[0]   # 입력 활성화


def test_llm_selector():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="llmSelect"' in html
    assert "function loadLlmSetting" in MAIN.read_text(encoding="utf-8") and "/api/llm/settings" in MAIN.read_text(encoding="utf-8")


def test_tts_settings_panel():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function loadTtsSettings" in js and "/api/tts/settings" in js
    html = (PANEL / "index.html").read_text(encoding="utf-8")
    assert 'id="ttsStyle"' in html and 'id="ttsVoiceId"' in html


def test_first_screen_auto_health_and_projects():
    html = HTML.read_text(encoding="utf-8")
    main = MAIN.read_text(encoding="utf-8")
    assert 'id="btnNewProject"' in html and 'id="newProjectForm"' in html
    assert "checkBackend();" in main                 # 열면 자동 호출
    assert "_setHealth" in main and "loadProjects()" in main
    assert ".proj-item" in main                       # 가독 카드형 목록


def test_tts_custom_player_and_scene_comp():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "tts-player" in js and "function _bindTtsPlayer" in js and "tts-dur" in js
    assert "sa-comp" in js                             # 도구상자 컴프 버튼
    main = MAIN.read_text(encoding="utf-8")
    assert "function buildSceneComp" in main and "function _assemble" in main


def test_buildall_button_and_full_comp():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="btnBuildAll"' in html
    assert "btnBuildAll" in MAIN.read_text(encoding="utf-8")


def test_gallery_select_import():
    js = (PANEL / "js" / "gallery.js").read_text(encoding="utf-8")
    assert "function importSelectedToProject" in js and "btnGalImport" in js


def test_storyboard_no_double_plus_concat():
    # '+   + ' 이중 플러스 = 단항 플러스로 문자열이 NaN 되는 버그 패턴(재발 방지)
    import re
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    bad = [ln for ln in js.splitlines() if re.match(r"\s*\+\s+\+\s", ln)]
    assert not bad, "이중 + 연결 발견(단항 플러스 NaN 위험): " + repr(bad[:3])


def test_storyboard_tts_player_renders_without_nan():
    # renderRow를 node로 실행해 TTS 플레이어 HTML이 NaN 없이 생성되는지 검증
    import subprocess, json
    sb = str(PANEL / "js" / "storyboard.js")
    script = (
        "global.window={localStorage:{getItem:function(){return null;},setItem:function(){}}};"
        "global.document={getElementById:function(){return null;},addEventListener:function(){}};"
        "eval(require('fs').readFileSync(" + json.dumps(sb) + ",'utf8'));"
        "var s={sceneNumber:1,sceneId:'x',title:'t',narration:'n',_image:'storyboard/a.png',"
        "_layers:[],_audio:'audio/tts_x.mp3',_audio_dur:13.5,"
        "_status:{narration:true,image:true,layers:false,tts:true},characters:[]};"
        "var h=renderRow(s,'/p');"
        "process.stdout.write(JSON.stringify({nan:h.indexOf('NaN')>=0,play:h.indexOf('>\\u25b6<')>=0,player:h.indexOf('tts-player')>=0}));"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    res = json.loads(out.stdout)
    assert res["player"] and res["play"] and not res["nan"], (out.stdout, out.stderr)


def test_layer_select_modal():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="layerModal"' in html and 'id="layerList"' in html and 'id="layerSubmit"' in html
    assert 'id="layerTabs"' in html                       # 여러 씬 탭
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "_submitLayerSplit" in js and "_switchLayerTab" in js and "_layerMulti" in js
    assert "한 번에 한 씬만" not in js                      # 단일 제한 해제됨


def test_poll_job_helper_and_async_callers():
    main = MAIN.read_text(encoding="utf-8")
    assert "function _pollJob" in main and "/api/jobs/" in main   # 폴백 유지
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "_awaitJob" in js                     # splitLayers SSE 대기
    a = (PANEL / "js" / "assistant.js").read_text(encoding="utf-8")
    assert "_awaitJob" in a


def test_jsx_subtitle_uses_comp_size():
    jsx = (PANEL / "jsx" / "build_scene.jsx").read_text(encoding="utf-8")
    assert "[cw / 2, ch * 0.88]" in jsx
    assert "[W / 2, H * 0.88]" not in jsx


def test_no_hardcoded_machine_paths_in_panel():
    main = MAIN.read_text(encoding="utf-8")
    assert "/Users/jleavens_macmini" not in main


def test_main_js_escapes_dynamic_html():
    main = MAIN.read_text(encoding="utf-8")
    assert "_esc(p.title" in main            # 프로젝트 제목 이스케이프
    # data-name/data-label 왕복 속성은 encodeURIComponent/decodeURIComponent
    assert 'encodeURIComponent(nm)' in main
    assert 'decodeURIComponent(this.getAttribute("data-name")' in main
    assert "_esc(nm)" in main.split("function showCharacters")[1]


def test_refresh_row_single_scene():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function refreshRow" in js
    assert "bindRows(fresh)" in js                       # 새 행만 스코프 바인딩(중복 리스너 방지)
    assert "function bindRows(scope)" in js
    # 단일 씬 작업(genTts)은 refreshRow 사용
    assert "refreshRow" in js.split("function genTts")[1]


def test_jsx_uses_json_parse():
    jsx = (PANEL / "jsx" / "build_scene.jsx").read_text(encoding="utf-8")
    assert "JSON.parse" in jsx
    assert (PANEL / "jsx" / "json2.jsx").exists()
    # json2는 ES3 호환(parse만) — const/let/arrow 금지
    j2 = (PANEL / "jsx" / "json2.jsx").read_text(encoding="utf-8")
    assert "JSON.parse" in j2 and "=>" not in j2 and "const " not in j2 and "let " not in j2
    main = MAIN.read_text(encoding="utf-8")
    assert "json2.jsx" in main


def test_jsx_has_motion():
    jsx = (PANEL / "jsx" / "build_scene.jsx").read_text(encoding="utf-8")
    assert "function applyMoves" in jsx and "function applyCamera" in jsx
    for t in ["slide_in", "pop", "bob", "zoom_emphasis", "slow_zoom_in"]:
        assert t in jsx


def test_panel_motion_button():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "sa-motion" in js and "function planMotion" in js and "/api/scenes/motion" in js
    html = HTML.read_text(encoding="utf-8")
    assert 'id="sa-motion"' in html


def test_render_queue_wired():
    assert (PANEL / "jsx" / "render_queue.jsx").exists()
    jsx = (PANEL / "jsx" / "render_queue.jsx").read_text(encoding="utf-8")
    assert "function akQueueRender" in jsx and "renderQueue.items.add" in jsx
    html = HTML.read_text(encoding="utf-8")
    assert 'id="btnQueueRender"' in html
    main = MAIN.read_text(encoding="utf-8")
    assert "function queueRender" in main and "render_queue.jsx" in main


def test_v3_import_ui_wired():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="btnImportV3"' in html and 'id="v3Path"' in html and 'id="v3Status"' in html
    main = MAIN.read_text(encoding="utf-8")
    assert "function importV3" in main and "/api/projects/import-v3" in main
    assert '$("btnImportV3").addEventListener' in main


def test_pipeline_button_wired():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="btnRunPipeline"' in html and 'id="pipelineStatus"' in html
    pl = (PANEL / "js" / "planning.js").read_text(encoding="utf-8")
    assert "function runPipeline" in pl and "/api/pipeline/run" in pl and "_awaitJob" in pl


def test_sheet_toolbar_and_checkboxes():
    html = HTML.read_text(encoding="utf-8")
    for bid in ['id="sheet-actionbar"', 'id="sa-img"', 'id="sa-layer"', 'id="sa-tts"',
                'id="sa-motion"', 'id="sa-comp"', 'id="sa-del"']:
        assert bid in html, bid
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "scene-sel" in js and "SEL_SCENES" in js and "selAllScenes" in js
    assert "function bindSheetToolbar" in js and "_runSeq" in js
    assert "col-asset" not in js and "work-actions" not in js   # 구 구조 제거


def test_render_row_checkbox_and_dots():
    """renderRow 실행 — 체크박스 + 진행 점 4개 + 버튼 없음(도구상자로 이동)."""
    import subprocess, json
    sb = str(PANEL / "js" / "storyboard.js")
    script = (
        "global.window={localStorage:{getItem:function(){return null;},setItem:function(){}}};"
        "global.document={getElementById:function(){return null;},addEventListener:function(){}};"
        "eval(require('fs').readFileSync(" + json.dumps(sb) + ",'utf8'));"
        "var s={sceneNumber:3,sceneId:'y',title:'t',narration:'n',_image:'storyboard/a.png',"
        "_layers:['layers/y__0.png'],_audio:'audio/tts_y.mp3',_audio_dur:5,"
        "_status:{image:true,layers:true,tts:false,motion:false},characters:[]};"
        "var h=renderRow(s,'/p');"
        "process.stdout.write(JSON.stringify({"
        "chk:h.indexOf('scene-sel')>=0,"
        "dots:(h.match(/dot (on|off)/g)||[]).length===4,"
        "on:(h.match(/dot on/g)||[]).length===2,"
        "noBtn:h.indexOf('gen-img')<0&&h.indexOf('scene-comp')<0,"
        "player:h.indexOf('tts-player')>=0&&h.indexOf('NaN')<0}));"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    res = json.loads(out.stdout)
    assert res["chk"] and res["dots"] and res["on"] and res["noBtn"] and res["player"], out.stdout


def test_layer_overlay_and_text_buttons():
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "function toggleLayerOverlay" in js and "lyr-overlay" in js and "img-wrap" in js
    html = HTML.read_text(encoding="utf-8")
    assert "drop-shadow" in html                       # 알파 윤곽 빨간 테두리
    assert ">씬 추가<" in html and ">병합<" in html and ">삭제<" in html   # 구조 버튼은 텍스트


def test_jsx_bob_null_pivot():
    jsx = (PANEL / "jsx" / "build_scene.jsx").read_text(encoding="utf-8")
    assert "function addBobNull" in jsx and "addNull" in jsx
    assert 'loopOut("pingpong")' in jsx and "KeyframeEase" in jsx
    assert "il.parent = nl" in jsx and "layer.foot" in jsx


def test_jsx_no_auto_fade():
    """자동 페이드(배경 오퍼시티 0→100) 금지 — 모든 모션은 모션 플랜에서만."""
    jsx = (PANEL / "jsx" / "build_scene.jsx").read_text(encoding="utf-8")
    assert "li === 0" not in jsx
    assert "function addLayerObj(proj, comp, layer, W, H)" in jsx   # fade 파라미터 제거


def test_sse_push_wired():
    main = MAIN.read_text(encoding="utf-8")
    assert "EventSource" in main and "/api/events" in main
    assert "function _awaitJob" in main and "function connectEvents" in main
    assert "connectEvents();" in main                      # 연결 시 SSE 구독
    # 호출부는 _awaitJob 사용(폴링은 폴백)
    for f in ["storyboard.js", "assistant.js", "planning.js"]:
        js = (PANEL / "js" / f).read_text(encoding="utf-8")
        assert "_awaitJob(j.job_id" in js, f
