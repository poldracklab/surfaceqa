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
