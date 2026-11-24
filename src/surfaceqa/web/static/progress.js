// The build progress page: ask how far the build is, once a second, until it ends.
import {progressText, progressFraction, shouldLeave, pollDelay} from "./start_logic.js";

const $ = (id) => document.getElementById(id);

function showProblems(problems) {
  $("problems").replaceChildren(...problems.map((p) => {
    const li = document.createElement("li");
    li.textContent = `${p.key}: ${p.reason}`;
    return li;
  }));
}

function show(status) {
  $("state").textContent = progressText(status);
  $("bar").value = progressFraction(status);
  $("bar").hidden = status.state !== "running";
  $("cancel").hidden = status.state !== "running";
  $("open").hidden = status.state === "running" || !status.openable;
  showProblems(status.problems || []);
  $("log").hidden = !(status.log_tail || []).length;
  $("log").textContent = (status.log_tail || []).join("\n");
}

async function poll() {
  let status;
  try {
    status = await (await fetch("/start/status")).json();
  } catch {
    $("state").textContent = "surfaceqa is not answering; it may have been closed.";
    setTimeout(poll, 3000);
    return;
  }
  show(status);
  if (shouldLeave(status)) { location.href = "/"; return; }
  const delay = pollDelay(status);
  if (delay !== null) setTimeout(poll, delay);
}

poll();
