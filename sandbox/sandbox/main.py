"""Sandbox HTTP API. Only this service talks to the Docker socket."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .backends import DockerBackend, LocalBackend
from .languages import LANGS
from .runner import run_program

log = logging.getLogger("sandbox")
TOKEN = os.environ.get("SANDBOX_TOKEN", "")
MAX_CONCURRENT = int(os.environ.get("SANDBOX_MAX_CONCURRENT", "4"))


def make_backend():
    kind = os.environ.get("SANDBOX_BACKEND", "docker")
    return LocalBackend() if kind == "local" else DockerBackend()


class RunRequest(BaseModel):
    language: str
    source: str = Field(max_length=200_000)
    tests: list[str] = Field(default_factory=list, max_length=100)
    entrypoint: str = "Main"
    time_limit_s: float = 2.0
    memory_mb: int | None = None


def create_app(backend=None) -> FastAPI:
    state: dict = {}

    @asynccontextmanager
    async def lifespan(app):
        state["backend"] = backend or make_backend()
        state["sem"] = asyncio.Semaphore(MAX_CONCURRENT)
        try:
            n = state["backend"].cleanup_orphans()
            if n:
                log.warning("removed %d leftover sandbox containers", n)
        except Exception as e:
            log.warning("orphan cleanup failed: %s", e)
        yield

    app = FastAPI(title="Autograder sandbox", lifespan=lifespan)

    def auth(x_sandbox_token: str = Header(default="")):
        if TOKEN and not secrets.compare_digest(x_sandbox_token, TOKEN):
            raise HTTPException(401, "bad sandbox token")

    @app.get("/health")
    def health():
        b = state["backend"]
        return {"ok": True, "backend": b.name,
                "images": {k: b.image_present(v.image) for k, v in LANGS.items()}}

    @app.post("/run", dependencies=[Depends(auth)])
    async def run(req: RunRequest):
        if req.language not in LANGS:
            raise HTTPException(400, f"unsupported language {req.language!r}")
        if any(len(t) > 2_000_000 for t in req.tests):
            raise HTTPException(400, "test input too large")
        async with state["sem"]:
            try:
                res = await asyncio.to_thread(
                    run_program, state["backend"], req.language, req.source, req.tests,
                    entrypoint=req.entrypoint, time_limit_s=req.time_limit_s,
                    memory_mb=req.memory_mb)
            except ValueError as e:
                raise HTTPException(400, str(e))
        return res.to_dict()

    return app


app = create_app()
