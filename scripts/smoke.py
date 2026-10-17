#!/usr/bin/env python3
"""End-to-end check of a running stack (used by `make smoke` and Jenkins).

Signs in, loads courses from the Classroom MCP server, grades the first
assignment through the sandbox, and checks the results look sane.
Only needs the Python standard library.

    python3 scripts/smoke.py http://localhost:8000 ta <password> [--grade]

With CLASSROOM_MODE=demo it grades the demo class. With google it only checks
that your real courses load, unless --grade is given: grading downloads and
re-grades real students' work (your score overrides are kept).
"""
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

args = [a for a in sys.argv[1:] if a != "--grade"]
grade_real = "--grade" in sys.argv[1:]
base = (args[0] if len(args) > 0 else "http://localhost:8000").rstrip("/")
user = args[1] if len(args) > 1 else "ta"
pw = args[2] if len(args) > 2 else "change-me"
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
mode = st["classroom"].get("mode")
step(f"sync from Classroom ({mode} mode)"); call("POST", "/api/courses/sync")
courses = call("GET", "/api/courses")
demo = [c for c in courses if c["ext_id"].startswith("demo-")]
real = [c for c in courses if not c["ext_id"].startswith("demo-")]
if mode == "demo":
    pick = demo
    assert pick, "the demo course did not load"
else:
    pick = [c for c in real if c["assignments"]]
    assert real, "no Google Classroom courses loaded"
    print(f"   {len(real)} course(s): " + "; ".join(f"{c['name']} ({len(c['assignments'])} assignments)"
                                                   for c in real))
    if demo:
        print(f"   note: {len(demo)} demo course(s) from an earlier demo run are still in the database")
    if not grade_real:
        print("   grading skipped: it would re-grade real students' work (pass --grade to do it)")
        print("SMOKE TEST PASSED")
        sys.exit(0)
    assert pick, "no course has assignments to grade"
course = pick[0]
assert course["assignments"], f"{course['name']} has no assignments"
aid = course["assignments"][0]["id"]
step(f"grade {course['name']}: {course['assignments'][0]['title']}")
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
if mode == "demo":
    full = {r["student"]["name"] for r in subs if r["final_score"] == 20}
    assert {"Ananya Bose", "Sneha Paul", "Priya Dutta"} <= full, f"expected full marks, got {full}"
    assert call("GET", f"/api/assignments/{aid}/similarity"), "expected a similar pair in the demo class"
print("SMOKE TEST PASSED")
