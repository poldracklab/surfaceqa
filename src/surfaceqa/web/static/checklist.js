// The checklist beside the viewer: locations to jump to, and the whole-brain passes.
import * as L from "./logic.js";

const ZOOM_MM = 60;

const sidebar = document.getElementById("checklist");
const spots = [...sidebar.querySelectorAll(".spot[data-grid]")];
let current = null; // index into spots

function select(viewer, index) {
  if (index === null) return;
  current = index;
  const button = spots[index];
  sidebar.querySelectorAll("[data-scroll]").forEach((b) => b.classList.remove("active"));
  spots.forEach((spot) => spot.classList.toggle("active", spot === button));
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

// The whole-brain passes: one large coronal view to scroll from end to end. The plane can
// be switched in the toolbar. The T1 pass hides the surfaces so the image itself is judged.
function bindScrollPasses(viewer) {
  for (const button of sidebar.querySelectorAll("[data-scroll]")) {
    button.addEventListener("click", () => {
      spots.forEach((spot) => spot.classList.remove("active"));
      sidebar.querySelectorAll("[data-scroll]").forEach((b) => b.classList.toggle("active", b === button));
      current = null;
      viewer.setHighlight(null);
      viewer.setSurfaces(button.dataset.scroll === "contours");
      viewer.setLayout("coronal", {fit: true});
    });
  }
}

async function start() {
  const viewer = window.surfaceqaViewer;
  if (!viewer) return;
  await viewer.ready;
  bindSpots(viewer);
  bindScrollPasses(viewer);
}

start().catch((error) => console.warn("surfaceqa: the checklist could not start", error));
