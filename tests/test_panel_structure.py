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
    for el in ['id="btnReloadFiles"', 'id="planFiles"', 'id="planViewer"']:
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
    assert "function sceneOp" in js and "op-split" in js and "op-merge" in js
    assert "scene-badges" in js


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
    assert "scene-comp" in js                          # 씬별 컴프 버튼
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
    js = (PANEL / "js" / "storyboard.js").read_text(encoding="utf-8")
    assert "_openLayerModal" in js and "_submitLayerSplit" in js
    assert "confirm(" not in js.split("function analyzeLayers")[1].split("function ")[1]  # confirm 제거됨
