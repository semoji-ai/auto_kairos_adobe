/* 제작 비서 — NL 지시를 /api/assistant 로 보내 플랜·결과를 로그에 표시. main.js 전역 사용. */
function _chatAppend(html) {
  var log = $("chatLog");
  log.innerHTML += '<div class="chat-msg">' + html + '</div>';
  log.scrollTop = log.scrollHeight;
}

function sendChat() {
  if (!SELECTED_PROJECT) { _chatAppend("⚠ 프로젝트를 먼저 선택하세요."); return; }
  var inp = $("chatInput");
  var msg = (inp.value || "").trim();
  if (!msg) return;
  _chatAppend("🧑 " + _esc(msg));
  inp.value = "";
  _chatAppend("🤖 계획 세우는 중…");
  fetch(BACKEND + "/api/assistant", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: SELECTED_PROJECT, instruction: msg }),
  }).then(function (r) { return r.json(); })
    .then(function (j) {
      if (j.error) { _chatAppend("실패: " + _esc(j.error)); return; }
      if (j.status !== "running" || !j.job_id) { _chatAppend("실패: " + _esc(JSON.stringify(j))); return; }
      _chatAppend("🤖 실행 중…");
      var seenLogs = 0;
      _awaitJob(j.job_id, function (job) {
        if (job.status !== "completed") { _chatAppend("실패: " + _esc(job.error || JSON.stringify(job))); return; }
        var out = job.result || {};
        if (out.reply) {                                 // 질문/상담 → 답변 모드
          _chatAppend("🤖 " + _esc(out.reply).replace(/\n/g, "<br>"));
          if (!(out.plan || []).length) return;          // 답변만(실행 없음)
        }
        if (!(out.plan || []).length) {
          _chatAppend("🤖 실행할 액션을 찾지 못했습니다. 실행 지시(예: \"음성 입혀서 합쳐줘\") 또는 질문으로 다시 말씀해 주세요.");
          return;
        }
        var plan = (out.plan || []).map(function (a) { return "• " + a.action + " — " + _esc(a.reason || ""); }).join("<br>");
        _chatAppend("📋 계획:<br>" + plan);
        (out.results || []).forEach(function (res) {
          _chatAppend("✓ " + res.action + ": " + _esc(JSON.stringify(res.result)));
        });
        _chatAppend("완료. 시트/AE를 확인하세요.");
        if (typeof loadSheet === "function") loadSheet();
      }, function (logs) {
        for (; seenLogs < logs.length; seenLogs++) _chatAppend("… " + _esc(logs[seenLogs]));
      }, 2400);   // 60분 한도 — 비서가 무거운 액션(분리·이미지) 실행 시 대비
    })
    .catch(function (e) { _chatAppend("오류: " + _esc(String(e))); });
}

document.addEventListener("DOMContentLoaded", function () {
  var b = $("btnChatSend"); if (b) b.addEventListener("click", sendChat);
  var i = $("chatInput");
  if (i) i.addEventListener("keydown", function (e) { if (e.key === "Enter") sendChat(); });
});
