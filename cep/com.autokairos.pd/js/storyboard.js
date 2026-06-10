/* 스토리보드 프로덕션 시트 — 씬당 1행. BACKEND/$/SELECTED_PROJECT/SELECTED_CHARACTER는 main.js 전역. */

function _esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* 컬럼 너비(px) — 인덱스 2(스크립트)는 flex(1fr). 드래그로 갱신. */
var COLW = [30, 220, null, 120, 60];

/* 씬별 원본 나레이션 — blur 시 변경 감지용 */
var NAR_ORIG = {};

function _colsCss() {
  return COLW.map(function (w, i) { return i === 2 ? "minmax(150px,1fr)" : w + "px"; }).join(" ");
}

function _applyCols() {
  var el = $("sheet");
  if (el) el.style.setProperty("--cols", _colsCss());
}

function _bindColResize() {
  var handles = $("sheet").querySelectorAll(".col-resize");
  for (var i = 0; i < handles.length; i++) {
    handles[i].addEventListener("mousedown", function (e) {
      e.preventDefault();
      var idx = parseInt(this.getAttribute("data-col"), 10);
      var startX = e.clientX, startW = COLW[idx] || 100;
      function move(ev) {
        COLW[idx] = Math.max(30, startW + (ev.clientX - startX));
        _applyCols();
      }
      function up() {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
      }
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
    });
  }
}

function loadSheet() {
  if (!SELECTED_PROJECT) { $("sheet").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("sheet").textContent = "불러오는 중...";
  fetch(BACKEND + "/api/scenes?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var dir = j.dir || "", list = j.scenes || [];
      if (!list.length) { $("sheet").textContent = "(씬 없음 — 씬 분해 먼저)"; return; }
      NAR_ORIG = {};
      list.forEach(function (s) { NAR_ORIG[s.sceneNumber] = s.narration || ""; });
      var head = '<div class="sheet-head">'
        + '<div>#</div>'
        + '<div>이미지<span class="col-resize" data-col="1"></span></div>'
        + '<div>스크립트</div>'
        + '<div>에셋<span class="col-resize" data-col="3"></span></div>'
        + '<div>TTS<span class="col-resize" data-col="4"></span></div>'
        + '</div>';
      $("sheet").innerHTML = head + list.map(function (s) { return renderRow(s, dir); }).join("");
      _applyCols();
      _bindColResize();
      bindRows();
    })
    .catch(function (e) { $("sheet").textContent = "오류: " + e; });
}

function renderRow(s, dir) {
  var n = s.sceneNumber;
  var media = s._image
    ? '<img class="main" src="file://' + dir + '/' + s._image + '">'
    : '<div style="color:#666;font-size:11px">(없음)</div>';
  var layers = (s._layers || []).map(function (lp) {
    return '<img class="lyr" src="file://' + dir + '/' + lp + '" title="' + _esc(lp) + '">';
  }).join("");
  var chars = (s.characters || []).join(", ");
  return ''
    + '<div class="sheet-row" data-scene="' + n + '" ondragover="event.preventDefault()" ondrop="dropOnScene(event,' + n + ')">'
    // 씬#
    + '  <div class="col-num">' + n + '</div>'
    // 이미지 미리보기 + 레이어 썸네일
    + '  <div class="col-img">' + media + (layers ? '<div>' + layers + '</div>' : '') + '</div>'
    // 스크립트(나레이션)
    + '  <div class="col-script">'
    + '    <div class="row-title">' + _esc(s.title || "") + '</div>'
    + '    <textarea class="nar" data-scene="' + n + '" rows="3">' + _esc(s.narration || "") + '</textarea>'
    + '    <div class="row-status" data-scene="' + n + '"></div>'
    + '  </div>'
    // 에셋(캐릭터 + 씬 이미지 생성)
    + '  <div class="col-asset">'
    + (chars ? '<div style="font-size:11px">👤 ' + _esc(chars) + '</div>' : '<div style="font-size:11px;color:#666">인물 없음</div>')
    + '    <button class="gen-img alt" data-scene="' + n + '">씬 이미지 생성</button>'
    + '    <div style="font-size:10px;color:#666;margin-top:2px">소스 드래그로 교체</div>'
    + '  </div>'
    // TTS(자리 — P6)
    + '  <div class="col-tts" style="font-size:11px;color:#666">(P6)</div>'
    + '</div>';
}

function bindRows() {
  // 나레이션: 저장 버튼 없이 blur 시 변경되었으면 확인 후 저장(아니오=되돌림)
  var tas = $("sheet").querySelectorAll("textarea.nar");
  for (var t = 0; t < tas.length; t++) {
    tas[t].addEventListener("blur", function () {
      var n = this.getAttribute("data-scene");
      var orig = NAR_ORIG[n] || "";
      if (this.value === orig) return;
      if (confirm("씬 " + n + " 나레이션 변경사항을 저장하시겠습니까?")) {
        saveNarration(n);
        NAR_ORIG[n] = this.value;
      } else {
        this.value = orig;   // 되돌림
      }
    });
  }
  var gen = $("sheet").querySelectorAll("button.gen-img");
  for (var k = 0; k < gen.length; k++) {
    gen[k].addEventListener("click", function () { genSceneImage(this.getAttribute("data-scene")); });
  }
}

function _rowStatus(n, msg) {
  var el = $("sheet").querySelector('.row-status[data-scene="' + n + '"]');
  if (el) el.textContent = msg;
}

function saveNarration(n) {
  var ta = $("sheet").querySelector('textarea.nar[data-scene="' + n + '"]');
  if (!ta) return;
  _rowStatus(n, "저장 중...");
  fetch(BACKEND + "/api/scenes/narration", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10), narration: ta.value }),
  }).then(function (r) { return r.json(); })
    .then(function (j) { _rowStatus(n, j.ok ? "저장됨 ✓" : ("실패: " + JSON.stringify(j))); })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
}

function genSceneImage(n) {
  _rowStatus(n, "씬 이미지 생성 중... (codex, 수십 초)" + (SELECTED_CHARACTER ? " [" + SELECTED_CHARACTER + "]" : ""));
  fetch(BACKEND + "/api/scenes/image", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10),
                           character: SELECTED_CHARACTER || "" }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      _rowStatus(n, (j.result && j.result.status === "completed") ? "생성 완료 ✓" : ("실패: " + JSON.stringify(j)));
      if (j.result && j.result.status === "completed") loadSheet();   // 썸네일 갱신
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
}

function dropOnScene(ev, n) {
  ev.preventDefault();
  var src = ev.dataTransfer.getData("text/plain");
  if (!src) return;
  _rowStatus(n, "적용 중... (" + src + ")");
  fetch(BACKEND + "/api/scenes/set-image", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: n, src: src }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      _rowStatus(n, (j.result && j.result.status === "completed") ? "적용됨 ✓" : ("실패: " + JSON.stringify(j)));
      if (j.result && j.result.status === "completed") loadSheet();
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
}
