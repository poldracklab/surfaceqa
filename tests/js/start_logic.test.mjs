import test from "node:test";
import assert from "node:assert/strict";
import {crumbs, folderLabel, planMessage, planQuery, progressText, progressFraction, shouldLeave, pollDelay} from "../../src/surfaceqa/web/static/start_logic.js";

test("crumbs split a path into the folders above it", () => {
  assert.deepEqual(crumbs("/Volumes/data/study"), [
    {name: "/", path: "/"}, {name: "Volumes", path: "/Volumes"},
    {name: "data", path: "/Volumes/data"}, {name: "study", path: "/Volumes/data/study"}]);
  assert.deepEqual(crumbs("/"), [{name: "/", path: "/"}]);
  assert.deepEqual(crumbs("/a/"), [{name: "/", path: "/"}, {name: "a", path: "/a"}]);
});

test("a folder says what it holds", () => {
  assert.equal(folderLabel({name: "sub-01", subject: true, n_subjects: 0}), "sub-01 — a subject");
  assert.equal(folderLabel({name: "study", subject: false, n_subjects: 12}), "study — 12 subjects");
  assert.equal(folderLabel({name: "one", subject: false, n_subjects: 1}), "one — 1 subject");
  assert.equal(folderLabel({name: "docs", subject: false, n_subjects: 0}), "docs");
});

test("the plan is said in a sentence", () => {
  assert.equal(planMessage({error: "No subject found", out: "", adds: false, n_subjects: 0}), "No subject found");
  assert.equal(planMessage({error: null, out: "/d/surfaceqa", adds: false, n_subjects: 46}),
    "46 subjects will be built into /d/surfaceqa");
  assert.equal(planMessage({error: null, out: "/d/surfaceqa", adds: true, n_subjects: 1}),
    "1 subject will be added to the QA directory that is already in /d/surfaceqa");
});

test("the plan query repeats the sources and escapes them", () => {
  assert.equal(planQuery(["/a b", "/c&d"], "/out"), "source=%2Fa+b&source=%2Fc%26d&out=%2Fout");
  assert.equal(planQuery([], ""), "out=");
});

const running = (stage, done, total) => ({state: "running", stage, done, total, problems: [], cohort_failed: false});

test("progress is said in words", () => {
  assert.equal(progressText({state: "none"}), "No build is running.");
  assert.equal(progressText(running(null, 0, 0)), "Starting…");
  assert.equal(progressText(running("render", 3, 46)), "Rendering: 3 of 46 subjects done");
  assert.equal(progressText(running("cohort", 0, 1)), "Comparing the subjects with each other");
  assert.equal(progressText(running("indicators", 1, 46)), "Computing indicators: 1 of 46 subjects done");
  assert.equal(progressText({state: "done", total: 46, problems: [], cohort_failed: false}), "Finished: 46 subjects.");
  assert.equal(progressText({state: "done", total: 1, problems: [], cohort_failed: false}), "Finished: 1 subject.");
  assert.equal(progressText({state: "done", total: 46, problems: [{}, {}], cohort_failed: false}),
    "Finished, but 2 of 46 subjects could not be built.");
  assert.equal(progressText({state: "done", total: 46, problems: [], cohort_failed: true}),
    "Finished: 46 subjects. The comparison across subjects failed.");
  assert.match(progressText({state: "cancelled"}), /^Cancelled\. Subjects that were finished are kept/);
  assert.equal(progressText({state: "stopped"}), "The build stopped before it finished.");
});

test("the bar fills over the three stages", () => {
  assert.equal(progressFraction(running(null, 0, 0)), 0);
  assert.equal(progressFraction(running("render", 0, 10)), 0);
  assert.equal(progressFraction(running("render", 5, 10)), 0.3);
  assert.equal(progressFraction(running("cohort", 0, 1)), 0.6);
  assert.equal(progressFraction(running("indicators", 5, 10)), 0.8);
  assert.equal(progressFraction({state: "done", total: 10}), 1);
});

test("the page leaves for the project only after a clean build", () => {
  assert.equal(shouldLeave({state: "done", problems: [], cohort_failed: false}), true);
  assert.equal(shouldLeave({state: "done", problems: [{}], cohort_failed: false}), false);
  assert.equal(shouldLeave({state: "done", problems: [], cohort_failed: true}), false);
  for (const state of ["running", "cancelled", "stopped", "none"]) {
    assert.equal(shouldLeave({state, problems: [], cohort_failed: false}), false);
  }
});

test("polling goes on only while the build runs", () => {
  assert.equal(pollDelay({state: "running"}), 1000);
  for (const state of ["done", "cancelled", "stopped", "none"]) assert.equal(pollDelay({state}), null);
});
