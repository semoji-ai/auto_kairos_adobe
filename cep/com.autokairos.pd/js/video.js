/* 비디오 변환(이미지→비디오) 모달 — 체크된 씬 1개 대상.
   BACKEND/$/SELECTED_PROJECT/_awaitJob/_rowStatus/_esc/refreshRow는 전역(main.js·storyboard.js). */

var VIDEO_SCENE = null;      // 현재 모달 대상 씬 번호(int)
var VIDEO_MODELS = [];       // GET /api/video/models 의 models
var VIDEO_AUTHED = false;    // 힉스필드 인증 상태

/* 도구상자 [🎬 비디오] → 체크된 씬 1개로 모달 오픈 */
function openVideoModal() {
  var ns = _needChecked(1, "비디오 변환");
  if (!ns) return;
  if (ns.length > 1) { alert("비디오 변환은 한 씬만 체크하세요."); return; }
  VIDEO_SCENE = ns[0];
  $("videoModalTitle").textContent = "비디오 변환 — 씬 " + VIDEO_SCENE;
  $("videoModelWrap").innerHTML = "";
  $("videoParams").innerHTML = "";
  $("videoPrompt").value = "";
  $("videoStatus").textContent = "모델 목록 불러오는 중...";
  $("videoModal").hidden = false;
  _setVideoBusy(true);
  fetch(BACKEND + "/api/video/models").then(function (r) { return r.json(); })
    .then(function (j) {
      VIDEO_MODELS = j.models || [];
      var st = j.status || {};
      VIDEO_AUTHED = !!st.authed;
      if (!VIDEO_AUTHED) {
        $("videoStatus").textContent = "힉스필드 인증 필요 — 터미널에서 'higgsfield auth login' 실행 후 다시 여세요."
          + (st.hint ? " (" + st.hint + ")" : "");
        _setVideoBusy(true);   // 인증 전에는 생성/프롬프트 비활성 유지
        return;
      }
      if (!VIDEO_MODELS.length) {
        $("videoStatus").textContent = "사용 가능한 모델이 없습니다.";
        return;
      }
      var defaults = _readVideoModalDefaults();   // localStorage ak_video_defaults(설정 탭)
      $("videoModelWrap").innerHTML = '<div class="label">모델</div>'
        + '<select id="videoModel"></select>';
      var sel = $("videoModel");
      sel.innerHTML = VIDEO_MODELS.map(function (m) {
        var selAttr = (defaults && defaults.model === m.id) ? " selected" : "";
        return '<option value="' + _esc(m.id) + '"' + selAttr + '>' + _esc(m.label || m.id) + '</option>';
      }).join("");
      sel.addEventListener("change", function () { _renderVideoParams(); });
      _renderVideoParams(defaults && defaults.model === sel.value ? defaults.params : null);
      _setVideoBusy(false);
      $("videoStatus").textContent = "모델·파라미터를 고르고 프롬프트를 작성하세요.";
    })
    .catch(function (e) { $("videoStatus").textContent = "모델 목록 오류: " + e; });
}

/* localStorage ak_video_defaults(설정 탭 저장값) 읽기 */
function _readVideoModalDefaults() {
  try {
    var raw = window.localStorage.getItem("ak_video_defaults");
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

/* 선택 모델의 params → 컨트롤 동적 렌더(prompt 파라미터는 제외 — 별도 textarea 사용).
   presetVals(있으면) 로 기본값을 덮어씀(설정 탭 저장값 프리필) */
function _renderVideoParams(presetVals) {
  var m = _currentVideoModel();
  var box = $("videoParams");
  if (!m) { box.innerHTML = ""; return; }
  var pv = presetVals || {};
  var html = "";
  (m.params || []).forEach(function (p) {
    if (p.name === "prompt") return;
    var id = "vp_" + p.name;
    var lab = '<div class="label">' + _esc(p.name) + (p.required ? " *" : "") + '</div>';
    var has = Object.prototype.hasOwnProperty.call(pv, p.name);
    if (p.type === "boolean") {
      var on = has ? !!pv[p.name] : !!p['default'];
      html += '<label class="video-chk"><input type="checkbox" data-name="' + _esc(p.name)
        + '" data-type="boolean" id="' + id + '"' + (on ? " checked" : "") + '> '
        + _esc(p.name) + (p.required ? " *" : "") + '</label>';
    } else if (p.enum && p.enum.length) {
      var cur = has ? pv[p.name] : p['default'];
      html += lab + '<select data-name="' + _esc(p.name) + '" data-type="string" id="' + id + '">'
        + p.enum.map(function (opt) {
          return '<option value="' + _esc(opt) + '"'
            + (String(opt) === String(cur) ? " selected" : "") + '>' + _esc(opt) + '</option>';
        }).join("") + '</select>';
    } else if (p.type === "integer") {
      var iv = has ? pv[p.name] : p['default'];
      html += lab + '<input type="number" data-name="' + _esc(p.name) + '" data-type="integer" id="' + id
        + '" value="' + (iv != null ? _esc(iv) : "") + '">';
    } else {
      var sv = has ? pv[p.name] : p['default'];
      html += lab + '<input type="text" data-name="' + _esc(p.name) + '" data-type="string" id="' + id
        + '" value="' + (sv != null ? _esc(sv) : "") + '">';
    }
  });
  box.innerHTML = html;
}

function _currentVideoModel() {
  var sel = $("videoModel");
  if (!sel) return null;
  var id = sel.value;
  for (var i = 0; i < VIDEO_MODELS.length; i++) {
    if (VIDEO_MODELS[i].id === id) return VIDEO_MODELS[i];
  }
  return null;
}

/* 렌더된 컨트롤에서 params 수집 — boolean은 체크값, integer는 숫자, 빈 문자열은 생략 */
function _collectVideoParams() {
  var params = {};
  var ctrls = $("videoParams").querySelectorAll("[data-name]");
  for (var i = 0; i < ctrls.length; i++) {
    var el = ctrls[i];
    var name = el.getAttribute("data-name");
    var typ = el.getAttribute("data-type");
    if (typ === "boolean") {
      params[name] = !!el.checked;
    } else if (typ === "integer") {
      var v = (el.value || "").trim();
      if (v === "") continue;
      params[name] = parseInt(v, 10);
    } else {
      var s = (el.value || "").trim();
      if (s === "") continue;   // 빈 문자열은 생략
      params[name] = s;
    }
  }
  return params;
}

/* 생성/프롬프트 버튼 활성/비활성 토글 */
function _setVideoBusy(busy) {
  var g = $("videoGenerate"), p = $("videoGenPrompt");
  if (g) g.disabled = busy;
  if (p) p.disabled = busy;
}

/* [LLM 프롬프트 생성] — /api/video/prompt 잡 → 완료 시 textarea 채움 */
function _videoGenPrompt() {
  var m = _currentVideoModel();
  if (!m) { $("videoStatus").textContent = "모델을 먼저 선택하세요."; return; }
  _setVideoBusy(true);
  $("videoStatus").textContent = "LLM 프롬프트 생성 중...";
  fetch(BACKEND + "/api/video/prompt", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: VIDEO_SCENE, model: m.id }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "running" || !j.job_id) {
        $("videoStatus").textContent = "실패: " + (j.error || JSON.stringify(j));
        _setVideoBusy(false); return;
      }
      _awaitJob(j.job_id, function (job) {
        var prompt = job.result && job.result.prompt;
        if (job.status === "completed" && prompt) {
          $("videoPrompt").value = prompt;
          $("videoStatus").textContent = "프롬프트 생성 완료 — 확인·수정 후 [생성].";
        } else {
          $("videoStatus").textContent = "프롬프트 생성 실패: " + (job.error || JSON.stringify(job));
        }
        _setVideoBusy(false);
      }, function (logs) {
        if (logs.length) $("videoStatus").textContent = "프롬프트 생성 중... " + logs[logs.length - 1];
      });
    })
    .catch(function (e) { $("videoStatus").textContent = "오류: " + e; _setVideoBusy(false); });
}

/* [생성] — /api/video/generate 잡 → _awaitJob 대기(수 분), 완료 시 결과 안내 + 행 상태 */
function _videoGenerate() {
  var m = _currentVideoModel();
  if (!m) { $("videoStatus").textContent = "모델을 먼저 선택하세요."; return; }
  var prompt = ($("videoPrompt").value || "").trim();
  if (!prompt) { $("videoStatus").textContent = "프롬프트를 입력하거나 [LLM 프롬프트 생성]을 누르세요."; return; }
  var params = _collectVideoParams();
  var n = VIDEO_SCENE;
  _setVideoBusy(true);
  $("videoStatus").textContent = "비디오 생성 중... (수 분 소요)";
  _rowStatus(n, "비디오 생성 중... (" + (m.label || m.id) + ", 수 분)");
  fetch(BACKEND + "/api/video/generate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: n, model: m.id,
                           prompt: prompt, params: params }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (!j.job_id) {
        $("videoStatus").textContent = "실패: " + (j.error || JSON.stringify(j));
        _rowStatus(n, "비디오 실패: " + (j.error || ""));
        _setVideoBusy(false); return;
      }
      _awaitJob(j.job_id, function (job) {
        var res = job.result && job.result.result;
        if (job.status === "completed" && res && res.rel) {
          $("videoStatus").textContent = "비디오 생성 완료 ✓ — " + res.rel;
          _rowStatus(n, "비디오 완료 ✓ (" + res.rel + ")");
        } else {
          $("videoStatus").textContent = "비디오 생성 실패: " + (job.error || JSON.stringify(job));
          _rowStatus(n, "비디오 실패: " + (job.error || ""));
        }
        _setVideoBusy(false);
      }, function (logs) {
        if (logs.length) $("videoStatus").textContent = "비디오 생성 중... " + logs[logs.length - 1];
      }, 1600);   // 40분 한도 — 수 분+큐 대기 대비
    })
    .catch(function (e) { $("videoStatus").textContent = "오류: " + e; _setVideoBusy(false); });
}

function _closeVideoModal() { $("videoModal").hidden = true; }

document.addEventListener("DOMContentLoaded", function () {
  var g = $("videoGenerate"); if (g) g.addEventListener("click", _videoGenerate);
  var p = $("videoGenPrompt"); if (p) p.addEventListener("click", _videoGenPrompt);
  var c = $("videoCancel"); if (c) c.addEventListener("click", _closeVideoModal);
  var x = $("videoClose"); if (x) x.addEventListener("click", _closeVideoModal);
});
