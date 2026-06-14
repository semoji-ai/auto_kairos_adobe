// auto_kairos — manifest 기반 AE 컴프 생성 (PoC, 최소 모션)
// 입력: manifest 경로(JSON). 출력: 씬별 컴프 + Final 컴프(순서 배치).
// JSON 파싱: json2.jsx 폴리필(JSON.parse) 우선, 없으면 eval 폴백.

function akBuildScene(manifestPath) {
    // 디자인 토큰(semoji) — manifest.ae_tokens 로드 실패 시 내장 기본값
    var TK = { colors: { bgRgb: [35, 38, 43], textRgb: [232, 234, 237], mutedRgb: [154, 160, 166], accentRgb: [74, 144, 217] },
               fonts: { headline: "", body: "", number: "", fallback: "AppleSDGothicNeo-Bold" },
               type: { headline: 110, sub: 48, item: 52, metric: 220, metricLabel: 54, quote: 64, quoteWho: 40, barLabel: 36, barValue: 40 } };

    // 폰트 해석 — AE 폰트 DB(app.fonts)에서 PS명 검증, 실패 시 패밀리 키워드 검색으로 보정.
    // AE가 못 찾으면 경고 수집(빌드 결과 문자열에 노출) — 조용한 폴백 금지.
    var FONT_WARN = [];
    function resolveFontPS(ps, famKey, styleHint) {
        try {
            if (!(app.fonts && app.fonts.allFonts)) return ps;   // 구버전 AE — 검증 불가, 그대로
            var groups = app.fonts.allFonts, i, j, f;
            for (i = 0; i < groups.length; i++) for (j = 0; j < groups[i].length; j++) {
                if (groups[i][j].postScriptName === ps) return ps;   // 설치 확인됨
            }
            if (famKey) {                                        // PS명 불일치 → 패밀리로 탐색
                var best = null, key = String(famKey).toLowerCase();
                for (i = 0; i < groups.length && !best; i++) for (j = 0; j < groups[i].length; j++) {
                    f = groups[i][j];
                    if (String(f.familyName).toLowerCase().indexOf(key) < 0) continue;
                    if (!best) best = f;
                    if (styleHint && String(f.styleName).toLowerCase().indexOf(String(styleHint).toLowerCase()) >= 0) { best = f; break; }
                }
                if (best) { FONT_WARN.push(ps + "→" + best.postScriptName); return best.postScriptName; }
            }
            FONT_WARN.push(ps + " 미설치(AE 재시작 필요)");
        } catch (e) { }
        return ps;
    }

    // 배경 솔리드 + 텍스트/셰이프 빌더 — 레이아웃 씬(JSON→결정적 렌더)
    function addBgSolid(comp, W, H, rgb) {
        return comp.layers.addSolid([rgb[0] / 255, rgb[1] / 255, rgb[2] / 255], "bg", W, H, 1.0);
    }
    // 텍스트 레이어 — opts: {x,y,size,rgb,font,just,track,box:[w,h],leading}
    // box 지정 시 박스 텍스트(자동 줄바꿈, x/y=박스 중심). 폰트는 폴백 체인 + 적용 검증.
    function addTextL(comp, str, opts) {
        var tl = opts.box
            ? comp.layers.addBoxText([opts.box[0], opts.box[1]], String(str))
            : comp.layers.addText(String(str));
        var td = tl.property("Source Text").value;
        td.fontSize = opts.size;
        td.fillColor = [opts.rgb[0] / 255, opts.rgb[1] / 255, opts.rgb[2] / 255];
        var chain = [opts.font, TK.fonts.fallback, "AppleSDGothicNeo-Bold"];
        for (var fi = 0; fi < chain.length; fi++) {
            if (!chain[fi]) continue;
            try {
                td.font = chain[fi];
                tl.property("Source Text").setValue(td);
                td = tl.property("Source Text").value;
                if (td.font === chain[fi]) break;        // 실제 적용됐는지 되읽어 확인
            } catch (e) { }
        }
        try { td.justification = opts.just || ParagraphJustification.CENTER_JUSTIFY; } catch (e) { }
        try { if (opts.track) td.tracking = opts.track; } catch (e) { }
        try { if (opts.leading) { td.autoLeading = false; td.leading = opts.size * opts.leading; } } catch (e) { }
        tl.property("Source Text").setValue(td);
        if (opts.box) {
            try { tl.property("Anchor Point").setValue([opts.box[0] / 2, opts.box[1] / 2]); } catch (e) { }
        }
        tl.property("Position").setValue([opts.x, opts.y]);
        return tl;
    }
    function addRectL(comp, name, x, y, w, h, rgb) {   // 좌상단 기준 사각형 셰이프
        var sl = comp.layers.addShape(); sl.name = name;
        var grp = sl.property("Contents").addProperty("ADBE Vector Group");
        var rect = grp.property("Contents").addProperty("ADBE Vector Shape - Rect");
        rect.property("Size").setValue([w, h]);
        var fill = grp.property("Contents").addProperty("ADBE Vector Graphic - Fill");
        fill.property("Color").setValue([rgb[0] / 255, rgb[1] / 255, rgb[2] / 255]);
        sl.property("Position").setValue([x + w / 2, y + h / 2]);
        return sl;
    }
    // 점선 적용 — dash="4 6" 형식(있으면). 셰이프 레이어 첫 스트로크에.
    function applyDash(layer, dash, S) {
        if (!dash) return;
        try {
            var grp = layer.property("Contents").property(1);
            var stroke = null, cc = grp.property("Contents");
            for (var i = 1; i <= cc.numProperties; i++) {
                if (cc.property(i).matchName === "ADBE Vector Graphic - Stroke") { stroke = cc.property(i); break; }
            }
            if (!stroke) return;
            var parts = String(dash).split(/\s+/);
            var dProp = stroke.property("Dashes").addProperty("ADBE Vector Stroke Dash 1");
            dProp.setValue(parseFloat(parts[0]) * S);
        } catch (e) { }
    }
    // 평행선 해칭 한 방향을 사각형 [x0..x1, y0..y1]에 클립해 그룹에 추가.
    // dir: "diag1"(↘ 기울기1) / "diag2"(↙ 기울기-1) / "vert" / "horiz"
    function _hatchDir(hc, x0, x1, y0, y1, sp, dir) {
        var b, pts, pp, shp;
        if (dir === "vert") {
            for (b = x0 + sp / 2; b < x1; b += sp) {
                pp = hc.addProperty("ADBE Vector Shape - Group");
                shp = new Shape(); shp.vertices = [[b, y0], [b, y1]]; shp.closed = false;
                pp.property("Path").setValue(shp);
            }
            return;
        }
        if (dir === "horiz") {
            for (b = y0 + sp / 2; b < y1; b += sp) {
                pp = hc.addProperty("ADBE Vector Shape - Group");
                shp = new Shape(); shp.vertices = [[x0, b], [x1, b]]; shp.closed = false;
                pp.property("Path").setValue(shp);
            }
            return;
        }
        var slope = (dir === "diag2") ? -1 : 1;          // y = slope*x + b
        var bMin = (slope > 0) ? (y0 - x1) : (y0 + x0);
        var bMax = (slope > 0) ? (y1 - x0) : (y1 + x1);
        for (b = bMin; b <= bMax; b += sp) {
            pts = [];
            var yA = slope * x0 + b; if (yA >= y0 && yA <= y1) pts.push([x0, yA]);
            var yB = slope * x1 + b; if (yB >= y0 && yB <= y1) pts.push([x1, yB]);
            var xA = (y0 - b) / slope; if (xA > x0 && xA < x1) pts.push([xA, y0]);
            var xB = (y1 - b) / slope; if (xB > x0 && xB < x1) pts.push([xB, y1]);
            if (pts.length < 2) continue;
            pp = hc.addProperty("ADBE Vector Shape - Group");
            shp = new Shape(); shp.vertices = [pts[0], pts[1]]; shp.closed = false;
            pp.property("Path").setValue(shp);
        }
    }
    // chartagent 명세 반영 막대 — 채움(+패턴 오퍼시티) + 외곽선 + 패턴을 한 레이어에.
    // 사각형은 레이어 원점 중심 [-w/2..w/2, -h/2..h/2] → bar 루프가 앵커/포지션으로 하단 고정.
    function addBarShape(comp, name, w, h, rgb, CS, S) {
        var sl = comp.layers.addShape(); sl.name = name;
        var root = sl.property("Contents");
        // 패턴 종류 — chartagent: diagonal_hatch / wide_diagonal / crosshatch_light / vertical_stripe / dot_sparse
        var pk = CS.patternKind || "";
        var patterned = pk && pk !== "solid" && pk !== "none";
        var outlineW = (CS.outlineWidth || 0) * S;
        var x0 = -w / 2, x1 = w / 2, y0 = -h / 2, y1 = h / 2;
        // 채움 — 패턴이면 약하게(패턴 오퍼시티), 아니면 단색
        var fg = root.addProperty("ADBE Vector Group");
        var rect = fg.property("Contents").addProperty("ADBE Vector Shape - Rect");
        rect.property("Size").setValue([w, h]);
        var fill = fg.property("Contents").addProperty("ADBE Vector Graphic - Fill");
        fill.property("Color").setValue(rgb);
        if (patterned) { try { fill.property("Opacity").setValue((CS.patternOpacity != null ? CS.patternOpacity : 0.45) * 100); } catch (e) { } }
        // 패턴 — 사각형에 클립된 선/점들(같은 레이어 → Scale 동반)
        if (patterned) {
            var sp = (CS.patternSpacing || 14) * S, sw = (CS.patternStrokeWidth || 1.3) * S;
            if (pk === "wide_diagonal") sp *= 1.7;
            if (pk === "dot_sparse") {
                // 점 격자 — 작은 원 채움
                var dg = root.addProperty("ADBE Vector Group"), dc = dg.property("Contents");
                var r = Math.max(1.2 * S, sw);
                for (var dx = x0 + sp; dx < x1; dx += sp) {
                    for (var dy = y0 + sp; dy < y1; dy += sp) {
                        var eg = dc.addProperty("ADBE Vector Group");
                        var el = eg.property("Contents").addProperty("ADBE Vector Shape - Ellipse");
                        el.property("Size").setValue([r * 2, r * 2]);
                        el.property("Position").setValue([dx, dy]);
                    }
                }
                var df = dc.addProperty("ADBE Vector Graphic - Fill");
                df.property("Color").setValue(rgb);
            } else {
                var hg = root.addProperty("ADBE Vector Group"), hc = hg.property("Contents");
                if (pk === "vertical_stripe") {
                    _hatchDir(hc, x0, x1, y0, y1, sp, "vert");
                } else if (pk === "crosshatch_light") {
                    _hatchDir(hc, x0, x1, y0, y1, sp, "diag1");
                    _hatchDir(hc, x0, x1, y0, y1, sp, "diag2");   // 양방향 교차
                } else {                                          // diagonal_hatch / wide_diagonal / 기타
                    _hatchDir(hc, x0, x1, y0, y1, sp, "diag1");
                }
                var hst = hg.property("Contents").addProperty("ADBE Vector Graphic - Stroke");
                hst.property("Color").setValue(rgb);
                hst.property("Stroke Width").setValue(sw);
            }
        }
        // 외곽선 — 마지막에 추가(맨 위)
        if (outlineW > 0) {
            var og = root.addProperty("ADBE Vector Group");
            var orect = og.property("Contents").addProperty("ADBE Vector Shape - Rect");
            orect.property("Size").setValue([w, h]);
            var ost = og.property("Contents").addProperty("ADBE Vector Graphic - Stroke");
            ost.property("Color").setValue(rgb);
            ost.property("Stroke Width").setValue(outlineW);
        }
        return sl;
    }
    // 지도 오버레이 — 지도는 배경판(이미지)이고 마커/라벨/경로는 AE 네이티브 레이어.
    // geo: {markers:[{name,x,y}], route:[[x,y]...], labelRgb} — 픽셀 좌표(map.project 기준).
    // 키프레임/경로/라벨 전부 AE에서 직접 수정 가능.
    function renderMapOverlay(comp, geo, W, H, dur) {
        var c = TK.colors, S = W / 1920;
        var ac = [c.accentRgb[0] / 255, c.accentRgb[1] / 255, c.accentRgb[2] / 255];
        var lr = geo.labelRgb || [26, 26, 26];
        // 1) 이동 경로 — 셰이프 패스 + Trim Paths(끝 0→100%)로 선이 그려지는 애니메이션
        if (geo.route && geo.route.length >= 2) {
            var rl = comp.layers.addShape(); rl.name = "map_route";
            rl.property("Position").setValue([0, 0]);
            rl.property("Anchor Point").setValue([0, 0]);
            var rg = rl.property("Contents").addProperty("ADBE Vector Group");
            var pathProp = rg.property("Contents").addProperty("ADBE Vector Shape - Group");
            var shp = new Shape();
            shp.vertices = geo.route; shp.closed = false;
            pathProp.property("Path").setValue(shp);
            var st = rg.property("Contents").addProperty("ADBE Vector Graphic - Stroke");
            st.property("Color").setValue(ac);
            st.property("Stroke Width").setValue(8 * S);
            try {
                st.property("Line Cap").setValue(2);                    // 둥근 끝
                st.property("Dashes").addProperty("Dash");              // 점선(여정 느낌)
                st.property("Dashes").property("Dash").setValue(26 * S);
            } catch (eD) { }
            var trim = rg.property("Contents").addProperty("ADBE Vector Filter - Trim");
            var te = trim.property("End");
            te.setValueAtTime(0.4, 0); te.setValueAtTime(Math.max(1.2, dur * 0.6), 100);
            try { te.setTemporalEaseAtKey(2, [new KeyframeEase(0, 33)], [new KeyframeEase(0, 33)]); } catch (eE) { }
        }
        // 2) 마커 — 점별 셰이프 레이어(흰 테두리 원), 순차 팝 등장
        var marks = geo.markers || [];
        for (var mi = 0; mi < marks.length; mi++) {
            var m = marks[mi], t0 = 0.3 + mi * 0.4;
            var ml = comp.layers.addShape(); ml.name = "map_marker_" + (m.name || mi);
            var mg = ml.property("Contents").addProperty("ADBE Vector Group");
            var el = mg.property("Contents").addProperty("ADBE Vector Shape - Ellipse");
            el.property("Size").setValue([34 * S, 34 * S]);
            var mfill = mg.property("Contents").addProperty("ADBE Vector Graphic - Fill");
            mfill.property("Color").setValue(ac);
            var mst = mg.property("Contents").addProperty("ADBE Vector Graphic - Stroke");
            mst.property("Color").setValue([1, 1, 1]);
            mst.property("Stroke Width").setValue(6 * S);
            ml.property("Anchor Point").setValue([0, 0]);               // 피벗=원 중심(팝이 제자리)
            ml.property("Position").setValue([m.x, m.y]);
            var msc = ml.property("Scale");
            msc.setValueAtTime(t0, [0, 0]);
            msc.setValueAtTime(t0 + 0.25, [115, 115]);
            msc.setValueAtTime(t0 + 0.38, [100, 100]);
            // 3) 라벨 — 텍스트 레이어(테마 대비색), 마커 옆에서 페이드 인
            if (m.name) {
                var tl2 = addTextL(comp, m.name, { x: m.x, y: m.y + 56 * S, size: 36 * S,
                                                   rgb: lr, font: TK.fonts.bold || TK.fonts.body });
                tl2.name = "map_label_" + m.name;
                var lop = tl2.property("Opacity");
                lop.setValueAtTime(t0 + 0.15, 0); lop.setValueAtTime(t0 + 0.45, 100);
            }
        }
    }

    // 레이아웃 5종 결정적 렌더 — 1080p 기준 토큰을 S=W/1920 배율로 스케일(4K/720p 대응).
    // 긴 텍스트는 박스 텍스트(자동 줄바꿈 + 행간 1.25). 세로 폼은 별도 템플릿 필요(추후).
    function renderLayout(comp, s, W, H) {
        var c = TK.colors, t = TK.type;
        var S = W / 1920;                                  // 해상도 배율(1080p=1)
        addBgSolid(comp, W, H, c.bgRgb);
        if (s.layout === "headline_only") {
            // 액센트 바(타이틀 위 포인트) + 줄바꿈 박스 헤드라인 + 서브
            addRectL(comp, "accent", W / 2 - 60 * S, H * 0.30, 120 * S, 10 * S, c.accentRgb);
            addTextL(comp, s.headline || "", { x: W / 2, y: H * 0.47, size: t.headline * S, rgb: c.textRgb,
                                               font: TK.fonts.headline, box: [W * 0.84, H * 0.34], leading: 1.25 });
            if (s.sub) addTextL(comp, s.sub, { x: W / 2, y: H * 0.67, size: t.sub * S, rgb: c.mutedRgb,
                                               font: TK.fonts.body, box: [W * 0.7, H * 0.12], leading: 1.3 });
        } else if (s.layout === "items_list") {
            addTextL(comp, s.headline || "", { x: W / 2, y: H * 0.16, size: t.sub * 1.5 * S, rgb: c.textRgb, font: TK.fonts.headline });
            addRectL(comp, "rule", W * 0.16, H * 0.235, W * 0.68, 3 * S, c.accentRgb);   // 제목 밑줄
            var items = s.items || [];
            var y0 = H * 0.33, gap = Math.min(130 * S, (H * 0.58) / Math.max(1, items.length));
            for (var ii = 0; ii < items.length; ii++) {
                var by = y0 + ii * gap;
                var bl = addRectL(comp, "bullet" + ii, W * 0.16, by - 21 * S, 12 * S, 42 * S, c.accentRgb);
                var boxW = W * 0.62;
                var il2 = addTextL(comp, items[ii], { x: W * 0.2 + boxW / 2, y: by, size: t.item * S, rgb: c.textRgb,
                                                      font: TK.fonts.body, just: ParagraphJustification.LEFT_JUSTIFY,
                                                      box: [boxW, gap * 0.9], leading: 1.2 });
                var op = il2.property("Opacity");                     // 순차 등장
                op.setValueAtTime(0.2 + ii * 0.35, 0); op.setValueAtTime(0.5 + ii * 0.35, 100);
                var opb = bl.property("Opacity");
                opb.setValueAtTime(0.2 + ii * 0.35, 0); opb.setValueAtTime(0.5 + ii * 0.35, 100);
            }
        } else if (s.layout === "metric_spotlight") {
            addTextL(comp, s.value || "", { x: W / 2, y: H * 0.46, size: t.metric * S, rgb: c.accentRgb, font: TK.fonts.number });
            addRectL(comp, "rule", W / 2 - 110 * S, H * 0.585, 220 * S, 5 * S, c.accentRgb);
            addTextL(comp, s.label || "", { x: W / 2, y: H * 0.68, size: t.metricLabel * S, rgb: c.textRgb,
                                            font: TK.fonts.body, box: [W * 0.7, H * 0.12], leading: 1.3 });
        } else if (s.layout === "bar") {
            addTextL(comp, s.headline || "", { x: W / 2, y: H * 0.13, size: t.sub * 1.4 * S, rgb: c.textRgb, font: TK.fonts.headline });
            var ch2 = s.chart || {}, labels = ch2.labels || [], vals = ch2.values || [];
            var n = Math.max(1, vals.length), maxV = 0;
            for (var vi = 0; vi < vals.length; vi++) if (vals[vi] > maxV) maxV = vals[vi];
            // chartagent 명세서(chartSpec) — 없으면 단순 단색 막대 기본값
            var CS = s.chartSpec || {};
            var areaW = W * 0.7, baseY = H * 0.76, maxH = H * 0.42;
            var bw = Math.min(150 * S, areaW / n * 0.55), gap2 = areaW / n;
            var accent = [c.accentRgb[0] / 255, c.accentRgb[1] / 255, c.accentRgb[2] / 255];
            var muted = [c.mutedRgb[0] / 255, c.mutedRgb[1] / 255, c.mutedRgb[2] / 255];
            // 가이드선(기준선 위 수평선) — chartSpec.guideLineCount 만큼 점선
            var glc = CS.guideLineCount || 0;
            for (var gi = 1; gi <= glc; gi++) {
                var gy = baseY - (maxH * gi) / (glc + 1);
                var gl = addRectL(comp, "guide" + gi, W * 0.13, gy, W * 0.74, (CS.guideStrokeWidth || 1) * S, c.mutedRgb);
                gl.property("Opacity").setValue((CS.guideOpacity != null ? CS.guideOpacity : 0.3) * 100);
                applyDash(gl, CS.guideDash, S);              // 점선 패턴(있으면)
            }
            addRectL(comp, "axis", W * 0.13, baseY, W * 0.74, (CS.axisStrokeWidth || 2) * S, c.mutedRgb);  // 기준선
            for (var bi = 0; bi < n; bi++) {
                var bh = maxV ? (vals[bi] / maxV) * maxH : 0;
                var bx = W * 0.15 + gap2 * bi + (gap2 - bw) / 2;
                // chartSpec 반영 막대(채움+외곽선+해칭이 한 레이어 → Scale 애니메이션 동반)
                var bar = addBarShape(comp, "bar" + bi, bw, bh, accent, CS, S);
                bar.property("Anchor Point").setValue([0, bh / 2]);   // 하단 고정 성장
                bar.property("Position").setValue([bx + bw / 2, baseY]);
                var sc2 = bar.property("Scale");
                sc2.setValueAtTime(0.2 + bi * 0.15, [100, 0]); sc2.setValueAtTime(0.7 + bi * 0.15, [100, 100]);
                addTextL(comp, labels[bi] || "", { x: bx + bw / 2, y: baseY + 56 * S, size: t.barLabel * S, rgb: c.mutedRgb, font: TK.fonts.body });
                var vt = addTextL(comp, String(vals[bi]) + (ch2.unit || ""), { x: bx + bw / 2, y: baseY - bh - 28 * S, size: t.barValue * S, rgb: c.textRgb, font: TK.fonts.bold || TK.fonts.body });
                var vop = vt.property("Opacity");                     // 수치는 막대 완성 후 표시
                vop.setValueAtTime(0.55 + bi * 0.15, 0); vop.setValueAtTime(0.8 + bi * 0.15, 100);
            }
        } else if (s.layout === "quote") {
            // 인용 — 명조(경기천년바탕). 여는따옴표=텍스트 박스 좌상단, 닫는따옴표=우하단, 출처=우측 정렬
            var qf = TK.fonts.quote || TK.fonts.headline;
            var qBoxW = W * 0.62, qBoxH = H * 0.36, qY = H * 0.47;
            addTextL(comp, "“", { x: W / 2 - qBoxW / 2 - 70 * S, y: qY - qBoxH / 2 + 10 * S,
                                  size: t.quote * 2.2 * S, rgb: c.accentRgb, font: qf });
            addTextL(comp, s.quote_text || "", { x: W / 2, y: qY, size: t.quote * S, rgb: c.textRgb,
                                                 font: qf, box: [qBoxW, qBoxH], leading: 1.5 });
            addTextL(comp, "”", { x: W / 2 + qBoxW / 2 + 70 * S, y: qY + qBoxH / 2 - 10 * S,
                                  size: t.quote * 2.2 * S, rgb: c.accentRgb, font: qf });
            addTextL(comp, "— " + (s.quote_who || ""), { x: W / 2 + qBoxW / 2 - 200 * S, y: qY + qBoxH / 2 + 90 * S,
                                  size: t.quoteWho * S, rgb: c.mutedRgb, font: qf,
                                  just: ParagraphJustification.RIGHT_JUSTIFY, box: [400 * S, t.quoteWho * 1.6 * S] });
        }
    }
    // 레이어 추가. layer.position 있으면 그 좌표·스케일로(크롭된 요소), 없으면 컴프 채움·중앙(풀프레임/배경).
    // 자동 효과(페이드 등)는 넣지 않는다 — 모든 모션은 모션 플랜(applyMoves)에서만(규칙 기반).
    function addLayerObj(proj, comp, layer, W, H) {
        var f = new File(layer.path);
        if (!f.exists) return null;
        var foot = proj.importFile(new ImportOptions(f));
        var il = comp.layers.add(foot);
        var sw = il.source.width, sh = il.source.height;
        il.property("Anchor Point").setValue([sw / 2, sh / 2]);
        if (layer.position) {                         // 크롭된 요소 — 원위치 좌표 적용
            il.property("Position").setValue([layer.position[0], layer.position[1]]);
            var es = (layer.scale != null) ? layer.scale : 100;
            il.property("Scale").setValue([es, es]);
        } else {                                      // 풀프레임(배경/단일 이미지) — 채움·중앙
            il.property("Position").setValue([W / 2, H / 2]);
            var fs = Math.max(W / sw, H / sh) * 100;
            il.property("Scale").setValue([fs, fs]);
        }
        return il;
    }
    // 프리셋 모션 → 키프레임(결정적). 실패해도 빌드는 계속(try/catch).
    // 발밑(불투명 하단 중앙) 피벗 null 생성 + 페어런팅 + 세로 스케일 100↔(100+amt) 이지이즈 핑퐁 루프.
    // foot = manifest가 계산한 알파 bbox 하단 중앙(전신=발, 상반신=절단점) — 까딱까딱 idle.
    function addBobNull(comp, il, layer, t0, amt, sceneDur) {
        var nl = comp.layers.addNull(sceneDur);
        nl.name = (layer.name || "el") + "_피벗";
        nl.property("Position").setValue([layer.foot[0], layer.foot[1]]);
        il.parent = nl;                                   // AE가 월드 변환 보존하며 페어런팅
        var sp = nl.property("Scale");
        var half = 0.6;                                   // 반주기 0.6s
        sp.setValueAtTime(t0, [100, 100]);
        sp.setValueAtTime(Math.min(sceneDur, t0 + half), [100, 100 + amt]);
        try {                                             // easy ease 양 키
            var ez = new KeyframeEase(0, 33.34);
            sp.setTemporalEaseAtKey(1, [ez, ez], [ez, ez]);
            sp.setTemporalEaseAtKey(2, [ez, ez], [ez, ez]);
        } catch (e) { }
        try { sp.expression = 'loopOut("pingpong")'; } catch (e) { }
        return nl;
    }

    function applyMoves(comp, il, layer, sceneDur, cw, ch) {
        var moves = layer.moves;
        if (!moves || !moves.length) return;
        var P = il.property("Position").value;
        var S = il.property("Scale").value;
        for (var mi = 0; mi < moves.length; mi++) {
            var mv = moves[mi];
            var t0 = Math.max(0, mv.start || 0);
            var t1 = Math.min(sceneDur, t0 + (mv.duration || 0.5));
            if (t1 <= t0) continue;
            var amt = mv.amount;
            try {
                if (mv.type === "slide_in") {
                    var dx = 0, dy = 0, off = amt || cw * 0.18;
                    if (mv.direction === "right") dx = off; else if (mv.direction === "up") dy = -off;
                    else if (mv.direction === "down") dy = off; else dx = -off;
                    var pp = il.property("Position");
                    pp.setValueAtTime(t0, [P[0] + dx, P[1] + dy]);
                    pp.setValueAtTime(t1, [P[0], P[1]]);
                    if (!mv.noFade) {                        // 캐릭터(noFade)는 오퍼시티 키프레임 금지
                        var op0 = il.property("Opacity");
                        op0.setValueAtTime(t0, 0); op0.setValueAtTime(t0 + (t1 - t0) * 0.5, 100);
                    }
                } else if (mv.type === "fade_in") {
                    var op1 = il.property("Opacity");
                    op1.setValueAtTime(t0, 0); op1.setValueAtTime(t1, 100);
                } else if (mv.type === "exit_fade") {
                    var op2 = il.property("Opacity");
                    op2.setValueAtTime(t0, 100); op2.setValueAtTime(t1, 0);
                } else if (mv.type === "pop") {
                    var sp = il.property("Scale");
                    sp.setValueAtTime(t0, [S[0] * 0.6, S[1] * 0.6]);
                    sp.setValueAtTime(t0 + (t1 - t0) * 0.7, [S[0] * 1.06, S[1] * 1.06]);
                    sp.setValueAtTime(t1, [S[0], S[1]]);
                } else if (mv.type === "zoom_emphasis") {
                    var sp2 = il.property("Scale");
                    sp2.setValueAtTime(t0, [S[0], S[1]]);
                    sp2.setValueAtTime(t0 + (t1 - t0) * 0.5, [S[0] * 1.08, S[1] * 1.08]);
                    sp2.setValueAtTime(t1, [S[0], S[1]]);
                } else if (mv.type === "drift") {
                    var d2 = amt || 18;
                    var pd = il.property("Position");
                    pd.setValueAtTime(t0, [P[0], P[1]]);
                    pd.setValueAtTime(t1, [P[0] + d2, P[1] - d2 * 0.4]);
                } else if (mv.type === "bob") {
                    if (layer.foot) {                     // 발밑 피벗 null 스쿼시 루프(우월 경로)
                        addBobNull(comp, il, layer, t0, (amt && amt <= 5 ? amt : 1), sceneDur);
                    } else {                              // foot 없으면 구식 y 진동 폴백
                        var b2 = amt || 8, pb = il.property("Position");
                        var steps = Math.max(2, Math.floor((t1 - t0) / 0.6));
                        for (var bi = 0; bi <= steps; bi++) {
                            var tb = t0 + (t1 - t0) * bi / steps;
                            pb.setValueAtTime(tb, [P[0], P[1] + ((bi % 2) ? -b2 : 0)]);
                        }
                    }
                } else if (mv.type === "shake") {
                    var s2 = amt || 10, ps = il.property("Position");
                    for (var si2 = 0; si2 <= 6; si2++) {
                        var ts = t0 + (t1 - t0) * si2 / 6;
                        ps.setValueAtTime(ts, [P[0] + ((si2 % 2) ? s2 : -s2) * (1 - si2 / 6), P[1]]);
                    }
                }
            } catch (e) { /* 모션 1개 실패는 무시 — 빌드 지속 */ }
        }
    }

    // Final 씬 레이어 카메라 — slow zoom/pan(결정적)
    function applyCamera(fl, cam, t, dur, baseScale, W, H) {
        if (!cam || !cam.type || cam.type === "none") return;
        try {
            var amt = cam.amount || 6;
            if (cam.type === "slow_zoom_in" || cam.type === "slow_zoom_out") {
                var z = 1 + amt / 100.0;
                var sIn = cam.type === "slow_zoom_in";
                var sp = fl.property("Scale");
                sp.setValueAtTime(t, [baseScale * (sIn ? 1 : z), baseScale * (sIn ? 1 : z)]);
                sp.setValueAtTime(t + dur, [baseScale * (sIn ? z : 1), baseScale * (sIn ? z : 1)]);
            } else {
                var px = cam.amount || 40;
                var dir2 = cam.type === "pan_left" ? -1 : 1;
                var pp2 = fl.property("Position");
                var base = fl.property("Position").value;
                pp2.setValueAtTime(t, [base[0] - dir2 * px / 2, base[1]]);
                pp2.setValueAtTime(t + dur, [base[0] + dir2 * px / 2, base[1]]);
            }
        } catch (e) { }
    }
    try {
        var mf = new File(manifestPath);
        if (!mf.exists) { return "ERROR: manifest 없음: " + manifestPath; }
        mf.open("r"); var raw = mf.read(); mf.close();
        var m = (typeof JSON === "object" && JSON.parse) ? JSON.parse(raw) : eval("(" + raw + ")");

        // ae_tokens 로드(있으면 기본 토큰 덮어쓰기) — 실패해도 내장 기본값으로 진행
        try {
            if (m.ae_tokens) {
                var tf = new File(m.ae_tokens);
                if (tf.exists) {
                    tf.open("r"); var tr = tf.read(); tf.close();
                    var tj = (typeof JSON === "object" && JSON.parse) ? JSON.parse(tr) : eval("(" + tr + ")");
                    if (tj.colors) TK.colors = tj.colors;
                    if (tj.fonts) TK.fonts = tj.fonts;
                    if (tj.type) TK.type = tj.type;
                    if (tj.families) TK.families = tj.families;
                }
            }
        } catch (eTk) { }

        // 프로젝트 테마 색 오버라이드(manifest.themeColors) — ae_tokens 로드 여부와 무관하게 항상 적용
        if (m.themeColors) {
            for (var ck in m.themeColors) { TK.colors[ck] = m.themeColors[ck]; }
        }

        // 폰트 PS명을 AE 폰트 DB 기준으로 검증/보정(패밀리 키워드 + 굵기 힌트)
        try {
            var FAM = TK.families || {};
            var HINT = { body: "Medium", subtitle: "Medium", bold: "Bold" };
            for (var fk in TK.fonts) {
                if (fk === "fallback" || !TK.fonts[fk]) continue;
                TK.fonts[fk] = resolveFontPS(TK.fonts[fk], FAM[fk], HINT[fk]);
            }
        } catch (eF) { }

        var W = m.width || 1920, H = m.height || 1080, FPS = m.fps || 30;
        var scenes = m.scenes || [];
        if (!scenes.length) { return "ERROR: scenes 비어있음"; }

        app.beginUndoGroup("auto_kairos PoC build");
        var proj = app.project || app.newProject();

        var comps = [], totalDur = 0, log = [];
        for (var i = 0; i < scenes.length; i++) {
            var s = scenes[i];
            var dur = s.duration || 3;
            var name = s.ae_comp_name || ("Scene_" + (i + 1));
            // 씬 컴프 크기 = 씬 이미지 크기(레이어들과 동일) → 같은 크기 레이어가 1:1·중앙으로 정확히 겹침
            var cw = s.width || W, ch = s.height || H;
            var comp = proj.items.addComp(name, cw, ch, 1.0, dur, FPS);

            // 레이아웃 씬(비이미지) — 셰이프/텍스트 결정적 렌더. 실패해도 빌드 지속.
            var isLayoutScene = s.layout && s.layout !== "cinematic";
            if (isLayoutScene) {
                try { renderLayout(comp, s, cw, ch); }
                catch (eL) { log.push(name + ": 레이아웃 렌더 실패 " + eL.toString()); }
            }
            // 레이어 스택(있으면) — 배열 앞이 먼저 추가되어 최하단(배경). 없으면 단일 이미지.
            else if (s.layers && s.layers.length) {
                for (var li = 0; li < s.layers.length; li++) {
                    var ok = addLayerObj(proj, comp, s.layers[li], cw, ch);
                    if (!ok) log.push(name + ": 레이어 누락 " + s.layers[li].name);
                    else if (s.layers[li].moves) applyMoves(comp, ok, s.layers[li], dur, cw, ch);
                }
            } else if (s.image) {
                if (!addLayerObj(proj, comp, { path: s.image }, cw, ch)) log.push(name + ": image 누락");
            }
            // 지도 씬 — 지도 배경판 위에 마커/라벨/경로를 AE 네이티브 레이어로
            if (s.mapGeo) {
                try { renderMapOverlay(comp, s.mapGeo, cw, ch, dur); }
                catch (eMap) { log.push(name + ": 지도 오버레이 실패 " + eMap.toString()); }
            }

            // 오디오 (있으면) — 자막은 씬 컴프가 아닌 Final에 일괄(subtitle_layers.jsx)
            if (s.audio) {
                var aF = new File(s.audio);
                if (aF.exists) { comp.layers.add(proj.importFile(new ImportOptions(aF))); }
            }

            comps.push(comp); totalDur += dur;
        }

        // Final 컴프(1920x1080) — 씬 컴프를 순서대로 배치(크기 다르면 채움 스케일 + 중앙)
        var fc = proj.items.addComp("Final", W, H, 1.0, Math.max(totalDur, 1), FPS);
        var t = 0;
        for (var j = 0; j < comps.length; j++) {
            var fl = fc.layers.add(comps[j]);
            var fsc = Math.max(W / comps[j].width, H / comps[j].height) * 100;
            fl.property("Scale").setValue([fsc, fsc]);
            fl.startTime = t;
            if (scenes[j].camera) applyCamera(fl, scenes[j].camera, t, comps[j].duration, fsc, W, H);
            t += comps[j].duration;
        }
        fc.openInViewer();
        app.endUndoGroup();

        return "OK: 씬 컴프 " + comps.length + "개 + Final(" + totalDur + "s)" +
               (log.length ? " | " + log.join(", ") : "") +
               (FONT_WARN.length ? " | 폰트: " + FONT_WARN.join(", ") : "");
    } catch (e) {
        return "ERROR: " + e.toString();
    }
}
