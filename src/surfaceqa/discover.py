"""Find subject folders inside source folders."""

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


@dataclass(frozen=True)
class SubjectRef:
    source: str
    name: str
    path: Path

    @property
    def key(self) -> str:
        return f"{self.source}__{self.name}"


def is_subject(path: Path) -> bool:
    return (path / "mri").is_dir() and (path / "surf").is_dir() and "fsaverage" not in path.name


def _subject_dirs(source: Path) -> list[Path]:
    if is_subject(source):
        return [source]
    return [p for p in sorted(source.iterdir()) if p.is_dir() and is_subject(p)]


def _matches(name: str, patterns: list[str] | None) -> bool:
    return not patterns or any(fnmatch(name, p) for p in patterns)


def source_root(source: Path) -> Path:
    """The subjects folder a source refers to: itself, or its parent if it is one subject."""
    source = Path(source).resolve()
    return source.parent if is_subject(source) else source


def _check_unique_keys(refs: list[SubjectRef]) -> None:
    by_key: dict[str, SubjectRef] = {}
    for ref in refs:
        other = by_key.setdefault(ref.key, ref)
        if other.path != ref.path:
            raise ValueError(
                f"two subjects would both be stored as {ref.key}: {other.path} and {ref.path}. "
                "Rename one of the source folders so their names differ.")


def find_subjects(sources: list[Path], patterns: list[str] | None = None) -> list[SubjectRef]:
    paths = {path for source in sources for path in _subject_dirs(Path(source).resolve())}
    refs = [SubjectRef(source=path.parent.name, name=path.name, path=path)
            for path in paths if _matches(path.name, patterns)]
    _check_unique_keys(refs)
    return sorted(refs, key=lambda r: r.key)
