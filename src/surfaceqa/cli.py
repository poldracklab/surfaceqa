"""Command line entry point: surfaceqa build | serve."""

import argparse
import sys
from pathlib import Path

from surfaceqa.build import BuildResult, build_all
from surfaceqa.discover import find_subjects, source_root
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
    serve = commands.add_parser("serve", help="open a QA directory in the browser")
    serve.add_argument("qa_dir", type=Path)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--blind", action="store_true",
                       help="shuffle the subjects per reviewer and hide indicator results until "
                            "the reviewer submits")
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
    roots = [source_root(source) for source in sources]
    out = (args.out or roots[0].parent / "surfaceqa").resolve()
    if _inside(out, roots):
        return _fail(f"--out {out} is inside a source folder; nothing is written into the input data")
    try:
        refs = find_subjects(sources, args.subjects)
    except ValueError as error:
        return _fail(str(error))
    if not refs:
        return _fail("no subjects found (a subject is a folder containing mri/ and surf/)")
    results = build_all(refs, out, jobs=args.jobs)
    write_site(out)
    _report(results)
    print(f"Report: {out / 'index.html'}  (view with: surfaceqa serve {out})")
    return 1 if any(r.status == "failed" for r in results) else 0


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    from surfaceqa import server

    qa_dir = args.qa_dir.resolve()
    if not (qa_dir / "index.html").is_file():
        return _fail(f"{qa_dir} has no index.html; run `surfaceqa build` first")
    print(f"surfaceqa: http://{args.host}:{args.port}/")
    uvicorn.run(server.create_app(qa_dir, blind=args.blind), host=args.host, port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return _build(args) if args.command == "build" else _serve(args)


if __name__ == "__main__":
    sys.exit(main())
