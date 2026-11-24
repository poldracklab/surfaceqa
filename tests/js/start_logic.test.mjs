import test from "node:test";
import assert from "node:assert/strict";
import {crumbs, folderLabel, planMessage, planQuery} from "../../src/surfaceqa/web/static/start_logic.js";

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
