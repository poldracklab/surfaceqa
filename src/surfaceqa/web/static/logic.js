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
