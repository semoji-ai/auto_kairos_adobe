/* 스토리보드 프로덕션 시트 — 씬당 1행. BACKEND/$/SELECTED_PROJECT/SELECTED_CHARACTER는 main.js 전역. */

function _esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function loadSheet() {
  if (!SELECTED_PROJECT) { $("sheet").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("sheet").textContent = "불러오는 중...";
  fetch(BACKEND + "/api/scenes?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var dir = j.dir || "", list = j.scenes || [];
      if (!list.length) { $("sheet").textContent = "(씬 없음 — 씬 분해 먼저)"; return; }
      $("sheet").innerHTML = list.map(function (s) { return renderRow(s, dir); }).join("");
      bindRows();
    })
    .catch(function (e) { $("sheet").textContent = "오류: " + e; });
}

function renderRow(s, dir) {
  var n = s.sceneNumber;
  var media = s._image
    ? '<img src="file://' + dir + '/' + s._image + '" style="width:100%;border-radius:4px;">'
    : '<div style="color:#666;font-size:11px">(이미지 없음)</div>';
  var layers = (s._layers || []).map(function (lp) {
    return '<img src="file://' + dir + '/' + lp + '" style="width:38px;height:auto;margin:2px;border-radius:3px;" title="' + _esc(lp) + '">';
  }).join("");
  var chars = (s.characters || []).join(", ");
  return ''
    + '<div class="box" style="display:block" data-scene="' + n + '">'
    + '  <div style="color:#9aa0a6;font-size:11px">#' + n + " · " + _esc(s.title || "") + (chars ? " · 👤 " + _esc(chars) : "") + '</div>'
    + '  <div style="margin:4px 0">' + media + '</div>'
    + (layers ? '<div style="margin:2px 0">' + layers + '</div>' : '')
    + '  <textarea class="nar" data-scene="' + n + '" rows="2" style="width:100%;box-sizing:border-box;background:#23262b;color:#e6e6e6;border:1px solid #33363c;border-radius:5px;padding:6px;">' + _esc(s.narration || "") + '</textarea>'
    + '  <div style="display:flex;gap:6px">'
    + '    <button class="sv-nar" data-scene="' + n + '" style="margin:4px 0">나레이션 저장</button>'
    + '    <button class="gen-img alt" data-scene="' + n + '" style="margin:4px 0">씬 이미지 생성</button>'
    + '  </div>'
    + '  <div class="row-status" data-scene="' + n + '" style="font-size:11px;color:#9aa0a6"></div>'
    + '</div>';
}

function bindRows() {
  var save = $("sheet").querySelectorAll("button.sv-nar");
  for (var i = 0; i < save.length; i++) {
    save[i].addEventListener("click", function () { saveNarration(this.getAttribute("data-scene")); });
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
