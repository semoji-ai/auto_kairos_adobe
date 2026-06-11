// auto_kairos — manifest 기반 AE 컴프 생성 (PoC, 최소 모션)
// 입력: manifest 경로(JSON). 출력: 씬별 컴프 + Final 컴프(순서 배치).
// ExtendScript에는 native JSON이 없을 수 있어 eval로 파싱(로컬 신뢰 파일 전제, PoC).

function akBuildScene(manifestPath) {
    // 레이어/이미지를 화면 채움 스케일로 추가(필요 시 페이드인). 없으면 null.
    function addFilledLayer(proj, comp, absPath, W, H, fade) {
        var f = new File(absPath);
        if (!f.exists) return null;
        var foot = proj.importFile(new ImportOptions(f));
        var il = comp.layers.add(foot);
        var sc = Math.max(W / il.source.width, H / il.source.height) * 100;
        il.property("Scale").setValue([sc, sc]);
        if (fade) { var op = il.property("Opacity"); op.setValueAtTime(0, 0); op.setValueAtTime(0.5, 100); }
        return il;
    }
    try {
        var mf = new File(manifestPath);
        if (!mf.exists) { return "ERROR: manifest 없음: " + manifestPath; }
        mf.open("r"); var raw = mf.read(); mf.close();
        var m = eval("(" + raw + ")");

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
                    var ok = addFilledLayer(proj, comp, s.layers[li].path, cw, ch, li === 0);
                    if (!ok) log.push(name + ": 레이어 누락 " + s.layers[li].name);
                }
            } else if (s.image) {
                if (!addFilledLayer(proj, comp, s.image, cw, ch, true)) log.push(name + ": image 누락");
            }

            // 자막 텍스트 레이어 (있으면)
            if (s.subtitle) {
                var tl = comp.layers.addText(s.subtitle);
                var td = tl.property("Source Text").value;
                td.fontSize = 60; td.fillColor = [1, 1, 1];
                tl.property("Source Text").setValue(td);
                tl.property("Position").setValue([W / 2, H * 0.88]);
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
            fl.startTime = t; t += comps[j].duration;
        }
        fc.openInViewer();
        app.endUndoGroup();

        return "OK: 씬 컴프 " + comps.length + "개 + Final(" + totalDur + "s)" +
               (log.length ? " | " + log.join(", ") : "");
    } catch (e) {
        return "ERROR: " + e.toString();
    }
}
