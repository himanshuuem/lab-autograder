from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import api, grading
from .config import settings
from .db import init_engine
from .worker import Worker

STATIC = Path(__file__).resolve().parent.parent / "static"


def create_app(start_worker: bool | None = None) -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    os.makedirs(settings.data_dir, exist_ok=True)
    init_engine(settings.database_url)
    worker = Worker(lambda jid: grading.run_grade_job(jid, api.classroom_client(), api.sandbox_client()))

    @asynccontextmanager
    async def lifespan(app):
        if settings.start_worker if start_worker is None else start_worker:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(title="Autograder", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.worker = worker
    app.include_router(api.public)
    app.include_router(api.api)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app() if os.environ.get("AUTOGRADER_NO_APP") != "1" else None
