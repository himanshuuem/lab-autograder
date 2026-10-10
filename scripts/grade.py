#!/usr/bin/env python3
"""Grade one assignment through the dashboard API (stdlib only).

    python3 scripts/grade.py URL USER PASSWORD [COURSE_EXT_ID] [ASSIGNMENT_EXT_ID] [--publish-draft] [--stdout-csv]
Blank ids pick the first course / assignment. Progress goes to stderr.
"""
import http.cookiejar
import json
import sys
import time
import urllib.request

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
base, user, pw = args[0].rstrip("/"), args[1], args[2]
course_ext = args[3] if len(args) > 3 else ""
assign_ext = args[4] if len(args) > 4 else ""
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def call(method, path, body=None, raw=False):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=300) as r:
        data = r.read()
    return data if raw else json.loads(data or b"null")


call("POST", "/api/login", {"username": user, "password": pw})
call("POST", "/api/courses/sync")
aid = None
for c in call("GET", "/api/courses"):
    for a in c["assignments"]:
        d = call("GET", f"/api/assignments/{a['id']}")
        if (not course_ext or d["course_ext_id"] == course_ext) and (not assign_ext or d["ext_id"] == assign_ext):
            aid = a["id"]
            break
    if aid:
        break
if aid is None:
    sys.exit(f"no assignment matches course={course_ext or 'any'} assignment={assign_ext or 'any'}")
log(f"grading assignment {aid}")
job = call("POST", f"/api/assignments/{aid}/grade")
while job["status"] in ("queued", "running"):
    time.sleep(2)
    job = call("GET", f"/api/jobs/{job['id']}")
    log(f"  {job['progress']}/{job['total']}  {job['message']}")
if job["status"] != "done":
    sys.exit(f"grading failed: {job['message']}")
if "--publish-draft" in flags:
    log(call("POST", f"/api/assignments/{aid}/publish", {"assign": False}))
csv = call("GET", f"/api/assignments/{aid}/export.csv", raw=True)
if "--stdout-csv" in flags:
    sys.stdout.write(csv.decode())
else:
    name = f"grades-{aid}.csv"
    open(name, "wb").write(csv)
    log(f"wrote {name}")
