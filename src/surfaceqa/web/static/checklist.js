// The checklist below the viewer: jump-to buttons and the two slice montages.
import * as L from "./logic.js";

const TILES = 20;
const TILE_WIDTH = 150;
const ZOOM_MM = 60;

function parseGrid(text) {
  return text.split(",").map(Number);
}

function bindSpots(viewer) {
  for (const button of document.querySelectorAll("#checklist .spot")) {
    button.addEventListener("click", () => {
      const finding = button.dataset.finding;
      viewer.setHighlight(finding === undefined ? null : Number(finding));
      viewer.goTo(parseGrid(button.dataset.grid), {zoomMm: ZOOM_MM});
    });
  }
}

function drawTileContours(ctx, data, plane, slice, scaleX, scaleY) {
  const contours = data.contours.coronal;
  for (const [name, style] of Object.entries(data.meta.surfaces)) {
    const seg = L.sliceSegments(contours.buffer, contours.index, name, slice);
    ctx.beginPath();
    for (let k = 0; k < seg.length; k += 4) {
      ctx.moveTo((seg[k] + 0.5) * scaleX, (seg[k + 1] + 0.5) * scaleY);
      ctx.lineTo((seg[k + 2] + 0.5) * scaleX, (seg[k + 3] + 0.5) * scaleY);
    }
    ctx.strokeStyle = style.color;
    ctx.lineWidth = 1;
    ctx.stroke();
  }
}

function makeTile(data, viewer, slice, withContours) {
  const plane = data.meta.planes.coronal;
  const vox = data.meta.voxel_sizes;
  const dpr = window.devicePixelRatio || 1;
  const height = Math.round(TILE_WIDTH * (plane.height * vox[plane.v_axis]) / (plane.width * vox[plane.h_axis]));
  const canvas = document.createElement("canvas");
  canvas.width = TILE_WIDTH * dpr;
  canvas.height = height * dpr;
  canvas.style.width = `${TILE_WIDTH}px`;
  canvas.style.height = `${height}px`;
  canvas.title = `coronal slice ${slice + 1}`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const img = new Image();
  img.onload = () => {
    ctx.drawImage(img, 0, 0, TILE_WIDTH, height);
    if (withContours) drawTileContours(ctx, data, plane, slice, TILE_WIDTH / plane.width, height / plane.height);
  };
  img.src = data.sliceUrl("coronal", slice);
  canvas.addEventListener("click", () => viewer.goToSlice("coronal", slice));
  return canvas;
}

function fillMontages(data, viewer) {
  const n = data.meta.planes.coronal.n_slices;
  const range = L.surfaceSliceRange(data.contours.coronal.index) || [0, n - 1];
  const slices = L.montageSlices(n, TILES, range[0], range[1]);
  for (const box of document.querySelectorAll("#checklist .montage")) {
    const withContours = box.dataset.contours === "1";
    for (const slice of slices) box.append(makeTile(data, viewer, slice, withContours));
  }
}

async function start() {
  const viewer = window.surfaceqaViewer;
  if (!viewer) return;
  const data = await viewer.ready;
  bindSpots(viewer);
  fillMontages(data, viewer);
}

start();
