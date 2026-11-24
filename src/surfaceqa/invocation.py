"""Recover a subject's original command line and compose the commands that rerun it."""

import shlex
from pathlib import Path

FASTSURFER_FLAGS = {"seg": ["--edits"], "surf": ["--edits", "--surf_only"]}
RECON_ALL_STAGES = {"pial": ["-autorecon-pial"], "wm": ["-autorecon2-wm", "-autorecon3"],
                    "cp": ["-autorecon2-cp", "-autorecon3"]}
REPLACED_FLAGS = ("--edits", "--surf_only", "--seg_only")  # a rerun sets these itself
STATUS_WORDS = {"finished", "exited"}  # recon-all's own closing lines also start with its name
FASTSURFER_PLACEHOLDER = "run_fastsurfer.sh <the options of the first run>"
RECON_ALL_PLACEHOLDER = "<the other options of the first run, such as -T2pial>"
# Options of a first run that a rerun must not repeat, with how many values follow each:
# its inputs and subject, and add-on analyses that are not part of rebuilding the surfaces.
# Compared in lower case with one dash, as recon-all accepts several spellings.
DROPPED = {"-i": 1, "-t2": 1, "-flair": 1, "-s": 1, "-subjid": 1, "-subject": 1, "-sid": 1,
           "-long": 2, "-all": 0, "-brainstem-structures": 0, "-qcache": 0,
           "-hippocampal-subfields-t1": 0, "-hippocampal-subfields-t2": 2,
           "-hippocampal-subfields-t1t2": 2}
RERUN_FLAGS = {"-autorecon2-wm", "-autorecon2-cp", "-autorecon-pial", "-autorecon-bfs"}  # after an edit
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
    if not words or Path(words[0]).name != "recon-all" or STATUS_WORDS & set(words):
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


def first_run_commands(subject_dir: Path, pipeline: str) -> list[str]:
    """The commands that made the subject, before any rerun after an edit."""
    first = []
    for command in all_commands(subject_dir, pipeline):
        if first and RERUN_FLAGS & set(command.split()):
            break
        first.append(command)
    return first


def _words(command: str | None) -> list[str] | None:
    try:
        return shlex.split(command or "") or None
    except ValueError:
        return None


def _fastsurfer_rerun(words: list[str] | None, flags: list[str]) -> str:
    if words is None:
        return " ".join([FASTSURFER_PLACEHOLDER, *flags])
    kept = [word for word in words if word not in REPLACED_FLAGS]
    return shlex.join(kept + flags)


def _spelling(word: str) -> str:
    return "-" + word.lstrip("-").lower()


def _option_groups(words: list[str]) -> list[list[str]]:
    """Each kept option of a command with its values, without inputs, subject and stage flags."""
    groups, skip = [], 0
    for word in words[1:]:
        name = _spelling(word)
        if skip:
            skip -= 1
        elif name in DROPPED:
            skip = DROPPED[name]
        elif name == "-expert":
            groups.append(["-xopts-use"])
            skip = 1
        elif word.startswith("-") and not name.startswith("-autorecon"):
            groups.append([word])
        elif not word.startswith("-") and groups:
            groups[-1].append(word)
    return groups


def _kept_options(commands: list[list[str]]) -> list[str]:
    """The options of the first run's stages, each once, as first given."""
    kept: dict[str, list[str]] = {}
    for words in commands:
        for group in _option_groups(words):
            kept.setdefault(group[0], group)
    return [word for group in kept.values() for word in group]


def _subject_words(words: list[str] | None, name: str) -> list[str]:
    """How the rerun names its subject: `-s name`, or the first run's `-long timepoint base`."""
    spelled = [_spelling(word) for word in words or []]
    if "-long" in spelled and len(words) > spelled.index("-long") + 2:
        at = spelled.index("-long")
        return ["-long", *words[at + 1:at + 3]]
    return ["-s", name]


def _recon_all_rerun(words: list[str] | None, stages: list[str], name: str,
                     more: list[list[str]]) -> str:
    start = shlex.join(["recon-all", *_subject_words(words, name), *stages])
    if words is None:
        return f"{start} {RECON_ALL_PLACEHOLDER}"
    return " ".join([start, shlex.join(_kept_options([words, *more]))]).strip()


def _bare_commands(pipeline: str, command: str | None, name: str, more) -> dict[str, str]:
    words = _words(command)
    if pipeline == "fastsurfer":
        return {key: _fastsurfer_rerun(words, flags) for key, flags in FASTSURFER_FLAGS.items()}
    if pipeline == "freesurfer":
        later = [w for w in (_words(c) for c in more) if w]
        return {key: _recon_all_rerun(words, stages, name, later)
                for key, stages in RECON_ALL_STAGES.items()}
    return {}


def rerun_commands(pipeline: str, command: str | None, name: str,
                   template: str | None = None, more: tuple[str, ...] | list[str] = ()) -> dict[str, str]:
    """The rerun command for each kind of edit.

    `template` is the user's launch line; `more` are the later stages of a first run that
    was done in several commands, whose options a rerun needs as well.
    """
    commands = _bare_commands(pipeline, command, name, more)
    if not template:
        return commands
    return {key: template.replace(PLACEHOLDER, value) for key, value in commands.items()}
