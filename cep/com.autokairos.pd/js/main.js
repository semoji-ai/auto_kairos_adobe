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
        return '<img src="file://' + dir + '/' + n + '" style="width:90px;height:auto;margin:3px;border-radius:4px;cursor:pointer;" title="' + n + '">';
      }).join("");
      $("gallery").setAttribute("data-dir", dir);
      $("gallery").setAttribute("data-names", imgs.join(","));
      var gi = $("gallery").querySelectorAll("img");
      for (var x = 0; x < gi.length; x++) {
        gi[x].addEventListener("click", function () {
          importToAE($("gallery").getAttribute("data-dir"),
                     [this.getAttribute("title")], "references", "gallery");
        });
      }
    });
}

function genStoryboard() {
  if (!SELECTED_PROJECT) { $("storyboard").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("storyboard").textContent = "스토리보드 생성 중... (씬별 codex, 수 분)";
  fetch(BACKEND + "/api/storyboard/generate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "completed") { $("storyboard").textContent = "실패/일부: " + JSON.stringify(j); }
      return showStoryboard();
    })
    .catch(function (e) { $("storyboard").textContent = "오류: " + e; });
}

function showStoryboard() {
  fetch(BACKEND + "/api/storyboard/list?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var dir = j.dir || "", imgs = j.images || [];
      if (!imgs.length) { $("storyboard").textContent = "(스토리보드 없음)"; return; }
      $("storyboard").innerHTML = imgs.map(function (n) {
        return '<img src="file://' + dir + '/' + n + '" style="width:120px;height:auto;margin:3px;border-radius:4px;cursor:pointer;" title="' + n + '">';
      }).join("");
      $("storyboard").setAttribute("data-dir", dir);
      $("storyboard").setAttribute("data-names", imgs.join(","));
      var si = $("storyboard").querySelectorAll("img");
      for (var x = 0; x < si.length; x++) {
        si[x].addEventListener("click", function () {
          importToAE($("storyboard").getAttribute("data-dir"),
                     [this.getAttribute("title")], "storyboard", "storyboard");
        });
      }
    });
}

function genLayers() {
  if (!SELECTED_PROJECT) { $("layers").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("layers").textContent = "레이어 생성 중... (씬별 배경+인물, codex)";
  fetch(BACKEND + "/api/layers/generate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "completed") { $("layers").textContent = "실패/일부: " + JSON.stringify(j); }
      return showLayers();
    })
    .catch(function (e) { $("layers").textContent = "오류: " + e; });
}

function showLayers() {
  fetch(BACKEND + "/api/layers/list?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var dir = j.dir || "", imgs = j.images || [];
      if (!imgs.length) { $("layers").textContent = "(레이어 없음)"; return; }
      $("layers").innerHTML = imgs.map(function (n) {
        return '<img src="file://' + dir + '/' + n + '" style="width:100px;height:auto;margin:3px;border:1px solid #444;border-radius:4px;background:#666;cursor:pointer;" title="' + n + '">';
      }).join("");
      $("layers").setAttribute("data-dir", dir);
      $("layers").setAttribute("data-names", imgs.join(","));
      var li = $("layers").querySelectorAll("img");
      for (var x = 0; x < li.length; x++) {
        li[x].addEventListener("click", function () {
          importToAE($("layers").getAttribute("data-dir"),
                     [this.getAttribute("title")], "layers", "layers");
        });
      }
    });
}

function importToAE(dir, names, folderName, statusElId) {
  if (!names || !names.length) { return; }
  var paths = names.map(function (n) { return dir + "/" + n; });
  var jsx;
  try { jsx = readLocal("./jsx/import_to_ae.jsx"); }
  catch (e) { $(statusElId).textContent = "jsx 로드 실패: " + e; return; }
  var call = "\nakImportToProject(" + JSON.stringify(JSON.stringify(paths)) + ", " +
             JSON.stringify(folderName) + ");";
  evalScript(jsx + call).then(function (r) {
    var note = document.getElementById(statusElId + "_note");
    if (!note) {
      note = document.createElement("div");
      note.id = statusElId + "_note";
      note.style.cssText = "color:#7fd17f;font-size:11px;margin:4px 0;";
      var el = $(statusElId);
      if (!el) { return; }
      el.parentNode.insertBefore(note, el);
    }
    note.textContent = "AE 가져오기: " + r;
  });
}

function importAllImages() {
  importToAE($("gallery").getAttribute("data-dir") || "",
             ($("gallery").getAttribute("data-names") || "").split(",").filter(Boolean),
             "references", "gallery");
}

function importAllStoryboard() {
  importToAE($("storyboard").getAttribute("data-dir") || "",
             ($("storyboard").getAttribute("data-names") || "").split(",").filter(Boolean),
             "storyboard", "storyboard");
}

function importAllLayers() {
  importToAE($("layers").getAttribute("data-dir") || "",
             ($("layers").getAttribute("data-names") || "").split(",").filter(Boolean),
             "layers", "layers");
}

document.addEventListener("DOMContentLoaded", function () {
  $("btnHealth").addEventListener("click", checkBackend);
  $("btnBuild").addEventListener("click", buildComp);
  $("btnProjects").addEventListener("click", loadProjects);
  $("btnManuscript").addEventListener("click", showManuscript);
  $("btnDecompose").addEventListener("click", decompose);
  $("btnRefList").addEventListener("click", makeReferences);
  $("btnGenImages").addEventListener("click", genImages);
  $("btnRefreshGallery").addEventListener("click", showGallery);
  $("btnGenStoryboard").addEventListener("click", genStoryboard);
  $("btnGenLayers").addEventListener("click", genLayers);
  $("btnImportImages").addEventListener("click", importAllImages);
  $("btnImportStoryboard").addEventListener("click", importAllStoryboard);
  $("btnImportLayers").addEventListener("click", importAllLayers);
});
