"""The real MCP protocol over HTTP, with the official MCP client."""
import asyncio
import base64
import json
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from classroom_mcp.demo_provider import DemoProvider


def _port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def server(request):
    import os
    os.environ["MCP_TOKEN"] = "tok"
    from classroom_mcp.server import create_app
    port = _port()
    srv = uvicorn.Server(uvicorn.Config(create_app(DemoProvider()), port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(5)


async def call(url, tool, args=None, token="tok"):
    async with streamablehttp_client(f"{url}/mcp", headers={"Authorization": f"Bearer {token}"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool(tool, args or {})
            assert not res.isError, res.content
            return res.structuredContent or json.loads(res.content[0].text)


def test_health_is_public(server):
    assert httpx.get(f"{server}/health").json() == {"ok": True, "mode": "demo"}


def test_mcp_requires_token(server):
    r = httpx.post(f"{server}/mcp", json={})
    assert r.status_code == 401


def test_tools_over_mcp(server):
    async def go():
        async with streamablehttp_client(f"{server}/mcp", headers={"Authorization": "Bearer tok"}) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = {t.name for t in (await s.list_tools()).tools}
                assert tools == {"list_courses", "list_coursework", "list_submissions",
                                 "download_file", "set_grade", "server_info"}
    asyncio.run(go())
    courses = asyncio.run(call(server, "list_courses"))["courses"]
    assert courses[0]["id"] == "demo-it2271"
    subs = asyncio.run(call(server, "list_submissions",
                            {"course_id": "demo-it2271", "coursework_id": "cw-lab3"}))["submissions"]
    assert len(subs) == 11
    f = asyncio.run(call(server, "download_file", {"file_id": "f-s01"}))
    assert base64.b64decode(f["data_b64"]).startswith(b"%PDF")
    assert asyncio.run(call(server, "set_grade", {"course_id": "demo-it2271", "coursework_id": "cw-lab3",
                                                   "submission_id": "sub-s01", "grade": 19}))["ok"]


def test_provider_errors_become_tool_errors(server):
    async def go():
        async with streamablehttp_client(f"{server}/mcp", headers={"Authorization": "Bearer tok"}) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("list_coursework", {"course_id": "nope"})
                assert res.isError and "unknown course" in res.content[0].text
    asyncio.run(go())


class _Teacher(DemoProvider):
    """Stands in for GoogleProvider(access_token=...): lists only that teacher's course."""
    def __init__(self, token):
        super().__init__()
        self.token = token

    def list_courses(self):
        return [{"id": f"course-of-{self.token}", "name": self.token, "section": "", "link": ""}]


def test_each_teacher_acts_with_their_own_token():
    import os
    os.environ["MCP_TOKEN"] = "tok"
    from classroom_mcp.server import create_app
    port = _port()
    made = []
    srv = uvicorn.Server(uvicorn.Config(create_app(DemoProvider(), lambda t: made.append(t) or _Teacher(t)),
                                        port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    while not srv.started:
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}"

    async def courses(google=None):
        h = {"Authorization": "Bearer tok", **({"X-Google-Access-Token": google} if google else {})}
        async with streamablehttp_client(f"{url}/mcp", headers=h) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("list_courses", {})
                assert not res.isError, res.content
                data = res.structuredContent or json.loads(res.content[0].text)
                return [c["id"] for c in data["courses"]]
    try:
        assert asyncio.run(courses("asha")) == ["course-of-asha"]
        assert asyncio.run(courses("ravi")) == ["course-of-ravi"]
        assert asyncio.run(courses("asha")) == ["course-of-asha"]
        assert asyncio.run(courses()) == ["demo-it2271"]            # no token: the server's own account
        assert made == ["asha", "ravi"]                              # asha's provider was reused
    finally:
        srv.should_exit = True
        th.join(5)
