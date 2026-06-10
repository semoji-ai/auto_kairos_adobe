/* 갤러리 패널 — 프로젝트 미디어 탐색 + 검색(serper/pixabay) + 드래그→시트.
   BACKEND/$/SELECTED_PROJECT는 main.js 전역. */

function _gesc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function loadGallery() {
  if (!SELECTED_PROJECT) { $("gallery-panel").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("gallery-panel").textContent = "불러오는 중...";
  fetch(BACKEND + "/api/media?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var items = j.items || [];
      if (!items.length) { $("gallery-panel").textContent = "(소스 없음)"; return; }
      $("gallery-panel").innerHTML = items.map(function (it) {
        if (it.type === "image") {
          return '<div class="gal-item">'
            + '<img src="file://' + it.dir + '/' + it.rel + '" draggable="true"'
            + ' ondragstart="event.dataTransfer.setData(\'text/plain\', this.getAttribute(\'data-rel\'))"'
            + ' data-rel="' + _gesc(it.rel) + '" title="' + _gesc(it.rel) + ' — 시트 행으로 드래그 / ↧AE로 임포트"'
            + ' class="gal-thumb" style="cursor:grab;">'
            + '<button class="gal-ae" data-rel="' + _gesc(it.rel) + '" data-dir="' + _gesc(it.dir) + '" title="AE 프로젝트로 가져오기">↧AE</button>'
            + '</div>';
        }
        return '<div class="gal-item"><span style="display:inline-block;padding:6px;background:#23262b;border-radius:4px;font-size:11px;">🎬 ' + _gesc(it.name) + '</span>'
          + '<button class="gal-ae" data-rel="' + _gesc(it.rel) + '" data-dir="' + _gesc(it.dir) + '" title="AE 프로젝트로 가져오기">↧AE</button></div>';
      }).join("");
      var aebtns = $("gallery-panel").querySelectorAll("button.gal-ae");
      for (var i = 0; i < aebtns.length; i++) {
        aebtns[i].addEventListener("click", function () {
          if (typeof importToAE === "function") {
            importToAE(this.getAttribute("data-dir"), [this.getAttribute("data-rel")], "gallery", "gallery-panel");
          }
        });
      }
    })
    .catch(function (e) { $("gallery-panel").textContent = "오류: " + e; });
}

function searchGallery() {
  if (!SELECTED_PROJECT) { $("gallery-panel").textContent = "프로젝트를 먼저 선택하세요."; return; }
  var q = ($("galSearch").value || "").trim();
  if (!q) { $("gallery-panel").textContent = "검색어를 입력하세요."; return; }
  var engine = $("galEngine").value;
  $("gallery-panel").textContent = "검색 중... (" + engine + ")";
  fetch(BACKEND + "/api/search-images?project_id=" + encodeURIComponent(SELECTED_PROJECT) +
        "&q=" + encodeURIComponent(q) + "&engine=" + encodeURIComponent(engine))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.error) { $("gallery-panel").textContent = "검색 오류: " + j.error; return; }
      var imgs = j.images || [];
      if (!imgs.length) { $("gallery-panel").textContent = "(결과 없음)"; return; }
      $("gallery-panel").innerHTML = imgs.map(function (im, idx) {
        return '<img src="' + _gesc(im.thumb) + '" data-url="' + _gesc(im.url) + '" data-idx="' + idx
          + '" title="클릭하면 소스로 저장: ' + _gesc(im.title) + '"'
          + ' class="gal-thumb" style="cursor:pointer;">';
      }).join("");
      var gi = $("gallery-panel").querySelectorAll("img[data-url]");
      for (var i = 0; i < gi.length; i++) {
        gi[i].addEventListener("click", function () {
          saveSearchResult(this.getAttribute("data-url"), "search_" + this.getAttribute("data-idx") + ".jpg");
        });
      }
    })
    .catch(function (e) { $("gallery-panel").textContent = "오류: " + e; });
}

function saveSearchResult(url, name) {
  $("gallery-panel").innerHTML = "<div>저장 중... " + _gesc(name) + "</div>" + $("gallery-panel").innerHTML;
  fetch(BACKEND + "/api/search-images/save", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, url: url, name: name }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.result && j.result.status === "completed") loadGallery();  // 소스 목록 갱신
      else $("gallery-panel").textContent = "저장 실패: " + JSON.stringify(j);
    })
    .catch(function (e) { $("gallery-panel").textContent = "오류: " + e; });
}

document.addEventListener("DOMContentLoaded", function () {
  $("btnGalRefresh").addEventListener("click", loadGallery);
  $("btnGalSearch").addEventListener("click", searchGallery);
});
