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
      _pollJob(j.job_id, function (job) {
        if (job.status !== "completed") { _chatAppend("실패: " + _esc(job.error || JSON.stringify(job))); return; }
        var out = job.result || {};
        var plan = (out.plan || []).map(function (a) { return "• " + a.action + " — " + _esc(a.reason || ""); }).join("<br>");
        _chatAppend("📋 계획:<br>" + (plan || "(없음)"));
        (out.results || []).forEach(function (res) {
          _chatAppend("✓ " + res.action + ": " + _esc(JSON.stringify(res.result)));
        });
        _chatAppend("완료. 시트/AE를 확인하세요.");
        if (typeof loadSheet === "function") loadSheet();
      }, function (logs) {
        for (; seenLogs < logs.length; seenLogs++) _chatAppend("… " + _esc(logs[seenLogs]));
      });
    })
    .catch(function (e) { _chatAppend("오류: " + _esc(String(e))); });
}

document.addEventListener("DOMContentLoaded", function () {
  var b = $("btnChatSend"); if (b) b.addEventListener("click", sendChat);
  var i = $("chatInput");
  if (i) i.addEventListener("keydown", function (e) { if (e.key === "Enter") sendChat(); });
});
