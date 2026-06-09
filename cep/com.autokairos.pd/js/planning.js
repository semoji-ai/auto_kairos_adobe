/* 기획 탭 — 산출물 파일 목록(그룹) + 미리보기. BACKEND/$/SELECTED_PROJECT는 main.js 전역. */

function loadPlanningFiles() {
  if (!SELECTED_PROJECT) { $("planFiles").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("planFiles").textContent = "불러오는 중...";
  fetch(BACKEND + "/api/projects/files?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var groups = j.groups || [];
      if (!groups.length) { $("planFiles").textContent = "(문서 없음)"; return; }
      $("planFiles").innerHTML = groups.map(function (g) {
        var items = g.files.map(function (n) {
          return '<a href="#" data-file="' + n + '" style="display:inline-block;margin:2px 8px 2px 0;color:#7ab0ff;">' + n + '</a>';
        }).join("");
        return '<div style="margin:4px 0"><span style="color:#9aa0a6">' + g.label + '</span><br>' + items + '</div>';
      }).join("");
      var links = $("planFiles").querySelectorAll("a[data-file]");
      for (var i = 0; i < links.length; i++) {
        links[i].addEventListener("click", function (e) {
          e.preventDefault();
          viewPlanningFile(this.getAttribute("data-file"));
        });
      }
    })
    .catch(function (e) { $("planFiles").textContent = "오류: " + e; });
}

function viewPlanningFile(name) {
  $("planViewer").textContent = "불러오는 중... (" + name + ")";
  fetch(BACKEND + "/api/projects/file?project_id=" + encodeURIComponent(SELECTED_PROJECT) +
        "&name=" + encodeURIComponent(name))
    .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
    .then(function (res) {
      $("planViewer").textContent =
        (res.ok && res.j.content != null) ? res.j.content : ("(열 수 없음) " + JSON.stringify(res.j));
    })
    .catch(function (e) { $("planViewer").textContent = "오류: " + e; });
}

document.addEventListener("DOMContentLoaded", function () {
  $("btnReloadFiles").addEventListener("click", loadPlanningFiles);
});
