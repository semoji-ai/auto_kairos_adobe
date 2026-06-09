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
  $("health").textContent = "확인 중...";
  fetch(BACKEND + "/health")
    .then(function (r) { return r.json(); })
    .then(function (j) {
      $("health").textContent =
        "backend: " + j.backend_status +
        "\ncodex: " + j.codex_status +
        "\nversion: " + j.version;
    })
    .catch(function (e) {
      $("health").textContent = "연결 실패 — 백엔드(app.py)가 실행 중인지 확인: " + e;
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
var SELECTED_CHARACTER = null;  // char_<name>.png 의 <name> — 스토리보드 생성 시 character_ref로 사용

function genCharacter() {
  if (!SELECTED_PROJECT) { $("characters").textContent = "프로젝트를 먼저 선택하세요."; return; }
  var name = ($("charName").value || "").trim();
  var looks = ($("charLooks").value || "").trim();
  if (!name || !looks) { $("characters").textContent = "이름과 헤어·의상을 입력하세요."; return; }
  $("characters").textContent = "캐릭터 생성 중... (베이스 리스타일, codex)";
  fetch(BACKEND + "/api/characters/generate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, name: name, looks: looks }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (!j.character || j.character.status !== "completed") {
        $("characters").textContent = "실패: " + JSON.stringify(j); return;
      }
      SELECTED_CHARACTER = name;
      return showCharacters();
    })
    .catch(function (e) { $("characters").textContent = "오류: " + e; });
}

function showCharacters() {
  if (!SELECTED_PROJECT) { $("characters").textContent = "프로젝트를 먼저 선택하세요."; return; }
  fetch(BACKEND + "/api/characters/list?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var dir = j.dir || "", imgs = j.images || [];
      if (!imgs.length) { $("characters").textContent = "(캐릭터 없음)"; return; }
      $("characters").innerHTML = imgs.map(function (n) {
        var nm = n.replace(/^char_/, "").replace(/\.png$/, "");
        var sel = (nm === SELECTED_CHARACTER) ? "border:2px solid #4A90D9;" : "border:2px solid transparent;";
        return '<img src="file://' + dir + '/' + n + '" data-name="' + nm + '" style="width:90px;height:auto;margin:3px;border-radius:4px;cursor:pointer;' + sel + '" title="' + nm + ' — 클릭하면 씬 생성 기준 캐릭터로 선택">';
      }).join("");
      var ci = $("characters").querySelectorAll("img");
      for (var x = 0; x < ci.length; x++) {
        ci[x].addEventListener("click", function () {
          SELECTED_CHARACTER = this.getAttribute("data-name");
          showCharacters();  // 선택 테두리 갱신
        });
      }
    });
}

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
          var pid = this.getAttribute("data-pid");
          $("current").textContent = "현재 프로젝트: " + this.textContent;
          enterProject(pid, this.textContent);   // nav.js — 상세 뷰로 입장
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
  var charNote = SELECTED_CHARACTER ? " (기준 캐릭터: " + SELECTED_CHARACTER + ")" : " (무캐릭터)";
  $("storyboard").textContent = "스토리보드 생성 중... (씬별 codex, 수 분)" + charNote;
  fetch(BACKEND + "/api/storyboard/generate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, character: SELECTED_CHARACTER || "" }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "completed") { $("storyboard").textContent = "실패/일부: " + JSON.stringify(j); }
      return showStoryboard();
    })
    .catch(function (e) { $("storyboard").textContent = "오류: " + e; });
}

function showStoryboard() {
  if (!SELECTED_PROJECT) { $("storyboard").textContent = "프로젝트를 먼저 선택하세요."; return; }
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
  if (!SELECTED_PROJECT) { $("layers").textContent = "프로젝트를 먼저 선택하세요."; return; }
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

function createProject() {
  var title = ($("newTitle").value || "").trim();
  if (!title) { $("current").textContent = "제목을 입력하세요."; return; }
  fetch(BACKEND + "/api/projects/create", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title, channel: $("newStyle").value, duration: $("newDuration").value }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (!j.project_id) { $("current").textContent = "생성 실패: " + JSON.stringify(j); return; }
      SELECTED_PROJECT = j.project_id;
      enterProject(j.project_id, j.title + " (" + j.project_id + ") [planned]");
      $("current").textContent = "현재 프로젝트: " + j.title + " (" + j.project_id + ") [planned]";
      $("newTitle").value = "";
      loadProjects();
    })
    .catch(function (e) { $("current").textContent = "오류: " + e; });
}

document.addEventListener("DOMContentLoaded", function () {
  $("btnCreate").addEventListener("click", createProject);
  $("btnHealth").addEventListener("click", checkBackend);
  $("btnBuild").addEventListener("click", buildComp);
  $("btnProjects").addEventListener("click", loadProjects);
  $("btnManuscript").addEventListener("click", showManuscript);
  $("btnDecompose").addEventListener("click", decompose);
  $("btnGenCharacter").addEventListener("click", genCharacter);
  $("btnRefreshCharacters").addEventListener("click", showCharacters);
  $("btnRefList").addEventListener("click", makeReferences);
  $("btnGenImages").addEventListener("click", genImages);
  $("btnRefreshGallery").addEventListener("click", showGallery);
  $("btnGenStoryboard").addEventListener("click", genStoryboard);
  $("btnRefreshStoryboard").addEventListener("click", showStoryboard);
  $("btnGenLayers").addEventListener("click", genLayers);
  $("btnRefreshLayers").addEventListener("click", showLayers);
  $("btnImportImages").addEventListener("click", importAllImages);
  $("btnImportStoryboard").addEventListener("click", importAllStoryboard);
  $("btnImportLayers").addEventListener("click", importAllLayers);
});
