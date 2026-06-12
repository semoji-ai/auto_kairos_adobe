// auto_kairos — manifest 기반 AE 컴프 생성 (PoC, 최소 모션)
// 입력: manifest 경로(JSON). 출력: 씬별 컴프 + Final 컴프(순서 배치).
// JSON 파싱: json2.jsx 폴리필(JSON.parse) 우선, 없으면 eval 폴백.

function akBuildScene(manifestPath) {
    // 레이어 추가. layer.position 있으면 그 좌표·스케일로(크롭된 요소), 없으면 컴프 채움·중앙(풀프레임/배경).
    function addLayerObj(proj, comp, layer, W, H, fade) {
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
        if (fade) { var op = il.property("Opacity"); op.setValueAtTime(0, 0); op.setValueAtTime(0.5, 100); }
        return il;
    }
    // 프리셋 모션 → 키프레임(결정적). 실패해도 빌드는 계속(try/catch).
    function applyMoves(il, moves, sceneDur, cw, ch) {
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
                    var op0 = il.property("Opacity");
                    op0.setValueAtTime(t0, 0); op0.setValueAtTime(t0 + (t1 - t0) * 0.5, 100);
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
                    var b2 = amt || 8, pb = il.property("Position");
                    var steps = Math.max(2, Math.floor((t1 - t0) / 0.6));
                    for (var bi = 0; bi <= steps; bi++) {
                        var tb = t0 + (t1 - t0) * bi / steps;
                        pb.setValueAtTime(tb, [P[0], P[1] + ((bi % 2) ? -b2 : 0)]);
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

            // 레이어 스택(있으면) — 배열 앞이 먼저 추가되어 최하단(배경). 없으면 단일 이미지.
            if (s.layers && s.layers.length) {
                for (var li = 0; li < s.layers.length; li++) {
                    var ok = addLayerObj(proj, comp, s.layers[li], cw, ch, li === 0);
                    if (!ok) log.push(name + ": 레이어 누락 " + s.layers[li].name);
                    else if (s.layers[li].moves) applyMoves(ok, s.layers[li].moves, dur, cw, ch);
                }
            } else if (s.image) {
                if (!addLayerObj(proj, comp, { path: s.image }, cw, ch, true)) log.push(name + ": image 누락");
            }

            // 자막 텍스트 레이어 (있으면)
            if (s.subtitle) {
                var tl = comp.layers.addText(s.subtitle);
                var td = tl.property("Source Text").value;
                td.fontSize = 60; td.fillColor = [1, 1, 1];
                tl.property("Source Text").setValue(td);
                tl.property("Position").setValue([cw / 2, ch * 0.88]);
            }

            // 오디오 (있으면)
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
               (log.length ? " | " + log.join(", ") : "");
    } catch (e) {
        return "ERROR: " + e.toString();
    }
}
