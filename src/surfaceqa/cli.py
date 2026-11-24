"""Command line entry point: surfaceqa [start] | build | serve | finalize | export | report."""

import argparse
import os
import signal
import socket
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from surfaceqa import progress
from surfaceqa.build import BuildResult, build_all
from surfaceqa.discover import find_subjects, source_root
from surfaceqa.lock import Busy, build_lock
from surfaceqa.settings import has_placeholder, save_rerun_template, save_sources
from surfaceqa.site import write_site

USAGE_ERROR = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="surfaceqa")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="render report pages for subjects")
    build.add_argument("sources", nargs="+", type=Path, metavar="SOURCE",
                       help="a FastSurfer or FreeSurfer subjects folder, or one subject folder")
    build.add_argument("--out", type=Path, help="QA directory (default: surfaceqa/ beside the first source)")
    build.add_argument("--subjects", nargs="+", metavar="PATTERN", help="only subjects matching these shell patterns")
    build.add_argument("--jobs", type=int, default=1, help="subjects to build in parallel")
    build.add_argument("--progress", action="store_true",
                       help="keep build_status.json in the QA directory up to date while building")
    build.add_argument("--rerun-template", metavar="TEMPLATE",
                       help="the line that launches these subjects' pipeline, with {command} where "
                            "its command goes; fix guidance then shows complete rerun commands")
    serve = commands.add_parser("serve", help="open a QA directory in the browser")
    serve.add_argument("qa_dir", type=Path)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--blind", action="store_true",
                       help="shuffle the subjects per reviewer and hide indicator results until "
                            "the reviewer submits")
    finalize = commands.add_parser("finalize", help="combine the reviewers' ratings into final labels")
    finalize.add_argument("qa_dir", type=Path)
    export = commands.add_parser("export", help="write the ratings, marks, final labels and indicators as tables")
    export.add_argument("qa_dir", type=Path)
    export.add_argument("--out", type=Path, help="folder for the tables (default: export/ in the QA directory)")
    start = commands.add_parser("start", help="open the start page in the browser to choose the data "
                                              "(what `surfaceqa` alone does)")
    start.add_argument("--port", type=int, default=8765, help="the next free port is used if this one is taken")
    start.add_argument("--no-browser", action="store_true", help="print the address and do not open a browser")
    report = commands.add_parser("report", help="write a page showing how errors are spread over subjects and regions")
    report.add_argument("qa_dir", type=Path)
    return parser


def _fail(message: str) -> int:
    print(f"surfaceqa: {message}", file=sys.stderr)
    return USAGE_ERROR


def _inside(path: Path, folders: list[Path]) -> bool:
    return any(path == folder or folder in path.parents for folder in folders)


def _report(results: list[BuildResult]) -> None:
    for result in results:
        detail = f"  ({', '.join(result.missing)})" if result.missing else ""
        print(f"{result.key}  {result.status}{detail}")
    counts = {s: sum(r.status == s for r in results) for s in ("built", "updated", "unchanged", "missing", "failed")}
    print(", ".join(f"{n} {status}" for status, n in counts.items() if n))


def _build(args: argparse.Namespace) -> int:
    sources = [source.resolve() for source in args.sources]
    absent = [str(s) for s in sources if not s.is_dir()]
    if absent:
        return _fail(f"not a folder: {', '.join(absent)}")
    if args.rerun_template is not None and not has_placeholder(args.rerun_template):
        return _fail("--rerun-template must contain {command} where the pipeline's command goes")
    roots = [source_root(source) for source in sources]
    out = (args.out or roots[0].parent / "surfaceqa").resolve()
    if _inside(out, roots):
        return _fail(f"--out {out} is inside a source folder; nothing is written into the input data")
    if any(out in root.parents for root in roots):
        return _fail(f"--out {out} contains a source folder; choose a place outside the input data")
    try:
        refs = find_subjects(sources, args.subjects)
    except ValueError as error:
        return _fail(str(error))
    if not refs:
        return _fail("no subjects found (a subject is a folder containing mri/ and surf/)")
    try:
        with build_lock(out):
            results = _run_build(args, sources, refs, out)
    except Busy:
        return _fail_build("a build of this QA directory is already running")
    _report(results)
    print(f"Report: {out / 'index.html'}  (view with: surfaceqa serve {out})")
    return 1 if any(r.status == "failed" for r in results) else 0


def _fail_build(message: str) -> int:
    print(f"surfaceqa: {message}", file=sys.stderr)
    return 1


def _running(out: Path):
    """Called by the build as it advances: keeps the status file current."""
    def tell(stage: str, done: int, total: int) -> None:
        progress.write(out, state="running", pid=os.getpid(), stage=stage, done=done, total=total)
    return tell


def _run_build(args: argparse.Namespace, sources: list[Path], refs: list, out: Path) -> list[BuildResult]:
    save_sources(out, sources)  # first, so a build that is stopped can be taken up again
    results = build_all(refs, out, jobs=args.jobs, progress=_running(out) if args.progress else None)
    if args.rerun_template is not None:
        save_rerun_template(out, sorted({ref.source for ref in refs}), args.rerun_template)
    write_site(out)
    if args.progress:
        progress.write(out, state="done", stage="indicators", done=len(refs), total=len(refs),
                       problems=progress.problems(out, results), cohort_failed=progress.cohort_failed(out))
    return results


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from surfaceqa import server

    qa_dir = args.qa_dir.resolve()
    if not (qa_dir / "index.html").is_file():
        return _fail(f"{qa_dir} has no index.html; run `surfaceqa build` first")
    print(f"surfaceqa: http://{args.host}:{args.port}/")
    uvicorn.run(server.create_app(qa_dir, blind=args.blind), host=args.host, port=args.port, log_level="warning")
    return 0


def _qa_dir(args: argparse.Namespace) -> Path | None:
    qa_dir = args.qa_dir.resolve()
    return qa_dir if (qa_dir / "subjects").is_dir() else None


def _not_a_qa_dir(args: argparse.Namespace) -> int:
    return _fail(f"{args.qa_dir} is not a QA directory; make one with `surfaceqa build`")


def _finalize(args: argparse.Namespace) -> int:
    from surfaceqa.finalize import describe_disagreement, finalize

    qa_dir = _qa_dir(args)
    if qa_dir is None:
        return _not_a_qa_dir(args)
    records = finalize(qa_dir)
    write_site(qa_dir)
    for record in records:
        if record["status"] == "disagreement":
            print(describe_disagreement(record))
    counts = {s: sum(r["status"] == s for r in records)
              for s in ("agreed", "single", "settled", "disagreement", "unreviewed")}
    print(", ".join(f"{n} {status}" for status, n in counts.items() if n))
    return 0


def _export(args: argparse.Namespace) -> int:
    from surfaceqa.export import export_tables

    qa_dir = _qa_dir(args)
    if qa_dir is None:
        return _not_a_qa_dir(args)
    for path in export_tables(qa_dir, args.out):
        print(path)
    return 0


def _report_command(args: argparse.Namespace) -> int:
    from surfaceqa.report import write_report

    qa_dir = _qa_dir(args)
    if qa_dir is None:
        return _not_a_qa_dir(args)
    print(write_report(qa_dir))
    return 0


PORTS_TRIED = 20


def _free_port(first: int) -> int | None:
    """The first port from `first` on that nothing on this machine is listening on."""
    for port in range(first, first + PORTS_TRIED + 1):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    return None


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _open_when_listening(port: int, address: str, wait: float = 15.0) -> threading.Thread:
    """Open the browser as soon as the server answers, so it never shows a refused connection."""
    def run() -> None:
        import webbrowser

        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if _listening(port):
                webbrowser.open(address)
                return
            time.sleep(0.1)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def _start(args: argparse.Namespace) -> int:
    """The start page, for one person on this machine: only 127.0.0.1, behind a launch token."""
    import secrets

    import uvicorn

    from surfaceqa import jobs, server
    from surfaceqa.server_start import StartMode

    port = _free_port(args.port)
    if port is None:
        return _fail(f"no free port between {args.port} and {args.port + PORTS_TRIED}; give another with --port")
    mode = StartMode(secrets.token_urlsafe(16))
    address = f"http://127.0.0.1:{port}/?token={mode.token}"
    print(f"surfaceqa: {address}\nOpen this address in a browser on this machine. Ctrl-C stops surfaceqa.")
    if not args.no_browser:
        _open_when_listening(port, address)
    try:
        with _exit_on(signal.SIGTERM, signal.SIGHUP):
            uvicorn.run(server.create_app(None, start=mode), host="127.0.0.1", port=port, log_level="warning")
    finally:
        if mode.job is not None:
            jobs.cancel(mode.job)  # a build must not go on unseen after the tool is closed
    return 0


def _leave(number: int, frame) -> None:
    raise SystemExit(128 + number)


@contextmanager
def _exit_on(*signals: int):
    """Leave in the ordinary way when the terminal is closed or the program is told to end,
    so that what must be cleared up is cleared up."""
    before = {number: signal.signal(number, _leave) for number in signals}
    try:
        yield
    finally:
        for number, handler in before.items():
            signal.signal(number, handler)


COMMANDS = {"build": _build, "serve": _serve, "finalize": _finalize, "export": _export,
            "report": _report_command, "start": _start}
HELP = ("-h", "--help")


def _with_default_command(argv: list[str]) -> list[str]:
    """`surfaceqa` alone, or with only options, means `surfaceqa start`."""
    bare = not argv or (argv[0].startswith("-") and argv[0] not in HELP)
    return ["start", *argv] if bare else argv


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = _parser().parse_args(_with_default_command(argv))
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
