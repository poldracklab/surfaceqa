// Pure viewer arithmetic: no DOM, no imports. Tested with `node --test`.

const MIN_SCALE = 0.5;
const MAX_SCALE = 32;

// Segments of one surface on one slice, as x1, y1, x2, y2, ... in screen pixels.
export function sliceSegments(buffer, index, surface, i) {
  const offsets = index.surfaces[surface];
  const start = offsets[i];
  const count = (offsets[i + 1] - start) * 4;
  const raw = new Uint16Array(buffer, start * 8, count);
  const out = new Float32Array(count);
  for (let k = 0; k < count; k++) out[k] = raw[k] / index.quant - 0.5;
  return out;
}

function flip(value, size, flipped) {
  return flipped ? size - 1 - value : value;
}

export function gridToScreen(grid, plane) {
  return {
    x: flip(grid[plane.h_axis], plane.width, plane.h_flip),
    y: flip(grid[plane.v_axis], plane.height, plane.v_flip),
    slice: grid[plane.axis],
  };
}

export function screenToGrid(x, y, slice, plane, shape) {
  const grid = [0, 0, 0];
  grid[plane.axis] = slice;
  grid[plane.h_axis] = clampSlice(flip(x, plane.width, plane.h_flip), shape[plane.h_axis]);
  grid[plane.v_axis] = clampSlice(flip(y, plane.height, plane.v_flip), shape[plane.v_axis]);
  return grid;
}

export function clampSlice(i, n) {
  return Math.min(n - 1, Math.max(0, Math.round(i)));
}

// Where the other two planes cut this view.
export function crosshairs(cursor, plane) {
  const {x, y} = gridToScreen(cursor, plane);
  return {x, y};
}

export function initialCursor(shape) {
  return shape.map((n) => Math.floor(n / 2));
}

export function fit(viewW, viewH, imgW, imgH) {
  const scale = Math.min(viewW / imgW, viewH / imgH);
  return {scale, dx: (viewW - imgW * scale) / 2, dy: (viewH - imgH * scale) / 2};
}

// Zoom by `factor`, keeping the image point under (px, py) under it.
export function zoomAt(view, factor, px, py) {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
  const ratio = scale / view.scale;
  return {scale, dx: px - (px - view.dx) * ratio, dy: py - (py - view.dy) * ratio};
}

// The "hold to hide surfaces" key: the physical S key, not cmd/ctrl/alt + S.
export function isHideKey(event) {
  return event.code === "KeyS" && !event.metaKey && !event.ctrlKey && !event.altKey;
}

// Screen coordinates of one finding's voxels that lie on a slice of a plane.
export function findingVoxelsOnSlice(voxels, finding, plane, slice) {
  const out = [];
  const end = (finding.voxel_start + finding.voxel_count) * 3;
  for (let k = finding.voxel_start * 3; k < end; k += 3) {
    if (voxels[k + plane.axis] !== slice) continue;
    const grid = [voxels[k], voxels[k + 1], voxels[k + 2]];
    const {x, y} = gridToScreen(grid, plane);
    out.push([x, y]);
  }
  return out;
}

// After the canvas changes size: same zoom, same image point at the centre.
export function resizeView(view, oldW, oldH, newW, newH) {
  return {scale: view.scale, dx: view.dx + (newW - oldW) / 2, dy: view.dy + (newH - oldH) / 2};
}

// A view centred on screen point (x, y) showing fieldMm across the smaller canvas dimension.
// Returns null for a canvas with no size (a hidden view), which cannot be zoomed.
export function zoomTo(viewW, viewH, plane, pixel, x, y, fieldMm) {
  if (viewW <= 0 || viewH <= 0) return null;
  const scale = Math.min(viewW, viewH) / fieldMm;
  return {
    scale,
    dx: viewW / 2 - (x + 0.5) * pixel.h * scale,
    dy: viewH / 2 - (y + 0.5) * pixel.v * scale,
  };
}

// Next position in a list of n items; no wrapping; from "nothing selected" start at either end.
export function stepIndex(current, delta, n) {
  if (n === 0) return null;
  if (current === null) return delta > 0 ? 0 : n - 1;
  return Math.min(n - 1, Math.max(0, current + delta));
}

const PLANE_NAMES = ["coronal", "sagittal", "axial"];

// Which views a layout shows: "three" (or anything unknown) shows all, otherwise the one named.
export function visiblePlanes(layout) {
  return PLANE_NAMES.includes(layout) ? [layout] : [...PLANE_NAMES];
}

// The box, in screen pixels, around every contour of a plane (all surfaces, all slices),
// or null when there are none.
export function contourBounds(buffer, index) {
  const raw = new Uint16Array(buffer);
  if (raw.length === 0) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let k = 0; k < raw.length; k += 2) {
    const x = raw[k], y = raw[k + 1];
    if (x < x0) x0 = x;
    if (x > x1) x1 = x;
    if (y < y0) y0 = y;
    if (y > y1) y1 = y;
  }
  const toPixel = (value) => value / index.quant - 0.5;
  return {x0: toPixel(x0), y0: toPixel(y0), x1: toPixel(x1), y1: toPixel(y1)};
}

// A view that fills the canvas with a box of image pixels, leaving `pad` (a fraction of
// the box) free on every side. Null for a canvas with no size.
export function fitBox(viewW, viewH, pixel, box, pad) {
  if (viewW <= 0 || viewH <= 0) return null;
  const width = (box.x1 - box.x0 + 1) * pixel.h * (1 + 2 * pad);
  const height = (box.y1 - box.y0 + 1) * pixel.v * (1 + 2 * pad);
  const scale = Math.min(viewW / width, viewH / height);
  return {
    scale,
    dx: viewW / 2 - ((box.x0 + box.x1) / 2 + 0.5) * pixel.h * scale,
    dy: viewH / 2 - ((box.y0 + box.y1) / 2 + 0.5) * pixel.v * scale,
  };
}

// ---- reviewing ----

// Nearest point to (x, y) on one segment a-b, with distances in mm.
function nearestOnSegment(ax, ay, bx, by, x, y, pixel) {
  const ux = (bx - ax) * pixel.h, uy = (by - ay) * pixel.v;
  const wx = (x - ax) * pixel.h, wy = (y - ay) * pixel.v;
  const length2 = ux * ux + uy * uy;
  const t = length2 === 0 ? 0 : Math.min(1, Math.max(0, (wx * ux + wy * uy) / length2));
  const px = ax + t * (bx - ax), py = ay + t * (by - ay);
  return {x: px, y: py, dist: Math.hypot((x - px) * pixel.h, (y - py) * pixel.v)};
}

// The point on the drawn contours nearest (x, y), with its surface, or null when none lies
// within maxDist mm. segmentsBySurface: {name: [x1, y1, x2, y2, ...]} in image pixels.
export function nearestOnContours(segmentsBySurface, x, y, maxDist, pixel = {h: 1, v: 1}) {
  let best = null;
  for (const [surface, seg] of Object.entries(segmentsBySurface)) {
    for (let k = 0; k + 3 < seg.length; k += 4) {
      const hit = nearestOnSegment(seg[k], seg[k + 1], seg[k + 2], seg[k + 3], x, y, pixel);
      if (hit.dist <= maxDist && (best === null || hit.dist < best.dist)) best = {...hit, surface};
    }
  }
  return best;
}

// Like screenToGrid, but keeps the position between voxels: a mark sits on the contour.
export function screenToGridExact(x, y, slice, plane) {
  const grid = [0, 0, 0];
  grid[plane.axis] = slice;
  grid[plane.h_axis] = flip(x, plane.width, plane.h_flip);
  grid[plane.v_axis] = flip(y, plane.height, plane.v_flip);
  return grid;
}

// The marks within `reach` slices of a slice of a plane.
export function marksOnSlice(marks, plane, slice, reach) {
  return marks.filter((mark) => Math.abs(Math.round(mark.grid[plane.axis]) - slice) <= reach);
}

// How many things are still to do before a review can be submitted (marks not counted).
export function itemsRemaining(review, itemIds) {
  if (review.unratable && review.unratable.trim()) return 0;
  const unrated = itemIds.filter((id) => !review.items[id] || review.items[id].rating === null);
  return unrated.length + (review.grade ? 0 : 1);
}

// The level of a scale chosen by a number key, or null.
export function levelForKey(key, scale) {
  const level = scale.find((entry) => entry.key === key);
  return level ? level.id : null;
}

// Next checklist item; stops at the ends; from "none" starts at the first.
export function stepItem(current, delta, n) {
  if (n === 0) return null;
  if (current === null) return 0;
  return Math.min(n - 1, Math.max(0, current + delta));
}

// True when the keys pressed are text for this element. A rating button, tick box or slider
// that was clicked keeps the focus, and the keys must go on working as shortcuts there.
export function isTyping(target) {
  if (target.tagName === "TEXTAREA" || target.tagName === "SELECT") return true;
  return target.tagName === "INPUT" && !["radio", "checkbox", "range", "button"].includes(target.type);
}

// ---- linking two viewers ------------------------------------------------------------------

// A point through a 4x4 matrix given as rows (the last row is 0, 0, 0, 1).
export function applyAffine(m, p) {
  return [0, 1, 2].map((r) => m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3]);
}

// The inverse of such a matrix, or null when there is none.
export function invertAffine(m) {
  if (!Array.isArray(m)) return null;
  const [[a, b, c], [d, e, f], [g, h, i]] = m;
  const det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  if (!Number.isFinite(det) || Math.abs(det) < 1e-12) return null;
  const inv = [
    [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
    [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
    [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
  ];
  const shift = [m[0][3], m[1][3], m[2][3]];
  const rows = inv.map((row) => [...row, -(row[0] * shift[0] + row[1] * shift[1] + row[2] * shift[2])]);
  return [...rows, [0, 0, 0, 1]];
}

const POSITION = "surfaceqa:position";

// What one viewer tells the other: where its cursor is, in scanner coordinates when the run
// has them and in surface (tkr) coordinates, and which views it shows.
export function positionMessage(cursor, meta, layout) {
  const scanner = meta.grid_to_scanner ? applyAffine(meta.grid_to_scanner, cursor) : null;
  return {type: POSITION, scanner, tkr: applyAffine(meta.grid_to_tkr, cursor), layout};
}

function isPoint(p) {
  return Array.isArray(p) && p.length === 3 && p.every((v) => typeof v === "number" && Number.isFinite(v));
}

// The voxel of this run at the position another viewer sent, or null when the message is not
// a usable position. Scanner coordinates are used when both runs have them; an earlier run
// without them is assumed to share the surface coordinates of the run it is compared with.
export function cursorFromMessage(message, meta) {
  if (!message || message.type !== POSITION) return null;
  const byScanner = isPoint(message.scanner) && meta.grid_to_scanner;
  const point = byScanner ? message.scanner : message.tkr;
  const toGrid = invertAffine(byScanner ? meta.grid_to_scanner : meta.grid_to_tkr);
  if (!isPoint(point) || !toGrid) return null;
  return applyAffine(toGrid, point).map(Math.round);
}

// The name a review page gives itself when it opens, so the server can tell this page's
// saves from those of another window. (crypto.randomUUID needs https; this does not.)
export function writerId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

// How long to wait before trying a failed save again: 2 s, doubling, at most 30 s.
export function retryDelay(failures) {
  return Math.min(30000, 1000 * 2 ** Math.min(failures, 10));
}
