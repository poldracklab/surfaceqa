"""Recover a subject's original command line and compose the commands that rerun it."""

import shlex
from pathlib import Path

FASTSURFER_FLAGS = {"seg": ["--edits"], "surf": ["--edits", "--surf_only"]}
RECON_ALL_STAGES = {"pial": ["-autorecon-pial"], "wm": ["-autorecon2-wm", "-autorecon3"],
                    "cp": ["-autorecon2-cp", "-autorecon3"]}
FASTSURFER_PLACEHOLDER = "run_fastsurfer.sh <the options of the first run>"
RECON_ALL_PLACEHOLDER = "<the other options of the first run, such as -T2pial>"
DROPPED_WITH_VALUE = {"-i", "-T2", "-FLAIR", "-s", "-subjid", "-subject", "-sid"}
PLACEHOLDER = "{command}"


def _lines(path: Path) -> list[str]:
    try:
        return path.read_text(errors="replace").splitlines()
    except OSError:
        return []


def _fastsurfer_commands(scripts: Path) -> list[str]:
    prefix = "Invocation:"
    found = (line[len(prefix):].strip() for line in _lines(scripts / "deep-seg.log")
             if line.startswith(prefix))
    return [command for command in found if command]


def _recon_all_call(line: str, following: str) -> str | None:
    """The command when `line` starts one; recon-all 6 put the arguments on the next line."""
    words = line.split()
    if not words or Path(words[0]).name != "recon-all":
        return None
    if len(words) == 1:
        return f"{line.strip()} {following.strip()}" if following.lstrip().startswith("-") else None
    return line.strip() if words[1].startswith("-") else None


def _recon_all_commands(scripts: Path) -> list[str]:
    lines = _lines(scripts / "recon-all.log")
    calls = (_recon_all_call(line, following) for line, following in zip(lines, lines[1:] + [""]))
    return [call for call in calls if call]


def all_commands(subject_dir: Path, pipeline: str) -> list[str]:
    """Every command line the subject's log recorded, oldest first."""
    scripts = Path(subject_dir) / "scripts"
    if pipeline == "fastsurfer":
        return _fastsurfer_commands(scripts)
    return _recon_all_commands(scripts) if pipeline == "freesurfer" else []


def original_command(subject_dir: Path, pipeline: str) -> str | None:
    """The command of the subject's first run as its log recorded it, or None."""
    return next(iter(all_commands(subject_dir, pipeline)), None)


def _words(command: str | None) -> list[str] | None:
    try:
        return shlex.split(command or "") or None
    except ValueError:
        return None


def _fastsurfer_rerun(words: list[str] | None, flags: list[str]) -> str:
    if words is None:
        return " ".join([FASTSURFER_PLACEHOLDER, *flags])
    kept = [word for word in words if word not in ("--edits", "--surf_only")]
    return shlex.join(kept + flags)


def _kept_options(words: list[str]) -> list[str]:
    """The first run's options without its inputs, its subject and its stage flags."""
    kept, skip = [], False
    for word in words[1:]:
        if skip:
            skip = False
        elif word in DROPPED_WITH_VALUE:
            skip = True
        elif word == "-expert":
            kept.append("-xopts-use")
            skip = True
        elif word != "-all" and not word.startswith("-autorecon"):
            kept.append(word)
    return kept


def _recon_all_rerun(words: list[str] | None, stages: list[str], name: str) -> str:
    start = shlex.join(["recon-all", "-s", name, *stages])
    if words is None:
        return f"{start} {RECON_ALL_PLACEHOLDER}"
    return " ".join([start, shlex.join(_kept_options(words))]).strip()


def _bare_commands(pipeline: str, command: str | None, name: str) -> dict[str, str]:
    words = _words(command)
    if pipeline == "fastsurfer":
        return {key: _fastsurfer_rerun(words, flags) for key, flags in FASTSURFER_FLAGS.items()}
    if pipeline == "freesurfer":
        return {key: _recon_all_rerun(words, stages, name)
                for key, stages in RECON_ALL_STAGES.items()}
    return {}


def rerun_commands(pipeline: str, command: str | None, name: str,
                   template: str | None = None) -> dict[str, str]:
    """The rerun command for each kind of edit; `template` is the user's launch line."""
    commands = _bare_commands(pipeline, command, name)
    if not template:
        return commands
    return {key: template.replace(PLACEHOLDER, value) for key, value in commands.items()}
