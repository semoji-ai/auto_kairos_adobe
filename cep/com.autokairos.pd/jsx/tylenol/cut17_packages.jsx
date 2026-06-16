// 타이레놀 컷17 재현 — 4제품 패키지 2.5D + 3D 카메라.
// gemini 분석: 흰 그리드 배경, 4패키지가 각기 다른 방향에서 중앙으로 슬라이드인, 2.5D 약간 기울임.
// 고급: 3D 레이어 + 카메라 푸시인(깊이감) + Drop Shadow(패키지 그림자) + 그레인.
// 실행: AE > File > Scripts > Run Script File... → 이 파일.

function akTylenolPackages() {
    try {
        var W = 1920, H = 1080, FPS = 30, DUR = 2.0;
        var GRID_BG = [247 / 255, 247 / 255, 247 / 255];
        var proj = app.project || app.newProject();
        var here = new File($.fileName).parent;
        app.beginUndoGroup("TYL Cut17 Packages");
        var comp = proj.items.addComp("TYL_17_Packages", W, H, 1.0, DUR, FPS);
        comp.motionBlur = true;

        // (1) 흰 그리드 배경
        comp.layers.addSolid(GRID_BG, "bg", W, H, 1.0);
        var grid = comp.layers.addShape(); grid.name = "grid";
        var gc = grid.property("Contents");
        for (var gx = 0; gx <= W; gx += 80) { var l = gc.addProperty("ADBE Vector Group").property("Contents").addProperty("ADBE Vector Shape - Group"); var s = new Shape(); s.vertices = [[gx, 0], [gx, H]]; s.closed = false; l.property("Path").setValue(s); }
        for (var gy = 0; gy <= H; gy += 80) { var l2 = gc.addProperty("ADBE Vector Group").property("Contents").addProperty("ADBE Vector Shape - Group"); var s2 = new Shape(); s2.vertices = [[0, gy], [W, gy]]; s2.closed = false; l2.property("Path").setValue(s2); }
        var gst = gc.addProperty("ADBE Vector Graphic - Stroke"); gst.property("Color").setValue([0.90, 0.90, 0.92]); gst.property("Stroke Width").setValue(1);
        grid.property("Opacity").setValue(55);

        // (2) 4 패키지 — 3D 레이어 + Z축 깊이 분리(입체 쇼케이스). 각기 다른 방향 슬라이드인.
        // 깊이: 앞(Z 음수)일수록 카메라에 가까워 크고, 카메라 횡이동 시 더 많이 움직임(패럴랙스).
        var items = [
            { f: "assets/pkg_cold.png", gx: W * 0.30, gy: H * 0.34, from: "left", z: -140, tilt: -8 },
            { f: "assets/pkg_er.png", gx: W * 0.70, gy: H * 0.34, from: "right", z: 120, tilt: 8 },
            { f: "assets/pkg_500mg.png", gx: W * 0.30, gy: H * 0.66, from: "left", z: 60, tilt: -6 },
            { f: "assets/pkg_womens.png", gx: W * 0.70, gy: H * 0.66, from: "right", z: -80, tilt: 6 }
        ];
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            var ff = new File(here.fsName + "/" + it.f);
            if (!ff.exists) continue;
            var item = proj.importFile(new ImportOptions(ff));
            var pkg = comp.layers.add(item);
            pkg.threeDLayer = true;
            var s = (W * 0.24 / item.width) * 100;
            var tg = pkg.property("ADBE Transform Group");
            tg.property("ADBE Scale").setValue([s, s, s]);
            tg.property("ADBE Rotate Y").setValue(it.tilt);          // 살짝 기울임(원근으로 입체)
            var t0 = 0.1 + i * 0.18, t1 = t0 + 0.45, t2 = t0 + 0.6;  // 슬라이드인 + 오버슈트 정착
            var pos = tg.property("ADBE Position");
            var offx = it.from === "left" ? -W * 0.45 : W * 0.45;
            var over = it.from === "left" ? 18 : -18;                // 목표 살짝 넘었다 정착(생동감)
            pos.setValueAtTime(t0, [it.gx + offx, it.gy, it.z]);
            pos.setValueAtTime(t1, [it.gx + over, it.gy, it.z]);
            pos.setValueAtTime(t2, [it.gx, it.gy, it.z]);
            try { pos.setTemporalEaseAtKey(2, [new KeyframeEase(0, 85), new KeyframeEase(0, 85), new KeyframeEase(0, 85)]); } catch (e) {}
            var op = tg.property("ADBE Opacity"); op.setValueAtTime(t0, 0); op.setValueAtTime(t0 + 0.18, 100);
            pkg.motionBlur = true;
            try {
                var ds = pkg.property("ADBE Effect Parade").addProperty("ADBE Drop Shadow");
                ds.property("ADBE Drop Shadow-0002").setValue(70);
                ds.property("ADBE Drop Shadow-0004").setValue(30);
                ds.property("ADBE Drop Shadow-0005").setValue(70);
            } catch (eD) {}
        }

        // (3) 목적 있는 카메라 — 제품군 입체 쇼케이스(패럴랙스).
        //  잘림 방지: 기본 Z 거리(Z=0 레이어 1:1) 유지, X만 미세 횡이동 → 깊이별 패키지가
        //  다르게 움직여 입체감이 드러난다. 무브 작게(±36px).
        var cam = comp.layers.addCamera("cam", [W / 2, H / 2]);
        var cpos = cam.property("ADBE Transform Group").property("ADBE Position").value;   // 기본 거리 보존
        var cp = cam.property("ADBE Transform Group").property("ADBE Position");
        cp.setValueAtTime(0, [W / 2 - 36, H / 2, cpos[2]]);
        cp.setValueAtTime(DUR, [W / 2 + 36, H / 2, cpos[2]]);
        try { cp.setTemporalEaseAtKey(1, [new KeyframeEase(0, 40), new KeyframeEase(0, 40), new KeyframeEase(0, 40)]);
              cp.setTemporalEaseAtKey(2, [new KeyframeEase(0, 40), new KeyframeEase(0, 40), new KeyframeEase(0, 40)]); } catch (e) {}

        // (4) 그레인 — 조정 레이어
        var grain = comp.layers.addSolid([1, 1, 1], "grain", W, H, 1.0);
        grain.adjustmentLayer = true;
        try {
            var ag = grain.property("ADBE Effect Parade").addProperty("ADBE Add Grain");
            ag.property("ADBE AddGrain-0002").setValue(0.4); ag.property("ADBE AddGrain-0003").setValue(0.6);
        } catch (eg) {
            try { var nz = grain.property("ADBE Effect Parade").addProperty("ADBE Noise2"); nz.property("ADBE Noise2-0001").setValue(6); grain.property("Opacity").setValue(40); } catch (eN) {}
        }

        comp.openInViewer();
        app.endUndoGroup();
        return "OK: TYL_17_Packages (2.5D 패키지 + 3D 카메라)";
    } catch (e) {
        try { app.endUndoGroup(); } catch (_) {}
        return "ERROR: " + e.toString();
    }
}
akTylenolPackages();
