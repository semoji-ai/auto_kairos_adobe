// auto_kairos — Final 컴프에 말자막 레이어 일괄 생성.
// 입력: subsPath(subtitles.json 절대경로), tokensPath(ae_tokens.json, ""면 기본).
// 각 cue → 텍스트 레이어(startTime/outPoint로 타이밍), 하단 중앙.

function akBuildSubtitles(subsPath, tokensPath) {
    try {
        var f = new File(subsPath);
        if (!f.exists) return "ERROR: subtitles.json 없음";
        f.open("r"); var raw = f.read(); f.close();
        var data = (typeof JSON === "object" && JSON.parse) ? JSON.parse(raw) : eval("(" + raw + ")");
        var cues = data.cues || [];
        if (!cues.length) return "ERROR: 자막 줄 없음";

        var size = 54, fontName = "", txt = [1, 1, 1];
        try {
            if (tokensPath) { var tf = new File(tokensPath); if (tf.exists) { tf.open("r"); var tr = tf.read(); tf.close();
                var tk = (typeof JSON === "object" && JSON.parse) ? JSON.parse(tr) : eval("(" + tr + ")");
                if (tk.type && tk.type.subtitle) size = tk.type.subtitle;
                if (tk.fonts && tk.fonts.subtitle) fontName = tk.fonts.subtitle;
                if (tk.colors && tk.colors.textRgb) txt = [tk.colors.textRgb[0] / 255, tk.colors.textRgb[1] / 255, tk.colors.textRgb[2] / 255]; } }
        } catch (e) { }

        var comp = null;
        for (var i = 1; i <= app.project.numItems; i++) {
            var it = app.project.item(i);
            if (it instanceof CompItem && it.name === "Final") { comp = it; break; }
        }
        if (!comp) return "ERROR: Final 컴프 없음 — 먼저 컴프를 빌드하세요";

        app.beginUndoGroup("auto_kairos subtitles");
        var W = comp.width, H = comp.height, made = 0;
        for (var ci = 0; ci < cues.length; ci++) {
            var c = cues[ci];
            if (!c.text || c.end == null || c.start == null) continue;
            var tl = comp.layers.addText(String(c.text));
            tl.name = "sub_" + (ci + 1);
            var td = tl.property("Source Text").value;
            td.fontSize = size; td.fillColor = txt;
            try { td.applyStroke = true; td.strokeColor = [0, 0, 0]; td.strokeWidth = Math.max(4, size / 12); td.strokeOverFill = false; } catch (e) { }
            try { if (fontName) td.font = fontName; } catch (e) { }
            try { td.justification = ParagraphJustification.CENTER_JUSTIFY; } catch (e) { }
            tl.property("Source Text").setValue(td);
            tl.property("Position").setValue([W / 2, H * 0.92]);
            tl.startTime = c.start;
            tl.inPoint = c.start;
            tl.outPoint = Math.max(c.start + 0.2, c.end);
            made++;
        }
        app.endUndoGroup();
        return "OK: 자막 레이어 " + made + "개 생성(Final)";
    } catch (e) {
        try { app.endUndoGroup(); } catch (_) { }
        return "ERROR: " + e.toString();
    }
}
