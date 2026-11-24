// Recording a review: ratings, marks, grade; saved as the reviewer goes.
import * as L from "./logic.js";
import {refreshGuidance} from "./guidance.js";

const SAVE_DELAY = 500; // ms after the last change
const ZOOM_MM = 60;
const data = JSON.parse(document.getElementById("review-data").textContent);
const {protocol, key} = data;
const review = data.review;
const sidebar = document.getElementById("checklist");
const itemEls = [...sidebar.querySelectorAll(".item[data-item]")];
const itemIds = itemEls.map((el) => el.dataset.item);
const PASSES = ["birdseye", "t1"];
const FINDING_KIND = {pial_out: "pial_out", gray_missed: "gray_missed", white_short: "white_short",
  crossing: "crossing", topology: "topology"};
const ui = {
  grade: document.getElementById("grade"), notes: document.getElementById("notes"),
  unratable: document.getElementById("unratable"), reason: document.getElementById("unratable-reason"),
  remaining: document.getElementById("remaining"), missing: document.getElementById("missing"),
  status: document.getElementById("save-status"), help: document.getElementById("help"),
};
const state = {current: null, timer: null, saving: Promise.resolve(), dirty: false, locked: false, viewer: null};

function scaleOf(id) {
  return PASSES.includes(id) ? protocol.pass_scale : protocol.region_scale;
}

// ---- showing the review ----

function showItem(el) {
  const entry = review.items[el.dataset.item];
  el.classList.toggle("rated", entry.rating !== null);
  for (const radio of el.querySelectorAll('input[type="radio"]')) radio.checked = radio.value === entry.rating;
}

function showRemaining() {
  const n = L.itemsRemaining(review, itemIds);
  const wantsReason = ui.unratable.checked && !ui.reason.value.trim();
  ui.remaining.textContent = wantsReason ? "Give the reason this subject cannot be rated."
    : n === 0 ? "Everything is rated." : `${n} still to do before you can submit.`;
}

function showStatus(text, isError = false) {
  ui.status.textContent = text;
  ui.status.classList.toggle("error", isError);
}

function kindSelect(mark) {
  const select = document.createElement("select");
  for (const kind of protocol.mark_kinds) select.add(new Option(kind.label, kind.id, false, kind.id === mark.kind));
  select.addEventListener("change", () => { mark.kind = select.value; changed(); });
  return select;
}

function button(label, onClick) {
  const el = document.createElement("button");
  el.type = "button";
  el.textContent = label;
  el.addEventListener("click", onClick);
  return el;
}

function markRow(mark) {
  const row = document.createElement("li");
  const note = document.createElement("input");
  note.type = "text";
  note.placeholder = "Note";
  note.maxLength = 2000;
  note.value = mark.note;
  note.addEventListener("input", () => { mark.note = note.value; changed(); });
  const where = mark.surface ? `on ${mark.surface}` : "not on a surface";
  const label = document.createElement("span");
  label.className = "muted";
  label.textContent = mark.finding === null ? where : `finding, ${where}`;
  row.append(kindSelect(mark), label, note,
    button("go to", () => state.viewer.goTo(mark.grid.map(Math.round), {zoomMm: ZOOM_MM})),
    button("remove", () => { review.marks.splice(review.marks.indexOf(mark), 1); showMarks(); changed(); }));
  return row;
}

function showMarks() {
  for (const list of sidebar.querySelectorAll("ul.marks")) {
    list.replaceChildren(...review.marks.filter((m) => m.region === list.dataset.marks).map(markRow));
  }
  state.viewer.setMarks(review.marks);
}

function showAll() {
  itemEls.forEach(showItem);
  for (const el of itemEls) el.querySelector(".item-note").value = review.items[el.dataset.item].note;
  ui.grade.value = review.grade || "";
  ui.notes.value = review.notes || "";
  ui.unratable.checked = Boolean(review.unratable);
  ui.reason.value = review.unratable || "";
  ui.reason.hidden = !ui.unratable.checked;
  showMarks();
  showRemaining();
  if (review.submitted) showStatus(`Submitted ${review.submitted.slice(0, 16).replace("T", " ")} UTC. Changes are saved as a revision.`);
}

// ---- saving ----

function payload(extra = {}) {
  const marks = review.marks.map(({region, kind, grid, surface, finding, note}) => ({region, kind, grid, surface, finding, note}));
  // reviewer and saved let the server refuse a page that is out of date: opened under
  // another name, or behind a save made in another window
  return {run: review.run, reviewer: review.reviewer, saved: review.saved, items: review.items, marks,
    grade: review.grade, notes: review.notes, unratable: review.unratable, ...extra};
}

function lock(message) {
  state.locked = true;
  showStatus(message, true);
  for (const el of sidebar.querySelectorAll("input, select, textarea, button.mark-here, button.accept, #submit, #skip")) el.disabled = true;
}

function detailText(detail) {
  return Array.isArray(detail) ? detail.join("; ") : String(detail);
}

async function send(method, path, body) {
  const response = await fetch(path, {method, headers: {"content-type": "application/json"}, body: JSON.stringify(body)});
  const result = await response.json().catch(() => ({detail: `the server answered ${response.status}`}));
  return {status: response.status, result};
}

async function saveNow(extra = {}) {
  if (state.locked) return false;
  state.dirty = false;
  try {
    const {status, result} = await send("PUT", `/api/review/${encodeURIComponent(key)}`, payload(extra));
    if (status === 409) { lock(result.detail); return false; }
    if (status !== 200) { state.dirty = true; showStatus(`Not saved: ${detailText(result.detail)}`, true); return false; }
    review.saved = result.review.saved;
    showStatus(`Saved ${new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`);
    refreshGuidance();
    return true;
  } catch (error) {
    state.dirty = true;
    showStatus(`Not saved: the server could not be reached (${error.message})`, true);
    return false;
  }
}

// Saves run one after another, so an older save can never land after a newer one.
function queueSave(extra) {
  clearTimeout(state.timer);
  state.saving = state.saving.then(() => saveNow(extra));
  return state.saving;
}

function changed() {
  state.dirty = true;
  showRemaining();
  ui.missing.replaceChildren(); // the list from a refused submit is out of date now
  clearTimeout(state.timer);
  state.timer = setTimeout(queueSave, SAVE_DELAY);
}

function showMissing(lines) {
  ui.missing.replaceChildren(...lines.map((line) => Object.assign(document.createElement("li"), {textContent: line})));
  const first = itemEls.find((el) => review.items[el.dataset.item].rating === null);
  if (first) setCurrent(itemEls.indexOf(first));
}

async function submit() {
  await queueSave();
  if (state.locked) return;
  let answer;
  try {
    answer = await send("POST", `/api/review/${encodeURIComponent(key)}/submit`, payload());
  } catch (error) {
    return showStatus(`Not submitted: the server could not be reached (${error.message})`, true);
  }
  const {status, result} = answer;
  if (status === 200) return window.location.reload();
  if (status === 409) return lock(result.detail);
  if (result.saved) review.saved = result.saved; // the draft was stored even though it is incomplete
  if (Array.isArray(result.detail)) { showStatus("Not submitted yet:", true); return showMissing(result.detail); }
  showStatus(`Not submitted: ${detailText(result.detail)}`, true);
}

async function skip() {
  if (await queueSave({skipped: true})) window.location.assign(`/next?after=${encodeURIComponent(key)}`);
}

// ---- rating ----

function setCurrent(index) {
  if (index === null) return;
  state.current = index;
  itemEls.forEach((el, i) => el.classList.toggle("current", i === index));
  itemEls[index].scrollIntoView({block: "nearest"});
}

function rate(index, level) {
  const el = itemEls[index];
  review.items[el.dataset.item].rating = level;
  showItem(el);
  changed();
}

function bindItems() {
  itemEls.forEach((el, index) => {
    el.addEventListener("pointerdown", () => setCurrent(index));
    for (const radio of el.querySelectorAll('input[type="radio"]')) radio.addEventListener("change", () => rate(index, radio.value));
    const note = el.querySelector(".item-note");
    note.addEventListener("input", () => { review.items[el.dataset.item].note = note.value; changed(); });
  });
}

function bindOverall() {
  ui.grade.addEventListener("change", () => { review.grade = ui.grade.value || null; changed(); });
  ui.notes.addEventListener("input", () => { review.notes = ui.notes.value; changed(); });
  const unratable = () => {
    ui.reason.hidden = !ui.unratable.checked;
    review.unratable = ui.unratable.checked ? ui.reason.value : null;
    changed();
  };
  ui.unratable.addEventListener("change", unratable);
  ui.reason.addEventListener("input", unratable);
  document.getElementById("submit").addEventListener("click", submit);
  document.getElementById("skip").addEventListener("click", skip);
}

// ---- marking ----

function addMark(mark) {
  review.marks.push({finding: null, note: "", surface: null, ...mark});
  showMarks();
  changed();
}

async function markIn(regionButton) {
  if (state.locked) return;
  regionButton.classList.add("armed");
  regionButton.textContent = "Click the misplaced contour (Esc cancels)";
  const point = await state.viewer.pick();
  regionButton.classList.remove("armed");
  regionButton.textContent = "Mark a problem";
  if (point) addMark({region: regionButton.dataset.markRegion, kind: protocol.mark_kinds[0].id, ...point});
}

function acceptFinding(el) {
  const region = el.closest(".item").dataset.item;
  const finding = Number(el.dataset.accept);
  if (review.marks.some((mark) => mark.finding === finding)) return;
  addMark({region, finding, grid: el.dataset.grid.split(",").map(Number),
    kind: FINDING_KIND[el.dataset.kind] || protocol.mark_kinds[0].id});
}

function bindMarks() {
  for (const el of sidebar.querySelectorAll(".mark-here")) el.addEventListener("click", () => markIn(el));
  for (const el of sidebar.querySelectorAll(".accept")) el.addEventListener("click", () => acceptFinding(el));
}

// ---- keys ----

function typing(event) {
  return L.isTyping(event.target);
}

function onKey(event) {
  if (event.key === "Escape") ui.help.hidden = true;
  if (typing(event) || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.key === "?") { ui.help.hidden = !ui.help.hidden; return; }
  if (event.key === "j") return setCurrent(L.stepItem(state.current, 1, itemEls.length));
  if (event.key === "k") return setCurrent(L.stepItem(state.current, -1, itemEls.length));
  if (event.key === "g") { event.preventDefault(); return ui.grade.focus(); }
  if (event.key === "N") return window.location.assign(`/next?after=${encodeURIComponent(key)}`);
  if (state.current === null || state.locked) return;
  const el = itemEls[state.current];
  const level = L.levelForKey(event.key, scaleOf(el.dataset.item));
  if (level) return rate(state.current, level);
  const markButton = el.querySelector(".mark-here");
  if (event.key === "m" && markButton) markIn(markButton);
}

// A change made in the last half second is still sent when the page is left.
function flushOnLeave() {
  if (!state.dirty || state.locked) return;
  fetch(`/api/review/${encodeURIComponent(key)}`, {method: "PUT", keepalive: true,
    headers: {"content-type": "application/json"}, body: JSON.stringify(payload())});
}

async function start() {
  state.viewer = window.surfaceqaViewer;
  await state.viewer.ready;
  bindItems();
  bindOverall();
  bindMarks();
  showAll();
  window.addEventListener("keydown", onKey);
  window.addEventListener("pagehide", flushOnLeave);
}

start().catch((error) => showStatus(`Reviewing could not start (${error.message}); nothing will be saved.`, true));
