import test from "node:test";
import assert from "node:assert/strict";
import {
  sliceSegments, gridToScreen, screenToGrid, clampSlice, crosshairs, initialCursor, fit, zoomAt,
  isHideKey, findingVoxelsOnSlice, zoomTo, resizeView, stepIndex, visiblePlanes, contourBounds, fitBox,
} from "../../src/surfaceqa/web/static/logic.js";

const coronal = {axis: 1, h_axis: 0, v_axis: 2, h_flip: true, v_flip: true, width: 32, height: 40, n_slices: 48};
const sagittal = {axis: 0, h_axis: 1, v_axis: 2, h_flip: false, v_flip: true, width: 48, height: 40, n_slices: 32};
const shape = [32, 48, 40];

test("sliceSegments decodes quantized uint16", () => {
  const u = new Uint16Array([32, 32, 96, 160, 672, 32, 32, 32]); // (c + 0.5) * 64
  const index = {quant: 64, surfaces: {"lh.pial": [0, 1, 2], "rh.pial": [2, 2, 2]}};
  assert.deepEqual([...sliceSegments(u.buffer, index, "lh.pial", 0)], [0, 0, 1, 2]);
  assert.deepEqual([...sliceSegments(u.buffer, index, "lh.pial", 1)], [10, 0, 0, 0]);
  assert.equal(sliceSegments(u.buffer, index, "rh.pial", 1).length, 0);
});

test("gridToScreen applies flips", () => {
  assert.deepEqual(gridToScreen([3, 24, 39], coronal), {x: 28, y: 0, slice: 24});
  assert.deepEqual(gridToScreen([3, 24, 39], sagittal), {x: 24, y: 0, slice: 3});
});

test("screenToGrid inverts gridToScreen", () => {
  assert.deepEqual(screenToGrid(28, 0, 24, coronal, shape), [3, 24, 39]);
  assert.deepEqual(screenToGrid(24, 0, 3, sagittal, shape), [3, 24, 39]);
});

test("clampSlice", () => {
  assert.equal(clampSlice(-3, 48), 0);
  assert.equal(clampSlice(99, 48), 47);
  assert.equal(clampSlice(7.6, 48), 8);
});

test("crosshairs show the other two planes", () => {
  assert.deepEqual(crosshairs([3, 24, 39], coronal), {x: 28, y: 0});
});

test("initialCursor is the centre", () => {
  assert.deepEqual(initialCursor(shape), [16, 24, 20]);
});

test("fit centres the image", () => {
  assert.deepEqual(fit(640, 400, 32, 40), {scale: 10, dx: 160, dy: 0});
});

test("zoomAt keeps the pointed pixel fixed", () => {
  const v = zoomAt({scale: 10, dx: 160, dy: 0}, 2, 200, 100);
  assert.equal(v.scale, 20);
  assert.equal((200 - v.dx) / v.scale, (200 - 160) / 10);
  assert.equal(zoomAt({scale: 20, dx: 0, dy: 0}, 4, 0, 0).scale, 32);
});

test("isHideKey is the plain s key only", () => {
  assert.equal(isHideKey({code: "KeyS", key: "s"}), true);
  assert.equal(isHideKey({code: "KeyS", key: "S", shiftKey: true}), true); // releasing with shift still counts
  assert.equal(isHideKey({code: "KeyS", key: "s", metaKey: true}), false); // cmd+s is not "hide"
  assert.equal(isHideKey({code: "KeyS", key: "s", ctrlKey: true}), false);
  assert.equal(isHideKey({code: "KeyA", key: "a"}), false);
});

test("findingVoxelsOnSlice picks the voxels on the slice, in screen coordinates", () => {
  const voxels = new Uint16Array([3, 24, 39, 4, 24, 39, 3, 25, 39, 9, 9, 9]);
  assert.deepEqual(findingVoxelsOnSlice(voxels, {voxel_start: 0, voxel_count: 3}, coronal, 24), [[28, 0], [27, 0]]);
  assert.deepEqual(findingVoxelsOnSlice(voxels, {voxel_start: 3, voxel_count: 1}, coronal, 24), []);
});

test("zoomTo centres the point and sets the field of view", () => {
  const v = zoomTo(600, 400, coronal, {h: 0.8, v: 0.8}, 10, 20, 50);
  assert.equal(v.scale, 8); // 400 px / 50 mm
  assert.equal(v.dx + (10 + 0.5) * 0.8 * v.scale, 300);
  assert.equal(v.dy + (20 + 0.5) * 0.8 * v.scale, 200);
});

test("resizeView keeps the same image point at the centre and the same zoom", () => {
  const v = resizeView({scale: 8, dx: 100, dy: 40}, 600, 400, 800, 300);
  assert.equal(v.scale, 8);
  assert.equal((400 - v.dx) / 8, (300 - 100) / 8); // image point at the new centre = at the old centre
  assert.equal((150 - v.dy) / 8, (200 - 40) / 8);
});

test("zoomTo refuses a canvas with no size (a hidden view)", () => {
  assert.equal(zoomTo(0, 0, coronal, {h: 1, v: 1}, 10, 20, 50), null);
});

test("stepIndex moves through a list without wrapping, starting from either end", () => {
  assert.equal(stepIndex(null, 1, 5), 0);
  assert.equal(stepIndex(null, -1, 5), 4);
  assert.equal(stepIndex(2, 1, 5), 3);
  assert.equal(stepIndex(4, 1, 5), 4);
  assert.equal(stepIndex(0, -1, 5), 0);
  assert.equal(stepIndex(null, 1, 0), null);
});

test("visiblePlanes: all three, or the one chosen", () => {
  assert.deepEqual(visiblePlanes("three"), ["coronal", "sagittal", "axial"]);
  assert.deepEqual(visiblePlanes("sagittal"), ["sagittal"]);
  assert.deepEqual(visiblePlanes("nonsense"), ["coronal", "sagittal", "axial"]);
});

test("contourBounds is the box around every contour of a plane", () => {
  const q = (c) => (c + 0.5) * 64;
  const u = new Uint16Array([q(10), q(20), q(12), q(22), q(29), q(39), q(25), q(30)]);
  const index = {quant: 64, surfaces: {"lh.pial": [0, 1, 1], "rh.white": [1, 1, 2]}};
  assert.deepEqual(contourBounds(u.buffer, index), {x0: 10, y0: 20, x1: 29, y1: 39});
  assert.equal(contourBounds(new ArrayBuffer(0), {quant: 64, surfaces: {"lh.pial": [0, 0]}}), null);
});

test("fitBox fills the view with a box, centred, with padding", () => {
  const tight = fitBox(600, 400, {h: 1, v: 1}, {x0: 10, y0: 20, x1: 29, y1: 39}, 0);
  assert.equal(tight.scale, 20); // a 20 mm box in the 400 px dimension
  assert.equal(tight.dx + (19.5 + 0.5) * tight.scale, 300); // box centre at the view centre
  assert.equal(tight.dy + (29.5 + 0.5) * tight.scale, 200);
  const padded = fitBox(600, 400, {h: 1, v: 1}, {x0: 10, y0: 20, x1: 29, y1: 39}, 0.125);
  assert.equal(padded.scale, 16); // 12.5% of the box left free on every side
  assert.equal(fitBox(0, 400, {h: 1, v: 1}, {x0: 0, y0: 0, x1: 1, y1: 1}, 0), null);
});
