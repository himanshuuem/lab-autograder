#!/usr/bin/env python3
"""Create .env from .env.example, filling empty secrets with random values."""
import os
import secrets
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src, dst = os.path.join(ROOT, ".env.example"), os.path.join(ROOT, ".env")
FILL = {"ADMIN_PASSWORD": 12, "SECRET_KEY": 32, "POSTGRES_PASSWORD": 24, "MCP_TOKEN": 32,
        "SANDBOX_TOKEN": 32, "JENKINS_ADMIN_PASSWORD": 12}

if os.path.exists(dst):
    print(".env already exists; leaving it alone.")
    sys.exit(0)
out = []
for line in open(src):
    key = line.split("=", 1)[0].strip()
    if key in FILL and line.strip() == f"{key}=":
        line = f"{key}={secrets.token_urlsafe(FILL[key])}\n"
    out.append(line)
# the Classroom server runs as you, so it can read and refresh secrets/token.json
out.append(f"\n# Your user and group ids (set by make init)\nHOST_UID={os.getuid()}\nHOST_GID={os.getgid()}\n")
with open(dst, "w") as f:
    f.writelines(out)
os.chmod(dst, 0o600)
os.makedirs(os.path.join(ROOT, "secrets"), exist_ok=True)
pw = next(l.split("=", 1)[1].strip() for l in out if l.startswith("ADMIN_PASSWORD="))
print(f"Created .env. Dashboard login: ta / {pw}")
