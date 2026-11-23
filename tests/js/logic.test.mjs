import test from "node:test";
import assert from "node:assert/strict";
import {
  sliceSegments, gridToScreen, screenToGrid, clampSlice, crosshairs, initialCursor, fit, zoomAt,
  isHideKey,
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
