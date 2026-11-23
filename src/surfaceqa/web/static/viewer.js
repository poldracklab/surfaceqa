// The three-view slice viewer. DOM and drawing only; arithmetic lives in logic.js.
import * as L from "./logic.js";

const LINE_WIDTH = 1.5;
const PRELOAD = 3;
const BRAIN_PAD = 0.04; // free space around the brain, as a fraction of its size
const FINDING_RGB = "0, 229, 255";
const HINT_RGB = "255, 170, 0"; // places to look, which are not counted as findings
const WHEEL_STEP = 40; // wheel delta that moves one slice
const DRAG_THRESHOLD = 3; // pixels of movement before a press becomes a pan
const SNAP_MM = 3; // a mark placed this close to a drawn contour sits on it
const MARK_RGB = "255, 79, 216";
const MARK_REACH = 1; // slices on either side of a mark on which it is drawn

const root = document.getElementById("viewer");
const runUrl = root.dataset.run;
const state = {
  meta: null,
  cursor: [0, 0, 0],
  views: {},
  show: {surfaces: true, pial: true, white: true, findings: true},
  findings: [],
  voxels: null, // Uint16Array of R, A, S triples for every finding
  highlight: null,
  marks: [], // problems the reviewer has marked: {grid, ...}
  pick: null, // while the reviewer is placing a mark: the function that receives the point
  layout: "three",
  wholeImage: false,
  focusMm: null,
  keyHide: false,
  hovered: "coronal",
};

function sliceUrl(plane, i) {
  return `${runUrl}slices/${plane}/${String(i).padStart(3, "0")}.jpg`;
}

// Size of one image pixel in mm along the horizontal and vertical screen axes.
function pixelSize(plane) {
  const vox = state.meta.voxel_sizes;
  return {h: vox[plane.h_axis], v: vox[plane.v_axis]};
}

function makeView(panel) {
  const name = panel.dataset.plane;
  const canvas = panel.querySelector("canvas");
  return {
    name, panel, canvas, ctx: canvas.getContext("2d"), plane: state.meta.planes[name],
    view: {scale: 1, dx: 0, dy: 0}, contours: null, images: new Map(), wheel: 0, press: null,
    findingSlices: new Map(), // slice -> [{id, points}] for the findings overlay
    slider: panel.querySelector(".slider"),
  };
}

// Fit the view to the brain (the box around its surfaces) so it fills the panel, or to the
// whole image when asked (the T1 pass looks at the face and skull too) or when there are
// no surfaces yet.
function refit(v) {
  const size = pixelSize(v.plane);
  const [w, h] = [v.canvas.clientWidth, v.canvas.clientHeight];
  const brain = !state.wholeImage && v.bounds ? L.fitBox(w, h, size, v.bounds, BRAIN_PAD) : null;
  v.view = brain || L.fit(w, h, v.plane.width * size.h, v.plane.height * size.v);
  v.size = [w, h];
}

// The canvas changed size (window resize, enlarge): keep the zoom and what is at the centre.
function onResize(v) {
  const [w, h] = [v.canvas.clientWidth, v.canvas.clientHeight];
  if (w === 0 || h === 0) return;
  if (v.size[0] === 0 || v.size[1] === 0) {
    refit(v); // it was hidden: start from a fitted view, then return to the place being looked at
    if (state.focusMm) focus(v, state.focusMm);
  } else {
    v.view = L.resizeView(v.view, v.size[0], v.size[1], w, h);
  }
  v.size = [w, h];
  draw(v);
}

function image(v, i) {
  if (!v.images.has(i)) {
    const img = new Image();
    img.onload = () => { if (i === state.cursor[v.plane.axis]) draw(v); };
    img.src = sliceUrl(v.name, i);
    v.images.set(i, img);
  }
  return v.images.get(i);
}

function preload(v, i) {
  for (let d = -PRELOAD; d <= PRELOAD; d++) {
    const j = i + d;
    if (j >= 0 && j < v.plane.n_slices) image(v, j);
  }
}

// Canvas position (CSS pixels) of a screen coordinate; pixel centres are integers.
function toCanvas(v, x, y) {
  const size = pixelSize(v.plane);
  return [v.view.dx + (x + 0.5) * size.h * v.view.scale,
    v.view.dy + (y + 0.5) * size.v * v.view.scale];
}

function fromCanvas(v, px, py) {
  const size = pixelSize(v.plane);
  return [(px - v.view.dx) / (size.h * v.view.scale) - 0.5,
    (py - v.view.dy) / (size.v * v.view.scale) - 0.5];
}

function sizeCanvas(v) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(v.canvas.clientWidth * dpr);
  const h = Math.round(v.canvas.clientHeight * dpr);
  if (v.canvas.width !== w || v.canvas.height !== h) {
    v.canvas.width = w;
    v.canvas.height = h;
  }
  v.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawImage(v, i) {
  const img = image(v, i);
  if (!img.complete || img.naturalWidth === 0) return;
  const [x0, y0] = toCanvas(v, -0.5, -0.5);
  const [x1, y1] = toCanvas(v, v.plane.width - 0.5, v.plane.height - 0.5);
  v.ctx.imageSmoothingEnabled = false;
  v.ctx.drawImage(img, x0, y0, x1 - x0, y1 - y0);
}

function surfaceVisible(name) {
  if (state.keyHide || !state.show.surfaces) return false;
  return name.endsWith(".pial") ? state.show.pial : state.show.white;
}

function drawSurface(v, name, i) {
  const seg = L.sliceSegments(v.contours.buffer, v.contours.index, name, i);
  v.ctx.beginPath();
  for (let k = 0; k < seg.length; k += 4) {
    const [ax, ay] = toCanvas(v, seg[k], seg[k + 1]);
    const [bx, by] = toCanvas(v, seg[k + 2], seg[k + 3]);
    v.ctx.moveTo(ax, ay);
    v.ctx.lineTo(bx, by);
  }
  v.ctx.strokeStyle = state.meta.surfaces[name].color;
  v.ctx.lineWidth = LINE_WIDTH;
  v.ctx.stroke();
}

function drawContours(v, i) {
  if (!v.contours) return;
  for (const name of Object.keys(state.meta.surfaces)) {
    if (surfaceVisible(name) && v.contours.index.surfaces[name]) drawSurface(v, name, i);
  }
}

// Findings whose voxels touch a slice of this view, computed once per slice.
function findingsOnSlice(v, i) {
  if (!v.findingSlices.has(i)) {
    const hits = [];
    for (const finding of state.findings) {
      const points = L.findingVoxelsOnSlice(state.voxels, finding, v.plane, i);
      if (points.length) hits.push({id: finding.id, hint: finding.kind === "look_here", points});
    }
    v.findingSlices.set(i, hits);
  }
  return v.findingSlices.get(i);
}

function drawFindings(v, i) {
  if (!state.voxels || !state.show.findings || state.keyHide) return;
  const [x0, y0] = toCanvas(v, -0.5, -0.5);
  const [x1, y1] = toCanvas(v, 0.5, 0.5);
  for (const hit of findingsOnSlice(v, i)) {
    const rgb = hit.hint ? HINT_RGB : FINDING_RGB;
    v.ctx.fillStyle = `rgba(${rgb}, ${hit.id === state.highlight ? 0.7 : 0.35})`;
    for (const [x, y] of hit.points) {
      const [px, py] = toCanvas(v, x - 0.5, y - 0.5);
      v.ctx.fillRect(px, py, x1 - x0, y1 - y0);
    }
  }
}

// The reviewer's marks: a ring, solid on the mark's own slice and faint on its neighbours.
function drawMarks(v, i) {
  for (const mark of L.marksOnSlice(state.marks, v.plane, i, MARK_REACH)) {
    const {x, y} = L.gridToScreen(mark.grid, v.plane);
    const [cx, cy] = toCanvas(v, x, y);
    const here = Math.round(mark.grid[v.plane.axis]) === i;
    v.ctx.beginPath();
    v.ctx.arc(cx, cy, 9, 0, 2 * Math.PI);
    v.ctx.strokeStyle = `rgba(${MARK_RGB}, ${here ? 1 : 0.45})`;
    v.ctx.lineWidth = 2;
    v.ctx.stroke();
  }
}

function drawCrosshairs(v) {
  const cross = L.crosshairs(state.cursor, v.plane);
  const [cx, cy] = toCanvas(v, cross.x, cross.y);
  v.ctx.save();
  v.ctx.globalAlpha = 0.4;
  v.ctx.strokeStyle = "#ffffff";
  v.ctx.lineWidth = 1;
  v.ctx.beginPath();
  v.ctx.moveTo(cx, 0);
  v.ctx.lineTo(cx, v.canvas.clientHeight);
  v.ctx.moveTo(0, cy);
  v.ctx.lineTo(v.canvas.clientWidth, cy);
  v.ctx.stroke();
  v.ctx.restore();
}

function draw(v) {
  const i = state.cursor[v.plane.axis];
  sizeCanvas(v);
  v.ctx.clearRect(0, 0, v.canvas.clientWidth, v.canvas.clientHeight);
  drawImage(v, i);
  drawFindings(v, i);
  drawContours(v, i);
  drawMarks(v, i);
  drawCrosshairs(v);
  v.panel.querySelector(".readout").textContent = `${v.name}  slice ${i + 1} / ${v.plane.n_slices}`;
  v.slider.value = i;
  preload(v, i);
}

function drawAll() {
  Object.values(state.views).forEach(draw);
}

function step(v, amount) {
  const axis = v.plane.axis;
  state.cursor[axis] = L.clampSlice(state.cursor[axis] + amount, v.plane.n_slices);
  drawAll();
}

function pointerPosition(v, event) {
  const box = v.canvas.getBoundingClientRect();
  return [event.clientX - box.left, event.clientY - box.top];
}

function onWheel(v, event) {
  event.preventDefault();
  if (event.ctrlKey || event.metaKey) {
    const [px, py] = pointerPosition(v, event);
    v.view = L.zoomAt(v.view, Math.exp(-event.deltaY * 0.01), px, py);
    draw(v);
    return;
  }
  v.wheel += event.deltaMode === 1 ? event.deltaY * WHEEL_STEP : event.deltaY;
  const steps = Math.trunc(v.wheel / WHEEL_STEP);
  if (steps !== 0) {
    v.wheel -= steps * WHEEL_STEP;
    step(v, steps);
  }
}

function onPointerDown(v, event) {
  const [px, py] = pointerPosition(v, event);
  v.press = {px, py, dx: v.view.dx, dy: v.view.dy, moved: false};
  v.canvas.setPointerCapture(event.pointerId);
}

function onPointerMove(v, event) {
  state.hovered = v.name;
  if (!v.press) return;
  const [px, py] = pointerPosition(v, event);
  const moved = Math.hypot(px - v.press.px, py - v.press.py) > DRAG_THRESHOLD;
  if (!moved && !v.press.moved) return;
  v.press.moved = true;
  v.view = {...v.view, dx: v.press.dx + px - v.press.px, dy: v.press.dy + py - v.press.py};
  draw(v);
}

function onPointerUp(v, event) {
  const press = v.press;
  v.press = null;
  if (!press || press.moved) return;
  const [x, y] = fromCanvas(v, ...pointerPosition(v, event));
  if (x < -0.5 || y < -0.5 || x > v.plane.width - 0.5 || y > v.plane.height - 0.5) return;
  if (state.pick) return finishPick(pickedPoint(v, x, y));
  state.cursor = L.screenToGrid(x, y, state.cursor[v.plane.axis], v.plane, state.meta.shape);
  drawAll();
}

// The contours drawn on the current slice of a view, by surface.
function shownSegments(v) {
  const i = state.cursor[v.plane.axis];
  const shown = {};
  if (!v.contours) return shown;
  for (const name of Object.keys(state.meta.surfaces)) {
    if (!surfaceVisible(name) || !v.contours.index.surfaces[name]) continue;
    shown[name] = L.sliceSegments(v.contours.buffer, v.contours.index, name, i);
  }
  return shown;
}

// Where a click places a mark: on the nearest drawn contour if one is close, else where clicked.
function pickedPoint(v, x, y) {
  const snap = L.nearestOnContours(shownSegments(v), x, y, SNAP_MM, pixelSize(v.plane));
  const at = snap || {x, y, surface: null};
  const slice = state.cursor[v.plane.axis];
  return {grid: L.screenToGridExact(at.x, at.y, slice, v.plane), surface: at.surface};
}

function finishPick(point) {
  const resolve = state.pick;
  state.pick = null;
  root.classList.remove("picking");
  if (resolve) resolve(point);
}

// The next click on a view gives a point for a mark instead of moving the views.
// Resolves with {grid, surface}, or null when cancelled with Escape or by another pick.
function pick() {
  finishPick(null);
  root.classList.add("picking");
  return new Promise((resolve) => { state.pick = resolve; });
}

function setMarks(marks) {
  state.marks = marks;
  drawAll();
}

// Show all three views ("three") or one large view of a single plane.
// With `fit`, the views start again fitted to the brain, or to the whole image.
function setLayout(layout, {fit = false, wholeImage = false} = {}) {
  const visible = L.visiblePlanes(layout);
  const single = visible.length === 1;
  state.layout = single ? visible[0] : "three";
  if (fit) {
    state.focusMm = null;
    state.wholeImage = wholeImage;
  }
  for (const v of Object.values(state.views)) {
    if (fit) v.size = [0, 0]; // refit when the new size is known
    v.panel.classList.toggle("enlarged", single && v.name === visible[0]);
  }
  root.querySelector(".panels").classList.toggle("has-enlarged", single);
  for (const button of root.querySelectorAll(".layout")) {
    button.classList.toggle("active", button.dataset.layout === state.layout);
  }
  if (single) state.hovered = visible[0];
  if (fit) requestAnimationFrame(refitVisible); // the panel may not change size, so no resize event
}

function refitVisible() {
  for (const v of Object.values(state.views)) {
    if (v.canvas.clientWidth === 0) continue;
    refit(v);
    draw(v);
  }
}

function toggleEnlarge(v) {
  setLayout(state.layout === v.name ? "three" : v.name);
}

function setSurfaces(shown) {
  state.show.surfaces = shown;
  document.getElementById("show-surfaces").checked = shown;
  drawAll();
}

function typing(event) {
  return ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) && event.target.type !== "checkbox";
}

const KEY_STEPS = {ArrowUp: 1, ArrowDown: -1, ArrowRight: 1, ArrowLeft: -1, PageUp: 10, PageDown: -10};

function onKeyDown(event) {
  if (event.key === "Escape" && state.pick) return finishPick(null);
  if (typing(event)) return;
  if (L.isHideKey(event)) {
    if (!state.keyHide) setKeyHide(true);
  } else if (event.key in KEY_STEPS) {
    event.preventDefault();
    step(state.views[state.hovered], KEY_STEPS[event.key]);
  }
}

function setKeyHide(hidden) {
  state.keyHide = hidden;
  drawAll();
}

// Released by the S key coming up with any modifiers, or by the window losing focus,
// so the surfaces can never stay hidden while their boxes are ticked.
function onKeyUp(event) {
  if (event.code === "KeyS" && state.keyHide) setKeyHide(false);
}

function bindView(v) {
  v.canvas.addEventListener("wheel", (e) => onWheel(v, e), {passive: false});
  v.canvas.addEventListener("pointerdown", (e) => onPointerDown(v, e));
  v.canvas.addEventListener("pointermove", (e) => onPointerMove(v, e));
  v.canvas.addEventListener("pointerup", (e) => onPointerUp(v, e));
  v.canvas.addEventListener("pointercancel", () => { v.press = null; });
  v.canvas.addEventListener("dblclick", () => toggleEnlarge(v));
  v.slider.max = v.plane.n_slices - 1;
  v.slider.addEventListener("input", () => step(v, Number(v.slider.value) - state.cursor[v.plane.axis]));
  new ResizeObserver(() => onResize(v)).observe(v.canvas);
}

function bindToolbar() {
  for (const key of ["surfaces", "pial", "white", "findings"]) {
    const box = document.getElementById(`show-${key}`);
    if (!box) continue; // the findings box is absent in a blind review
    box.addEventListener("change", () => { state.show[key] = box.checked; drawAll(); });
  }
  for (const button of root.querySelectorAll(".layout")) {
    button.addEventListener("click", () => setLayout(button.dataset.layout));
  }
  document.getElementById("reset-view").addEventListener("click", () => {
    state.cursor = L.initialCursor(state.meta.shape);
    state.focusMm = null;
    state.wholeImage = false;
    Object.values(state.views).forEach(refit);
    drawAll();
  });
}

function labelEdges(v) {
  for (const side of ["left", "right", "top", "bottom"]) {
    v.panel.querySelector(`.edge.${side}`).textContent = v.plane.edges[side];
  }
}

async function loadContours(v) {
  const [index, buffer] = await Promise.all([
    fetch(`${runUrl}contours_${v.name}.json`).then((r) => r.json()),
    fetch(`${runUrl}contours_${v.name}.bin`).then((r) => r.arrayBuffer()),
  ]);
  v.contours = {index, buffer};
  v.bounds = L.contourBounds(buffer, index);
  refit(v); // now that the brain's extent is known
  draw(v);
}

// Findings are optional: a subject without them still gets the viewer.
async function loadFindings() {
  if (root.dataset.findings === "off") return; // blind review: not asked for, not shown
  try {
    const found = await fetch(`${runUrl}findings.json`).then((r) => (r.ok ? r.json() : null));
    if (!found || !found.findings.length) return;
    const buffer = await fetch(`${runUrl}findings_voxels.bin`).then((r) => r.arrayBuffer());
    state.findings = found.findings;
    state.voxels = new Uint16Array(buffer);
    drawAll();
  } catch (error) {
    console.warn("surfaceqa: findings could not be loaded", error);
  }
}

// Zoom a view onto the cursor. A hidden view is left alone and marked so that it
// is zoomed when it becomes visible again.
function focus(v, zoomMm) {
  const {x, y} = L.gridToScreen(state.cursor, v.plane);
  const view = L.zoomTo(v.canvas.clientWidth, v.canvas.clientHeight, v.plane, pixelSize(v.plane), x, y, zoomMm);
  if (view) v.view = view;
  else v.size = [0, 0];
}

function goTo(grid, {zoomMm} = {}) {
  state.cursor = grid.map((value, axis) => L.clampSlice(value, state.meta.shape[axis]));
  state.focusMm = zoomMm || null;
  if (zoomMm) Object.values(state.views).forEach((v) => focus(v, zoomMm));
  drawAll();
  root.closest(".workspace").scrollIntoView({block: "nearest"});
}

function goToSlice(planeName, slice) {
  const v = state.views[planeName];
  const grid = [...state.cursor];
  grid[v.plane.axis] = slice;
  Object.values(state.views).forEach(refit);
  goTo(grid);
}

function setHighlight(id) {
  state.highlight = id;
  drawAll();
}

// What other scripts on the page (the checklist) may use.
function publicData() {
  const contours = Object.fromEntries(Object.values(state.views).map((v) => [v.name, v.contours]));
  return {meta: state.meta, contours, sliceUrl};
}

function showError(error) {
  const note = document.createElement("p");
  note.className = "note";
  note.textContent = `The viewer could not load this subject (${error.message}). Open the page through "surfaceqa serve".`;
  root.prepend(note);
}

async function start() {
  state.meta = await fetch(root.dataset.meta).then((r) => r.json());
  state.cursor = L.initialCursor(state.meta.shape);
  for (const panel of root.querySelectorAll(".panel")) {
    const v = makeView(panel);
    state.views[v.name] = v;
    labelEdges(v);
    refit(v);
    bindView(v);
  }
  bindToolbar();
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("blur", () => { if (state.keyHide) setKeyHide(false); });
  drawAll();
  await Promise.all(Object.values(state.views).map(loadContours));
  loadFindings();
  return publicData();
}

const ready = start();
window.surfaceqaViewer = {ready, goTo, goToSlice, setHighlight, setLayout, setSurfaces, setMarks, pick};
ready.catch(showError);
