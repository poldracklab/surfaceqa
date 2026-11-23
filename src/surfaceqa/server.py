"""The web app that serves a QA directory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def create_app(qa_dir: Path) -> FastAPI:
    app = FastAPI(title="surfaceqa", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/", StaticFiles(directory=Path(qa_dir), html=True), name="qa")
    return app
