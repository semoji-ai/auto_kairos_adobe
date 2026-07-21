/* ⚙ 설정 탭 — 힉스필드 계정 / 비디오 기본값 / TTS 설정 / 이미지 안내.
   BACKEND/$/SELECTED_PROJECT/_esc 는 main.js·storyboard.js 전역. main.js→nav.js→settings.js 순 로드. */

var SET_VIDEO_MODELS = [];        // GET /api/video/models 의 models
var SET_VIDEO_COST_TIMER = null;  // 예상 크레딧 디바운스 타이머
var AK_VIDEO_DEFAULTS_KEY = "ak_video_defaults";

/* 설정 탭 진입 시 4개 섹션 로드 */
function loadSettings() {
  loadSetAccount();
  loadSetVideo();
  loadSetTts();
}

/* ---------- 1) 힉스필드 계정 ---------- */
function loadSetAccount() {
  var box = $("setAccount");
  if (box) box.textContent = "계정 확인 중...";
  fetch(BACKEND + "/api/video/account").then(function (r) { return r.json(); })
    .then(function (j) {
      if (!box) return;
      if (j && j.authed) {
        box.innerHTML = _esc(j.email || "(이메일 없음)")
          + " · " + _esc(j.plan || "-")
          + " · 남은 크레딧 <span class=\"set-credit\">" + _esc(j.credits != null ? j.credits : "-") + "</span>";
      } else {
        box.textContent = "힉스필드 미로그인 — 터미널에서 'higgsfield auth login' 실행 후 새로고침.";
      }
    })
    .catch(function (e) { if (box) box.textContent = "계정 오류: " + e; });
}

/* ---------- 2) 비디오 기본 설정 ---------- */
function loadSetVideo() {
  var wrap = $("setVideoModelWrap");
  var params = $("setVideoParams");
  if (wrap) wrap.innerHTML = "";
  if (params) params.innerHTML = "";
  $("setVideoCost").textContent = "—";
  $("setVideoHint").textContent = "모델 목록 불러오는 중...";
  fetch(BACKEND + "/api/video/models").then(function (r) { return r.json(); })
    .then(function (j) {
      SET_VIDEO_MODELS = (j && j.models) || [];
      var st = (j && j.status) || {};
      if (!st.authed) {
        $("setVideoHint").textContent = "힉스필드 인증 필요 — 'higgsfield auth login' 실행 후 새로고침."
          + (st.hint ? " (" + st.hint + ")" : "");
        return;
      }
      if (!SET_VIDEO_MODELS.length) {
        $("setVideoHint").textContent = "사용 가능한 모델이 없습니다.";
        return;
      }
      $("setVideoHint").textContent = "모델·파라미터를 고르면 비디오 모달의 기본값으로 저장됩니다.";
      var saved = _readVideoDefaults();
      var opts = SET_VIDEO_MODELS.map(function (m) {
        var selAttr = (saved && saved.model === m.id) ? " selected" : "";
        return '<option value="' + _esc(m.id) + '"' + selAttr + '>' + _esc(m.label || m.id) + '</option>';
      }).join("");
      wrap.innerHTML = '<div class="label">모델</div><select id="setVideoModel">' + opts + '</select>';
      $("setVideoModel").addEventListener("change", function () {
        _renderSetVideoParams(null);
        _debounceSetVideoCost();
      });
      _renderSetVideoParams(saved && saved.params);
      _debounceSetVideoCost();
    })
    .catch(function (e) { $("setVideoHint").textContent = "모델 목록 오류: " + e; });
}

function _currentSetVideoModel() {
  var sel = $("setVideoModel");
  if (!sel) return null;
  for (var i = 0; i < SET_VIDEO_MODELS.length; i++) {
    if (SET_VIDEO_MODELS[i].id === sel.value) return SET_VIDEO_MODELS[i];
  }
  return null;
}

/* 선택 모델의 params → 컨트롤 렌더. presetVals(있으면) 로 기본값 덮어씀 */
function _renderSetVideoParams(presetVals) {
  var m = _currentSetVideoModel();
  var box = $("setVideoParams");
  if (!m) { box.innerHTML = ""; return; }
  var pv = presetVals || {};
  var html = "";
  (m.params || []).forEach(function (p) {
    if (p.name === "prompt") return;
    var id = "svp_" + p.name;
    var lab = '<div class="label">' + _esc(p.name) + (p.required ? " *" : "") + '</div>';
    var has = Object.prototype.hasOwnProperty.call(pv, p.name);
    if (p.type === "boolean") {
      var on = has ? !!pv[p.name] : !!p['default'];
      html += '<label class="set-chk"><input type="checkbox" data-name="' + _esc(p.name)
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
  var ctrls = box.querySelectorAll("[data-name]");
  for (var i = 0; i < ctrls.length; i++) {
    ctrls[i].addEventListener("change", _debounceSetVideoCost);
    ctrls[i].addEventListener("input", _debounceSetVideoCost);
  }
}

/* 렌더된 컨트롤에서 params 수집 */
function _collectSetVideoParams() {
  var params = {};
  var box = $("setVideoParams");
  var ctrls = box.querySelectorAll("[data-name]");
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
      if (s === "") continue;
      params[name] = s;
    }
  }
  return params;
}

/* 예상 크레딧 — 디바운스 ~400ms 후 POST /api/video/cost */
function _debounceSetVideoCost() {
  if (SET_VIDEO_COST_TIMER) clearTimeout(SET_VIDEO_COST_TIMER);
  SET_VIDEO_COST_TIMER = setTimeout(_fetchSetVideoCost, 400);
}

function _fetchSetVideoCost() {
  var m = _currentSetVideoModel();
  var out = $("setVideoCost");
  if (!m) { out.textContent = "—"; return; }
  var body = { model: m.id, params: _collectSetVideoParams() };
  if (SELECTED_PROJECT) body.project_id = SELECTED_PROJECT;
  out.textContent = "계산 중...";
  fetch(BACKEND + "/api/video/cost", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      out.textContent = (j && j.credits != null && !j.error) ? String(j.credits) : "-";
    })
    .catch(function () { out.textContent = "-"; });
}

/* localStorage 읽기/쓰기 */
function _readVideoDefaults() {
  try {
    var raw = window.localStorage.getItem(AK_VIDEO_DEFAULTS_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) { return null; }
}

function _saveVideoDefaults() {
  var m = _currentSetVideoModel();
  if (!m) return;
  var data = { model: m.id, params: _collectSetVideoParams() };
  try {
    window.localStorage.setItem(AK_VIDEO_DEFAULTS_KEY, JSON.stringify(data));
    $("setVideoSaved").textContent = " 저장됨 ✓";
  } catch (e) {
    $("setVideoSaved").textContent = " 저장 실패: " + e;
  }
}

/* ---------- 3) 음성(TTS) 설정 ---------- */
var SET_TTS_PRESETS = {};   // presets.presets (style → {label,voice_id,voice_settings})

function loadSetTts() {
  var body = $("setTtsBody");
  var need = $("setTtsNeedProject");
  if (!SELECTED_PROJECT) {
    if (body) body.hidden = true;
    if (need) need.hidden = false;
    return;
  }
  if (body) body.hidden = false;
  if (need) need.hidden = true;
  $("setTtsSaved").textContent = "";
  fetch(BACKEND + "/api/tts/settings?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var cfg = (j && j.config) || {};
      var presets = (j && j.presets) || {};
      var models = (j && j.models) || [];
      SET_TTS_PRESETS = (presets.presets) || {};
      // 모델 드롭다운
      var msel = $("setTtsModel");
      msel.innerHTML = models.map(function (m) {
        return '<option value="' + _esc(m.id) + '"'
          + (String(m.id) === String(cfg.model) ? " selected" : "") + '>' + _esc(m.label || m.id) + '</option>';
      }).join("");
      // 보이스 프리셋 드롭다운
      var psel = $("setTtsPreset");
      var keys = [];
      for (var k in SET_TTS_PRESETS) { if (Object.prototype.hasOwnProperty.call(SET_TTS_PRESETS, k)) keys.push(k); }
      psel.innerHTML = keys.map(function (key) {
        var pr = SET_TTS_PRESETS[key] || {};
        return '<option value="' + _esc(key) + '"'
          + (String(key) === String(cfg.style) ? " selected" : "") + '>' + _esc(pr.label || key) + '</option>';
      }).join("");
      psel.onchange = function () {
        var pr = SET_TTS_PRESETS[psel.value] || {};
        if (pr.voice_id) $("setTtsVoiceId").value = pr.voice_id;
      };
      // voice_id 직접입력
      $("setTtsVoiceId").value = cfg.voice_id || "";
      // voice_settings 컨트롤
      _renderTtsVoiceSettings(cfg.voice_settings || {});
    })
    .catch(function (e) { $("setTtsSaved").textContent = " 로드 오류: " + e; });
}

/* voice_settings — stability/similarity_boost/style/speed 는 number, use_speaker_boost 는 checkbox */
function _renderTtsVoiceSettings(vs) {
  var box = $("setTtsVs");
  var nums = [
    { name: "stability", min: 0, max: 1, step: 0.05, def: 0.5 },
    { name: "similarity_boost", min: 0, max: 1, step: 0.05, def: 0.75 },
    { name: "style", min: 0, max: 1, step: 0.05, def: 0 },
    { name: "speed", min: 0.5, max: 2, step: 0.05, def: 1 }
  ];
  var html = "";
  nums.forEach(function (n) {
    var v = (vs[n.name] != null) ? vs[n.name] : n.def;
    html += '<div class="label">' + n.name + '</div>'
      + '<input type="number" data-vs="' + n.name + '" data-vstype="number" min="' + n.min
      + '" max="' + n.max + '" step="' + n.step + '" value="' + _esc(v) + '">';
  });
  var sb = (vs.use_speaker_boost != null) ? !!vs.use_speaker_boost : false;
  html += '<label class="set-chk"><input type="checkbox" data-vs="use_speaker_boost" data-vstype="boolean"'
    + (sb ? " checked" : "") + '> use_speaker_boost</label>';
  box.innerHTML = html;
}

function _collectTtsVoiceSettings() {
  var vs = {};
  var ctrls = $("setTtsVs").querySelectorAll("[data-vs]");
  for (var i = 0; i < ctrls.length; i++) {
    var el = ctrls[i];
    var name = el.getAttribute("data-vs");
    if (el.getAttribute("data-vstype") === "boolean") {
      vs[name] = !!el.checked;
    } else {
      var v = (el.value || "").trim();
      if (v === "") continue;
      vs[name] = parseFloat(v);
    }
  }
  return vs;
}

function _saveSetTts() {
  if (!SELECTED_PROJECT) return;
  var body = {
    project_id: SELECTED_PROJECT,
    model: $("setTtsModel").value,
    voice_id: ($("setTtsVoiceId").value || "").trim(),
    voice_settings: _collectTtsVoiceSettings()
  };
  var psel = $("setTtsPreset");
  if (psel && psel.value) body.style = psel.value;
  $("setTtsSaved").textContent = " 저장 중...";
  fetch(BACKEND + "/api/tts/settings", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(function (r) { return r.json(); })
    .then(function () { $("setTtsSaved").textContent = " 저장됨 ✓"; })
    .catch(function (e) { $("setTtsSaved").textContent = " 저장 실패: " + e; });
}

document.addEventListener("DOMContentLoaded", function () {
  var a = $("btnSetAccountReload"); if (a) a.addEventListener("click", loadSetAccount);
  var v = $("btnSaveVideoDefaults"); if (v) v.addEventListener("click", _saveVideoDefaults);
  var t = $("btnSaveSetTts"); if (t) t.addEventListener("click", _saveSetTts);
});
