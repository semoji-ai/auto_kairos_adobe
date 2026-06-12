/* 지도 씬 렌더 — 패널(Chromium)에서 MapLibre GL을 직접 띄워 1920x1080 캔버스를 캡처하고
   백엔드에 PNG로 저장 → 씬 이미지로 링크. 타일: OpenFreeMap(키 불필요).
   좌표 규칙: scenes.json은 [위도, 경도] — MapLibre는 [경도, 위도]라서 여기서 swap. */

var MAP_STYLE_URL = "https://tiles.openfreemap.org/styles/bright";

function _swapLL(c) { return [c[1], c[0]]; }   // [lat,lng] → [lng,lat]

// s: 씬 객체(map_center/map_zoom/map_markers). resolve(상대경로) / reject(에러)
function renderMapScene(s) {
  return new Promise(function (resolve, reject) {
    if (typeof maplibregl === "undefined") { reject("maplibre-gl 미로드"); return; }
    var center = s.map_center && s.map_center.length === 2 ? _swapLL(s.map_center) : [127.0, 37.5];
    var host = document.createElement("div");
    host.style.cssText = "position:fixed;left:-99999px;top:0;width:1920px;height:1080px";
    document.body.appendChild(host);
    var done = false;
    function finish(err, dataUrl) {
      if (done) return; done = true;
      try { map.remove(); } catch (e) { }
      host.remove();
      if (err) reject(err); else resolve(dataUrl);
    }
    var map;
    try {
      map = new maplibregl.Map({
        container: host, style: MAP_STYLE_URL,
        center: center, zoom: s.map_zoom || 5,
        interactive: false, attributionControl: false,
        preserveDrawingBuffer: true,            // canvas.toDataURL 필수
        fadeDuration: 0,
      });
    } catch (e) { finish("지도 초기화 실패: " + e); return; }
    map.on("error", function (e) {
      // 타일 일부 실패는 무시(렌더 지속) — 스타일 로드 실패만 치명
      if (e && e.error && /style/i.test(String(e.error.message || ""))) finish("스타일 로드 실패: " + e.error.message);
    });
    map.on("load", function () {
      var marks = s.map_markers || [];
      if (marks.length) {
        var fc = { type: "FeatureCollection", features: marks.map(function (m) {
          return { type: "Feature", properties: { name: m.name || "" },
                   geometry: { type: "Point", coordinates: _swapLL(m.coord) } };
        }) };
        map.addSource("ak-markers", { type: "geojson", data: fc });
        map.addLayer({ id: "ak-marker-dot", type: "circle", source: "ak-markers",
          paint: { "circle-radius": 14, "circle-color": "#4A90D9",
                   "circle-stroke-width": 5, "circle-stroke-color": "#ffffff" } });
        map.addLayer({ id: "ak-marker-label", type: "symbol", source: "ak-markers",
          layout: { "text-field": ["get", "name"], "text-size": 34,
                    "text-offset": [0, 1.3], "text-anchor": "top",
                    "text-font": ["Noto Sans Bold"] },
          paint: { "text-color": "#1a1a1a", "text-halo-color": "#ffffff", "text-halo-width": 2.5 } });
      }
      map.once("idle", function () {                       // 타일+심볼 렌더 완료 시점
        try { finish(null, map.getCanvas().toDataURL("image/png")); }
        catch (e) { finish("캡처 실패: " + e); }
      });
    });
    setTimeout(function () { finish("지도 렌더 타임아웃(45s)"); }, 45000);
  });
}

// 체크된(또는 단일) 씬의 지도 생성 → 백엔드 저장 → 행 갱신
function genMapForScene(s) {
  return renderMapScene(s).then(function (dataUrl) {
    return fetch(BACKEND + "/api/scenes/map-image", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: SELECTED_PROJECT, sceneNumber: s.sceneNumber, dataUrl: dataUrl }),
    }).then(function (r) { return r.json(); });
  });
}
