/* 지도 씬 렌더 — 패널(Chromium)에서 MapLibre GL을 직접 띄워 1920x1080 캔버스를 캡처하고
   백엔드에 PNG로 저장 → 씬 이미지로 링크. 타일: OpenFreeMap(키 불필요).
   좌표 규칙: scenes.json은 [위도, 경도] — MapLibre는 [경도, 위도]라서 여기서 swap. */

/* CEP Chromium 폴리필 — maplibre v5가 쓰는 최신 API가 구버전 CEF에 없음 */
(function () {
  if (typeof AbortSignal !== "undefined") {
    if (!AbortSignal.prototype.throwIfAborted) {           // Chrome 100+
      AbortSignal.prototype.throwIfAborted = function () {
        if (this.aborted) throw (this.reason !== undefined ? this.reason : new Error("Aborted"));
      };
    }
    if (!AbortSignal.timeout) {                            // Chrome 103+
      AbortSignal.timeout = function (ms) {
        var c = new AbortController();
        setTimeout(function () { c.abort(new Error("TimeoutError")); }, ms);
        return c.signal;
      };
    }
    if (!AbortSignal.abort) {                              // Chrome 93+
      AbortSignal.abort = function (reason) {
        var c = new AbortController(); c.abort(reason); return c.signal;
      };
    }
  }
  if (typeof structuredClone === "undefined") {            // Chrome 98+
    window.structuredClone = function (v) { return JSON.parse(JSON.stringify(v)); };
  }
  if (!Array.prototype.at) {                               // Chrome 92+
    Array.prototype.at = function (i) { return this[i < 0 ? this.length + i : i]; };
  }
})();

var MAP_BRIGHT_URL = "https://tiles.openfreemap.org/styles/bright";
var MAP_DARK_URL = "https://tiles.openfreemap.org/styles/dark";

/* 맵 테마 — v3 mapStyles.ts 이식(레이어 paint 오버라이드).
   CSS 필터 테마는 캔버스 캡처에 안 구워지므로 오버라이드 방식만 사용. */
var MAP_THEMES = {
  warm_earth: { url: MAP_BRIGHT_URL, overrides: [          // 세모지 기본 — 따뜻한 대지색
    { match: "background", paint: { "background-color": "#F0E8DE" } },
    { match: "water", paint: { "fill-color": "#C8BAA0" } },
    { match: "waterway*", paint: { "line-color": "#B8A888" } },
    { match: "landcover*", paint: { "fill-color": "#E4DCC8", "fill-opacity": 0.5 } },
    { match: "landuse*", paint: { "fill-color": "#E8DDCC", "fill-opacity": 0.3 } },
    { match: "park*", paint: { "fill-color": "#D4CCB8", "fill-opacity": 0.5 } },
    { match: "boundary*", paint: { "line-color": "#8A6E48", "line-width": 1.6, "line-opacity": 0.9 } },
    { match: "road*", paint: { "line-color": "#C8B498", "line-opacity": 0.7 } },
    { match: "building*", paint: { "fill-color": "#E0D6C8", "fill-opacity": 0.4 } },
  ] },
  matte_slate: { url: MAP_DARK_URL, overrides: [           // 뉴트럴 다크
    { match: "background", paint: { "background-color": "#1A1C22" } },
    { match: "water", paint: { "fill-color": "#0E1018" } },
    { match: "waterway*", paint: { "line-color": "#1E2030" } },
    { match: "landcover*", paint: { "fill-color": "#22242E", "fill-opacity": 0.4 } },
    { match: "landuse*", paint: { "fill-color": "#20222C", "fill-opacity": 0.3 } },
    { match: "park*", paint: { "fill-color": "#1E2028", "fill-opacity": 0.3 } },
    { match: "boundary*", paint: { "line-color": "#6A6E7C", "line-width": 1.4, "line-opacity": 0.8 } },
    { match: "road*", paint: { "line-color": "#383C48", "line-opacity": 0.6 } },
    { match: "building*", paint: { "fill-color": "#24262E", "fill-opacity": 0.3 } },
  ] },
  clean_white: { url: MAP_BRIGHT_URL, overrides: [         // 순백 모던
    { match: "background", paint: { "background-color": "#FFFFFF" } },
    { match: "water", paint: { "fill-color": "#D6E6F5" } },
    { match: "waterway*", paint: { "line-color": "#B0D0F0" } },
    { match: "landcover*", paint: { "fill-color": "#F0F4F0", "fill-opacity": 0.3 } },
    { match: "landuse*", paint: { "fill-color": "#F8F8FA", "fill-opacity": 0.2 } },
    { match: "park*", paint: { "fill-color": "#E8F2E8", "fill-opacity": 0.3 } },
    { match: "boundary*", paint: { "line-color": "#A0AAB8", "line-width": 1.2, "line-opacity": 0.8 } },
    { match: "road*", paint: { "line-color": "#D8DCE4", "line-opacity": 0.7 } },
    { match: "building*", paint: { "fill-color": "#F0F0F4", "fill-opacity": 0.3 } },
  ] },
  dark_cyber: { url: MAP_DARK_URL, overrides: [
    { match: "boundary*", paint: { "line-color": "#4A8080", "line-width": 1.2, "line-opacity": 0.8 } },
    { match: "water", paint: { "fill-color": "#18202A" } },
    { match: "road*", paint: { "line-color": "#2A3540", "line-opacity": 0.6 } },
  ] },
  bright: { url: MAP_BRIGHT_URL, overrides: [] },
};

// v3 applyLayerOverrides 이식 — match는 정확 일치 또는 "prefix*"
function _applyOverrides(map, overrides) {
  var style = map.getStyle();
  if (!style || !style.layers) return;
  for (var i = 0; i < overrides.length; i++) {
    var ov = overrides[i];
    var isPrefix = ov.match.charAt(ov.match.length - 1) === "*";
    var prefix = isPrefix ? ov.match.slice(0, -1) : "";
    for (var j = 0; j < style.layers.length; j++) {
      var id = style.layers[j].id;
      if (!(isPrefix ? id.indexOf(prefix) === 0 : id === ov.match)) continue;
      for (var k in (ov.paint || {})) {
        try { map.setPaintProperty(id, k, ov.paint[k]); } catch (e) { }
      }
    }
  }
}

function _mapTheme() {                                      // ae_tokens.map.defaultTheme(세모지=warm_earth)
  var name = (typeof TOKENS === "object" && TOKENS && TOKENS.map && TOKENS.map.defaultTheme) || "warm_earth";
  return MAP_THEMES[name] || MAP_THEMES.warm_earth;
}

function _swapLL(c) { return [c[1], c[0]]; }   // [lat,lng] → [lng,lat]

// s: 씬 객체(map_center/map_zoom/map_markers). resolve(상대경로) / reject(에러)
function renderMapScene(s) {
  return new Promise(function (resolve, reject) {
    if (typeof maplibregl === "undefined") { reject("maplibre-gl 미로드 — 패널 재오픈 필요"); return; }
    var glTest = document.createElement("canvas");
    if (!glTest.getContext("webgl2") && !glTest.getContext("webgl")) {
      reject("WebGL 비활성 — AE를 완전히 재시작해야 적용됩니다(manifest에 --enable-webgl 추가됨)"); return;
    }
    var center = s.map_center && s.map_center.length === 2 ? _swapLL(s.map_center) : [127.0, 37.5];
    var host = document.createElement("div");
    host.style.cssText = "position:fixed;left:-99999px;top:0;width:1920px;height:1080px";
    document.body.appendChild(host);
    var done = false;
    function finish(err, dataUrl) {
      if (done) return; done = true;
      stopRepaint();
      try { map.remove(); } catch (e) { }
      host.remove();
      if (err) reject(err); else resolve(dataUrl);
    }
    var map, stage = "init", lastErr = "";
    var repaint = null;                          // 숨김 패널 rAF 스로틀 대응 — 강제 리페인트
    function stopRepaint() { if (repaint) { clearInterval(repaint); repaint = null; } }
    try {
      var theme = _mapTheme();
      map = new maplibregl.Map({
        container: host, style: theme.url,
        center: center, zoom: s.map_zoom || 5,
        interactive: false, attributionControl: false,
        preserveDrawingBuffer: true,            // canvas.toDataURL 필수
        fadeDuration: 0,
      });
    } catch (e) { finish("지도 초기화 실패: " + e); return; }
    repaint = setInterval(function () { try { map.triggerRepaint(); } catch (e) { } }, 400);
    map.on("error", function (e) {
      // 타일 일부 실패는 무시(렌더 지속) — 마지막 에러는 타임아웃 진단에 사용
      lastErr = String((e && e.error && e.error.message) || e || "");
      if (/style/i.test(lastErr) && stage === "init") finish("스타일 로드 실패: " + lastErr);
    });
    map.on("load", function () {
      stage = "load";
      _applyOverrides(map, theme.overrides);               // 아트스타일 맵 테마 적용
      // idle(타일 완전 로드)을 기다리되, 못 받으면 18초 후 현재 상태로 캡처(베스트에포트)
      var bestEffort = setTimeout(function () { capture(); }, 18000);
      function capture() {
        clearTimeout(bestEffort); stopRepaint();
        captureNow();
      }
      map.once("idle", function () {                       // 타일 렌더 완료 시점
        stage = "idle";
        capture();
      });
      // 마커/경로는 지도에 굽지 않는다 — captureNow가 map.project()로
      // 위경도→캡처 픽셀 좌표(geo 사이드카)만 추출(AE 셰이프/텍스트 재료)
      function captureNow() {
        try {
          var dark = theme.url === MAP_DARK_URL;
          var geo = { markers: [], route: [],
                      labelRgb: dark ? [232, 234, 237] : [26, 26, 26] };   // 테마 대비색(jsx 라벨용)
          (s.map_markers || []).forEach(function (m) {
            var pt = map.project(_swapLL(m.coord));
            geo.markers.push({ name: m.name || "", x: Math.round(pt.x), y: Math.round(pt.y) });
          });
          (s.map_route || []).forEach(function (c) {
            var rp = map.project(_swapLL(c));
            geo.route.push([Math.round(rp.x), Math.round(rp.y)]);
          });
          finish(null, { dataUrl: map.getCanvas().toDataURL("image/png"), geo: geo });
        } catch (e) { finish("캡처 실패: " + e); }
      }
    });
    setTimeout(function () {
      stopRepaint();
      finish("지도 렌더 타임아웃(45s) — 단계: " + stage + (lastErr ? ", 마지막 에러: " + lastErr : ""));
    }, 45000);
  });
}

// 체크된(또는 단일) 씬의 지도 생성 → 백엔드 저장(이미지+geo 사이드카) → 행 갱신
function genMapForScene(s) {
  return renderMapScene(s).then(function (res) {
    return fetch(BACKEND + "/api/scenes/map-image", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: s.sceneNumber,
                             dataUrl: res.dataUrl, geo: res.geo }),
    }).then(function (r) { return r.json(); });
  });
}
