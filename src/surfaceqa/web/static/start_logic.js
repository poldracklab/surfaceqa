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
