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

        // (2) 4 패키지 — 2.5D(3D 레이어 + Y축 약간 기울임), 각기 다른 방향 슬라이드인
        // gemini: 좌상=좌측에서, 우상=우측에서, 좌하=좌측에서, 우하=우측에서
        var items = [
            { f: "assets/pkg_cold.png", gx: W * 0.30, gy: H * 0.34, from: "left", tilt: -12 },
            { f: "assets/pkg_er.png", gx: W * 0.70, gy: H * 0.34, from: "right", tilt: 12 },
            { f: "assets/pkg_500mg.png", gx: W * 0.30, gy: H * 0.66, from: "left", tilt: -8 },
            { f: "assets/pkg_womens.png", gx: W * 0.70, gy: H * 0.66, from: "right", tilt: 8 }
        ];
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            var ff = new File(here.fsName + "/" + it.f);
            if (!ff.exists) continue;
            var item = proj.importFile(new ImportOptions(ff));
            var pkg = comp.layers.add(item);
            pkg.threeDLayer = true;                                  // 3D 레이어
            var s = (W * 0.26 / item.width) * 100;                   // 화면 26% 폭
            var tg = pkg.property("ADBE Transform Group");
            tg.property("ADBE Scale").setValue([s, s, s]);
            tg.property("ADBE Rotate Y").setValue(it.tilt);          // 2.5D 기울임(Y축)
            var t0 = 0.1 + i * 0.18, t1 = t0 + 0.5;                  // 스태거 슬라이드인
            var pos = tg.property("ADBE Position");
            var offx = it.from === "left" ? -W * 0.4 : W * 0.4;
            pos.setValueAtTime(t0, [it.gx + offx, it.gy, 0]);
            pos.setValueAtTime(t1, [it.gx, it.gy, 0]);
            try { pos.setTemporalEaseAtKey(2, [new KeyframeEase(0, 80), new KeyframeEase(0, 80), new KeyframeEase(0, 80)]); } catch (e) {}
            var op = tg.property("ADBE Opacity"); op.setValueAtTime(t0, 0); op.setValueAtTime(t0 + 0.2, 100);
            pkg.motionBlur = true;
            // 패키지 그림자(Drop Shadow) — 2.5D 입체감
            try {
                var ds = pkg.property("ADBE Effect Parade").addProperty("ADBE Drop Shadow");
                ds.property("ADBE Drop Shadow-0002").setValue(60);   // opacity
                ds.property("ADBE Drop Shadow-0004").setValue(28);   // distance
                ds.property("ADBE Drop Shadow-0005").setValue(60);   // softness
            } catch (eD) {}
        }

        // (3) 3D 카메라 — 살짝 푸시인(깊이감)
        var cam = comp.layers.addCamera("cam", [W / 2, H / 2]);
        var cp = cam.property("ADBE Transform Group").property("ADBE Position");
        cp.setValueAtTime(0, [W / 2, H / 2, -1650]);
        cp.setValueAtTime(DUR, [W / 2, H / 2, -1350]);
        try { cp.setTemporalEaseAtKey(1, [new KeyframeEase(0, 50), new KeyframeEase(0, 50), new KeyframeEase(0, 50)]);
              cp.setTemporalEaseAtKey(2, [new KeyframeEase(0, 50), new KeyframeEase(0, 50), new KeyframeEase(0, 50)]); } catch (e) {}

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
