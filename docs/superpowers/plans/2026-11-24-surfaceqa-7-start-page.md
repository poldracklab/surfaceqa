# One-Command Start Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `uvx surfaceqa` starts a local server on an empty start page where a researcher picks a FreeSurfer/FastSurfer folder, watches it build, and reviews it.

**Architecture:** The existing FastAPI app gains a "start mode" (`create_app(None, start=StartMode(token))`): a second router with the start page, a folder browser, and build control, guarded by a launch token, a loopback `Host` check and a same-origin check. A build from the page is the existing `surfaceqa build` command run as a child process that writes its progress to a JSON file in the QA directory; the server only reads that file and can kill the process group. `serve` is untouched.

**Tech Stack:** Python 3.13, FastAPI/Starlette, Jinja2, vanilla JS modules (`node --test` through `tests/test_js.py`), pytest, uv.

**Spec:** `docs/superpowers/specs/2026-11-24-surfaceqa-start-page-design.md`

## Global Constraints

- `uv run` for every command; no code or imports in `__init__.py`.
- pytest, functions and fixtures; tests written, seen to fail, and committed before the implementation.
- Short functions; one responsibility per module.
- Nothing is ever written into a source folder.
- Start mode binds `127.0.0.1` only; there is no `--host` for it.
- `serve` offers no start page, folder browser or build route (404).
- The folder browser returns folder names only, never file names.
- State outside QA directories: only `recent.json` in `$SURFACEQA_HOME` (default `~/.surfaceqa`). Every test sets `SURFACEQA_HOME` to a temp folder (autouse fixture in `tests/conftest.py`).
- Commit messages end with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Review Focus

1. A request to a start-mode route with `Host: evil.example` or a cross-site `Origin`, or without the token cookie → refused (403), for every start route including the folder listing. (Task 5)
2. A build killed mid-way (Cancel, or the process dying) → no half-written `current.json`, `settings.json`, cohort file or status file; the page says "stopped", not "running" forever. (Tasks 1, 4)
3. Output location inside a source, a non-empty folder that is not a QA directory, or an unwritable place → refused with a message, nothing created. (Task 3)
4. Folder browser given a path that does not exist, is a file, cannot be read, or contains thousands of entries / symlink loops → an error message or a listing, never a traceback or a hang. (Task 3)
5. A second build of the same QA directory (second instance, or command line) while one runs → refused; a lock left by a dead process does not block. (Task 2)

---

### Task 1: Settings keep everything; source record; whole-file writes

**Files:**
- Modify: `src/surfaceqa/layout.py`, `src/surfaceqa/settings.py`, `src/surfaceqa/cli.py`, `src/surfaceqa/build.py` (writer of `current.json`), `src/surfaceqa/cohort.py`, `src/surfaceqa/report.py` (use the shared helper)
- Test: `tests/test_settings.py`, `tests/test_layout.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `layout.replace_text(path: Path, text: str) -> None` (temp file in the same folder + `os.replace`; moved from `report._replace`); `settings.save_sources(qa_dir, paths: list[Path]) -> None` (adds, keeps order, no duplicates, stores resolved strings under `"sources"`); `settings.sources(qa_dir) -> list[Path]`.

- [ ] Tests (fail first): `save_rerun_template` after `save_sources` keeps the sources and the reverse; `save_sources` twice with an overlapping list keeps one entry each; `sources` of a directory without settings or with junk is `[]`; `replace_text` leaves no temp file and, when the write raises (monkeypatched `os.replace`), leaves the old content; `surfaceqa build` records the source paths as given by the user (a single-subject source records the subject folder, so a later check builds only it).
- [ ] Run `uv run pytest tests/test_settings.py tests/test_layout.py tests/test_cli.py -q` → the new tests FAIL.
- [ ] Commit tests.
- [ ] Implement. `current.json`, `settings.json`, cohort `.json`/`.npz` and the report use `replace_text` (or the same pattern for binary).
- [ ] Run the whole suite → PASS. Commit.

### Task 2: Build progress, build lock, `--progress`

**Files:**
- Create: `src/surfaceqa/lock.py`, `src/surfaceqa/progress.py`
- Modify: `src/surfaceqa/build.py`, `src/surfaceqa/cli.py`
- Test: `tests/test_lock.py`, `tests/test_progress.py`, `tests/test_build.py`, `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `build_all(refs, qa_dir, jobs=1, progress: Callable[[str, int, int], None] | None = None)`; called as `progress(stage, done, total)` with stage `"render" | "cohort" | "indicators"`, once at 0 and after each subject (cohort: 0/1 then 1/1). Results unchanged.
  - `lock.build_lock(qa_dir) -> ContextManager` writing `<qa>/build.lock` = `{"pid": int}`; raises `lock.Busy` when the lock's process is alive; a lock of a dead pid is replaced; removed on exit.
  - `lock.building(qa_dir) -> bool`.
  - `progress.STATUS_FILE = "build_status.json"`; `progress.write(qa_dir, **fields)`; `progress.read(qa_dir) -> dict | None`. Fields: `state` (`"running" | "done"`), `stage`, `done`, `total`, `pid`, `problems` (list of `{"key", "status", "reason"}`, reason = last non-empty line of `error.txt`, or the missing files), `cohort_failed` (bool).
  - CLI: `build --progress` (flag): takes the lock, writes the status file through the callback and a final `state: "done"` with `problems`. Without the flag `build` still takes the lock; `Busy` → exit 1 with "a build of this QA directory is already running".
  - `cli.py` gets `if __name__ == "__main__": sys.exit(main())`.

- [ ] Tests (fail first): callback sequence for a 2-subject build with `jobs=1` and `jobs=2` (same totals, monotonic `done`, the three stages in order); no callback → identical results to today; lock refused while held by a live pid (own pid), replaced when pid is dead, released after an exception; `build --progress` leaves `state == "done"`, `total == number of subjects`, and a failed subject (existing failing fixture) listed in `problems` with a one-line reason; a second `build` under a held lock exits 1 and builds nothing.
- [ ] Run → FAIL. Commit tests.
- [ ] Implement. With a pool, iterate `pool.map` lazily and call back in the parent.
- [ ] Whole suite → PASS. Commit.

### Task 3: Start-page logic without a server

**Files:**
- Create: `src/surfaceqa/recent.py`, `src/surfaceqa/start.py`
- Modify: `tests/conftest.py` (autouse `SURFACEQA_HOME`)
- Test: `tests/test_recent.py`, `tests/test_start.py`

**Interfaces:**
- Consumes: `discover.is_subject`, `discover.source_root`, `settings.sources`, `build.load_meta`.
- Produces:
  - `recent.home() -> Path`; `recent.remember(qa_dir, now: datetime | None = None)`; `recent.forget(qa_dir)`; `recent.projects() -> list[dict]` newest first: `{"path", "opened", "exists", "sources": [names], "n_subjects"}`; at most 20 kept; a junk file reads as empty.
  - `start.is_qa_dir(path) -> bool` (has `subjects/`).
  - `start.describe(path) -> {"path", "name", "subject": bool, "n_subjects": int}` (direct children only).
  - `start.list_folders(path) -> {"path", "parent" | None, "folders": [describe…], "error": str | None}`: sub-folders sorted by name, hidden ones left out, files never listed, at most 500 (then `"truncated": True`); unreadable / missing / not a folder → `error`, empty list.
  - `start.places() -> list[dict]`: home, and each folder in `/Volumes` (macOS) or `/mnt`, `/media` when present.
  - `start.default_out(sources: list[Path]) -> Path`: `<root of first source>/../surfaceqa` if it exists as a QA directory or its parent is writable; otherwise `~/surfaceqa/<root name>`, with `-2`, `-3`… while that folder exists and `settings.sources` of it differs from these sources.
  - `start.check_request(sources: list[Path], out: Path) -> str | None`: message when a source is not a folder, holds no subject, `out` is inside a source root, `out` is a non-empty folder that is not a QA directory, or cannot be created/written (checked without creating it). `None` when fine.
  - `start.adds_to_existing(out) -> bool`.

- [ ] Tests (fail first), one per rule above, including: a folder with a file and a hidden folder lists neither; a symlink loop does not hang (`describe` looks one level down only); `default_out` beside a read-only parent (chmod, skipped when running as root) falls back to home; the `-2` rule; `check_request` creates nothing in any refused case; `recent` survives a corrupt file and drops the 21st entry.
- [ ] Run → FAIL. Commit tests. Implement. Suite → PASS. Commit.

### Task 4: Background build

**Files:**
- Create: `src/surfaceqa/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `python -m surfaceqa.cli build SOURCES --out OUT --jobs N --progress`, `progress.read`, `lock.building`.
- Produces:
  - `jobs.default_jobs() -> int` (`max(1, cpu_count // 2)`).
  - `jobs.start(sources: list[Path], out: Path, jobs: int) -> Job` (`Job` is a small dataclass: `out`, `process: subprocess.Popen`); child in its own session (`start_new_session=True`), output to `<out>/build.log`.
  - `jobs.status(job) -> dict`: the status file's fields plus `state` resolved as `"running"` (process alive), `"done"` (file says done), `"cancelled"` (after `cancel`), `"stopped"` (process ended without `done`; includes `log_tail`, last 5 lines of `build.log`).
  - `jobs.cancel(job) -> None`: kills the process group, waits, removes a lock left behind.

- [ ] Tests (fail first), on the synthetic sources: a started job reaches `done` with the right total and the QA directory then has `index.html`; `cancel` on a job slowed by an environment switch the worker honours only under test (`SURFACEQA_TEST_DELAY` seconds slept per subject in the progress callback of the CLI) ends as `cancelled`, leaves no `build.lock`, no live child, and every JSON file in the QA directory parses; building again afterwards completes; a job whose source vanishes before start ends as `stopped` with a log tail.
- [ ] Run → FAIL. Commit tests. Implement. Suite → PASS. Commit.

### Task 5: Start mode in the server: guard, start page, folder browser

**Files:**
- Create: `src/surfaceqa/server_start.py`, `src/surfaceqa/web/templates/start.html`, `src/surfaceqa/web/templates/token.html`, `src/surfaceqa/web/static/start.js`, `src/surfaceqa/web/static/start_logic.js`
- Modify: `src/surfaceqa/server.py`, `src/surfaceqa/site.py`
- Test: `tests/test_server_start.py`, `tests/js/start_logic.test.js`

**Interfaces:**
- Consumes: Tasks 3–4.
- Produces:
  - `server_start.StartMode(token: str)` (dataclass, also holds `job: Job | None`); `create_app(qa_dir: Path | None, blind=False, start: StartMode | None = None)`.
  - Guard (middleware, start mode only, all paths except `/static`): `Host` name must be `127.0.0.1` or `localhost` → else 403; `?token=` equal to the launch token sets cookie `surfaceqa_token` (HttpOnly, SameSite=Strict) and redirects to the same path without it; no valid cookie → 403 with `token.html` (a form to paste the token); `POST`/`PUT` with an `Origin` whose host differs from `Host` → 403. Token comparison with `secrets.compare_digest`.
  - No project open: any project route → 303 to `/start`. `/` → `/start`.
  - Routes: `GET /start` (page: recent projects, open by path, new data); `GET /start/folders?path=` → `start.list_folders` JSON (no path → `places`); `GET /start/plan?source=…&source=…&out=` → `{"out", "error", "adds", "n_subjects"}` (default out when `out` is empty); `POST /start/open` (form `path`) → checks `is_qa_dir`, writes the site if `index.html` is missing, remembers it, sets `app.state.qa_dir`, 303 `/`; `POST /start/forget`; `POST /start/build` (form `source` repeated, `out`) → `check_request`, refuse while a job runs, `jobs.start`, 303 `/start/progress`.
  - `start_logic.js`: pure helpers (`crumbs(path)`, `folderLabel(entry)`, `planMessage(plan)`); `start.js` wires the page.
  - Page works without a build: the folder list and path box are a plain form fallback is not required; script is required for the browser.

- [ ] Tests (fail first, `TestClient` with `base_url="http://127.0.0.1"`): every start route 403 with a foreign `Host`, without the cookie, and (for POST) with a foreign `Origin`; `?token=` sets the cookie and redirects; wrong token → 403; `serve`-mode app answers 404 on every `/start…` route and its index has no start links; project routes redirect to `/start` when nothing is open; `/start/folders` lists the synthetic sources folder with subject counts and no file names; `/start/open` on a built QA directory opens it and it appears in `/start` as recent; on a non-QA folder → message, nothing opened; `/start/plan` reports the refusals of Task 3; names with `<` are escaped on the page; JS helper tests.
- [ ] Run → FAIL. Commit tests. Implement. Suite → PASS. Commit.

### Task 6: Progress page, cancel, and the project index in start mode

**Files:**
- Create: `src/surfaceqa/web/templates/progress.html`, `src/surfaceqa/web/static/progress.js`
- Modify: `src/surfaceqa/server_start.py`, `src/surfaceqa/site.py`, `src/surfaceqa/web/templates/index.html`, `src/surfaceqa/web/static/start_logic.js`
- Test: `tests/test_server_start.py`, `tests/test_site.py`, `tests/js/start_logic.test.js`

**Interfaces:**
- Produces:
  - `GET /start/progress` (page), `GET /start/status` → `jobs.status` JSON plus `"project": "/"`-opening link data; `POST /start/cancel`; `POST /start/check` → builds `settings.sources(qa_dir)` of the open project into it.
  - When a job ends (first status read that is not `running`): the QA directory is opened as the project and remembered (also after cancel/stop if it has `subjects/`).
  - `start_logic.js`: `progressText(status)`, `shouldLeave(status)` (true only for `done` with no `problems` and no `cohort_failed`), `pollDelay`.
  - `site.render_index(records, view, report=None, start: dict | None = None)` with `start = {"can_check": bool, "building": bool}`: "Check for new or changed subjects" (only if `can_check`), "Other projects" link, and a "A build is running — progress" line when `building`.

- [ ] Tests (fail first): build from the page end to end on the synthetic sources (POST build → poll status until `done` → `/` shows the subjects, project is in recent); a build with a failing subject keeps `shouldLeave` false and the status names the subject with a one-line reason; cancel → `cancelled`, a new build is accepted afterwards; second `POST /start/build` while running → message, one process; `POST /start/check` rebuilds after a surface changes (subject's run changes) and is refused (message) for a project without recorded sources; index shows the three additions only in start mode; reviewing works while `building` is true.
- [ ] Run → FAIL. Commit tests. Implement. Suite → PASS. Commit.

### Task 7: The command, packaging, README

**Files:**
- Create: `LICENSE` (MIT, holder as in `pyproject.toml` authors), `tests/test_package.py`
- Modify: `src/surfaceqa/cli.py`, `pyproject.toml` (version `0.2.0`, `license = "MIT"`, `license-files`), `README.md`
- Test: `tests/test_cli.py`, `tests/test_package.py`

**Interfaces:**
- Produces: `surfaceqa` and `surfaceqa start [--port N] [--no-browser]`; `cli._free_port(first: int) -> int` (first free of `first … first+20` on 127.0.0.1, else error); prints `surfaceqa: http://127.0.0.1:<port>/?token=<token>`; opens it with `webbrowser.open` unless `--no-browser`; token from `secrets.token_urlsafe(16)`.

- [ ] Tests (fail first): no sub-command and `start` both call the start function (uvicorn and `webbrowser` monkeypatched) with host `127.0.0.1`; `--no-browser` opens nothing; a taken port moves to the next and the printed address matches; `start` accepts no `--host`; `uv build --wheel` into a temp folder yields a wheel containing `surfaceqa/web/templates/start.html`, `surfaceqa/web/static/start.js` and the licence, and (marked slow but run by default) `uv run --isolated --with <wheel> surfaceqa --help` exits 0.
- [ ] Run → FAIL. Commit tests. Implement.
- [ ] README: new first section "Quick start" (`uvx surfaceqa`; the `uvx --from git+<repository>` form with a placeholder for the address; data on a server through `ssh -L 8765:localhost:8765 <server>` and `--no-browser`; where reviews are stored; that nothing leaves the machine), and "Publishing" notes for the maintainer (`uv build`, `uv publish`).
- [ ] Whole suite → PASS. Commit.
- [ ] Manual check in the browser (puppeteer): start with an empty `SURFACEQA_HOME`, pick the demo source folders into a scratch output, watch progress, land on the index, cancel a second build, reopen from recent projects.
