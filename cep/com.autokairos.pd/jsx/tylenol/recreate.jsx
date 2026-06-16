// 타이레놀 페이스리프트 70초 — 전체 1:1 재현(데이터 주도).
// cuts.json을 읽어 컷 유형별 컴프 생성 + Final 타임라인 조립. AE 네이티브 모션.
// 유형: logo(스케일팝) / text(reveal·slide·type) / items(스태거) / metric(타이핑) /
//       color_grid(그리드 스태거) / quote(단어 스태거) / image(에셋 연결 전 placeholder).
// 실행: AE > File > Scripts > Run Script File... → 이 파일 선택(끝에서 자동 호출).

function akTylenolRecreate() {
    try {
        // cuts.json 로드 — 이 스크립트와 같은 폴더
        var here = new File($.fileName).parent;
        var cf = new File(here.fsName + "/cuts.json");
        if (!cf.exists) return "ERROR: cuts.json 없음: " + cf.fsName;
        cf.open("r"); var raw = cf.read(); cf.close();
        var D = (typeof JSON === "object" && JSON.parse) ? JSON.parse(raw) : eval("(" + raw + ")");
        var W = D.width, H = D.height, FPS = D.fps;
        function col(name) { var c = D.colors[name] || [0, 0, 0]; return [c[0] / 255, c[1] / 255, c[2] / 255]; }

        var proj = app.project || app.newProject();
        app.beginUndoGroup("TYL Recreate");

        // ── 헬퍼 ──
        function addSolidBg(comp, rgb) { return comp.layers.addSolid(rgb, "bg", W, H, 1.0); }
        function addText(comp, str, opt) {
            var tl = opt.box ? comp.layers.addBoxText([opt.box[0], opt.box[1]], String(str))
                             : comp.layers.addText(String(str));
            var td = tl.property("Source Text").value;
            td.fontSize = opt.size; td.fillColor = opt.rgb;
            if (opt.tracking) td.tracking = opt.tracking;
            td.justification = ParagraphJustification.CENTER_JUSTIFY;
            var fonts = opt.fonts || ["AppleSDGothicNeo-Bold"];
            for (var i = 0; i < fonts.length; i++) { try { td.font = fonts[i]; } catch (e) {} }
            if (opt.leading) { td.autoLeading = false; td.leading = opt.size * opt.leading; }
            tl.property("Source Text").setValue(td);
            var r = tl.sourceRectAtTime(0, false);
            tl.property("Anchor Point").setValue([r.left + r.width / 2, r.top + r.height / 2]);
            tl.property("Position").setValue([opt.x == null ? W / 2 : opt.x, opt.y == null ? H / 2 : opt.y]);
            tl.motionBlur = true;
            return tl;
        }
        // Text Animator 키네틱 — type: reveal/slide/type/word_stagger
        function kineticAnim(tl, type, t0, dur) {
            try {
                var an = tl.property("ADBE Text Properties").property("ADBE Text Animators").addProperty("ADBE Text Animator");
                var props = an.property("ADBE Text Animator Properties");
                if (type === "slide") {
                    props.addProperty("ADBE Text Position 3D").setValue([0, 60, 0]);
                }
                props.addProperty("ADBE Text Opacity").setValue(0);
                var sel = an.property("ADBE Text Selectors").addProperty("ADBE Text Selector");
                if (type === "word_stagger") { try { sel.property("ADBE Text Range Type2").setValue(3); } catch (eW) {} }
                try { sel.property("ADBE Text Range Advanced").property("ADBE Text Range Smoothness").setValue(type === "type" ? 0 : 100); } catch (eS) {}
                var offp = sel.property("ADBE Text Percent Offset");
                offp.setValueAtTime(t0, 0); offp.setValueAtTime(t0 + dur, 100);
                try {
                    offp.setTemporalEaseAtKey(1, [new KeyframeEase(0, 75)], [new KeyframeEase(0, 75)]);
                    offp.setTemporalEaseAtKey(2, [new KeyframeEase(0, 33)], [new KeyframeEase(0, 33)]);
                } catch (eE) {}
            } catch (e) {}
        }
        function addRect(comp, name, x, y, w, h, rgb) {
            var sl = comp.layers.addShape(); sl.name = name;
            var g = sl.property("Contents").addProperty("ADBE Vector Group");
            g.property("Contents").addProperty("ADBE Vector Shape - Rect").property("Size").setValue([w, h]);
            g.property("Contents").addProperty("ADBE Vector Graphic - Fill").property("Color").setValue(rgb);
            sl.property("Position").setValue([x + w / 2, y + h / 2]);
            return sl;
        }

        // ── 컷 유형별 렌더 ──
        function renderLogo(comp, cut) {
            var t = addText(comp, cut.text, { size: cut.text.indexOf("\n") >= 0 ? 130 : 200,
                rgb: cut.bg === "red" ? [1, 1, 1] : col("red"), tracking: 24, leading: 1.1,
                fonts: ["Georgia-BoldItalic", "TimesNewRomanPS-BoldItalicMT", "Cafe24Ssurround"] });
            var sc = t.property("Scale");
            sc.setValueAtTime(0, [86, 86]); sc.setValueAtTime(0.3, [104, 104]); sc.setValueAtTime(0.45, [100, 100]);
            try { sc.setTemporalEaseAtKey(3, [new KeyframeEase(0, 70)], [new KeyframeEase(0, 70)]); } catch (e) {}
            var op = t.property("Opacity"); op.setValueAtTime(0, 0); op.setValueAtTime(0.18, 100);
        }
        function renderText(comp, cut) {
            var t = addText(comp, cut.text, { size: 140, rgb: col(cut.fg || "ink"), leading: 1.2,
                box: [W * 0.8, H * 0.5], fonts: ["Cafe24Ssurround", "OTSBAggroB", "AppleSDGothicNeo-Bold"] });
            kineticAnim(t, cut.motion || "reveal", 0.2, 0.7);
        }
        function renderItems(comp, cut) {
            addText(comp, cut.headline || "", { size: 90, y: H * 0.2, rgb: col("ink"),
                fonts: ["Cafe24Ssurround", "OTSBAggroB"] });
            var items = cut.items || [], n = items.length;
            var y0 = H * 0.36, gap = (H * 0.5) / Math.max(1, n);
            for (var i = 0; i < n; i++) {
                var it = addText(comp, items[i], { size: 64, y: y0 + i * gap, rgb: col("ink"),
                    fonts: ["OTSBAggroM", "AppleSDGothicNeo-Bold"] });
                var op = it.property("Opacity");                  // 순차(스태거) 등장
                op.setValueAtTime(0.2 + i * 0.22, 0); op.setValueAtTime(0.5 + i * 0.22, 100);
                var p = it.property("Position"), px = it.property("Position").value;
                p.setValueAtTime(0.2 + i * 0.22, [px[0] - 50, px[1]]);
                p.setValueAtTime(0.5 + i * 0.22, [px[0], px[1]]);
            }
        }
        function renderMetric(comp, cut) {
            var v = addText(comp, cut.value || "", { size: 280, y: H * 0.44, rgb: col("red"),
                fonts: ["Cafe24Ssurround", "Georgia-Bold"] });
            kineticAnim(v, "type", 0.2, 0.6);
            var l = addText(comp, cut.label || "", { size: 60, y: H * 0.66, rgb: col("ink"),
                fonts: ["OTSBAggroM"] });
            var op = l.property("Opacity"); op.setValueAtTime(0.7, 0); op.setValueAtTime(1.0, 100);
        }
        function renderColorGrid(comp, cut) {
            addText(comp, cut.headline || "", { size: 80, y: H * 0.16, rgb: col("ink"), fonts: ["Cafe24Ssurround"] });
            var blocks = cut.blocks || [], n = blocks.length;
            var cols = Math.ceil(Math.sqrt(n)), rows = Math.ceil(n / cols);
            var bw = W * 0.5 / cols, bh = H * 0.45 / rows, x0 = W * 0.25, y0 = H * 0.3, pad = 12;
            for (var i = 0; i < n; i++) {
                var r = Math.floor(i / cols), c = i % cols;
                var bx = x0 + c * bw, by = y0 + r * bh;
                var sl = addRect(comp, "block" + i, bx + pad, by + pad, bw - pad * 2, bh - pad * 2,
                    [blocks[i][0] / 255, blocks[i][1] / 255, blocks[i][2] / 255]);
                sl.property("Anchor Point").setValue([0, 0]);     // 그리드 스태거 — 셀별 시차 팝
                sl.property("Position").setValue([bx + pad, by + pad]);
                var t0 = 0.3 + i * 0.18, sc = sl.property("Scale");
                sc.setValueAtTime(t0, [0, 0]); sc.setValueAtTime(t0 + 0.3, [108, 108]); sc.setValueAtTime(t0 + 0.42, [100, 100]);
            }
        }
        function renderQuote(comp, cut) {
            var t = addText(comp, cut.text, { size: 90, rgb: col(cut.fg || "white"), leading: 1.4,
                box: [W * 0.8, H * 0.5], fonts: ["GyeonggiBatangR", "Cafe24Ssurround"] });
            kineticAnim(t, "word_stagger", 0.3, 1.2);
        }
        function renderImage(comp, cut) {                          // 에셋 연결 전 placeholder
            addText(comp, "[" + (cut.text || "이미지") + "]", { size: 70,
                rgb: cut.bg === "red" ? [1, 1, 1] : col("ink"), fonts: ["OTSBAggroM"] });
            addText(comp, "(에셋 연결 예정)", { size: 36, y: H * 0.6,
                rgb: cut.bg === "red" ? [1, 0.8, 0.8] : col("red"), fonts: ["OTSBAggroL", "OTSBAggroM"] });
        }

        // ── 컷별 컴프 생성 ──
        var comps = [], log = [];
        for (var ci = 0; ci < D.cuts.length; ci++) {
            var cut = D.cuts[ci];
            var comp = proj.items.addComp("TYL_" + cut.id, W, H, 1.0, cut.dur, FPS);
            comp.motionBlur = true;
            addSolidBg(comp, col(cut.bg || "white"));
            try {
                if (cut.type === "logo") renderLogo(comp, cut);
                else if (cut.type === "text") renderText(comp, cut);
                else if (cut.type === "items") renderItems(comp, cut);
                else if (cut.type === "metric") renderMetric(comp, cut);
                else if (cut.type === "color_grid") renderColorGrid(comp, cut);
                else if (cut.type === "quote") renderQuote(comp, cut);
                else renderImage(comp, cut);
            } catch (eC) { log.push(cut.id + ": " + eC.toString()); }
            comps.push({ comp: comp, dur: cut.dur, t: cut.t });
        }

        // ── Final 조립 ──
        var total = 0;
        for (var k = 0; k < comps.length; k++) total += comps[k].dur;
        var fc = proj.items.addComp("TYL_Final", W, H, 1.0, total, FPS);
        var t = 0;
        for (var j = 0; j < comps.length; j++) {
            var fl = fc.layers.add(comps[j].comp);
            fl.startTime = t; t += comps[j].dur;
        }
        fc.openInViewer();
        app.endUndoGroup();
        return "OK: " + comps.length + "컷 + Final(" + Math.round(total) + "s)" + (log.length ? " | " + log.join(", ") : "");
    } catch (e) {
        try { app.endUndoGroup(); } catch (_) {}
        return "ERROR: " + e.toString();
    }
}
akTylenolRecreate();
