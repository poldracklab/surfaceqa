"""Identify one run of a subject by the content of what the viewer shows: surfaces and T1."""

import hashlib
from pathlib import Path

from surfaceqa.contours import SURFACE_ORDER
from surfaceqa.pipelines import SubjectFiles


def run_fingerprint(files: SubjectFiles) -> str:
    """Changes when a surface or the T1 does: the image and its geometry are reviewed too."""
    digest = hashlib.sha256()
    for name in SURFACE_ORDER:
        digest.update(name.encode())
        digest.update(Path(files.surfaces[name]).read_bytes())
    digest.update(b"t1")
    digest.update(Path(files.t1).read_bytes())
    return digest.hexdigest()[:12]
