"use strict";
const $ = (id) => document.getElementById(id);
const labels = {1: "A 更好", 0: "相当", "-1": "B 更好"};
let bootstrap, current, poll, busy = false;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求失败，请重试。");
  return data;
}
function notice(message = "", error = false) {
  $("notice").textContent = message;
  $("notice").hidden = !message;
  $("notice").classList.toggle("error", error);
}
async function action(fn) {
  if (busy) return;
  busy = true; updateButtons();
  try { await fn(); } catch (error) { notice(error.message, true); }
  finally { busy = false; updateButtons(); }
}
function metricQuestion(code) {
  const [name, description] = bootstrap.metrics[code];
  const fieldset = document.createElement("fieldset"); fieldset.className = "question";
  const legend = document.createElement("legend");
  const small = document.createElement("span"); small.textContent = code;
  legend.append(small, document.createTextNode(name));
  const p = document.createElement("p"); p.textContent = description;
  const choices = document.createElement("div"); choices.className = "choices";
  for (const value of [1, 0, -1]) {
    const label = document.createElement("label"); label.className = "choice";
    const input = document.createElement("input"); input.type = "radio"; input.name = code; input.value = value; input.required = true;
    input.addEventListener("change", () => { saveDraft(); updateButtons(); });
    label.append(input, document.createTextNode(labels[value])); choices.append(label);
  }
  fieldset.append(legend, p, choices); return fieldset;
}
function selected(code) {
  const input = document.querySelector(`input[name="${code}"]:checked`);
  return input ? Number(input.value) : null;
}
function draftKey() { return `human-judge:${bootstrap.study_id}:${bootstrap.participant.id}:${current.id}`; }
function selectedReasons() { return [...document.querySelectorAll('input[name="reason"]:checked')].map(i => i.value); }
function reasonOptions() {
  const container = $("reason-options"); container.replaceChildren();
  for (const code of ["IF", "VQ", "TC", "NC"]) {
    const title = bootstrap.reasons[code];
    const label = document.createElement("label"); label.className = "choice";
    const input = document.createElement("input"); input.type = "checkbox"; input.name = "reason"; input.value = code;
    input.addEventListener("change", saveDraft);
    label.append(input, document.createTextNode(title)); container.append(label);
  }
}
function saveDraft() {
  if (!current) return;
  try { localStorage.setItem(draftKey(), JSON.stringify({scores: {OQ: selected("OQ")}, reasons: selectedReasons(), note: $("note").value, watched: {a: $("watched-a").checked, b: $("watched-b").checked}})); } catch (_) { /* Server remains the durable source of submitted data. */ }
}
function restoreDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem(draftKey()) || "null");
    if (!draft) return;
    for (const [code, value] of Object.entries(draft.scores || {})) {
      if (!Object.hasOwn(bootstrap.metrics, code) || ![-1,0,1].includes(value)) continue;
      const input = document.querySelector(`input[name="${code}"][value="${value}"]`); if (input) input.checked = true;
    }
    $("note").value = draft.note || "";
    for (const input of document.querySelectorAll('input[name="reason"]')) input.checked = (draft.reasons || []).includes(input.value);
    for (const side of ["a", "b"]) $(`watched-${side}`).checked = draft.watched?.[side] === true;
  } catch (_) { /* Ignore unavailable or stale local storage. */ }
}
function updateButtons() {
  const ready = current && ["a", "b"].every(s => current.media[s].status === "ready");
  $("submit").disabled = busy || !ready || !$("watched-a").checked || !$("watched-b").checked || selected("OQ") === null;
  document.querySelectorAll("#login-form button,#skip-form button,#logout").forEach(b => { b.disabled = busy; });
}
function applyMedia() {
  for (const side of ["a", "b"]) {
    const media = current.media[side], video = $(`video-${side}`), message = $(`media-${side}`);
    if (media.status === "ready") {
      if (video.getAttribute("src") !== media.url) { video.src = media.url; video.load(); }
      if (!video.error) message.hidden = true;
    } else {
      message.hidden = false;
      message.textContent = media.status === "error" ? "视频准备失败，请记录原因并跳过，或联系管理员。" : "视频正在准备，请稍候…";
    }
  }
  updateButtons();
}
async function pollMedia(pairId) {
  clearTimeout(poll);
  if (!current || current.id !== pairId) return;
  try {
    const data = await api(`/api/pairs/${pairId}`);
    if (current?.id !== pairId) return;
    current.media = data.media; applyMedia();
    if (Object.values(data.media).some(m => m.status === "preparing")) poll = setTimeout(() => pollMedia(pairId), 1800);
  } catch (error) { notice(error.message, true); poll = setTimeout(() => pollMedia(pairId), 4000); }
}
async function nextPair() {
  clearTimeout(poll);
  const data = await api("/api/next", {});
  for (const side of ["a", "b"]) { const video = $(`video-${side}`); video.pause(); video.removeAttribute("src"); video.load(); $(`time-${side}`).textContent = "—"; $(`watched-${side}`).checked = false; }
  current = data;
  const t = data.task;
  $("task-id").textContent = t.id;
  $("domain").textContent = ({sports: "体育", documentary: "纪录片", film: "电影"})[t.domain] || t.domain;
  $("intent").textContent = t.intent;
  $("target").textContent = `目标 ${t.target_seconds} 秒`;
  $("prompt").textContent = t.prompt;
  $("source-title").textContent = t.source_title;
  $("bgm").textContent = `BGM：${t.bgm_title}${t.bgm_moods.length ? " · " + t.bgm_moods.join(" / ") : ""}`;
  $("count").textContent = `已完成 ${data.completed} 组`;
  $("detail-questions").replaceChildren(metricQuestion("OQ"));
  reasonOptions();
  $("note").value = ""; $("skip-reason").value = ""; document.querySelector(".skip").open = false;
  restoreDraft(); updateButtons(); applyMedia();
  if (Object.values(current.media).some(m => m.status === "preparing")) poll = setTimeout(() => pollMedia(data.id), 1000);
}
async function start() {
  bootstrap = await api("/api/bootstrap");
  $("title").textContent = bootstrap.title; document.title = bootstrap.title;
  $("welcome").hidden = !!bootstrap.participant;
  $("workspace").hidden = !bootstrap.participant; $("identity").hidden = !bootstrap.participant;
  if (bootstrap.participant) { $("person").textContent = bootstrap.participant.label; await nextPair(); }
}
$("login-form").addEventListener("submit", e => { e.preventDefault(); action(async () => { await api("/api/session", {label: $("label").value}); notice(); await start(); }); });
$("logout").addEventListener("click", () => action(async () => { saveDraft(); clearTimeout(poll); for (const s of ["a", "b"]) $(`video-${s}`).pause(); await api("/api/logout", {}); current = null; notice(); await start(); }));
$("details-form").addEventListener("submit", e => { e.preventDefault(); action(async () => { await api(`/api/pairs/${current.id}/ratings`, {scores: {OQ: selected("OQ")}, reasons: selectedReasons(), watched: {a: $("watched-a").checked, b: $("watched-b").checked}, note: $("note").value}); try { localStorage.removeItem(draftKey()); } catch (_) {} await nextPair(); notice("本组整体质量判断已保存。已为你抽取下一组。"); window.scrollTo({top: 0, behavior: "smooth"}); }); });
$("skip-form").addEventListener("submit", e => { e.preventDefault(); action(async () => { await api(`/api/pairs/${current.id}/skip`, {note: $("skip-reason").value}); try { localStorage.removeItem(draftKey()); } catch (_) {} await nextPair(); notice("已记录跳过原因，并抽取下一组。"); window.scrollTo({top: 0, behavior: "smooth"}); }); });
$("note").addEventListener("input", saveDraft);
for (const side of ["a", "b"]) {
  const video = $(`video-${side}`);
  $(`watched-${side}`).addEventListener("change", () => { saveDraft(); updateButtons(); });
  video.addEventListener("play", () => $(`video-${side === "a" ? "b" : "a"}`).pause());
  video.addEventListener("loadedmetadata", () => { $(`time-${side}`).textContent = `${Math.floor(video.duration / 60)}:${String(Math.floor(video.duration % 60)).padStart(2, "0")}`; });
  video.addEventListener("error", () => { if (!video.getAttribute("src")) return; const message = $(`media-${side}`); message.hidden = false; message.textContent = "浏览器无法播放此视频。请勿猜测评分，可在下方记录问题并跳过。"; $(`watched-${side}`).checked = false; updateButtons(); });
  video.addEventListener("ratechange", () => { if (video.playbackRate !== 1) video.playbackRate = 1; });
}
action(start);
