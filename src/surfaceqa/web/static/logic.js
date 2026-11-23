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

// `count` slice indices evenly spaced strictly inside first..last (all of them if there are few).
export function montageSlices(n, count, first = 0, last = n - 1) {
  const span = last - first + 1;
  if (span <= count) return Array.from({length: span}, (_, i) => first + i);
  return Array.from({length: count}, (_, i) => first + Math.round(((i + 1) * (span - 1)) / (count + 1)));
}

// First and last slice on which any surface has a contour, or null if there are none.
export function surfaceSliceRange(index) {
  let first = Infinity;
  let last = -Infinity;
  for (const offsets of Object.values(index.surfaces)) {
    for (let i = 0; i + 1 < offsets.length; i++) {
      if (offsets[i + 1] > offsets[i]) {
        first = Math.min(first, i);
        last = Math.max(last, i);
      }
    }
  }
  return last < first ? null : [first, last];
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
