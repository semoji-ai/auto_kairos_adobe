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

document.addEventListener("DOMContentLoaded", function () {
  $("btnHealth").addEventListener("click", checkBackend);
  $("btnBuild").addEventListener("click", buildComp);
});
