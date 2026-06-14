/* 스토리보드 프로덕션 시트 — 씬당 1행. BACKEND/$/SELECTED_PROJECT/SELECTED_CHARACTER는 main.js 전역. */

function _esc(s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/* 진행 점 — 작업 칸에서 완료 상태 표시(●=완료, ○=미완) */
function _dot(label, on) {
  return '<span class="dot ' + (on ? "on" : "off") + '" title="' + label + (on ? " 완료" : " 미완") + '"></span>';
}

/* 컬럼 너비(px) — 4컬럼(씬#·이미지·스크립트·작업) 드래그 조절 + localStorage 저장 */
var COL_KEY = "ak_sheet_cols";
var COLW = _loadCols();

function _loadCols() {
  try {
    var s = window.localStorage.getItem(COL_KEY);
    if (s) { var a = JSON.parse(s); if (a && a.length === 4) return a; }
  } catch (e) {}
  return [30, 200, 300, 150];
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

// 디자인 토큰(ae_tokens) — 시트 미리보기가 색/크기를 AE 빌드와 동일 소스로 사용
var TOKENS = null;
function _loadTokens() {
  if (TOKENS) return Promise.resolve(TOKENS);
  return fetch(BACKEND + "/api/tokens").then(function (r) { return r.json(); })
    .then(function (j) { TOKENS = j || {}; return TOKENS; })
    .catch(function () { TOKENS = {}; return TOKENS; });
}

// 컴프 결과 미리보기 — jsx renderLayout(1920 기준)을 200px 폭으로 축소 미러링.
// 이미지 씬=이미지+자막 오버레이, 레이아웃 씬=셰이프/텍스트 근사 렌더(동일 토큰).
function _previewHTML(s, dir) {
  var T = TOKENS || {}, c = T.colors || {}, t = T.type || {};
  function px(v) { return (v * 200 / 1920).toFixed(1) + "px"; }      // 1920 디자인 px → 미리보기 px
  function rgb(a, fb) { a = a || fb; return "rgb(" + a[0] + "," + a[1] + "," + a[2] + ")"; }
  var BG = rgb(c.bgRgb, [35, 38, 43]), TX = rgb(c.textRgb, [232, 234, 237]),
      MU = rgb(c.mutedRgb, [154, 160, 166]), AC = rgb(c.accentRgb, [74, 144, 217]);
  // 자막 미리보기 — 나레이션 첫 ~20자(어절 경계), 하단 중앙
  var nar = (s.narration || "").replace(/\s+/g, " ").trim(), sub1 = "";
  if (nar) {
    var ws = nar.split(" ");
    for (var wi = 0; wi < ws.length; wi++) {
      if (sub1 && (sub1 + " " + ws[wi]).length > 20) break;
      sub1 = sub1 ? sub1 + " " + ws[wi] : ws[wi];
    }
  }
  var subEl = sub1 ? '<div class="pv-subtitle" style="font-size:' + px(t.subtitle || 54) + '">' + _esc(sub1) + "</div>" : "";
  var inner = "";
  if (s.layout === "map" && !s._image) {
    return '<div class="layout-badge">map — 🗺 지도 버튼으로 렌더</div>';
  }
  if (!s.layout || s.layout === "cinematic" || s.layout === "map") {
    if (!s._image) return '<div style="color:#666;font-size:11px">(없음)</div>';
    return '<div class="pv" style="background:' + BG + '">'
      + '<img class="main" src="file://' + dir + "/" + s._image + '">' + subEl + "</div>";
  }
  if (s.layout === "headline_only") {
    inner = '<div class="pv-abs" style="left:50%;top:30%;width:' + px(120) + ";height:" + px(10) + ";background:" + AC + ';transform:translateX(-50%)"></div>'
      + '<div class="pv-abs pv-headline" style="left:8%;width:84%;top:34%;font-size:' + px(t.headline || 110) + ";color:" + TX + ';text-align:center;line-height:1.25">' + _esc(s.headline || "") + "</div>"
      + (s.sub ? '<div class="pv-abs pv-body" style="left:15%;width:70%;top:62%;font-size:' + px(t.sub || 48) + ";color:" + MU + ';text-align:center">' + _esc(s.sub) + "</div>" : "");
  } else if (s.layout === "items_list") {
    inner = '<div class="pv-abs pv-headline" style="left:0;width:100%;top:11%;font-size:' + px((t.sub || 48) * 1.5) + ";color:" + TX + ';text-align:center">' + _esc(s.headline || "") + "</div>"
      + '<div class="pv-abs" style="left:16%;width:68%;top:23.5%;height:1px;background:' + AC + '"></div>';
    var items = s.items || [], gpct = Math.min(12, 58 / Math.max(1, items.length));
    for (var ii = 0; ii < items.length; ii++) {
      var typ = 33 + ii * gpct;
      inner += '<div class="pv-abs" style="left:16%;top:' + (typ - 1.8) + "%;width:" + px(12) + ";height:" + px(42) + ";background:" + AC + '"></div>'
        + '<div class="pv-abs pv-body" style="left:20%;width:62%;top:' + (typ - 2.2) + "%;font-size:" + px(t.item || 52) + ";color:" + TX + ';text-align:left;white-space:nowrap;overflow:hidden">' + _esc(items[ii]) + "</div>";
    }
  } else if (s.layout === "metric_spotlight") {
    inner = '<div class="pv-abs pv-number" style="left:0;width:100%;top:32%;font-size:' + px(t.metric || 220) + ";color:" + AC + ';text-align:center;line-height:1">' + _esc(s.value || "") + "</div>"
      + '<div class="pv-abs" style="left:50%;top:58.5%;width:' + px(220) + ";height:" + px(5) + ";background:" + AC + ';transform:translateX(-50%)"></div>'
      + '<div class="pv-abs pv-body" style="left:15%;width:70%;top:63%;font-size:' + px(t.metricLabel || 54) + ";color:" + TX + ';text-align:center">' + _esc(s.label || "") + "</div>";
  } else if (s.layout === "bar") {
    inner = '<div class="pv-abs pv-headline" style="left:0;width:100%;top:9%;font-size:' + px((t.sub || 48) * 1.4) + ";color:" + TX + ';text-align:center">' + _esc(s.headline || "") + "</div>"
      + '<div class="pv-abs" style="left:13%;width:74%;top:76%;height:1px;background:' + MU + '"></div>';
    var ch = s.chart || {}, vals = ch.values || [], labels = ch.labels || [];
    var n2 = Math.max(1, vals.length), maxV = 0;
    for (var vi = 0; vi < vals.length; vi++) if (vals[vi] > maxV) maxV = vals[vi];
    for (var bi = 0; bi < vals.length; bi++) {
      var bhPct = maxV ? (vals[bi] / maxV) * 42 : 0;                 // jsx maxH=H*0.42
      var gw = 70 / n2, bxPct = 15 + gw * bi + gw * 0.225, bwPct = gw * 0.55;
      var barStyle = "background:" + AC;
      var CS = s.chartSpec || {};
      if (CS.patternKind && CS.patternKind !== "solid" && CS.patternKind !== "none") {
        // 미리보기 해칭 근사 — CSS repeating-linear-gradient(대각/세로/교차)
        var ang = CS.patternKind === "vertical_stripe" ? "90deg" : "45deg";
        var gap = Math.max(3, (CS.patternSpacing || 12) / 4);
        barStyle = "background:repeating-linear-gradient(" + ang + "," + AC + " 0 1.5px,transparent 1.5px " + gap + "px)," + AC.replace("rgb", "rgba").replace(")", "," + (CS.patternOpacity || 0.4) + ")");
        if (CS.outlineWidth) barStyle += ";outline:1px solid " + AC;
      }
      inner += '<div class="pv-abs" style="left:' + bxPct + "%;width:" + bwPct + "%;top:" + (76 - bhPct) + "%;height:" + bhPct + "%;" + barStyle + '"></div>'
        + '<div class="pv-abs pv-body" style="left:' + (bxPct - gw * 0.2) + "%;width:" + (bwPct + gw * 0.4) + "%;top:78.5%;font-size:" + px(t.barLabel || 36) + ";color:" + MU + ';text-align:center;white-space:nowrap;overflow:hidden">' + _esc(labels[bi] || "") + "</div>"
        + '<div class="pv-abs pv-bold" style="left:' + (bxPct - gw * 0.2) + "%;width:" + (bwPct + gw * 0.4) + "%;top:" + (76 - bhPct - 4.5) + "%;font-size:" + px(t.barValue || 40) + ";color:" + TX + ';text-align:center">' + _esc(String(vals[bi]) + (ch.unit || "")) + "</div>";
    }
  } else if (s.layout === "quote") {
    inner = '<div class="pv-abs pv-quote" style="left:12%;top:24%;font-size:' + px((t.quote || 64) * 2.2) + ";color:" + AC + ';line-height:1">“</div>'
      + '<div class="pv-abs pv-quote" style="left:19%;width:62%;top:32%;font-size:' + px(t.quote || 64) + ";color:" + TX + ';text-align:center;line-height:1.5">' + _esc(s.quote_text || "") + "</div>"
      + '<div class="pv-abs pv-quote" style="right:12%;top:58%;font-size:' + px((t.quote || 64) * 2.2) + ";color:" + AC + ';line-height:1">”</div>'
      + '<div class="pv-abs pv-quote" style="left:19%;width:62%;top:72%;font-size:' + px(t.quoteWho || 40) + ";color:" + MU + ';text-align:right">— ' + _esc(s.quote_who || "") + "</div>";
  } else {
    return '<div class="layout-badge">' + _esc(s.layout) + "</div>";
  }
  return '<div class="pv" style="background:' + BG + '">' + inner + subEl + "</div>";
}

function loadSheet() {
  if (!SELECTED_PROJECT) { $("sheet").textContent = "프로젝트를 먼저 선택하세요."; return; }
  $("sheet").textContent = "불러오는 중...";
  _loadTokens().then(function () {
  return fetch(BACKEND + "/api/scenes?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var dir = j.dir || "", list = j.scenes || [];
      if (!list.length) { $("sheet").textContent = "(씬 없음 — 씬 분해 먼저)"; return; }
      NAR_ORIG = {};
      list.forEach(function (s) { NAR_ORIG[s.sceneNumber] = s.narration || ""; });
      var head = '<div class="sheet-head">'
        + '<div><input type="checkbox" id="selAllScenes" title="전체 선택/해제">#<span class="col-resize" data-col="0"></span></div>'
        + '<div>이미지<span class="col-resize" data-col="1"></span></div>'
        + '<div>스크립트<span class="col-resize" data-col="2"></span></div>'
        + '<div>작업<span class="col-resize" data-col="3"></span></div>'
        + '</div>';
      $("sheet").innerHTML = head + list.map(function (s) { return renderRow(s, dir); }).join("");
      _applyCols();
      _bindColResize();
      bindRows();
      loadThemes();
      var sa = $("selAllScenes");
      if (sa) sa.addEventListener("change", function () {
        var on = this.checked;
        SEL_SCENES = {};
        var cbs = $("sheet").querySelectorAll("input.scene-sel");
        for (var c = 0; c < cbs.length; c++) {
          cbs[c].checked = on;
          if (on) SEL_SCENES[cbs[c].getAttribute("data-scene")] = true;
        }
      });
      // 레이아웃 후 나레이션 높이 재계산(탭 표시 직후 scrollHeight=0 방지)
      if (window.requestAnimationFrame) requestAnimationFrame(_autosizeAll); else _autosizeAll();
    });
  })
    .catch(function (e) { $("sheet").textContent = "오류: " + e; });
}

function renderRow(s, dir) {
  var n = s.sceneNumber;
  var media = _previewHTML(s, dir);   // 컴프 결과 미리보기(배경+레이아웃+자막)
  var layers = (s._layers || []).map(function (lp) {
    return '<img class="lyr" src="file://' + dir + '/' + lp + '" title="' + _esc(lp)
      + ' — 클릭하면 씬 위에 위치 확인(빨간 윤곽선)">';
  }).join("");
  var chars = (s.characters || []).join(", ");
  var st = s._status || {};
  return ''
    + '<div class="sheet-row" data-scene="' + n + '" ondragover="event.preventDefault()" ondrop="dropOnScene(event,' + n + ')">'
    // 씬# — 체크박스로 선택 → 상단 도구상자 버튼이 체크된 씬에 일괄 실행
    + '  <div class="col-num">'
    +      '<label class="scene-sel-wrap"><input type="checkbox" class="scene-sel" data-scene="' + n + '"'
    +        (SEL_SCENES[n] ? ' checked' : '') + '> ' + n + '</label>'
    + '  </div>'
    // 이미지 미리보기 + 레이어 썸네일(클릭=씬 위에 빨간 윤곽선 오버레이)
    + '  <div class="col-img">'
    +      (s._image ? '<button class="unlink-img" data-scene="' + n + '" title="씬 이미지 링크 해제">✕</button>' : '')
    + '    <div class="img-wrap">' + media + '</div>'
    +      (layers ? '<div class="lyr-strip">' + layers + '</div>' : '')
    + '  </div>'
    // 스크립트(나레이션)
    + '  <div class="col-script">'
    + '    <div class="row-title">' + _esc(s.title || "") + '</div>'
    + '    <textarea class="nar" data-scene="' + n + '" rows="3">' + _esc(s.narration || "") + '</textarea>'
    + '  </div>'
    // 작업 — 진행 점(●=완료) + 플레이어 + 상태(실행 버튼은 시트 상단 도구상자)
    + '  <div class="col-work">'
    +      '<div class="work-dots" title="이미지·레이어·음성·모션 진행 상태">'
    +        _dot("이미지", st.image) + _dot("레이어", st.layers) + _dot("음성", st.tts) + _dot("모션", st.motion)
    +      '</div>'
    + (chars ? '<div class="work-chars">👤 ' + _esc(chars) + '</div>' : '')
    +      (s._audio
        ? ('<div class="tts-player">'
           + '<button class="tts-play" title="재생/정지">▶</button>'
           + '<span class="tts-dur">' + (s._audio_dur ? _fmtDur(s._audio_dur) : "--:--") + '</span>'
           + '<audio class="tts-audio" preload="none" src="file://' + dir + '/' + s._audio + '"></audio>'
           + '</div>')
        : '')
    + '    <div class="row-status" data-scene="' + n + '"></div>'
    + '  </div>'
    + '</div>';
}

function _autosize(ta) {
  ta.style.height = "auto";
  ta.style.height = (ta.scrollHeight + 2) + "px";   // 내용 높이에 맞춰 확장(스크롤 없음)
}

function _fmtDur(sec) {
  sec = Math.round(sec || 0);
  var m = Math.floor(sec / 60), s = sec % 60;
  return m + ":" + (s < 10 ? "0" : "") + s;
}

/* 커스텀 TTS 플레이어 — 좁은 칸에서도 재생 버튼·길이가 보이게 */
function _bindTtsPlayer(pl) {
  var audio = pl.querySelector(".tts-audio");
  var btn = pl.querySelector(".tts-play");
  var durEl = pl.querySelector(".tts-dur");
  if (!audio || !btn) return;
  audio.addEventListener("loadedmetadata", function () {
    if (isFinite(audio.duration)) durEl.textContent = _fmtDur(audio.duration);
  });
  btn.addEventListener("click", function () {
    if (audio.paused) { audio.play(); btn.textContent = "⏸"; }
    else { audio.pause(); btn.textContent = "▶"; }
  });
  audio.addEventListener("ended", function () { btn.textContent = "▶"; });
}

/* scope: 바인딩 대상 루트(기본 전체 시트). refreshRow는 새 행만 넘겨 중복 리스너 방지. */
function bindRows(scope) {
  scope = scope || $("sheet");
  // 나레이션: 저장 버튼 없이 blur 시 변경되었으면 확인 후 저장(아니오=되돌림)
  var tas = scope.querySelectorAll("textarea.nar");
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
  var un = scope.querySelectorAll("button.unlink-img");
  for (var u = 0; u < un.length; u++) {
    un[u].addEventListener("click", function () { unlinkScene(this.getAttribute("data-scene")); });
  }
  var players = scope.querySelectorAll(".tts-player");
  for (var pp = 0; pp < players.length; pp++) { _bindTtsPlayer(players[pp]); }
  var cbs = scope.querySelectorAll("input.scene-sel");
  for (var cb = 0; cb < cbs.length; cb++) {
    cbs[cb].addEventListener("change", function () {
      var n = this.getAttribute("data-scene");
      if (this.checked) SEL_SCENES[n] = true; else delete SEL_SCENES[n];
    });
  }
  var thumbs = scope.querySelectorAll("img.lyr");
  for (var th = 0; th < thumbs.length; th++) {
    thumbs[th].addEventListener("click", function () { toggleLayerOverlay(this); });
  }
}

/* 레이어 썸네일 클릭 — 풀프레임 레이어를 씬 이미지 위에 1:1로 겹치고
   알파 윤곽을 따라 빨간 테두리(drop-shadow) 표시. 같은 썸네일 재클릭=해제. */
function toggleLayerOverlay(thumb) {
  var row = thumb.closest(".sheet-row");
  if (!row) return;
  var wrap = row.querySelector(".img-wrap");
  if (!wrap) return;
  var prev = wrap.querySelector(".lyr-overlay");
  var was = thumb.classList.contains("sel");
  // 기존 오버레이/선택 해제
  if (prev) prev.parentNode.removeChild(prev);
  var sels = row.querySelectorAll("img.lyr.sel");
  for (var i = 0; i < sels.length; i++) sels[i].classList.remove("sel");
  if (was) return;                     // 같은 썸네일 → 토글 오프
  var ov = document.createElement("img");
  ov.className = "lyr-overlay";
  ov.src = thumb.src;                  // 풀프레임(씬과 동일 크기) — width:100%로 정확히 겹침
  wrap.appendChild(ov);
  thumb.classList.add("sel");
}

/* ===== 도구상자(시트 상단) — 체크된 씬에 일괄 실행 ===== */
var SEL_SCENES = {};    // {sceneNumber(str): true} — 재렌더에도 유지

function _checkedScenes() {
  return Object.keys(SEL_SCENES).map(function (k) { return parseInt(k, 10); })
    .sort(function (a, b) { return a - b; });
}

function _needChecked(min, what) {
  var ns = _checkedScenes();
  if (ns.length < (min || 1)) { alert("씬을 먼저 체크하세요" + (what ? " — " + what : "") + "."); return null; }
  return ns;
}

/* 순차 실행 — 각 씬을 차례로(fn은 promise 반환). 행 상태는 각 fn이 표시. */
function _runSeq(ns, fn) {
  return ns.reduce(function (p, n) {
    return p.then(function () { return fn(n); }).catch(function () { /* 한 씬 실패해도 계속 */ });
  }, Promise.resolve());
}

function bindSheetToolbar() {
  function on(id, h) { var b = $(id); if (b) b.addEventListener("click", h); }
  on("sa-img", function () {
    var ns = _needChecked(1, "이미지 생성"); if (ns) _runSeq(ns, genSceneImage);
  });
  on("sa-layer", function () {
    var ns = _needChecked(1, "레이어 분리"); if (!ns) return;
    analyzeLayers(ns);            // 여러 씬이면 탭 모달 — 분석 병렬, 분리도 병렬 잡
  });
  on("sa-tts", function () {
    var ns = _needChecked(1, "TTS 생성"); if (ns) _runSeq(ns, genTts);
  });
  on("sa-motion", function () {
    var ns = _needChecked(1, "모션 플랜"); if (ns) _runSeq(ns, planMotion);
  });
  on("sa-comp", function () {
    var ns = _needChecked(1, "AE 컴프"); if (ns) _runSeq(ns, function (n) {
      return Promise.resolve(buildSceneComp(n));
    });
  });
  on("sa-map", function () {
    var ns = _needChecked(1, "지도 렌더"); if (!ns) return;
    var box = $("aeresult"), st = $("sa-status");
    function say(t) { if (st) st.textContent = t; if (box) box.textContent = t; }
    say("지도 렌더 중... (타일 다운로드 수 초)");
    fetch(BACKEND + "/api/scenes?project_id=" + encodeURIComponent(SELECTED_PROJECT))
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var by = {}; (j.scenes || []).forEach(function (s) { by[s.sceneNumber] = s; });
        return _runSeq(ns, function (n) {
          var s = by[n];
          if (!s) return Promise.resolve();
          if (s.layout !== "map") { say("씬 " + n + ": layout이 map이 아니라 건너뜀"); return Promise.resolve(); }
          return genMapForScene(s)
            .then(function (res) {
              if (res && res.error) { say("씬 " + n + " 지도 실패: " + res.error); return; }
              say("씬 " + n + " 지도 완료 ✓"); refreshRow(n);
            })
            .catch(function (e) { say("씬 " + n + " 지도 실패: " + e); });
        });
      })
      .catch(function (e) { say("지도 렌더 실패: " + e); });
  });
  on("sa-chart", function () {
    var ns = _needChecked(1, "차트 명세서"); if (!ns) return;
    var st = $("sa-status"), box = $("aeresult");
    function say(t) { if (st) st.textContent = t; if (box) box.textContent = t; }
    say("차트 명세서 생성 중...");
    _runSeq(ns, function (n) {
      return fetch(BACKEND + "/api/scenes/chart-spec", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: n }),
      }).then(function (r) { return r.json(); })
        .then(function (res) {
          if (res && res.error) { say("씬 " + n + " 차트: " + res.error); return; }
          say("씬 " + n + " 차트 명세 완료 ✓ (" + (res.theme_set || "") + ")");
        })
        .catch(function (e) { say("씬 " + n + " 차트 실패: " + e); });
    });
  });
  on("sa-theme", function () {
    var ns = _needChecked(1, "씬 테마"); if (!ns) return;
    var tid = window.prompt("이 씬에 적용할 테마 id(비우면 해제):", "");
    _runSeq(ns, function (n) {
      return fetch(BACKEND + "/api/themes/set-scene", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: n, theme_id: tid || null }),
      }).then(function (r) { return r.json(); }).then(function () { refreshRow(n); });
    });
  });
  on("sa-add", function () {
    var ns = _checkedScenes();
    sceneOp("add", ns.length ? { after: ns[ns.length - 1] } : {});   // 체크 없으면 맨 끝에
  });
  on("sa-split", function () {
    var ns = _needChecked(1, "분할(1개만)"); if (!ns) return;
    if (ns.length > 1) { alert("분할은 한 씬만 체크하세요."); return; }
    sceneOp("split", { sceneNumber: ns[0] });
  });
  on("sa-merge", function () {
    var ns = _needChecked(1, "병합(1개만 — 다음 씬과 합쳐짐)"); if (!ns) return;
    if (ns.length > 1) { alert("병합은 한 씬만 체크하세요(그 씬과 다음 씬이 합쳐집니다)."); return; }
    sceneOp("merge", { sceneNumber: ns[0] });
  });
  on("sa-del", function () {
    var ns = _needChecked(1, "삭제"); if (!ns) return;
    if (!confirm("체크된 씬 " + ns.join(", ") + " 을 삭제할까요? (이미지/레이어 파일은 보존됩니다)")) return;
    SEL_SCENES = {};
    _runSeq(ns.slice().reverse(), function (n) {           // 높은 번호부터(재번호 영향 회피)
      return fetch(BACKEND + "/api/scenes/delete", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: n }),
      }).then(function (r) { return r.json(); });
    }).then(function () { loadSheet(); });
  });
}

document.addEventListener("DOMContentLoaded", bindSheetToolbar);

/* 단일 씬 행만 갱신 — 전체 loadSheet의 포커스 손실/스크롤 점프 방지.
   행 수가 변하는 구조 편집(add/del/split/merge)은 loadSheet 사용. */
function refreshRow(n) {
  fetch(BACKEND + "/api/scenes?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      var s = (j.scenes || []).filter(function (x) { return x.sceneNumber === parseInt(n, 10); })[0];
      var old = $("sheet").querySelector('.sheet-row[data-scene="' + n + '"]');
      if (!s || !old) { loadSheet(); return; }            // 못 찾으면 전체 갱신 폴백
      NAR_ORIG[s.sceneNumber] = s.narration || "";
      var tmp = document.createElement("div");
      tmp.innerHTML = renderRow(s, j.dir || "");
      var fresh = tmp.firstChild;
      old.parentNode.replaceChild(fresh, old);
      bindRows(fresh);                                     // 새 행만 바인딩(중복 리스너 방지)
      var ta = fresh.querySelector("textarea.nar");
      if (ta) _autosize(ta);
    })
    .catch(function () { loadSheet(); });
}

/* 씬 모션 플랜(LLM) — 동기 호출, 완료 시 상태줄 안내 */
function planMotion(n) {
  _rowStatus(n, "모션 설계 중... (LLM, 비동기)");
  return fetch(BACKEND + "/api/scenes/motion", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10) }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "running" || !j.job_id) { _rowStatus(n, "실패: " + (j.error || JSON.stringify(j))); return; }
      return new Promise(function (resolve) {
        _awaitJob(j.job_id, function (job) {
          var plan = job.result && job.result.plan;
          if (job.status === "completed" && plan) {
            var nmoves = (plan.layers || []).reduce(function (a, L) { return a + (L.moves || []).length; }, 0);
            _rowStatus(n, "모션 " + nmoves + "개 + 카메라 " + ((plan.camera || {}).type || "none") + " ✓ — 🎬 컴프로 적용");
            refreshRow(n);                                 // 모션 점 갱신
          } else {
            _rowStatus(n, "실패: " + (job.error || JSON.stringify(job)));
          }
          resolve();
        });
      });
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
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
  return fetch(BACKEND + "/api/scenes/image", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10),
                           character: SELECTED_CHARACTER || "" }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      _rowStatus(n, (j.result && j.result.status === "completed") ? "생성 완료 ✓" : ("실패: " + JSON.stringify(j)));
      if (j.result && j.result.status === "completed") refreshRow(n);   // 썸네일 갱신(행 단위)
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
      if (j.ok) refreshRow(n);
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
}

/* 레이어 분리 — 여러 씬 동시: 씬별 분석을 병렬로 돌리고 탭으로 확인·체크 후 일괄(병렬) 분리 */
var _layerMulti = {};        // {n: {els: [...], done: bool}}

function analyzeLayers(ns) {
  if (!(ns instanceof Array)) ns = [ns];
  _layerMulti = {};
  $("layerTabs").innerHTML = ns.map(function (n, i) {
    return '<button class="layer-tab' + (i === 0 ? " active" : "") + '" data-scene="' + n + '">씬 ' + n + '</button>';
  }).join("");
  $("layerList").innerHTML = "";
  ns.forEach(function (n) {
    var pane = document.createElement("div");
    pane.className = "layer-pane";
    pane.setAttribute("data-scene", n);
    pane.innerHTML = '<div style="color:#9aa0a6;padding:8px">씬 ' + n + ' 분석 중... (codex, 수십 초)</div>';
    pane.hidden = String(n) !== String(ns[0]);
    $("layerList").appendChild(pane);
  });
  $("layerModalStatus").textContent = ns.length + "개 씬 분석 중 — 완료된 탭부터 확인하세요.";
  $("layerModal").hidden = false;
  var tabs = $("layerTabs").querySelectorAll(".layer-tab");
  for (var t = 0; t < tabs.length; t++) {
    tabs[t].addEventListener("click", function () { _switchLayerTab(this.getAttribute("data-scene")); });
  }
  // 씬별 분석 병렬 실행
  ns.forEach(function (n) {
    _rowStatus(n, "레이어 분석 중...");
    fetch(BACKEND + "/api/scenes/analyze-layers", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10) }),
    }).then(function (r) { return r.json(); })
      .then(function (j) {
        var els = j.elements || [];
        _layerMulti[n] = { els: els, done: true };
        _renderLayerPane(n, els, j.error);
        _rowStatus(n, els.length ? (els.length + "개 요소 분석됨") : ("분석 실패: " + (j.error || "")));
        _updateLayerModalStatus();
      })
      .catch(function (e) {
        _layerMulti[n] = { els: [], done: true };
        _renderLayerPane(n, [], String(e));
        _updateLayerModalStatus();
      });
  });
}

function _renderLayerPane(n, els, err) {
  var pane = $("layerList").querySelector('.layer-pane[data-scene="' + n + '"]');
  if (!pane) return;
  if (!els.length) {
    pane.innerHTML = '<div style="color:#e74c3c;padding:8px">씬 ' + n + ' 분석 실패: ' + _esc(err || "") + '</div>';
    return;
  }
  pane.innerHTML = els.map(function (e, i) {
    var tag = e.kind === "character" ? "👤 인물" : "📦 사물";
    return '<label class="layer-chk"><input type="checkbox" data-idx="' + i + '" checked>'
      + '<span><b>' + tag + '</b> ' + _esc(e.name)
      + ' <span style="color:#9aa0a6">(' + _esc(e.location) + ')</span>'
      + (e.reason ? '<br><span style="font-size:10px;color:#9aa0a6">' + _esc(e.reason) + '</span>' : '')
      + '</span></label>';
  }).join("");
}

function _switchLayerTab(n) {
  var tabs = $("layerTabs").querySelectorAll(".layer-tab");
  for (var t = 0; t < tabs.length; t++) {
    tabs[t].classList.toggle("active", tabs[t].getAttribute("data-scene") === String(n));
  }
  var panes = $("layerList").querySelectorAll(".layer-pane");
  for (var p = 0; p < panes.length; p++) {
    panes[p].hidden = panes[p].getAttribute("data-scene") !== String(n);
  }
}

function _updateLayerModalStatus() {
  var total = Object.keys(_layerMulti).length;
  var done = Object.keys(_layerMulti).filter(function (k) { return _layerMulti[k].done; }).length;
  $("layerModalStatus").textContent = done < total
    ? ("분석 " + done + "/" + total + " 완료 — 완료된 탭부터 확인 가능")
    : "전체 분석 완료 — 탭별로 체크 확인 후 [선택 분리]를 누르세요(씬별 병렬 실행).";
}

function _closeLayerModal() { $("layerModal").hidden = true; }

function _submitLayerSplit() {
  var panes = $("layerList").querySelectorAll(".layer-pane");
  var jobs = [];
  for (var p = 0; p < panes.length; p++) {
    var n = panes[p].getAttribute("data-scene");
    var info = _layerMulti[n];
    if (!info || !info.els.length) continue;
    var chks = panes[p].querySelectorAll('input[type="checkbox"]');
    var chosen = [];
    for (var i = 0; i < chks.length; i++) {
      if (chks[i].checked) chosen.push(info.els[parseInt(chks[i].getAttribute("data-idx"), 10)]);
    }
    if (chosen.length) jobs.push({ n: n, els: chosen });
  }
  if (!jobs.length) { $("layerModalStatus").textContent = "분리할 요소를 1개 이상 체크하세요."; return; }
  _closeLayerModal();
  jobs.forEach(function (j) { splitLayers(j.n, j.els); });   // 씬별 병렬 잡(각자 폴링)
}

document.addEventListener("DOMContentLoaded", function () {
  var s = $("layerSubmit"); if (s) s.addEventListener("click", _submitLayerSplit);
  var c = $("layerCancel"); if (c) c.addEventListener("click", _closeLayerModal);
  var x = $("layerClose"); if (x) x.addEventListener("click", _closeLayerModal);
});

function splitLayers(n, els) {
  _rowStatus(n, "레이어 분리 중... (" + els.length + "개 요소 + 배경, codex)");
  fetch(BACKEND + "/api/scenes/split-layers", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10), elements: els }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "running" || !j.job_id) { _rowStatus(n, "실패: " + JSON.stringify(j)); return; }
      _awaitJob(j.job_id, function (job) {
        var res = (job.result && job.result.result) || {};
        var done = (res.layers || []).filter(function (l) { return l.status === "completed"; }).length;
        _rowStatus(n, done ? ("레이어 " + done + "개 생성 ✓") : ("실패: " + JSON.stringify(job.error || job)));
        if (done) refreshRow(n);   // 레이어 썸네일 갱신(행 단위)
      }, function (logs) {
        if (logs.length) _rowStatus(n, "레이어 분리 중... " + logs[logs.length - 1]);
      }, 1600);   // 40분 한도 — 병렬 분리 시 큐 대기 포함(5분 기본은 거짓 타임아웃 유발)
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
      if (ok) refreshRow(n);
    })
    .catch(function (e) { _rowStatus(n, "오류: " + e); });
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
  _rowStatus(n, "TTS 생성 중... (ElevenLabs)");
  return fetch(BACKEND + "/api/scenes/tts", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: parseInt(n, 10) }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      var ok = j.result && j.result.status === "completed";
      _rowStatus(n, ok ? ("TTS 완료 (" + (j.result.duration || 0).toFixed(1) + "s)") : ("실패: " + JSON.stringify(j)));
      if (ok) refreshRow(n);      // 오디오 플레이어 표시(행 단위)
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

// 프로젝트 테마 드롭다운 — 카탈로그 로드 + 현재 프로젝트 테마 선택 + 변경 시 저장
function loadThemes() {
  var sel = $("projectTheme");
  if (!sel || !SELECTED_PROJECT) return;
  fetch(BACKEND + "/api/themes").then(function (r) { return r.json(); }).then(function (j) {
    var themeList = j.themes || [];
    fetch(BACKEND + "/api/scenes?project_id=" + encodeURIComponent(SELECTED_PROJECT))
      .then(function (r) { return r.json(); }).then(function (sd) {
        var cur = (sd._theme && sd._theme.id) || "";
        sel.innerHTML = themeList.map(function (t) {
          return '<option value="' + t.id + '"' + (t.id === cur ? " selected" : "") + ">" + _esc(t.label || t.id) + "</option>";
        }).join("");
      });
  });
  sel.onchange = function () {
    fetch(BACKEND + "/api/themes/set-project", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: SELECTED_PROJECT, theme_id: sel.value }),
    }).then(function () { loadSheet(); });
  };
}
