/* 뷰/탭 전환 — 목록 뷰 ↔ 상세 뷰, 기획/스토리보드 탭.
   SELECTED_PROJECT는 main.js의 전역(var)을 공유한다. main.js → nav.js 순 로드. */

function _$(id) { return document.getElementById(id); }

function showListView() {
  _$("view-detail").hidden = true;
  _$("view-list").hidden = false;
}

function enterProject(pid, label) {
  SELECTED_PROJECT = pid;            // main.js 전역
  _$("detailTitle").textContent = label || pid;
  _$("view-list").hidden = true;
  _$("view-detail").hidden = false;
  switchTab("planning");
  if (typeof loadPlanningFiles === "function") loadPlanningFiles();
}

function exitProject() {
  showListView();
}

function switchTab(name) {
  var planning = name === "planning";
  var pipeline = name === "pipeline";
  var storyboard = name === "storyboard";
  var settings = name === "settings";
  _$("tab-planning").hidden = !planning;
  _$("tab-pipeline").hidden = !pipeline;
  _$("tab-storyboard").hidden = !storyboard;
  _$("tab-settings").hidden = !settings;
  _$("btnTabPlanning").classList.toggle("active", planning);
  _$("btnTabPipeline").classList.toggle("active", pipeline);
  _$("btnTabStoryboard").classList.toggle("active", storyboard);
  _$("btnTabSettings").classList.toggle("active", settings);
  if (pipeline && typeof loadPipeStatus === "function") loadPipeStatus();
  if (storyboard && typeof loadSheet === "function") loadSheet();
  if (storyboard && typeof loadGallery === "function") loadGallery();
  if (settings && typeof loadSettings === "function") loadSettings();
}

document.addEventListener("DOMContentLoaded", function () {
  _$("btnBackToList").addEventListener("click", exitProject);
  _$("btnTabPlanning").addEventListener("click", function () { switchTab("planning"); });
  _$("btnTabPipeline").addEventListener("click", function () { switchTab("pipeline"); });
  _$("btnTabStoryboard").addEventListener("click", function () { switchTab("storyboard"); });
  _$("btnTabSettings").addEventListener("click", function () { switchTab("settings"); });
});
