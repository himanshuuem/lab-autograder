#!/usr/bin/env python3
"""Connect Lab Grader to your Google Classroom (run once, on a computer with a browser).

1. Put the OAuth client file from Google Cloud at secrets/credentials.json (see README).
2. Run: make google-auth
3. Sign in with the Google account you use for Classroom and allow access.
This writes secrets/token.json, then lists your courses to prove it works.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mcp_server"))
from classroom_mcp.google_provider import SCOPES  # noqa: E402  (one list of scopes)

SECRETS = os.environ.get("SECRETS_DIR", os.path.join(ROOT, "secrets"))
CRED = os.path.join(SECRETS, "credentials.json")
TOKEN = os.path.join(SECRETS, "token.json")

if not os.path.exists(CRED):
    sys.exit(f"Missing {CRED}.\nCreate an OAuth client of type 'Desktop app' in Google Cloud Console, "
             "download its JSON, and save it there. The README walks through it.")

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

flow = InstalledAppFlow.from_client_secrets_file(CRED, SCOPES)
try:
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent", access_type="offline")
except Exception as e:
    sys.exit(f"Sign-in did not complete: {e}")
with open(TOKEN, "w") as f:
    f.write(creds.to_json())
os.chmod(TOKEN, 0o600)
print(f"Saved {TOKEN}")

svc = build("classroom", "v1", credentials=creds, cache_discovery=False)
courses = svc.courses().list(teacherId="me", courseStates=["ACTIVE"]).execute().get("courses", [])
if not courses:
    print("Signed in, but this account teaches no active courses. Check you used your Classroom account.")
for c in courses:
    print(f"  {c['name']}  {c.get('section', '')}  (id {c['id']})")
print("\nNext: set CLASSROOM_MODE=google in .env, then run: docker compose up -d mcp app")
print("If the dashboard runs on another machine, copy secrets/token.json into that machine's secrets/ folder.")
