// auto_kairos — 씬 컴프를 현재 타임라인(활성 컴프, 없으면 Final)에 시간대로 배치.
// 입력: planJson = {"items":[{"sceneNumber":1,"comp":"S01_ab12","start":0,"duration":5}], ...} JSON 문자열
// 동작: 같은 이름 레이어가 이미 있으면 지우고 다시 놓음(멱등). 대상 컴프 길이는 필요 시 늘림.
// 반환: "OK: ..." | "ERROR: ..."

function akFindComp(name) {
    for (var i = 1; i <= app.project.numItems; i++) {
        var it = app.project.item(i);
        if (it instanceof CompItem && it.name === name) { return it; }
    }
    return null;
}

function akPlaceOnTimeline(planJson) {
    try {
        var plan = eval("(" + planJson + ")");
        var items = (plan && plan.items) || [];
        if (!items.length) { return "ERROR: 배치할 씬 없음"; }

        // 대상 컴프 — 활성 컴프 우선, 없으면 Final
        var target = null;
        var ai = app.project.activeItem;
        if (ai && ai instanceof CompItem) { target = ai; }
        if (!target) { target = akFindComp("Final"); }
        if (!target) { return "ERROR: 대상 컴프 없음 — AE에서 컴프를 열거나 Final 컴프를 먼저 만드세요"; }

        // 자기 자신을 자기 안에 넣으면 순환
        for (var c = 0; c < items.length; c++) {
            if (items[c].comp === target.name) {
                return "ERROR: 활성 컴프(" + target.name + ")가 배치 대상과 같습니다 — 다른 컴프를 여세요";
            }
        }

        app.beginUndoGroup("auto_kairos 타임라인 배치");
        var placed = 0, missing = [], maxEnd = 0;
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            var src = akFindComp(it.comp);
            if (!src) { missing.push(it.sceneNumber); continue; }

            // 기존 동일 레이어 제거(중복 방지)
            for (var L = target.numLayers; L >= 1; L--) {
                var lay = target.layer(L);
                if (lay.name === it.comp || (lay.source && lay.source === src)) { lay.remove(); }
            }
            var nl = target.layers.add(src);
            nl.name = it.comp;
            nl.startTime = it.start;
            nl.inPoint = it.start;
            nl.outPoint = it.start + it.duration;
            if (it.start + it.duration > maxEnd) { maxEnd = it.start + it.duration; }
            placed++;
        }
        if (maxEnd > target.duration) { target.duration = maxEnd; }
        app.endUndoGroup();

        var msg = "OK: " + placed + "개 배치 → " + target.name;
        if (missing.length) { msg += " (컴프 없어 건너뜀: 씬 " + missing.join(",") + " — 먼저 컴프 조립)"; }
        return msg;
    } catch (e) {
        try { app.endUndoGroup(); } catch (_) {}
        return "ERROR: " + e.toString();
    }
}
