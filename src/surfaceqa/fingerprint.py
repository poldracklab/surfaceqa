"""Identify one run of a subject by the content of its surface files."""

import hashlib
from pathlib import Path

from surfaceqa.contours import SURFACE_ORDER


def surface_fingerprint(surfaces: dict[str, Path]) -> str:
    digest = hashlib.sha256()
    for name in SURFACE_ORDER:
        digest.update(name.encode())
        digest.update(Path(surfaces[name]).read_bytes())
    return digest.hexdigest()[:12]
