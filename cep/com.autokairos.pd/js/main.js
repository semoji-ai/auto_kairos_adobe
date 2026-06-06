/* auto_kairos PD 패널 — PoC 로직.
   - 백엔드 /health 로 연결 확인 (#3)
   - build_scene.jsx 를 evalScript 로 AE에 실행해 컴프 생성 (#4)
   CSInterface 전체 라이브러리 대신 window.__adobe_cep__ 직접 사용(최소). */

var BACKEND = "http://127.0.0.1:8765";
var MANIFEST = "/Users/jleavens_macmini/LocalProjects/auto_kairos_adobe/poc/sample_manifest.json";

function $(id) { return document.getElementById(id); }

function evalScript(script) {
  return new Promise(function (resolve) {
    window.__adobe_cep__.evalScript(script, function (r) { resolve(r); });
  });
}

/* 로컬 파일(확장 내부 jsx) 동기 읽기 — file:// 에서 fetch가 막혀도 XHR은 동작 */
function readLocal(relPath) {
  var x = new XMLHttpRequest();
  x.open("GET", relPath, false);
  x.send();
  return x.responseText;
}

function checkBackend() {
  $("status").textContent = "확인 중...";
  fetch(BACKEND + "/health")
    .then(function (r) { return r.json(); })
    .then(function (j) {
      $("status").textContent =
        "backend: " + j.backend_status +
        "\ncodex: " + j.codex_status +
        "\nversion: " + j.version;
    })
    .catch(function (e) {
      $("status").textContent = "연결 실패 — 백엔드(app.py)가 실행 중인지 확인: " + e;
    });
}

function buildComp() {
  $("aeresult").textContent = "AE 실행 중...";
  var jsx;
  try {
    jsx = readLocal("./jsx/build_scene.jsx");
  } catch (e) {
    $("aeresult").textContent = "jsx 로드 실패: " + e;
    return;
  }
  var call = "\nakBuildScene(" + JSON.stringify(MANIFEST) + ");";
  evalScript(jsx + call).then(function (r) {
    $("aeresult").textContent = r || "(빈 응답 — AE 콘솔 확인)";
  });
}

var SELECTED_PROJECT = null;

function loadProjects() {
  $("projects").textContent = "불러오는 중...";
  fetch(BACKEND + "/api/projects").then(function (r) { return r.json(); })
    .then(function (j) {
      var rows = j.projects || [];
      if (!rows.length) { $("projects").textContent = "(프로젝트 없음)"; return; }
      $("projects").innerHTML = rows.map(function (p) {
        return '<div><a href="#" data-pid="' + p.project_id + '">'
          + p.project_id + " · " + p.title + " [" + p.status + "]</a></div>";
      }).join("");
      var links = $("projects").querySelectorAll("a[data-pid]");
      for (var i = 0; i < links.length; i++) {
        links[i].addEventListener("click", function (e) {
          e.preventDefault();
          SELECTED_PROJECT = this.getAttribute("data-pid");
          var all = $("projects").querySelectorAll("a");
          for (var k = 0; k < all.length; k++) { all[k].style.fontWeight = "normal"; }
          this.style.fontWeight = "bold";
        });
      }
    })
    .catch(function (e) { $("projects").textContent = "실패: " + e; });
}

function decompose() {
  if (!SELECTED_PROJECT) { $("scenes").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("scenes").textContent = "씬 분해 중... (codex)";
  fetch(BACKEND + "/api/skills/run", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, skill_name: "scene-decompose" }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "completed") { $("scenes").textContent = "실패: " + JSON.stringify(j); return; }
      return renderScenes();
    })
    .catch(function (e) { $("scenes").textContent = "오류: " + e; });
}

function renderScenes() {
  var path = "/Users/jleavens_macmini/LocalProjects/auto_kairos_adobe/projects/" + SELECTED_PROJECT + "/scenes.json";
  evalScript('(function(){var f=new File(' + JSON.stringify(path) +
    ');if(!f.exists)return "no scenes";f.open("r");var c=f.read();f.close();return c;})()')
    .then(function (txt) {
      try {
        var doc = JSON.parse(txt);
        $("scenes").innerHTML = (doc.scenes || []).map(function (s) {
          return "<div>#" + s.sceneNumber + " <b>" + s.title + "</b> — " +
            (s.narration || "").slice(0, 40) + "...</div>";
        }).join("") || "(씬 없음)";
      } catch (e) { $("scenes").textContent = txt; }
    });
}

function showManuscript() {
  if (!SELECTED_PROJECT) { $("manuscript").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("manuscript").textContent = "불러오는 중...";
  fetch(BACKEND + "/api/projects/file?project_id=" + encodeURIComponent(SELECTED_PROJECT) +
        "&name=final_manuscript.md")
    .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
    .then(function (res) {
      $("manuscript").textContent =
        (res.ok && res.j.content != null) ? res.j.content : ("(원고 없음) " + JSON.stringify(res.j));
    })
    .catch(function (e) { $("manuscript").textContent = "오류: " + e; });
}

function makeReferences() {
  if (!SELECTED_PROJECT) { $("gallery").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("gallery").textContent = "레퍼런스 목록 생성 중...";
  fetch(BACKEND + "/api/skills/run", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, skill_name: "reference-list" }),
  }).then(function (r) { return r.json(); })
    .then(function (j) { $("gallery").textContent = "레퍼런스 목록: " + j.status + " — 이제 [이미지 생성]"; })
    .catch(function (e) { $("gallery").textContent = "오류: " + e; });
}

function genImages() {
  if (!SELECTED_PROJECT) { $("gallery").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("gallery").textContent = "이미지 생성 중... (codex, 수십 초)";
  fetch(BACKEND + "/api/images/generate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "completed") { $("gallery").textContent = "실패: " + JSON.stringify(j); return; }
      return showGallery();
    })
    .catch(function (e) { $("gallery").textContent = "오류: " + e; });
}

function showGallery() {
  fetch(BACKEND + "/api/images/list?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var dir = j.dir || "";
      var imgs = j.images || [];
      if (!imgs.length) { $("gallery").textContent = "(이미지 없음)"; return; }
      $("gallery").innerHTML = imgs.map(function (n) {
        return '<img src="file://' + dir + '/' + n + '" style="width:90px;height:auto;margin:3px;border-radius:4px;" title="' + n + '">';
      }).join("");
    });
}

document.addEventListener("DOMContentLoaded", function () {
  $("btnHealth").addEventListener("click", checkBackend);
  $("btnBuild").addEventListener("click", buildComp);
  $("btnProjects").addEventListener("click", loadProjects);
  $("btnManuscript").addEventListener("click", showManuscript);
  $("btnDecompose").addEventListener("click", decompose);
  $("btnRefList").addEventListener("click", makeReferences);
  $("btnGenImages").addEventListener("click", genImages);
});
