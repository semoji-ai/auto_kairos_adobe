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
    assert 'id="health"' in html and 'id="aeresult"' in html
    assert '$("status")' not in main   # #status → #health 로 교체됨


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


def test_genmodal_present():
    html = HTML.read_text(encoding="utf-8")
    for el in ['id="genModal"', 'id="genCategory"', 'id="genPrompt"', 'id="genSubmit"',
               'id="genScene"', 'src="js/genmodal.js"']:
        assert el in html, el
