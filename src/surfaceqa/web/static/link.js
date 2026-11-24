// Keeps two viewers at the same place: the subject page and the comparison shown in its frame.
// Loaded by both pages. Each tells the other where its cursor is; arithmetic is in logic.js.
import * as L from "./logic.js";

const READY = "surfaceqa:ready";
const viewer = window.surfaceqaViewer;
const root = document.getElementById("viewer");
const select = document.getElementById("compare-with"); // only on the subject page
const linked = document.getElementById("compare-linked");
const box = document.getElementById("compare");
const frame = box ? box.querySelector("iframe") : null;
const embedded = !select;

// The window of the other viewer, or null when there is none.
function peer() {
  if (embedded) return window.parent !== window ? window.parent : null;
  return box.hidden ? null : frame.contentWindow;
}

// The subject page decides whether the two move together; the comparison always follows.
function isLinked() {
  return embedded || linked.checked;
}

async function send() {
  const other = peer();
  if (!other || !isLinked()) return;
  const {meta} = await viewer.ready;
  // "*": the message holds a position only, and pages opened from disk have no origin to name
  other.postMessage(L.positionMessage(viewer.cursor(), meta, viewer.layout()), "*");
}

async function receive(event) {
  if (!event.source || event.source !== peer() || !isLinked()) return;
  if (event.data && event.data.type === READY) return send();
  const {meta} = await viewer.ready;
  const grid = L.cursorFromMessage(event.data, meta);
  if (!grid) return;
  const layout = event.data.layout;
  if (typeof layout === "string" && layout !== viewer.layout()) viewer.setLayout(layout, {quiet: true});
  viewer.goTo(grid, {quiet: true});
}

function choose() {
  const chosen = select.value;
  box.hidden = !chosen;
  root.classList.toggle("comparing", Boolean(chosen));
  if (chosen) frame.src = chosen;
  else frame.removeAttribute("src");
}

window.addEventListener("message", receive);
root.addEventListener("surfaceqa:cursor", send);
root.addEventListener("surfaceqa:layout", send);
if (embedded) {
  viewer.ready.then(() => { if (peer()) peer().postMessage({type: READY}, "*"); });
} else {
  select.addEventListener("change", choose);
  linked.addEventListener("change", send);
}
