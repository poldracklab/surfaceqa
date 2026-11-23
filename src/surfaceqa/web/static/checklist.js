// The checklist beside the viewer: locations to jump to, and the whole-brain montage.
import * as L from "./logic.js";

const TILES = 20;
const TILE_PIXELS = 320;
const ZOOM_MM = 60;

const sidebar = document.getElementById("checklist");
const viewerRoot = document.getElementById("viewer");
const panels = viewerRoot.querySelector(".panels");
const montage = viewerRoot.querySelector(".montage");
const backButton = document.getElementById("back-to-views");
const spots = [...sidebar.querySelectorAll(".spot[data-grid]")];
let current = null; // index into spots

function showViews() {
  montage.hidden = true;
  panels.hidden = false;
  backButton.hidden = true;
}

function select(viewer, index) {
  if (index === null) return;
  current = index;
  const button = spots[index];
  spots.forEach((spot) => spot.classList.toggle("active", spot === button));
  showViews();
  const finding = button.dataset.finding;
  viewer.setHighlight(finding === undefined ? null : Number(finding));
  viewer.goTo(button.dataset.grid.split(",").map(Number), {zoomMm: ZOOM_MM});
  button.scrollIntoView({block: "nearest"});
}

function typing(event) {
  return ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) && event.target.type !== "checkbox";
}

function bindSpots(viewer) {
  spots.forEach((button, index) => button.addEventListener("click", () => select(viewer, index)));
  window.addEventListener("keydown", (event) => {
    if (typing(event) || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === "n") select(viewer, L.stepIndex(current, 1, spots.length));
    if (event.key === "p") select(viewer, L.stepIndex(current, -1, spots.length));
  });
}

function drawTileContours(ctx, data, slice, scaleX, scaleY) {
  const contours = data.contours.coronal;
  for (const [name, style] of Object.entries(data.meta.surfaces)) {
    const seg = L.sliceSegments(contours.buffer, contours.index, name, slice);
    ctx.beginPath();
    for (let k = 0; k < seg.length; k += 4) {
      ctx.moveTo((seg[k] + 0.5) * scaleX, (seg[k + 1] + 0.5) * scaleY);
      ctx.lineTo((seg[k + 2] + 0.5) * scaleX, (seg[k + 3] + 0.5) * scaleY);
    }
    ctx.strokeStyle = style.color;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
}

function makeTile(data, viewer, slice, withContours) {
  const plane = data.meta.planes.coronal;
  const vox = data.meta.voxel_sizes;
  const aspect = (plane.height * vox[plane.v_axis]) / (plane.width * vox[plane.h_axis]);
  const canvas = document.createElement("canvas");
  canvas.width = TILE_PIXELS;
  canvas.height = Math.round(TILE_PIXELS * aspect);
  canvas.title = `coronal slice ${slice + 1}`;
  const ctx = canvas.getContext("2d");
  const img = new Image();
  img.onload = () => {
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    if (withContours) drawTileContours(ctx, data, slice, canvas.width / plane.width, canvas.height / plane.height);
  };
  img.src = data.sliceUrl("coronal", slice);
  canvas.addEventListener("click", () => {
    showViews();
    viewer.goToSlice("coronal", slice);
  });
  return canvas;
}

// With surfaces: the slices that have surface. T1 only: the whole volume, face included.
function montageSlices(data, withContours) {
  const n = data.meta.planes.coronal.n_slices;
  const range = withContours ? L.surfaceSliceRange(data.contours.coronal.index) : null;
  return range ? L.montageSlices(n, TILES, range[0], range[1]) : L.montageSlices(n, TILES);
}

function showMontage(data, viewer, withContours) {
  montage.replaceChildren(...montageSlices(data, withContours).map(
    (slice) => makeTile(data, viewer, slice, withContours)));
  panels.hidden = true;
  montage.hidden = false;
  backButton.hidden = false;
}

function bindMontage(data, viewer) {
  for (const button of sidebar.querySelectorAll("[data-montage]")) {
    button.addEventListener("click", () => showMontage(data, viewer, button.dataset.montage === "contours"));
  }
  backButton.addEventListener("click", showViews);
}

async function start() {
  const viewer = window.surfaceqaViewer;
  if (!viewer) return;
  const data = await viewer.ready;
  bindSpots(viewer);
  bindMontage(data, viewer);
}

start().catch((error) => console.warn("surfaceqa: the checklist could not start", error));
