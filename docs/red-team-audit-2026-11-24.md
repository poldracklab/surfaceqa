# SurfaceQA red-team audit — 2026-11-24

Audited revision: `ff58485e1448a4e2ab4e1a5a9c3ac727628a086f`.

The code is clearly organized and has extensive tests, but this review found **11 actionable defects: four high-priority and seven medium-priority**. The highest-priority issues affect scientific input integrity and the trust boundary around imported QA directories. Automated indicators remain exploratory aids to human review; this audit does not establish their diagnostic accuracy.

P1 means address before relying on the affected workflow; P2 means a concrete defect under the stated conditions. These are engineering priorities, not CVSS scores. No production code or existing tests were changed. The pre-existing untracked `.env` was neither opened nor modified.

## Findings

### 1. P1 — A changed T1 does not invalidate the viewer or its reviews

**Location:** `src/surfaceqa/build.py:172–176` (surface-only fingerprint and unchanged branch).

The T1 supplies both displayed image intensity and spatial geometry, but the rendered-viewer cache is keyed by surfaces. Replacing `mri/orig.mgz` while retaining the surfaces reuses the existing run, JPEGs and metadata. Reviews remain attached to a supposedly current run even though its input image changed.

**Evidence:** Built a synthetic subject, replaced its T1 with an all-zero volume, and rebuilt. The result was `unchanged`, the run ID stayed the same, and the rendered JPEG was byte-identical. This is an executed reproduction, not only a missing-test observation.

**Remediation and regression:** Include T1 content/geometry in the rendering identity. Define which input changes create a new review run. Test both intensity changes and affine changes with unchanged surfaces, requiring updated images/transforms and an explicit review-invalidation decision.

### 2. P1 — Auxiliary images are accepted without checking spatial alignment

**Location:** `src/surfaceqa/subjectdata.py:57–61`.

Auxiliary image loading compares only the reoriented array shape against the T1. It discards the auxiliary affine and voxel sizes. Equal array dimensions do not imply that the same voxel indices refer to the same anatomy. Consequently, mismatched segmentation, ribbon or intensity images can silently produce incorrect voxelwise findings.

**Evidence:** Translated a synthetic segmentation affine 40 mm along scanner X without changing the array. The loader accepted it, returned the same array, and emitted no alignment warning. The scanner transforms differed by 40 mm.

**Remediation and regression:** Pass reference geometry into auxiliary loaders. Reject mismatches with a visible reason, or explicitly resample to the reference grid with appropriate categorical/continuous interpolation. Test translations, voxel-size changes and axis/orientation cases. The anatomical rationale is described in [NiBabel’s coordinate-system documentation](https://nipy.org/nibabel/coordinate_systems.html).

### 3. P1 — Imported metadata can cause writes outside the QA directory

**Location:** `src/surfaceqa/site.py:75`, `:208–221`; opening path at `src/surfaceqa/server_start.py:131–139`.

`_build_record` allows imported JSON to replace the subject key derived from the directory name. `write_site` uses that key in an output path without containment validation. Opening an imported QA directory without a root index invokes this generation step. The README explicitly supports opening directories built by someone else.

**Evidence:** A temporary subject's `missing.json` contained an absolute `key` pointing to a separate temporary directory. `write_site(qa)` overwrote that directory's existing `index.html`. The demonstrated write is a generated HTML page at an attacker-chosen existing directory, not unrestricted arbitrary file-content execution. Run metadata is also used in viewer output paths and needs the same boundary validation.

**Remediation and regression:** Keep filesystem-derived subject identity authoritative. Validate all imported run/source identifiers and resolve every output path within its intended root, including symlinks. Test absolute paths, `..`, conflicting metadata identity and symlink escapes through the actual project-opening route.

### 4. P1 — Imported report HTML executes in the privileged application origin

**Location:** `src/surfaceqa/server.py:118–125`.

The server returns a QA directory's `report/index.html` unchanged as HTML. An imported report can contain scripts; it is served in the same origin as authenticated folder browsing, project opening and build operations. HttpOnly cookies do not prevent same-origin scripts from making authenticated requests.

**Evidence:** An authenticated TestClient received an imported `<script>fetch("/start/folders")</script>` unchanged with HTTP 200 and no Content-Security-Policy. The index offers the report link. No browser exploit or exfiltration was performed; arbitrary script content and the shared origin were verified.

**Remediation and regression:** Render reports from validated data using trusted templates, or isolate imported HTML with an effective sandbox and restrictive CSP. A separate unprivileged origin is another option. Add a browser test demonstrating that imported report scripts cannot invoke privileged APIs; merely escaping metadata fields does not address raw HTML serving.

### 5. P2 — Leaving during autosave can discard the newest edit

**Location:** `src/surfaceqa/web/static/review.js:130–173` and `:299–303`; server compare-and-write at `src/surfaceqa/review_store.py:61–70`.

Normal saves are queued, but `flushOnLeave` sends independently. If a save is in flight and the user makes another change then navigates away, both requests can carry the same previous `saved` revision. If the older request lands first, the newer leave-time request conflicts. Its response is ignored after navigation, leaving the older content persisted. An acknowledged-on-disk save whose response is lost has a related retry problem: retrying the old revision gets a 409 and locks the editor.

**Evidence:** Executed the actual extracted JavaScript functions in Node with a deferred fetch. The two requests contained different notes and the same `saved:null`. Executed the corresponding persistence sequence: the second write raised `Conflict`, and persisted notes remained the first value. This was a controlled JavaScript/persistence reproduction, not a full browser navigation test.

**Remediation and regression:** Add request IDs/idempotency for ambiguous responses, retain unsaved edits durably, and coordinate navigation with pending saves. Preserve real conflict detection. Browser tests should cover delayed responses, edits during a request, response loss after commit, navigation and reload/recovery.

### 6. P2 — Historical export rows use current-run provenance

**Location:** `src/surfaceqa/export.py:50–55`, `:64–66`, `:81`.

Historical review and final rows take edit status, and rating rows take pipeline/version, from the current subject record rather than their own run. This mislabels the before/after history even when `current_run=no` correctly identifies an old review.

**Evidence:** Reviewed an unedited synthetic run, modified a surface, added a manual-edit file and rebuilt. The old run's saved provenance remained `edited=False`; its exported rating rows said `edited=yes, current_run=no`.

**Remediation and regression:** Load each exported row's run-specific metadata/provenance. Test unedited-to-edited history and pipeline/version changes, including ratings, marks and final rows.

### 7. P2 — Missing parcellation turns missed-gray findings into unscored hints

**Location:** `src/surfaceqa/regions.py:157–158`; `src/surfaceqa/qa.py:33–34`, `:46–47`.

When anatomical classification is unavailable, the fallback region is `outer_edge`. Region-based relabeling then treats that fallback as anatomical evidence and converts `gray_missed` to unscored `look_here`. Missing information therefore suppresses an indicator's score rather than remaining unknown.

**Evidence:** A synthetic 36-voxel finding scored 0.4 with an orbitofrontal parcellation. Removing only the parcellation converted it to `look_here/outer_edge`, scoring 0.0; the raw missed-gray indicator still scored 0.4.

**Remediation and regression:** Represent unknown region/classification confidence explicitly and do not apply anatomical downgrading to a fallback. Test the interaction of absent parcellation and finding relabeling, not just each function separately.

### 8. P2 — An empty source retains its old cohort statistics

**Location:** `src/surfaceqa/cohort.py:123–126`.

Cohort updates iterate only sources that still have eligible members. When the last member disappears, the source is omitted entirely and its stored statistics are never invalidated. Stored cohort state and potentially old findings therefore remain misleading.

**Evidence:** Created a cohort of 30 synthetic maps, computed statistics, removed all source subject folders and updated again. The update returned an empty changed-source set, while `load_cohort` still reported 30 members and the old median.

**Remediation and regression:** Reconcile previously stored source names with present membership and explicitly invalidate sources at zero members. Ensure affected finding state is refreshed or marked stale. Test deletion/failure of every member and subsequent repopulation.

### 9. P2 — Two server processes can both accept conflicting saves

**Location:** `src/surfaceqa/review_store.py:61–70`.

The lock around read/check/write is a `threading.Lock`; it coordinates threads in one process only. Two `serve`/`start` instances pointed at the same QA directory can both accept the same expected revision and silently overwrite an accepted save. A single server's ordinary multi-window conflict protection is present.

**Evidence:** Two processes were synchronized after reading the same stored review. Both writes returned success; only the second review remained (`accepted A`, `accepted B`, `persisted=B`).

**Remediation and regression:** Use a process-shared file lock or transactional storage for the entire revision check and write, or enforce one review server per QA directory. Test actual independent processes, not only threads.

### 10. P2 — The launch-token cookie is not isolated by port

**Location:** `src/surfaceqa/server_start.py:40–43`, `:64`.

A port suffix in the cookie name avoids collisions but does not restrict where the cookie is sent. Another local user's HTTP service on the same loopback hostname can receive the token if the user's browser visits it, then replay it to the local app. This requires that additional visit and is not an unauthenticated remote internet attack.

**Evidence:** After login at `127.0.0.1:8765`, an HTTPX request built for `127.0.0.1:9999` included `surfaceqa_token_8765`. No live browser attack was performed. Port non-isolation is specified in [RFC 6265, section 8.5](https://www.rfc-editor.org/rfc/rfc6265.html#section-8.5).

**Remediation and regression:** Reconsider host-wide cookies as the local-user security boundary; use an origin-bound authorization design and test cross-port behavior. Narrow the README isolation claim until that design is implemented. HttpOnly/SameSite alone cannot fix this issue.

### 11. P2 — A crafted token prompt can submit the token off-origin

**Location:** `src/surfaceqa/server_start.py:55–56`; `src/surfaceqa/web/templates/token.html:6`.

The token-entry form uses the decoded request path as its action. A path beginning with two slashes becomes a scheme-relative external form target. A user must follow the crafted local URL while unauthenticated and enter the launch token for disclosure to occur; token possession alone does not give an internet attacker direct access to loopback.

**Evidence:** `GET /%2fexample.com/` returned HTTP 403 with `<form method="get" action="//example.com/">`. No token was sent to an external server.

**Remediation and regression:** Use a fixed local form action and validate any return path separately. Test encoded slashes and backslashes, including redirect destinations.

## Scientific accuracy and validation limits

The explicit framing of findings as prompts for human review is appropriate. The repository's `docs/indicators-on-subject-07.md` correctly labels its three reconstructions of one person as exploratory inspection, not validation. It also documents plausible false positives, unconfirmed misses and correlated errors between segmentation and surfaces. Those observations cannot establish sensitivity, specificity or calibration across subjects, scanners, disease groups or pipelines.

Specific methodological choices need independent evaluation rather than being called programming bugs: mesh vertex-count thresholds depend on sampling density; rectangular voxel margins vary physically with resolution; zero-MAD cohort locations are excluded; region-based suppression can demote genuine outer-surface errors; and a shared reconstruction failure can evade within-cohort outlier detection. A score of zero must not be treated as evidence of an accurate reconstruction. Name-based cross-source subject matching also assumes identifiers refer to the same person across datasets.

A suitable next validation study would freeze thresholds, collect independent blinded expert ratings on held-out subjects spanning relevant pipelines/resolutions, report finding-level and subject-level performance with uncertainty, and stratify by available inputs. Examine failures where segmentation and surfaces agree incorrectly. Compare geometric landmarks/contours against an external reference viewer. Existing real-data smoke tests check plausibility and coordinate consistency, not expert-labeled accuracy. Rerun/edit recipes were inspected but not executed against a full FreeSurfer/FastSurfer installation in this audit.

## Code quality and maintainability

**Strengths:** 53 Python modules with focused responsibilities; the longest Python function found by AST inspection is 33 lines. Both `__init__.py` files are empty. Tests generally use functions and fixtures. Template autoescaping, safe DOM text operations, argument-array subprocess invocation, route allowlists and same-process review conflict checking are useful protections. The project tracks a uv lockfile and centralizes indicator thresholds and version constants.

**Gaps:** persisted records are largely loosely structured dictionaries, and identity/provenance is merged across layers without a central validated schema. Several defects above arise at those boundaries. Format and QA version bumps depend on developer discipline. Add explicit schemas and migrations for persisted records, preserving unknown/corrupt/stale states rather than silently treating them as absence. Maintain a dependency map from input files to derived assets and review identity.

There is no `.github` CI configuration in this checkout and no configured linter/type checker in `pyproject.toml`; external CI was not inspected. Browser tests are missing: `tests/test_js.py` uses source-text assertions for retry behavior, which cannot verify network ordering or navigation recovery. Add behavioral browser coverage for critical saving/authentication flows and CI for pytest, JavaScript tests and package-resource checks. The real-subject tests depend on a fixed external mount, limiting their portability. These are maintainability recommendations, separate from the 11 reproduced defects.

## Verification and scope

- Full repository test suite: `uv run pytest -q` — **994 passed, 1 warning in 205.08 seconds**. The warning is Starlette’s deprecation of HTTPX-backed TestClient use. The mounted real-subject tests ran; there were no skips.
- Focused scientific tests: 152 passed. Focused existing security tests: 86 passed, 192 deselected. These subsets overlap the full suite and are not extra independent validation samples.
- Adversarial checks used synthetic images, temporary QA directories, FastAPI TestClient, Node execution of actual autosave functions, and independent-process persistence checks.
- Source review covered CLI/start/server routes, templates and JavaScript, rendering/geometry, indicators and cohort logic, build/cache/provenance, reviews/consensus, and report/export paths.
- No production fixes, new committed tests, commits, deployments, external messages or destructive operations on real data were performed. Temporary reproduction files were isolated from the repository's data. This report is the only intended repository change.
- This was source review plus targeted execution, not a complete penetration test or formal proof. No comprehensive dependency-advisory scanner, live-browser exploit, clinical validation or load/memory stress test was completed. Absence of a reported vulnerability is not assurance that a dependency or path is secure. The shared `serve` command's documented trusted-network/no-accounts model was treated as an explicit boundary, rather than reported as an unexpected authentication bypass.

## Recommended sequence

1. Fix imported-directory containment and privileged HTML handling, plus the token form action.
2. Correct image cache identity and spatial alignment checks before relying on rebuilt or heterogeneous inputs.
3. Repair autosave recovery, historical provenance and multi-process concurrency.
4. Correct missing-region and zero-member cohort handling; add the corresponding interaction tests.
5. Establish behavioral browser CI and independent scientific validation before expanding claims for automated indicators.

For implementation, follow the repository's required workflow: write regression tests first, demonstrate RED, commit tests before implementation, then make the smallest modular fix and run relevant checks through `uv run`.
