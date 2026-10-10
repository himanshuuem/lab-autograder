"""Google Classroom MCP server (streamable HTTP at /mcp).

CLASSROOM_MODE=google  real Classroom + Drive, as the teacher whose access token comes
                       with the request (X-Google-Access-Token), else as token.json
CLASSROOM_MODE=demo    built-in sample course (default)
"""
from __future__ import annotations

import base64
import contextvars
import logging
import os
import secrets
from collections import OrderedDict
from typing import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from .provider import Provider, ProviderError

log = logging.getLogger("classroom.mcp")

# the signed-in teacher's Google access token for the request being handled
GOOGLE_TOKEN: contextvars.ContextVar[str] = contextvars.ContextVar("google_token", default="")


def make_provider() -> Provider:
    mode = os.environ.get("CLASSROOM_MODE", "demo").lower()
    if mode == "google":
        from .google_provider import GoogleProvider
        return GoogleProvider()
    from .demo_provider import DemoProvider
    return DemoProvider()


def make_user_provider() -> Callable[[str], Provider] | None:
    """How to act as the teacher whose token came with a request (google mode only)."""
    if os.environ.get("CLASSROOM_MODE", "demo").lower() != "google":
        return None
    from .google_provider import GoogleProvider
    return lambda token: GoogleProvider(access_token=token)


class _PerTeacher:
    """One provider per teacher token (it caches class rosters), the newest few kept."""

    def __init__(self, default: Provider, factory: Callable[[str], Provider] | None, keep: int = 32):
        self.default, self.factory, self.keep = default, factory, keep
        self._cache: OrderedDict[str, Provider] = OrderedDict()

    def current(self) -> Provider:
        token = GOOGLE_TOKEN.get()
        if not token or self.factory is None:
            return self.default
        p = self._cache.pop(token, None) or self.factory(token)
        self._cache[token] = p
        while len(self._cache) > self.keep:
            self._cache.popitem(last=False)
        return p


def build_server(provider: Provider, user_provider: Callable[[str], Provider] | None = None) -> FastMCP:
    providers = _PerTeacher(provider, user_provider)
    mcp = FastMCP(
        "google-classroom",
        instructions="Read Google Classroom courses, assignments and student submissions, "
                     "download submitted files, and record grades.",
        stateless_http=True,
        json_response=True,
        # only reachable on the private compose network; Host is "mcp:8200" there
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )

    def guard(fn, *a):
        try:
            return fn(*a)
        except ProviderError as e:
            raise ValueError(str(e)) from e

    @mcp.tool()
    def list_courses() -> dict:
        """Active courses where the signed-in user is a teacher."""
        return {"courses": guard(providers.current().list_courses)}

    @mcp.tool()
    def list_coursework(course_id: str) -> dict:
        """Assignments in a course, with their attached material files."""
        return {"coursework": guard(providers.current().list_coursework, course_id)}

    @mcp.tool()
    def list_submissions(course_id: str, coursework_id: str) -> dict:
        """Every student's submission for an assignment, with attached files."""
        return {"submissions": guard(providers.current().list_submissions, course_id, coursework_id)}

    @mcp.tool()
    def download_file(file_id: str) -> dict:
        """Download a Drive file (Google Docs are exported as PDF). Returns base64 data."""
        f = guard(providers.current().download_file, file_id)
        return {"file_id": f["file_id"], "title": f["title"], "mime": f["mime"],
                "size": len(f["data"]), "data_b64": base64.b64encode(f["data"]).decode()}

    @mcp.tool()
    def set_grade(course_id: str, coursework_id: str, submission_id: str,
                  grade: float, assign: bool = False) -> dict:
        """Set the draft grade; with assign=true also set the assigned (returned) grade."""
        return guard(providers.current().set_grade, course_id, coursework_id, submission_id, grade, assign)

    @mcp.tool()
    def server_info() -> dict:
        """Which provider is active (demo or google)."""
        return {"mode": provider.mode}

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request):
        return JSONResponse({"ok": True, "mode": provider.mode})

    return mcp


class BearerAuth:
    """Require `Authorization: Bearer <MCP_TOKEN>` on everything except /health, and pass
    the teacher's Google token (X-Google-Access-Token) on to the tools."""

    def __init__(self, app, token: str):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        if self.token and scope.get("path") != "/health":
            got = headers.get(b"authorization", b"").decode()
            if not secrets.compare_digest(got, f"Bearer {self.token}"):
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        reset = GOOGLE_TOKEN.set(headers.get(b"x-google-access-token", b"").decode())
        try:
            await self.app(scope, receive, send)
        finally:
            GOOGLE_TOKEN.reset(reset)


def create_app(provider: Provider | None = None, user_provider: Callable[[str], Provider] | None = None):
    if provider is None:
        provider, user_provider = make_provider(), make_user_provider()
    mcp = build_server(provider, user_provider)
    return BearerAuth(mcp.streamable_http_app(), os.environ.get("MCP_TOKEN", ""))


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8200")))


if __name__ == "__main__":
    main()
