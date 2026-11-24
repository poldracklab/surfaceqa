// The start page: browse to a folder, see what a build of it would do.
import {crumbs, folderLabel, planMessage, planQuery} from "./start_logic.js";

const $ = (id) => document.getElementById(id);
const source = $("source"), out = $("out"), chosen = $("chosen");
let planTimer = null;

function link(text, onClick) {
  const a = document.createElement("a");
  a.href = "#";
  a.textContent = text;
  a.addEventListener("click", (event) => { event.preventDefault(); onClick(); });
  return a;
}

function item(node) {
  const li = document.createElement("li");
  li.append(node);
  return li;
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

function showCrumbs(path) {
  const parts = crumbs(path).flatMap((c, i) => [i > 1 ? " / " : " ", link(c.name, () => browse(c.path))]);
  $("crumbs").replaceChildren(link("Places", showPlaces), " ▸", ...parts);
}

function showListing(listing) {
  showCrumbs(listing.path);
  $("folders").replaceChildren(...listing.folders.map((f) => item(link(folderLabel(f), () => browse(f.path)))));
  const none = listing.folders.length ? "" : "No folders in here.";
  $("browser-note").textContent = listing.error || (listing.truncated ? "Only the first 500 folders are shown." : none);
}

async function browse(path) {
  source.value = path;
  schedulePlan();
  try {
    showListing(await getJson(`/start/folders?path=${encodeURIComponent(path)}`));
  } catch {
    $("browser-note").textContent = "The folder could not be listed.";
  }
}

async function showPlaces() {
  const {places} = await getJson("/start/folders");
  $("crumbs").replaceChildren("Places");
  $("folders").replaceChildren(...places.map((p) => item(link(p.name === "Home" ? `Home (${p.path})` : p.path, () => browse(p.path)))));
  $("browser-note").textContent = "";
}

function sources() {
  const added = [...chosen.querySelectorAll("input")].map((input) => input.value);
  return source.value.trim() ? [...added, source.value.trim()] : added;
}

async function showPlan() {
  if (!sources().length) { $("plan").textContent = ""; return; }
  try {
    const plan = await getJson(`/start/plan?${planQuery(sources(), out.value.trim())}`);
    $("plan").textContent = planMessage(plan);
    $("plan").classList.toggle("error", Boolean(plan.error));
  } catch {
    $("plan").textContent = "";
  }
}

function schedulePlan() {
  clearTimeout(planTimer);
  planTimer = setTimeout(showPlan, 300);
}

function addFolder() {
  const path = source.value.trim();
  if (!path) return;
  const hidden = Object.assign(document.createElement("input"), {type: "hidden", name: "source", value: path});
  const li = item(hidden);
  li.append(`${path} `, link("remove", () => { li.remove(); schedulePlan(); }));
  chosen.append(li);
  source.value = "";
  schedulePlan();
}

source.addEventListener("input", schedulePlan);
out.addEventListener("input", schedulePlan);
$("add").addEventListener("click", addFolder);
$("add").hidden = false;
$("browser").hidden = false;
showPlaces();
