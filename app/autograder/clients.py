"""Clients for the Classroom MCP server and the sandbox."""
from __future__ import annotations

import asyncio
import base64
import json
from contextlib import asynccontextmanager

import httpx

from .config import settings


class ServiceError(RuntimeError):
    pass


@asynccontextmanager
async def _mcp_streams(url: str, headers: dict):
    try:  # mcp >= 1.24
        from mcp.client.streamable_http import streamable_http_client
        async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(120, read=300)) as hc:
            async with streamable_http_client(url, http_client=hc) as streams:
                yield streams
    except ImportError:
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(url, headers=headers, timeout=120) as streams:
            yield streams


class ClassroomClient:
    """Synchronous wrapper: each call opens a short MCP session."""

    def __init__(self, url: str | None = None, token: str | None = None, access_token: str | None = None):
        self.url = url or settings.mcp_url
        self.token = settings.mcp_token if token is None else token
        self.access_token = access_token          # the signed-in teacher's Google token

    async def _call(self, tool: str, args: dict) -> dict:
        from mcp import ClientSession
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        if self.access_token:
            headers["X-Google-Access-Token"] = self.access_token
        async with _mcp_streams(self.url, headers) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
                text = " ".join(getattr(c, "text", "") for c in res.content)
                if res.isError:
                    raise ServiceError(f"Classroom: {text or 'tool error'}")
                if res.structuredContent is not None:
                    return res.structuredContent
                return json.loads(text)

    def call(self, tool: str, **args) -> dict:
        try:
            return asyncio.run(self._call(tool, args))
        except ServiceError:
            raise
        except Exception as e:
            raise ServiceError(f"cannot reach the Classroom MCP server at {self.url}: "
                               f"{e.__class__.__name__}: {e}") from e

    # convenience
    def courses(self):
        return self.call("list_courses")["courses"]

    def coursework(self, course_id):
        return self.call("list_coursework", course_id=course_id)["coursework"]

    def submissions(self, course_id, coursework_id):
        return self.call("list_submissions", course_id=course_id, coursework_id=coursework_id)["submissions"]

    def download(self, file_id) -> tuple[str, bytes]:
        r = self.call("download_file", file_id=file_id)
        return r["title"], base64.b64decode(r["data_b64"])

    def set_grade(self, course_id, coursework_id, submission_id, grade, assign=False):
        return self.call("set_grade", course_id=course_id, coursework_id=coursework_id,
                         submission_id=submission_id, grade=grade, assign=assign)

    def info(self):
        return self.call("server_info")


class SandboxClient:
    def __init__(self, url: str | None = None, token: str | None = None, transport=None):
        self.url = (url or settings.sandbox_url).rstrip("/")
        self.token = settings.sandbox_token if token is None else token
        self.transport = transport

    def _client(self):
        return httpx.Client(transport=self.transport, timeout=httpx.Timeout(600, connect=10),
                            headers={"X-Sandbox-Token": self.token})

    def run(self, language: str, source: str, tests: list[str], *, entrypoint: str = "Main",
            time_limit_s: float = 2.0) -> dict:
        try:
            with self._client() as c:
                r = c.post(f"{self.url}/run", json={
                    "language": language, "source": source, "tests": tests,
                    "entrypoint": entrypoint, "time_limit_s": time_limit_s})
        except httpx.HTTPError as e:
            raise ServiceError(f"cannot reach the sandbox at {self.url}: {e}") from e
        if r.status_code != 200:
            raise ServiceError(f"sandbox error {r.status_code}: {r.text[:300]}")
        return r.json()

    def health(self) -> dict:
        with self._client() as c:
            return c.get(f"{self.url}/health").json()
