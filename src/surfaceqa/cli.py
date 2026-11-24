"""Command line entry point: surfaceqa build | serve | finalize | export | report."""

import argparse
import sys
from pathlib import Path

from surfaceqa.build import BuildResult, build_all
from surfaceqa.discover import find_subjects, source_root
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
    try:
        refs = find_subjects(sources, args.subjects)
    except ValueError as error:
        return _fail(str(error))
    if not refs:
        return _fail("no subjects found (a subject is a folder containing mri/ and surf/)")
    results = build_all(refs, out, jobs=args.jobs)
    save_sources(out, sources)
    if args.rerun_template is not None:
        save_rerun_template(out, sorted({ref.source for ref in refs}), args.rerun_template)
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


COMMANDS = {"build": _build, "serve": _serve, "finalize": _finalize, "export": _export,
            "report": _report_command}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
