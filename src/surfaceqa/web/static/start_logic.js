// What the start page says, kept apart from the page so it can be tested without a browser.

export function crumbs(path) {
  const names = path.split("/").filter(Boolean);
  return [{name: "/", path: "/"}, ...names.map((name, i) => ({name, path: "/" + names.slice(0, i + 1).join("/")}))];
}

function count(n) {
  return `${n} subject${n === 1 ? "" : "s"}`;
}

export function folderLabel(entry) {
  if (entry.subject) return `${entry.name} — a subject`;
  return entry.n_subjects ? `${entry.name} — ${count(entry.n_subjects)}` : entry.name;
}

export function planMessage(plan) {
  if (plan.error) return plan.error;
  return plan.adds
    ? `${count(plan.n_subjects)} will be added to the QA directory that is already in ${plan.out}`
    : `${count(plan.n_subjects)} will be built into ${plan.out}`;
}

export function planQuery(sources, out) {
  const query = new URLSearchParams();
  for (const source of sources) query.append("source", source);
  query.append("out", out);
  return query.toString();
}

const STAGES = {
  render: (s) => `Rendering: ${s.done} of ${count(s.total)} done`,
  cohort: () => "Comparing the subjects with each other",
  indicators: (s) => `Computing indicators: ${s.done} of ${count(s.total)} done`,
};

function finished(status) {
  const failed = (status.problems || []).length;
  const cohort = status.cohort_failed ? " The comparison across subjects failed." : "";
  return failed
    ? `Finished, but ${failed} of ${count(status.total)} could not be built.${cohort}`
    : `Finished: ${count(status.total)}.${cohort}`;
}

export function progressText(status) {
  switch (status.state) {
    case "running": return STAGES[status.stage] ? STAGES[status.stage](status) : "Starting…";
    case "done": return finished(status);
    case "cancelled":
      return "Cancelled. Subjects that were finished are kept; building the same folder again continues from there.";
    case "stopped": return "The build stopped before it finished.";
    default: return "No build is running.";
  }
}

// Rendering is most of the work; the comparison is brief; the indicators are the rest.
export function progressFraction(status) {
  if (status.state === "done") return 1;
  const part = status.total ? status.done / status.total : 0;
  const at = {render: 0.6 * part, cohort: 0.6, indicators: 0.6 + 0.4 * part}[status.stage] ?? 0;
  return Math.round(at * 1000) / 1000;
}

export function shouldLeave(status) {
  return status.state === "done" && !(status.problems || []).length && !status.cohort_failed;
}

export function pollDelay(status) {
  return status.state === "running" ? 1000 : null;
}
