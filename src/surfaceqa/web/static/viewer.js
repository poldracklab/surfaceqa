// The three-view slice viewer. DOM and drawing only; arithmetic lives in logic.js.
import * as L from "./logic.js";

const LINE_WIDTH = 1.5;
const PRELOAD = 3;
const WHEEL_STEP = 40; // wheel delta that moves one slice
const DRAG_THRESHOLD = 3; // pixels of movement before a press becomes a pan

const root = document.getElementById("viewer");
const runUrl = root.dataset.run;
const state = {
  meta: null,
  cursor: [0, 0, 0],
  views: {},
  show: {surfaces: true, pial: true, white: true},
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
  };
}

function refit(v) {
  const size = pixelSize(v.plane);
  v.view = L.fit(v.canvas.clientWidth, v.canvas.clientHeight,
    v.plane.width * size.h, v.plane.height * size.v);
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
  drawContours(v, i);
  drawCrosshairs(v);
  v.panel.querySelector(".readout").textContent = `${v.name}  slice ${i + 1} / ${v.plane.n_slices}`;
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
  state.cursor = L.screenToGrid(x, y, state.cursor[v.plane.axis], v.plane, state.meta.shape);
  drawAll();
}

function toggleEnlarge(v) {
  const panels = root.querySelector(".panels");
  const enlarging = !v.panel.classList.contains("enlarged");
  Object.values(state.views).forEach((o) => o.panel.classList.remove("enlarged"));
  v.panel.classList.toggle("enlarged", enlarging);
  panels.classList.toggle("has-enlarged", enlarging);
}

function typing(event) {
  return ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) && event.target.type !== "checkbox";
}

const KEY_STEPS = {ArrowUp: 1, ArrowDown: -1, ArrowRight: 1, ArrowLeft: -1, PageUp: 10, PageDown: -10};

function onKeyDown(event) {
  if (typing(event)) return;
  if (event.key === "s" && !state.keyHide) {
    state.keyHide = true;
    drawAll();
  } else if (event.key in KEY_STEPS) {
    event.preventDefault();
    step(state.views[state.hovered], KEY_STEPS[event.key]);
  }
}

function onKeyUp(event) {
  if (event.key === "s") {
    state.keyHide = false;
    drawAll();
  }
}

function bindView(v) {
  v.canvas.addEventListener("wheel", (e) => onWheel(v, e), {passive: false});
  v.canvas.addEventListener("pointerdown", (e) => onPointerDown(v, e));
  v.canvas.addEventListener("pointermove", (e) => onPointerMove(v, e));
  v.canvas.addEventListener("pointerup", (e) => onPointerUp(v, e));
  v.canvas.addEventListener("pointercancel", () => { v.press = null; });
  v.canvas.addEventListener("dblclick", () => toggleEnlarge(v));
  new ResizeObserver(() => { refit(v); draw(v); }).observe(v.canvas);
}

function bindToolbar() {
  for (const key of ["surfaces", "pial", "white"]) {
    const box = document.getElementById(`show-${key}`);
    box.addEventListener("change", () => { state.show[key] = box.checked; drawAll(); });
  }
  document.getElementById("reset-view").addEventListener("click", () => {
    state.cursor = L.initialCursor(state.meta.shape);
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
  draw(v);
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
  drawAll();
  await Promise.all(Object.values(state.views).map(loadContours));
}

start().catch(showError);
