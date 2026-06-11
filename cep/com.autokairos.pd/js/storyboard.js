/* 스토리보드 프로덕션 시트 — 씬당 1행. BACKEND/$/SELECTED_PROJECT/SELECTED_CHARACTER는 main.js 전역. */

function _esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function _badge(label, on) {
  return '<span class="badge ' + (on ? "on" : "off") + '">' + label + '</span>';
}

/* 컬럼 너비(px) — 5컬럼(씬#·이미지·스크립트·에셋·TTS) 전부 드래그 조절 + localStorage 저장 */
var COL_KEY = "ak_sheet_cols";
var COLW = _loadCols();

function _loadCols() {
  try {
    var s = window.localStorage.getItem(COL_KEY);
    if (s) { var a = JSON.parse(s); if (a && a.length === 5) return a; }
  } catch (e) {}
  return [30, 200, 280, 120, 70];
}

function _persistCols() {
  try { window.localStorage.setItem(COL_KEY, JSON.stringify(COLW)); } catch (e) {}
}

/* 씬별 원본 나레이션 — blur 시 변경 감지용 */
var NAR_ORIG = {};

function _colsCss() {
  return COLW.map(function (w) { return w + "px"; }).join(" ");
}

function _applyCols() {
  var el = $("sheet");
  if (el) el.style.setProperty("--cols", _colsCss());
}

function _autosizeAll() {
  var tas = $("sheet").querySelectorAll("textarea.nar");
  for (var i = 0; i < tas.length; i++) _autosize(tas[i]);
}

function _bindColResize() {
  var handles = $("sheet").querySelectorAll(".col-resize");
  for (var i = 0; i < handles.length; i++) {
    handles[i].addEventListener("mousedown", function (e) {
      e.preventDefault();
      var idx = parseInt(this.getAttribute("data-col"), 10);
      var startX = e.clientX, startW = COLW[idx] || 100;
      function move(ev) {
        COLW[idx] = Math.max(24, startW + (ev.clientX - startX));
        _applyCols();
        _autosizeAll();          // 폭 변하면 줄바꿈 → 세로 높이 재계산
      }
      function up() {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        _persistCols();          // 설정값 저장(다음에도 유지)
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
        + '<div>#<span class="col-resize" data-col="0"></span></div>'
        + '<div>이미지<span class="col-resize" data-col="1"></span></div>'
        + '<div>스크립트<span class="col-resize" data-col="2"></span></div>'
        + '<div>에셋<span class="col-resize" data-col="3"></span></div>'
        + '<div>TTS<span class="col-resize" data-col="4"></span></div>'
        + '</div>';
      $("sheet").innerHTML = head + list.map(function (s) { return renderRow(s, dir); }).join("");
      _applyCols();
      _bindColResize();
      bindRows();
      // 레이아웃 후 나레이션 높이 재계산(탭 표시 직후 scrollHeight=0 방지)
      if (window.requestAnimationFrame) requestAnimationFrame(_autosizeAll); else _autosizeAll();
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
    + '  <div class="col-num">' + n
    +      '<div class="scene-badges">'
    +        _badge("나", s._status && s._status.narration)
    +        _badge("이", s._status && s._status.image)
    +        _badge("레", s._status && s._status.layers)
    +        _badge("음", s._status && s._status.tts)
    +      '</div>'
    +      '<div class="scene-ops">'
    +        '<button class="op-add" data-scene="' + n + '" title="아래에 씬 추가">＋</button>'
    +        '<button class="op-split" data-scene="' + n + '" title="이 씬 분할">✂</button>'
    +        '<button class="op-merge" data-scene="' + n + '" title="다음 씬과 병합">⤵</button>'
    +        '<button class="op-del" data-scene="' + n + '" title="이 씬 삭제">🗑</button>'
    +      '</div>'
    + '  </div>'
    // 이미지 미리보기 + 레이어 썸네일
    + '  <div class="col-img">'
    +      (s._image ? '<button class="unlink-img" data-scene="' + n + '" title="씬 이미지 링크 해제">✕</button>' : '')
    +      (s._image ? '<button class="layer-img" data-scene="' + n + '" title="레이어 분리(LLM 분석)">⧉</button>' : '')
    +      media + (layers ? '<div>' + layers + '</div>' : '')
    + '  </div>'
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
    // TTS(씬별 생성 + 재생)
    + '  <div class="col-tts">'
    +      '<button class="gen-tts alt" data-scene="' + n + '">TTS 생성</button>'
    +      (s._audio ? '<audio controls preload="none" src="file://' + dir + '/' + s._audio + '"></audio>' : '')
    +      '<div class="row-status" data-scene="' + n + '"></div>'
    + '  </div>'
    + '</div>';
}

function _autosize(ta) {
  ta.style.height = "auto";
  ta.style.height = (ta.scrollHeight + 2) + "px";   // 내용 높이에 맞춰 확장(스크롤 없음)
}

function bindRows() {
  // 나레이션: 저장 버튼 없이 blur 시 변경되었으면 확인 후 저장(아니오=되돌림)
  var tas = $("sheet").querySelectorAll("textarea.nar");
  for (var t = 0; t < tas.length; t++) {
    _autosize(tas[t]);
    tas[t].addEventListener("input", function () { _autosize(this); });
    tas[t].addEventListener("blur", function () {
      var n = this.getAttribute("data-scene");
      var orig = NAR_ORIG[n] || "";
      if (this.value === orig) return;
      if (confirm("씬 " + n + " 나레이션 변경사항을 저장하시겠습니까?")) {
        saveNarration(n);
        NAR_ORIG[n] = this.value;
      } else {
        this.value = orig;   // 되돌림
        _autosize(this);
      }
    });
  }
  var gen = $("sheet").querySelectorAll("button.gen-img");
  for (var k = 0; k < gen.length; k++) {
    gen[k].addEventListener("click", function () { genSceneImage(this.getAttribute("data-scene")); });
  }
  var un = $("sheet").querySelectorAll("button.unlink-img");
  for (var u = 0; u < un.length; u++) {
    un[u].addEventListener("click", function () { unlinkScene(this.getAttribute("data-scene")); });
  }
  var ly = $("sheet").querySelectorAll("button.layer-img");
  for (var L = 0; L < ly.length; L++) {
    ly[L].addEventListener("click", function () { analyzeLayers(this.getAttribute("data-scene")); });
  }
  var gt = $("sheet").querySelectorAll("button.gen-tts");
  for (var g = 0; g < gt.length; g++) {
    gt[g].addEventListener("click", function () { genTts(this.getAttribute("data-scene")); });
  }
  _bindOp("op-add", function (n) { sceneOp("add", { after: parseInt(n, 10) }); });
  _bindOp("op-split", function (n) { sceneOp("split", { sceneNumber: parseInt(n, 10) }); });
  _bindOp("op-merge", function (n) { sceneOp("merge", { sceneNumber: parseInt(n, 10) }); });
  _bindOp("op-del", function (n) {
    if (confirm("씬 " + n + " 을 삭제할까요? (이미지/레이어 파일은 보존됩니다)"))
      sceneOp("delete", { sceneNumber: parseInt(n, 10) });
  });
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

function unlinkScene(n) {
  _rowStatus(n, "링크 해제 중...");
  fetch(BACKEND + "/api/scenes/unlink-image", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10) }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      _rowStatus(n, j.ok ? "링크 해제됨(파일은 갤러리에 보존)" : ("실패: " + JSON.stringify(j)));
      if (j.ok) loadSheet();
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
}

function analyzeLayers(n) {
  _rowStatus(n, "레이어 분석 중... (codex가 분할 요소 파악, 수십 초)");
  fetch(BACKEND + "/api/scenes/analyze-layers", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10) }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      var els = j.elements || [];
      if (!els.length) { _rowStatus(n, "분석 실패: " + (j.error || JSON.stringify(j))); return; }
      var list = els.map(function (e) {
        var tag = e.kind === "character" ? "[인물]" : "[사물]";
        return "· " + tag + " " + e.name + " (" + e.location + ")" + (e.reason ? " — " + e.reason : "");
      }).join("\n");
      if (confirm("내레이션 기반으로 다음 레이어를 분리합니다(움직임 필요한 것만):\n\n" + list + "\n\n진행할까요?")) {
        splitLayers(n, els);
      } else {
        _rowStatus(n, "분리 취소됨");
      }
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
}

function splitLayers(n, els) {
  _rowStatus(n, "레이어 분리 중... (" + els.length + "개 요소 + 배경, codex)");
  fetch(BACKEND + "/api/scenes/split-layers", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10), elements: els }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      var done = (j.result && j.result.layers) ? j.result.layers.filter(function (l) { return l.status === "completed"; }).length : 0;
      _rowStatus(n, done ? ("레이어 " + done + "개 생성 ✓") : ("실패: " + JSON.stringify(j)));
      if (done) loadSheet();   // 레이어 썸네일 갱신
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
      var ok = j.result && j.result.ok;
      _rowStatus(n, ok ? "적용됨 ✓" : ("실패: " + JSON.stringify(j)));
      if (ok) loadSheet();
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
}

function _bindOp(cls, fn) {
  var els = $("sheet").querySelectorAll("button." + cls);
  for (var i = 0; i < els.length; i++) {
    els[i].addEventListener("click", function () { fn(this.getAttribute("data-scene")); });
  }
}

function sceneOp(op, extra) {
  var b = { project_id: SELECTED_PROJECT };
  for (var k in extra) b[k] = extra[k];
  fetch(BACKEND + "/api/scenes/" + op, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(b),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.error) { alert("실패: " + j.error); return; }
      loadSheet();      // 갱신
    })
    .catch(function (e) { alert("오류: " + e); });
}

function genTts(n) {
  _rowStatus(n, "TTS 생성 중... (say)");
  fetch(BACKEND + "/api/scenes/tts", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10) }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      var ok = j.result && j.result.status === "completed";
      _rowStatus(n, ok ? ("TTS 완료 (" + (j.result.duration || 0).toFixed(1) + "s)") : ("실패: " + JSON.stringify(j)));
      if (ok) loadSheet();      // 오디오 플레이어 표시
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
}

function loadTtsSettings() {
  if (!SELECTED_PROJECT) return;
  fetch(BACKEND + "/api/tts/settings?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var sel = $("ttsStyle"); if (!sel) return;
      var presets = (j.presets && j.presets.presets) || {};
      sel.innerHTML = Object.keys(presets).map(function (k) {
        return '<option value="' + k + '">' + _esc(presets[k].label || k) + '</option>';
      }).join("");
      if (j.config) {
        sel.value = j.config.style;
        $("ttsStatus").textContent = "현재: " + j.config.style + " / voice " + j.config.voice_id;
      }
    }).catch(function () {});
}

function saveTtsSettings() {
  if (!SELECTED_PROJECT) { $("ttsStatus").textContent = "프로젝트를 먼저 선택하세요."; return; }
  var style = $("ttsStyle").value;
  var vid = ($("ttsVoiceId").value || "").trim();
  $("ttsStatus").textContent = "저장 중...";
  fetch(BACKEND + "/api/tts/settings", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, style: style, voice_id: vid }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      $("ttsStatus").textContent = j.config
        ? ("저장됨 — " + j.config.style + " / voice " + j.config.voice_id) : ("실패: " + JSON.stringify(j));
      $("ttsVoiceId").value = "";
    }).catch(function (e) { $("ttsStatus").textContent = "오류: " + e; });
}

document.addEventListener("DOMContentLoaded", function () {
  var b = $("btnSaveTts"); if (b) b.addEventListener("click", saveTtsSettings);
  var d = $("ttsSettings");
  if (d) d.addEventListener("toggle", function () { if (d.open) loadTtsSettings(); });
});
