// 타이레놀 — gemini 모션 분석(motion.json)을 읽어 AE 컴프를 자동 생성하는 범용 빌더.
// 파이프라인: gemini 영상분석 → 구조화 JSON → 이 빌더가 기계적으로 컴프화.
// 레이어 type: text / rrect(검색창·버튼·블록) / line(그리드·가이드) / image(패키지) / live(실사).
// anim prop: opacity / scale / position / typeOn(타이핑·리빌). ease: in/out/inout/over/linear.
// 실행: AE > File > Scripts > Run Script File... → 이 파일.

function akBuildFromJson() {
    try {
        var here = new File($.fileName).parent;
        var jf = new File(here.fsName + "/motion.json");
        if (!jf.exists) return "ERROR: motion.json 없음";
        jf.open("r"); var raw = jf.read(); jf.close();
        var D = (typeof JSON === "object" && JSON.parse) ? JSON.parse(raw) : eval("(" + raw + ")");
        var W = (D.comp && D.comp.w) || 1920, H = (D.comp && D.comp.h) || 1080, FPS = (D.comp && D.comp.fps) || 30;
        var proj = app.project || app.newProject();
        app.beginUndoGroup("TYL Build from JSON");

        function hex(h) {
            if (!h) return [0, 0, 0]; h = String(h).replace("#", "");
            if (h.length < 6) return [0, 0, 0];
            return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255];
        }
        function applyEase(prop, ki, dim, ease) {
            try {
                var inf = 75, e = []; for (var d = 0; d < dim; d++) e.push(new KeyframeEase(0, inf));
                if (ease === "in" || ease === "inout" || ease === "over") prop.setTemporalEaseAtKey(ki - 1, e, e);
                if (ease === "out" || ease === "inout" || ease === "over") prop.setTemporalEaseAtKey(ki, e, e);
            } catch (x) {}
        }
        function anchorCenter(layer) {
            try { var r = layer.sourceRectAtTime(0, false);
                  layer.property("Anchor Point").setValue([r.left + r.width / 2, r.top + r.height / 2]); } catch (x) {}
        }
        function assetFile(key) {
            var ext = (key === "live_clip" || key === "character_clip") ? ".mp4" : ".png";
            var f = new File(here.fsName + "/assets/" + key + ext);
            return f.exists ? f : null;
        }

        // 레이어 생성 ─ type별
        function makeText(comp, L) {
            var tl = comp.layers.addText(String(L.text || ""));
            var td = tl.property("Source Text").value;
            td.fontSize = L.size || 48; td.fillColor = hex(L.color || "#FFFFFF");
            var left = (L.align === "left");
            td.justification = left ? ParagraphJustification.LEFT_JUSTIFY : ParagraphJustification.CENTER_JUSTIFY;
            var ff = ["OTSBAggroM", "Cafe24Ssurround", "AppleSDGothicNeo-Bold"];
            for (var i = 0; i < ff.length; i++) { try { td.font = ff[i]; } catch (e) {} }
            tl.property("Source Text").setValue(td);
            var r = tl.sourceRectAtTime(0, false);
            tl.property("Anchor Point").setValue([left ? r.left : r.left + r.width / 2, r.top + r.height / 2]);
            tl.property("Position").setValue([L.x == null ? W / 2 : L.x, L.y == null ? H / 2 : L.y]);
            return tl;
        }
        function makeRRect(comp, L) {
            var sl = comp.layers.addShape(); sl.name = "rrect";
            var g = sl.property("Contents").addProperty("ADBE Vector Group");
            var rc = g.property("Contents").addProperty("ADBE Vector Shape - Rect");
            rc.property("Size").setValue([L.w || 200, L.h || 80]);
            rc.property("Roundness").setValue(L.round || 0);
            var f = g.property("Contents").addProperty("ADBE Vector Graphic - Fill"); f.property("Color").setValue(hex(L.color || "#FFFFFF"));
            if (L.stroke) { var s = g.property("Contents").addProperty("ADBE Vector Graphic - Stroke"); s.property("Color").setValue(hex(L.stroke)); s.property("Stroke Width").setValue(L.size || 2); }
            sl.property("Anchor Point").setValue([0, 0]);   // 그룹 원점 = 중심 → 스케일 팝 제자리
            sl.property("Position").setValue([L.x == null ? W / 2 : L.x, L.y == null ? H / 2 : L.y]);
            // 텍스트 라벨(버튼)
            if (L.text) {
                var t2 = makeText(comp, { text: L.text, color: "#333333", size: L.labelSize || 40, x: L.x, y: L.y, align: "center" });
            }
            return sl;
        }
        function makeLine(comp, L) {
            var sl = comp.layers.addShape(); sl.name = "line";
            var g = sl.property("Contents").addProperty("ADBE Vector Group");
            var p = g.property("Contents").addProperty("ADBE Vector Shape - Group");
            var sh = new Shape();
            var x = L.x == null ? W / 2 : L.x, y = L.y == null ? H / 2 : L.y, w = L.w || W, h = L.h || 0;
            sh.vertices = [[x - w / 2, y - h / 2], [x + w / 2, y + h / 2]]; sh.closed = false; p.property("Path").setValue(sh);
            var st = g.property("Contents").addProperty("ADBE Vector Graphic - Stroke");
            st.property("Color").setValue(hex(L.color || "#CCCCCC")); st.property("Stroke Width").setValue(L.size || 1);
            return sl;
        }
        function makeImage(comp, L) {
            var f = assetFile(L.asset); if (!f) return null;
            var item = proj.importFile(new ImportOptions(f));
            var L2 = comp.layers.add(item);
            var fit = (L.w ? L.w : W * 0.24) / item.width * 100;
            L2.property("Scale").setValue([fit, fit]);
            L2.property("Position").setValue([L.x == null ? W / 2 : L.x, L.y == null ? H / 2 : L.y]);
            return L2;
        }

        function applyAnim(layer, isText, anims) {
            if (!anims) return;
            for (var a = 0; a < anims.length; a++) {
                var an = anims[a], t0 = an.t0 || 0, t1 = an.t1 == null ? t0 + 0.5 : an.t1;
                var fr = an.from || [0], to = an.to || [100];
                try {
                    if (an.prop === "opacity") {
                        var op = layer.property("Opacity");
                        op.setValueAtTime(t0, fr[0]); op.setValueAtTime(t1, to[0]); applyEase(op, 2, 1, an.ease);
                    } else if (an.prop === "scale") {
                        var sc = layer.property("Scale");
                        sc.setValueAtTime(t0, [fr[0], fr[fr.length > 1 ? 1 : 0]]);
                        sc.setValueAtTime(t1, [to[0], to[to.length > 1 ? 1 : 0]]); applyEase(sc, 2, 2, an.ease);
                        if (an.ease === "over") { sc.setValueAtTime(t1 - (t1 - t0) * 0.25, [to[0] * 1.08, to[0] * 1.08]); }
                    } else if (an.prop === "position") {
                        var ps = layer.property("Position"), cur = ps.value;
                        var f2 = fr.length > 1 ? [fr[0], fr[1]] : [cur[0] + fr[0], cur[1]];
                        var t2 = to.length > 1 ? [to[0], to[1]] : [cur[0], cur[1]];
                        ps.setValueAtTime(t0, f2); ps.setValueAtTime(t1, t2); applyEase(ps, 2, 2, an.ease);
                    } else if (an.prop === "typeOn" && isText) {
                        var anim = layer.property("ADBE Text Properties").property("ADBE Text Animators").addProperty("ADBE Text Animator");
                        anim.property("ADBE Text Animator Properties").addProperty("ADBE Text Opacity").setValue(0);
                        var sel = anim.property("ADBE Text Selectors").addProperty("ADBE Text Selector");
                        try { sel.property("ADBE Text Range Advanced").property("ADBE Text Range Smoothness").setValue(0); } catch (e) {}
                        var off = sel.property("ADBE Text Percent Offset");
                        off.setValueAtTime(t0, 0); off.setValueAtTime(t1, 100);
                    }
                } catch (eA) {}
                layer.motionBlur = true;
            }
        }

        // ── 컷별 컴프 생성 ──
        var comps = [], log = [];
        for (var ci = 0; ci < D.cuts.length; ci++) {
            var cut = D.cuts[ci];
            var comp = proj.items.addComp("TYL_" + (cut.id || ci), W, H, 1.0, Math.max(0.4, cut.dur || 2), FPS);
            comp.motionBlur = true;
            comp.layers.addSolid(hex(cut.bg || "#FFFFFF"), "bg", W, H, 1.0);
            var layers = cut.layers || [];
            for (var li = layers.length - 1; li >= 0; li--) {     // 뒤 배열이 위로 — 순서 보존
                var L = layers[li], lay = null, isText = false;
                try {
                    if (L.type === "text") { lay = makeText(comp, L); isText = true; }
                    else if (L.type === "rrect") lay = makeRRect(comp, L);
                    else if (L.type === "line") lay = makeLine(comp, L);
                    else if (L.type === "image" || L.type === "live") lay = makeImage(comp, L);
                } catch (eL) { log.push((cut.id) + "/" + L.type + ": " + eL.toString()); }
                if (lay) applyAnim(lay, isText, L.anim);
            }
            comps.push({ c: comp, dur: cut.dur || 2 });
        }

        // ── Final 조립 ──
        var total = 0; for (var k = 0; k < comps.length; k++) total += comps[k].dur;
        var fc = proj.items.addComp("TYL_Final", W, H, 1.0, Math.max(1, total), FPS);
        var t = 0;
        for (var j = 0; j < comps.length; j++) { var fl = fc.layers.add(comps[j].c); fl.startTime = t; t += comps[j].dur; }
        fc.openInViewer();
        app.endUndoGroup();
        return "OK: " + comps.length + "컷 + Final(" + Math.round(total) + "s)" + (log.length ? " | 오류 " + log.length + ": " + log.slice(0, 3).join(" ; ") : "");
    } catch (e) {
        try { app.endUndoGroup(); } catch (_) {}
        return "ERROR: " + e.toString();
    }
}
akBuildFromJson();
