/* 파이프라인 탭 — Stage1-2 8단계를 세로 카드로 노출.
   ①브리프 래칫 → ②리서치 → ③원고 → ④씬 분석 → ⑤씬 검토 → ⑥엔티티 → ⑦시트 → ⑧씬 렌더.
   BACKEND/$/SELECTED_PROJECT/_awaitJob 는 main.js 전역. CEP ES5(var/function). */

var PIPE_STEPS = [
  { name: "brief",        num: "①", label: "브리프 래칫",
    done: function (s) { return s.brief; },      prereq: function (s) { return s.plan; },     need: "plan.md 필요 (기획 탭)" },
  { name: "research",     num: "②", label: "리서치",
    done: function (s) { return s.research; },   prereq: function (s) { return s.brief; },    need: "브리프(①) 먼저" },
  { name: "manuscript",   num: "③", label: "원고",
    done: function (s) { return s.manuscript; }, prereq: function (s) { return s.research; }, need: "리서치(②) 먼저" },
  { name: "scenes",       num: "④", label: "씬 분석",
    done: function (s) { return s.scenes; },     prereq: function (s) { return s.manuscript; }, need: "원고(③) 먼저" },
  { name: "scene-review", num: "⑤", label: "씬 검토",
    done: function (s) { return s.review; },     prereq: function (s) { return s.scenes; },   need: "씬 분석(④) 먼저" },
  { name: "entities",     num: "⑥", label: "엔티티",
    done: function (s) { return s.entities; },   prereq: function (s) { return s.scenes; },   need: "씬 분석(④) 먼저" },
  { name: "sheets",       num: "⑦", label: "시트 생성",
    done: function (s) { return s.sheets > 0; }, prereq: function (s) { return s.entities; }, need: "엔티티(⑥) 먼저" },
  { name: "render",       num: "⑧", label: "씬 렌더",
    done: function (s) { return s.rendered && s.rendered.done > 0; }, prereq: function (s) { return s.entities; }, need: "엔티티(⑥) 먼저" }
];

var PIPE_STATUS = {};        // 마지막 /api/pipe/status
var PIPE_RESULTS = {};       // {name: 요약문} — 이번 세션 잡 완료 결과
var PIPE_BUSY = {};          // {name: true} — 실행 중
var PIPE_GATE_CB = null;     // 검토 게이트 '계속' 콜백
var PIPE_RUNALL = false;     // 전체 실행 진행 중

function _pcId(name) { return "pc-" + name; }

/* 상태 기반 결과 요약(이번 세션 잡 결과가 있으면 그걸 우선) */
function _pipeSummary(name, s) {
  if (PIPE_RESULTS[name]) return PIPE_RESULTS[name];
  if (name === "sheets" && s.sheets > 0) return "시트 " + s.sheets + "개";
  if (name === "render" && s.rendered && s.rendered.total)
    return "렌더 " + s.rendered.done + "/" + s.rendered.total;
  return "";
}

/* 잡 result dict → 카드 요약문 */
function _pipeResultText(name, res) {
  res = res || {};
  if (name === "brief")        return "브리프 " + (res.score != null ? res.score : "?") + "점 " + (res.verdict || "") + " (" + (res.rounds || 0) + "R)";
  if (name === "research")     return "쿼리 " + (res.queries || 0) + " · 소스 " + (res.sources || 0) + " · 웹 " + (res.web_notes || 0);
  if (name === "manuscript")   return "원고 " + (res.score != null ? res.score : "?") + "점 " + (res.verdict || "") + " (" + (res.rounds || 0) + "R)";
  if (name === "scenes")       return "씬 " + (res.count || 0) + "개 (실사 " + (res.searched || 0) + ")";
  if (name === "scene-review") return "flags " + (res.flags || 0) + " · 이슈 " + (res.det_issues || 0);
  if (name === "entities")     return "엔티티 " + (res.entities || 0) + "개 · 역링크 " + (res.scenes_updated || 0);
  if (name === "sheets") {
    var sh = res.sheets || {};
    return "시트 char " + (sh.character || 0) + " / loc " + (sh.location || 0) + " / prop " + (sh.prop || 0) + (res.skipped && res.skipped.length ? " · skip " + res.skipped.length : "");
  }
  if (name === "render")       return "렌더 " + (res.rendered || 0) + "/" + (res.total || 0);
  return "완료";
}

function renderPipeCards() {
  var s = PIPE_STATUS || {};
  var host = $("pipe-cards");
  if (!host) return;
  var html = "";
  for (var i = 0; i < PIPE_STEPS.length; i++) {
    var st = PIPE_STEPS[i];
    var busy = !!PIPE_BUSY[st.name];
    var done = !!st.done(s);
    var canRun = !!st.prereq(s) && !busy;
    var dotCls = busy ? "busy" : (done ? "done" : "");
    var summary = _pipeSummary(st.name, s);
    var needTxt = st.prereq(s) ? "" : st.need;
    html += '<div class="pipe-card" id="' + _pcId(st.name) + '">'
      + '<div class="pc-head">'
      + '<span class="pc-dot ' + dotCls + '"></span>'
      + '<span class="pc-title">' + st.num + " " + st.label + '</span>'
      + '<button class="pc-run" data-step="' + st.name + '"' + (canRun ? "" : " disabled") + '>'
      + (busy ? "실행 중…" : (done ? "다시 실행" : "실행")) + '</button>'
      + '</div>'
      + '<div class="pc-log" id="' + _pcId(st.name) + '-log"></div>'
      + (summary ? '<div class="pc-result">' + summary + '</div>' : "")
      + (needTxt ? '<div class="pc-need">' + needTxt + '</div>' : "")
      + '</div>';
  }
  host.innerHTML = html;
  var btns = host.querySelectorAll("button[data-step]");
  for (var b = 0; b < btns.length; b++) {
    btns[b].addEventListener("click", function () {
      var nm = this.getAttribute("data-step");
      runPipeStep(nm, null);
    });
  }
}

function loadPipeStatus() {
  if (!SELECTED_PROJECT) { $("pipe-cards").textContent = "프로젝트를 먼저 선택하세요."; return; }
  fetch(BACKEND + "/api/pipe/status?project_id=" + encodeURIComponent(SELECTED_PROJECT))
    .then(function (r) { return r.json(); })
    .then(function (j) {
      PIPE_STATUS = j || {};
      renderPipeCards();
    })
    .catch(function (e) { $("pipe-cards").textContent = "상태 오류: " + e; });
}

/* 단일 단계 실행. onComplete(ok) 는 전체 실행 체인용(선택). */
function runPipeStep(name, onComplete) {
  if (!SELECTED_PROJECT) { alert("프로젝트를 먼저 선택하세요."); if (onComplete) onComplete(false); return; }
  if (PIPE_BUSY[name]) return;
  PIPE_BUSY[name] = true;
  renderPipeCards();
  var logEl = $(_pcId(name) + "-log");
  if (logEl) logEl.textContent = "시작…";
  fetch(BACKEND + "/api/pipe/" + name, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT })
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.status !== "running" || !j.job_id) {
        PIPE_BUSY[name] = false;
        if (logEl) logEl.textContent = "시작 실패: " + JSON.stringify(j);
        renderPipeCards();
        if (onComplete) onComplete(false);
        return;
      }
      _awaitJob(j.job_id, function (job) {
        PIPE_BUSY[name] = false;
        var ok = job.status === "completed";
        if (ok) {
          PIPE_RESULTS[name] = _pipeResultText(name, job.result);
        } else if (logEl) {
          logEl.textContent = "실패: " + (job.error || JSON.stringify(job));
        }
        loadPipeStatus();     // 산출물 반영해 점·요약 재계산
        if (onComplete) onComplete(ok);
      }, function (logs) {
        var el = $(_pcId(name) + "-log");
        if (el && logs && logs.length) el.textContent = logs[logs.length - 1];
      }, 2400);   // 1시간 한도(단계별 수십 분 소요 가능)
    })
    .catch(function (e) {
      PIPE_BUSY[name] = false;
      if (logEl) logEl.textContent = "오류: " + e;
      renderPipeCards();
      if (onComplete) onComplete(false);
    });
}

/* ===== 전체 실행 — 순차 + ②검토 게이트(브리프·원고 후 일시정지) ===== */
function _showGate(msg, cb) {
  PIPE_GATE_CB = cb;
  $("pipeGateMsg").textContent = msg;
  $("pipe-gate").classList.add("on");
}
function _hideGate() {
  PIPE_GATE_CB = null;
  $("pipe-gate").classList.remove("on");
}

function _pipeRunFrom(i) {
  if (i >= PIPE_STEPS.length) { _pipeAllDone(true); return; }
  var step = PIPE_STEPS[i];
  runPipeStep(step.name, function (ok) {
    if (!ok) { _pipeAllDone(false, step.label); return; }
    if (i === 0) {          // ① 브리프 완료 → 게이트
      _showGate("① 브리프 완료 — 기획 탭에서 editorial_brief.json 을 확인한 뒤 계속하세요.",
        function () { _pipeRunFrom(1); });
    } else if (i === 2) {   // ③ 원고 완료 → 게이트
      _showGate("③ 원고 완료 — 기획 탭에서 final_manuscript.md 를 확인한 뒤 계속하세요.",
        function () { _pipeRunFrom(3); });
    } else {
      _pipeRunFrom(i + 1);
    }
  });
}

function _pipeAllDone(success, failLabel) {
  PIPE_RUNALL = false;
  $("btnPipeRunAll").disabled = false;
  _hideGate();
  if (!success && failLabel) alert("전체 실행 중지 — '" + failLabel + "' 단계 실패. 로그를 확인하세요.");
}

function runPipeAll() {
  if (!SELECTED_PROJECT) { alert("프로젝트를 먼저 선택하세요."); return; }
  if (PIPE_RUNALL) return;
  if (!confirm("①브리프부터 ⑧씬 렌더까지 순차 실행합니다(LLM·이미지, 오래 걸림).\n브리프·원고 완료 후 검토 게이트에서 일시정지합니다. 진행할까요?")) return;
  PIPE_RUNALL = true;
  $("btnPipeRunAll").disabled = true;
  _pipeRunFrom(0);
}

document.addEventListener("DOMContentLoaded", function () {
  var reload = $("btnPipeReload");
  if (reload) reload.addEventListener("click", loadPipeStatus);
  var runall = $("btnPipeRunAll");
  if (runall) runall.addEventListener("click", runPipeAll);
  var gc = $("btnPipeGateContinue");
  if (gc) gc.addEventListener("click", function () {
    var cb = PIPE_GATE_CB;
    _hideGate();
    if (cb) cb();
  });
  var gs = $("btnPipeGateStop");
  if (gs) gs.addEventListener("click", function () { _pipeAllDone(false); });
});
