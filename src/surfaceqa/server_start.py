"""Start mode: the start page, the folder browser and builds, for one person on their own machine.

These routes list folders and start builds on request, so they exist only in an app made with a
StartMode, and every request to such an app must name the machine itself as host, carry the
launch token, and (when it changes something) come from the app's own pages.
"""

import re
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from surfaceqa import jobs, lock, recent, start
from surfaceqa.settings import sources as recorded_sources
from surfaceqa.site import render_page, write_site

TOKEN_COOKIE = "surfaceqa_token"
LOOPBACK_HOST = re.compile(r"(127\.0\.0\.1|localhost)(:\d+)?", re.IGNORECASE)
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

router = APIRouter()


@dataclass
class StartMode:
    token: str  # in the address printed at launch; nobody else on the machine knows it
    job: jobs.Job | None = None
    settled: jobs.Job | None = None  # the last job whose end has been acted on
    starting: threading.Lock = field(default_factory=threading.Lock)  # one build is begun at a time


# ---- the guard -------------------------------------------------------------------------------

def _cookie_name(request: Request) -> str:
    """One cookie per port, so two running copies of the tool do not sign each other out."""
    port = request.headers.get("host", "").rpartition(":")[2]
    return f"{TOKEN_COOKIE}_{port}" if port.isdigit() else TOKEN_COOKIE


def _right(given: str | None, token: str) -> bool:
    return given is not None and secrets.compare_digest(given.encode(), token.encode())


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    return origin is None or urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()


def _ask_for_token(request: Request) -> HTMLResponse:
    return HTMLResponse(render_page("token.html", action=request.url.path), status_code=403)


def _admit(request: Request, token: str) -> RedirectResponse:
    """Keep the token in a cookie and take it out of the address."""
    rest = [(name, value) for name, value in request.query_params.multi_items() if name != "token"]
    target = request.url.path + (f"?{urlencode(rest)}" if rest else "")
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(_cookie_name(request), token, httponly=True, samesite="strict")
    return response


async def guard(request: Request, call_next):
    token = request.app.state.start.token
    if not LOOPBACK_HOST.fullmatch(request.headers.get("host", "")):
        return PlainTextResponse("surfaceqa answers only to this machine's own address.", status_code=403)
    if request.url.path.startswith("/static/"):
        return await call_next(request)
    if "token" in request.query_params:
        given = request.query_params["token"]
        return _admit(request, token) if _right(given, token) else _ask_for_token(request)
    if not _right(request.cookies.get(_cookie_name(request)), token):
        return _ask_for_token(request)
    if request.method not in SAFE_METHODS and not _same_origin(request):
        return PlainTextResponse("This request did not come from surfaceqa's own pages.", status_code=403)
    if request.app.state.qa_dir is None and not request.url.path.startswith("/start"):
        return RedirectResponse("/start", status_code=303)  # no project is open yet
    return await call_next(request)


def install_start(app: FastAPI) -> None:
    app.middleware("http")(guard)
    app.include_router(router)


# ---- pages -----------------------------------------------------------------------------------

async def _form(request: Request) -> dict[str, list[str]]:
    return parse_qs((await request.body()).decode(errors="replace"), keep_blank_values=True)


def _first(form: dict[str, list[str]], name: str) -> str:
    return form.get(name, [""])[0].strip()


def _running_build(mode: StartMode) -> dict | None:
    return {"out": str(mode.job.out)} if job_running(mode) else None


def _page(app: FastAPI, error: str | None = None, status_code: int = 200) -> HTMLResponse:
    _status(app)  # a build that ended while nobody watched is taken note of here
    page = render_page("start.html", projects=recent.projects(), error=error,
                       build=_running_build(app.state.start))
    return HTMLResponse(page, status_code=status_code)


@router.get("/start", response_class=HTMLResponse)
def start_page(request: Request):
    return _page(request.app)


@router.get("/start/folders")
def folders(path: str | None = None) -> dict:
    """The sub-folders of a folder, or where browsing can begin. Never file names."""
    return {"places": start.places()} if not path else start.list_folders(Path(path))


@router.get("/start/plan")
def plan(request: Request) -> dict:
    return start.plan(request.query_params.getlist("source"), request.query_params.get("out", ""))


# ---- actions ---------------------------------------------------------------------------------

def open_project(app: FastAPI, qa_dir: Path) -> None:
    """Make this QA directory the one the app shows."""
    if not (qa_dir / "index.html").is_file():
        try:
            write_site(qa_dir)
        except OSError:  # someone else's read-only directory: the pages are rendered on request
            pass
    recent.remember(qa_dir)
    app.state.qa_dir = qa_dir


@router.post("/start/open")
async def open_existing(request: Request):
    text = _first(await _form(request), "path")
    if not text or not start.is_qa_dir(start.as_path(text)):
        return _page(request.app, f"{text or 'An empty path'} is not a QA directory: surfaceqa did not "
                                  "build it. To inspect new data, choose it under “Inspect new data”.", 400)
    await run_in_threadpool(open_project, request.app, start.as_path(text).resolve())
    return RedirectResponse("/", status_code=303)


@router.post("/start/forget")
async def forget(request: Request):
    recent.forget(start.as_path(_first(await _form(request), "path")))
    return RedirectResponse("/start", status_code=303)


def job_running(mode: StartMode) -> bool:
    return mode.job is not None and mode.job.process.poll() is None


def _busy(mode: StartMode, out: Path) -> str | None:
    if job_running(mode):
        return "A build is already running. Wait for it or cancel it first."
    if lock.building(out):
        return f"{out} is already being built by another program."
    return None


def _begin(app: FastAPI, sources: list[str], out: str):
    """Start building these folders into `out`, or say why not."""
    mode = app.state.start
    with mode.starting:  # two requests at once must not both find that nothing is running
        made = start.plan(sources, out)
        if made["error"]:
            return _page(app, made["error"], 400)
        target = Path(made["out"]).resolve()
        busy = _busy(mode, target)
        if busy:
            return _page(app, busy, 409)
        folders = [start.as_path(text).resolve() for text in sources if str(text).strip()]
        mode.job = jobs.start(folders, target, jobs.default_jobs())
    return RedirectResponse("/start/progress", status_code=303)


@router.post("/start/build")
async def build(request: Request):
    form = await _form(request)
    return await run_in_threadpool(_begin, request.app, form.get("source", []), _first(form, "out"))


@router.post("/start/check")
def check(request: Request):
    """Build the open project's folders again: new subjects are added, changed ones redone."""
    qa_dir = request.app.state.qa_dir
    if qa_dir is None:
        return RedirectResponse("/start", status_code=303)
    sources = recorded_sources(qa_dir)
    if not sources:
        return _page(request.app, f"{qa_dir} does not record which folders it was built from. Build "
                                  "them once under “Inspect new data” with this QA directory as the "
                                  "output.", 400)
    return _begin(request.app, [str(source) for source in sources], str(qa_dir))


@router.post("/start/cancel")
async def cancel(request: Request):
    job = request.app.state.start.job
    if job is None:
        return RedirectResponse("/start", status_code=303)
    await run_in_threadpool(jobs.cancel, job)
    return RedirectResponse("/start/progress", status_code=303)


# ---- progress --------------------------------------------------------------------------------

def _settle(app: FastAPI, mode: StartMode) -> None:
    """Once, when a job has ended: remember what it built, and show it unless the researcher
    has another project open."""
    job, mode.settled = mode.job, mode.job
    jobs.cleanup(job)  # a build that died by itself may have left workers and a lock
    if not start.is_qa_dir(job.out):
        return
    if app.state.qa_dir in (None, job.out):
        open_project(app, job.out)
    else:
        recent.remember(job.out)


def _status(app: FastAPI) -> dict:
    mode = app.state.start
    if mode.job is None:
        return {"state": "none"}
    answer = jobs.status(mode.job)
    if answer["state"] != "running" and mode.settled is not mode.job:
        _settle(app, mode)
    return {**answer, "open": app.state.qa_dir == mode.job.out, "openable": start.is_qa_dir(mode.job.out)}


@router.get("/start/status")
def status(request: Request) -> dict:
    return _status(request.app)


@router.get("/start/progress")
def progress_page(request: Request):
    if request.app.state.start.job is None:
        return RedirectResponse("/start", status_code=303)
    return HTMLResponse(render_page("progress.html", status=_status(request.app)))


def start_info(app: FastAPI) -> dict | None:
    """What the index page of the open project offers in start mode; None for `serve`."""
    mode, qa_dir = app.state.start, app.state.qa_dir
    if mode is None:
        return None
    return {"can_check": bool(recorded_sources(qa_dir)),
            "building": job_running(mode) and mode.job.out == qa_dir}
