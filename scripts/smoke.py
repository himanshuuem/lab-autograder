#!/usr/bin/env python3
"""End-to-end check of a running stack (used by `make smoke` and Jenkins).

Signs in, loads courses from the Classroom MCP server, grades the first
assignment through the sandbox, and checks the results look sane.
Only needs the Python standard library.

    python3 scripts/smoke.py http://localhost:8000 ta <password>
"""
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
user = sys.argv[2] if len(sys.argv) > 2 else "ta"
pw = sys.argv[3] if len(sys.argv) > 3 else "change-me"
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=120) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        sys.exit(f"FAIL {method} {path}: {e.code} {e.read()[:300]!r}")


def step(msg):
    print(f"-- {msg}", flush=True)


for i in range(60):
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=5) as r:
            if json.loads(r.read())["database"] == "ok":
                break
    except Exception:
        pass
    time.sleep(2)
else:
    sys.exit("FAIL app never became healthy")

step("sign in"); call("POST", "/api/login", {"username": user, "password": pw})
step("service status")
st = call("GET", "/api/status")
assert st["classroom"]["ok"], st
assert st["sandbox"]["ok"], st
missing = [k for k, v in (st["sandbox"].get("images") or {}).items() if not v]
if missing:
    sys.exit(f"FAIL runner images missing for {missing}: run `make images`")
step("sync from Classroom"); call("POST", "/api/courses/sync")
courses = call("GET", "/api/courses")
assert courses and courses[0]["assignments"], "no courses/assignments"
aid = courses[0]["assignments"][0]["id"]
step("grade assignment")
job = call("POST", f"/api/assignments/{aid}/grade")
for _ in range(600):
    job = call("GET", f"/api/jobs/{job['id']}")
    if job["status"] in ("done", "failed"):
        break
    time.sleep(1)
assert job["status"] == "done", job
subs = call("GET", f"/api/assignments/{aid}/submissions")["rows"]
graded = [r for r in subs if r["status"] == "GRADED"]
errors = [r for r in subs if r["status"] == "ERROR"]
print(f"   {len(subs)} submissions, {len(graded)} graded, {len(errors)} errors")
for r in sorted(subs, key=lambda r: r["student"]["name"]):
    print(f"   {r['student']['name']:<16} {str(r['final_score']):>6}  {', '.join(f['code'] for f in r['flags'])}")
assert graded, "nothing was graded"
assert not errors, f"submissions in ERROR: {[e['student']['name'] for e in errors]}"
if st["classroom"].get("mode") == "demo":
    full = {r["student"]["name"] for r in subs if r["final_score"] == 20}
    assert {"Ananya Bose", "Sneha Paul", "Priya Dutta"} <= full, f"expected full marks, got {full}"
    assert call("GET", f"/api/assignments/{aid}/similarity"), "expected a similar pair in the demo class"
print("SMOKE TEST PASSED")
