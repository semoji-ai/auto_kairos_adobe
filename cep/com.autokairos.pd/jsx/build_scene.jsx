// auto_kairos — manifest 기반 AE 컴프 생성 (PoC, 최소 모션)
// 입력: manifest 경로(JSON). 출력: 씬별 컴프 + Final 컴프(순서 배치).
// ExtendScript에는 native JSON이 없을 수 있어 eval로 파싱(로컬 신뢰 파일 전제, PoC).

function akBuildScene(manifestPath) {
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
            var comp = proj.items.addComp(name, W, H, 1.0, dur, FPS);

            // 이미지 레이어 (있으면) — 화면 채움 + 페이드인
            if (s.image) {
                var imgF = new File(s.image);
                if (imgF.exists) {
                    var foot = proj.importFile(new ImportOptions(imgF));
                    var il = comp.layers.add(foot);
                    var sc = Math.max(W / il.source.width, H / il.source.height) * 100;
                    il.property("Scale").setValue([sc, sc]);
                    var op = il.property("Opacity");
                    op.setValueAtTime(0, 0); op.setValueAtTime(0.5, 100);
                } else { log.push(name + ": image 누락"); }
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

        // Final 컴프 — 씬 순서대로 배치
        var fc = proj.items.addComp("Final", W, H, 1.0, Math.max(totalDur, 1), FPS);
        var t = 0;
        for (var j = 0; j < comps.length; j++) {
            var fl = fc.layers.add(comps[j]);
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
