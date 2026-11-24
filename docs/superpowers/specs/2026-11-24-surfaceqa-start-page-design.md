# surfaceqa: one-command start — design

## Intent

A researcher at another site should be able to inspect their own FreeSurfer or
FastSurfer output with one command and no knowledge of the tool's sub-commands.
Their data stays on their machine. Today they must install the package, run
`surfaceqa build <folders> --out …`, then `surfaceqa serve <qa_dir>`.

After this work:

```
uvx surfaceqa
```

downloads the tool, starts it, and opens the browser on a start page with no
data. The researcher picks a folder, watches the build, and lands in the review.

## Goals

- `surfaceqa` with no sub-command starts a local server and opens the browser.
- A start page where the researcher chooses the data, sees build progress, and
  reopens earlier work.
- The package is ready to publish so `uvx surfaceqa` works on macOS and Linux.
- The start page is the whole "front door", so a later Mac app only has to wrap it.

## Non-goals

- A Mac app (later step; needs an Apple Developer ID the user does not have yet).
- A hosted site with upload.
- Authentication. The start mode is for one person on their own machine.
- Windows testing. Nothing is done to prevent it working; it is not verified.

## Anti-goals

- The start mode must never be reachable from another machine: it lists folders
  and starts builds on request.
- Nothing is written into the input data (existing rule).
- Existing sub-commands and existing QA directories keep working unchanged.

## Approaches considered

1. **One command + start page (chosen).** Works on Mac and Linux, including
   servers reached over ssh. Costs one terminal line and `uv`.
2. **Mac app.** Double-click, but Mac only, ~150–200 MB, rebuilt per release,
   and needs signing to open without a warning. Deferred; it reuses the start page.
3. **Hosted upload site.** Set aside: identifiable head images on a public
   server, and no access control in the tool.

The user chose 1.

## Design

### Command

- `surfaceqa` (no sub-command) and `surfaceqa start` do the same thing.
- Options: `--port` (default 8765; if taken, the next free port is used and
  printed), `--no-browser`.
- There is no `--host`: start mode always binds `127.0.0.1`.
- The address is printed, and the browser opens on it unless `--no-browser`.
- `build`, `serve`, `finalize`, `export`, `report` are unchanged. `serve` does
  not offer the start page, the folder browser or building; a shared review
  server stays as it is.

### Start page (`/start`)

Shown at `/` when no project is open. Three parts:

1. **Recent projects.** QA directories opened before on this machine, newest
   first, each with its source folders and subject count. Click to open.
   Entries whose folder is gone are shown as missing and can be removed.
2. **Open an existing QA directory** by path (for one built on the command line
   or by a colleague).
3. **Inspect new data.**
   - A path box plus a folder browser. The browser lists sub-folders only,
     never files, and says for each folder whether it is a subject or how many
     subjects it holds. The home folder and mounted volumes are offered as
     starting points.
   - The choice may be a subjects folder or a single subject (as `build`
     accepts today). Several folders can be added before building.
   - Output location: by default `surfaceqa/` beside the first source, as
     `build` does. If that place cannot be written, `~/surfaceqa/<source name>`.
     The researcher can change it. A location inside a source is refused.
   - "Build" starts the build and goes to the progress page.

### Building

- The build runs in a separate process so pages stay responsive, with half the
  machine's cores as `jobs`.
- One build at a time. A second request while one runs is refused with a message.
- Progress page (`/start/progress`): subjects done of total, the pass in
  progress (render, cohort comparison, indicators), failures by name with the
  reason. It polls; closing the tab does not stop the build.
- "Cancel" stops the build. Finished subjects are kept, and building the same
  folder again continues from them (the build already skips current subjects).
- When the build ends, the page links to the project's index; with no failure
  it goes there by itself.
- `build_all` gains an optional progress callback; without it nothing changes.

### Inside a project

- The index page gets, in start mode only:
  - "Check for new or changed subjects": builds the project's source folders
    again.
  - "Other projects": back to the start page.
- The source folders of a project are recorded in its `settings.json` when it
  is built from the start page. A project without that record (built by the
  command line) offers no "check" button; its subjects' recorded paths are not
  guessed at.
- Reviewer name, blind mode off, report, export: as `serve` today.

### Safety of start mode

- Binds loopback only.
- Requests whose `Host` is not `127.0.0.1` or `localhost` (with the port) are
  refused, and state-changing requests must come from the same origin. This
  stops another web page open in the browser from listing folders or starting
  a build.

### Remembered projects

- `~/.surfaceqa/recent.json`: QA directory path and when it was last opened.
  Nothing else is stored outside QA directories. Overridable with the
  `SURFACEQA_HOME` environment variable (also used by tests).

### Packaging

- Version 0.2.0. MIT licence (the user's choice): a `LICENSE` file and the
  licence field in `pyproject.toml`.
- A test builds the wheel and checks it contains the templates and static files.
- README opens with a quick start: `uvx surfaceqa`, and for data on a server:
  `ssh -L 8765:localhost:8765 <server>` then `uvx surfaceqa --no-browser`.
- Publishing itself (`uv publish`, or pushing to GitHub for
  `uvx --from git+https://…`) is done by the user with their own account.

## Left to the builder

- Module split (suggested: `start.py` for folder listing and defaults,
  `recent.py`, `jobs.py` for the background build, routes in `server.py` or a
  sibling), page layout, polling interval.
- How the running app switches between "no project" and "project open".
