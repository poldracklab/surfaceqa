"""The web app that serves a QA directory and records reviews."""

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, quote

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles

from surfaceqa.layout import read_json
from surfaceqa.reviews import valid_reviewer
from surfaceqa.server_reviews import (Refused, current_review, has_submitted, next_subject,
                                      store_review)
from surfaceqa.site import (View, render_guidance, render_index, render_subject, render_viewer,
                            subject_records)

COOKIE = "surfaceqa_reviewer"
ONE_YEAR = 365 * 24 * 3600
MAX_BODY = 1_000_000  # bytes; a review is a few kilobytes
RUN_NAME = re.compile(r"[0-9a-f]{12}")
GATED = ("findings.json", "findings_voxels.bin")  # hidden from a blind reviewer until they submit
# The files of a run that the viewer asks for. Nothing else in the QA directory is served as a
# file: not the reviews, the final labels or the exports, and not the pages `build` wrote to
# disk, which show every reviewer's ratings. Exact spelling only, also on disks that ignore case.
PLANE = "(coronal|sagittal|axial)"
RUN_FILE = re.compile(rf"meta\.json|findings\.json|findings_voxels\.bin|contours_{PLANE}\.(bin|json)"
                      rf"|slices/{PLANE}/\d{{3,4}}\.jpg")
BAD_NAME = ("A reviewer name is 1 to 40 letters, digits, - or _ and starts with a letter or "
            "digit; no spaces. Capitals are stored as lower case.")

router = APIRouter()


def _qa_dir(request: Request) -> Path:
    return request.app.state.qa_dir


def _reviewer(request: Request) -> str | None:
    name = request.cookies.get(COOKIE)
    return name if name is not None and valid_reviewer(name) else None


def _view(request: Request) -> View:
    return View(reviewer=_reviewer(request), blind=request.app.state.blind, serving=True)


def _record(request: Request, key: str) -> dict:
    """The subject with this key, as the caller may see it; 404 when there is none."""
    for record in subject_records(_qa_dir(request), _view(request)):
        if record["key"] == key:
            return record
    raise HTTPException(404, "no such subject")


def _reviewable(request: Request, key: str) -> tuple[dict, str]:
    reviewer = _reviewer(request)
    if reviewer is None:
        raise HTTPException(401, "give your name first")
    record = _record(request, key)
    if not record["has_run"]:
        raise HTTPException(404, "this subject has no rendered run to review")
    return record, reviewer


def _local(target: str) -> str:
    """A redirect target on this site, or the index."""
    ok = target.startswith("/") and not target.startswith("//") and "\\" not in target
    return target if ok else "/"


@router.post("/reviewer")
async def set_reviewer(request: Request):
    form = parse_qs((await request.body()).decode(errors="replace"), keep_blank_values=True)
    name = form.get("name", [""])[0].strip().lower()
    if not valid_reviewer(name):
        return HTMLResponse(f"<p>{BAD_NAME}</p><p><a href='/'>Back</a></p>", status_code=400)
    response = RedirectResponse(_local(form.get("next", ["/"])[0]), status_code=303)
    response.set_cookie(COOKIE, name, max_age=ONE_YEAR, samesite="lax", httponly=True)
    return response


@router.post("/reviewer/clear")
def clear_reviewer():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE)
    return response


@router.get("/", response_class=HTMLResponse)
@router.get("/index.html", response_class=HTMLResponse)
def index(request: Request):
    view = _view(request)
    return render_index(subject_records(_qa_dir(request), view), view)


@router.get("/subjects/{key}/", response_class=HTMLResponse)
@router.get("/subjects/{key}/index.html", response_class=HTMLResponse)
def subject(request: Request, key: str):
    return render_subject(_record(request, key), _view(request))


@router.get("/subjects/{key}/guidance", response_class=HTMLResponse)
def guidance(request: Request, key: str):
    """The fix guidance of one subject as the current viewer may see it."""
    view = _view(request)
    if view.blind and view.reviewer is None:
        raise HTTPException(404)
    return render_guidance(_record(request, key), view)


@router.get("/next")
def next_page(request: Request, after: str | None = None):
    view = _view(request)
    if view.reviewer is None:
        return RedirectResponse("/", status_code=303)
    records = subject_records(_qa_dir(request), view)
    key = next_subject(records, view.reviewer, view.blind, after)
    return RedirectResponse(f"/subjects/{quote(key)}/" if key else "/", status_code=303)


@router.get("/api/review/{key}")
def get_review(request: Request, key: str):
    record, reviewer = _reviewable(request, key)
    return current_review(_qa_dir(request), record, reviewer)


async def _json_body(request: Request):
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        raise HTTPException(400, "malformed content-length") from None
    if declared > MAX_BODY:
        raise HTTPException(413, "the review is too large")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise HTTPException(413, "the review is too large")
    try:
        return json.loads(body)
    except ValueError:
        raise HTTPException(422, "the review is not valid JSON") from None


async def _store(request: Request, key: str, submit: bool):
    record, reviewer = _reviewable(request, key)
    payload = await _json_body(request)
    try:
        return await run_in_threadpool(store_review, _qa_dir(request), record, reviewer, payload,
                                       submit)
    except Refused as refused:
        return JSONResponse(refused.body(), status_code=refused.status)


@router.put("/api/review/{key}")
async def put_review(request: Request, key: str):
    return await _store(request, key, submit=False)


@router.post("/api/review/{key}/submit")
async def post_submit(request: Request, key: str):
    return await _store(request, key, submit=True)


@router.get("/subjects/{key}/error.txt")
def build_error(request: Request, key: str):
    record = _record(request, key)
    path = _qa_dir(request) / "subjects" / record["key"] / "error.txt"
    if not path.is_file():
        raise HTTPException(404)
    return PlainTextResponse(path.read_text(errors="replace"))


@router.get("/subjects/{key}/runs/{run}/viewer.html", response_class=HTMLResponse)
def run_viewer(request: Request, key: str, run: str):
    """The viewer of one run on its own, shown beside another subject for comparison."""
    view = _view(request)
    if view.blind and view.reviewer is None:
        raise HTTPException(404)
    record = _record(request, key)
    folder = _qa_dir(request) / "subjects" / record["key"] / "runs" / run
    meta = read_json(folder / "meta.json") if RUN_NAME.fullmatch(run) else None
    if meta is None:
        raise HTTPException(404)
    return render_viewer(record, meta, view)


@router.get("/subjects/{key}/runs/{run}/{name:path}")
def run_file(request: Request, key: str, run: str, name: str):
    """A viewer file of a run. In blind mode the findings wait until the reviewer has submitted."""
    record = _record(request, key)
    path = _qa_dir(request) / "subjects" / record["key"] / "runs" / run / name
    if not RUN_NAME.fullmatch(run) or not RUN_FILE.fullmatch(name) or not path.is_file():
        raise HTTPException(404)
    blind = request.app.state.blind
    if name in GATED and blind and not has_submitted(_qa_dir(request), record, _reviewer(request)):
        raise HTTPException(404)
    return FileResponse(path)


class RevalidatedFiles(StaticFiles):
    """The tool's scripts and styles. The browser asks before using a cached copy, so an
    upgraded server is never driven by the scripts of the version before."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-cache"
        return response


def create_app(qa_dir: Path, blind: bool = False) -> FastAPI:
    app = FastAPI(title="surfaceqa", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.qa_dir = Path(qa_dir)
    app.state.blind = blind
    app.include_router(router)
    # the scripts of this version of the tool, not the copy an earlier build left in the QA directory
    app.mount("/static", RevalidatedFiles(packages=[("surfaceqa", "web/static")]), name="static")
    return app
