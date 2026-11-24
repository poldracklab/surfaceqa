"""Start mode: the start page, the folder browser and builds, for one person on their own machine.

These routes list folders and start builds on request, so they exist only in an app made with a
StartMode, and every request to such an app must name the machine itself as host, carry the
launch token, and (when it changes something) come from the app's own pages.
"""

import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from surfaceqa import jobs, lock, recent, start
from surfaceqa.site import render_page, write_site

TOKEN_COOKIE = "surfaceqa_token"
LOOPBACK_HOST = re.compile(r"(127\.0\.0\.1|localhost)(:\d+)?", re.IGNORECASE)
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

router = APIRouter()


@dataclass
class StartMode:
    token: str  # in the address printed at launch; nobody else on the machine knows it
    job: jobs.Job | None = None


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


def _page(error: str | None = None, status_code: int = 200) -> HTMLResponse:
    page = render_page("start.html", projects=recent.projects(), error=error)
    return HTMLResponse(page, status_code=status_code)


@router.get("/start", response_class=HTMLResponse)
def start_page():
    return _page()


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
    if not text or not start.is_qa_dir(Path(text).expanduser()):
        return _page(f"{text or 'An empty path'} is not a QA directory (it has no subjects folder).", 400)
    await run_in_threadpool(open_project, request.app, Path(text).expanduser().resolve())
    return RedirectResponse("/", status_code=303)


@router.post("/start/forget")
async def forget(request: Request):
    recent.forget(Path(_first(await _form(request), "path")))
    return RedirectResponse("/start", status_code=303)


def job_running(mode: StartMode) -> bool:
    return mode.job is not None and mode.job.process.poll() is None


def _busy(mode: StartMode, out: Path) -> str | None:
    if job_running(mode):
        return f"A build is already running ({mode.job.out}). Wait for it or cancel it first."
    if lock.building(out):
        return f"{out} is already being built by another program."
    return None


@router.post("/start/build")
async def build(request: Request):
    form = await _form(request)
    made = start.plan(form.get("source", []), _first(form, "out"))
    if made["error"]:
        return _page(made["error"], 400)
    mode, out = request.app.state.start, Path(made["out"]).resolve()
    busy = _busy(mode, out)
    if busy:
        return _page(busy, 409)
    sources = [Path(text).expanduser().resolve() for text in form["source"] if text.strip()]
    mode.job = jobs.start(sources, out, jobs.default_jobs())
    return RedirectResponse("/start/progress", status_code=303)
