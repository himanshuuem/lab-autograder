"""Teachers and their Google accounts.

Each teacher signs in with Google (OAuth web flow, restricted to ALLOWED_DOMAIN) and grants
the app Classroom and Drive access; the grant (a refresh token) is kept encrypted with
SECRET_KEY, and every Classroom call is made with that teacher's own access token. Admins
are ADMIN_EMAILS (and the local ADMIN_USER form); with SIGNUP=approve a new teacher waits
until an admin lets them in.
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy import select

from .clients import ClassroomClient, ServiceError
from .config import settings
from .models import Course, User

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# what the Classroom server needs (mcp_server/classroom_mcp/google_provider.py), plus who you are
SCOPES = [
    "openid", "email", "profile",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.profile.emails",
    "https://www.googleapis.com/auth/drive.readonly",
]


class SignInError(Exception):
    pass


# ---------------------------------------------------------------- the grant, encrypted
def _fernet():
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(("google-token:" + settings.secret_key).encode()).digest())
    return Fernet(key)


def seal(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode() if token else ""


def unseal(sealed: str) -> str:
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(sealed.encode()).decode() if sealed else ""
    except InvalidToken:          # SECRET_KEY changed: the teacher signs in again
        return ""


# ---------------------------------------------------------------- OAuth web flow
def redirect_uri() -> str:
    return f"{settings.public_url}/api/auth/google/callback"


def auth_url(state: str) -> str:
    q = {"client_id": settings.google_client_id, "redirect_uri": redirect_uri(), "response_type": "code",
         "scope": " ".join(SCOPES), "access_type": "offline", "include_granted_scopes": "true",
         "prompt": "consent select_account", "state": state}
    if settings.allowed_domain:
        q["hd"] = settings.allowed_domain          # Google shows only college accounts
    return f"{AUTH_URL}?{urlencode(q)}"


def _post_token(data: dict) -> dict:
    """Google's token endpoint (tests replace this)."""
    r = httpx.post(TOKEN_URL, data=data, timeout=20)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200:
        raise SignInError(body.get("error_description") or body.get("error") or f"Google said {r.status_code}")
    return body


def _claims(id_token: str) -> dict:
    """The ID token's claims. It came straight from Google's token endpoint over TLS, so
    its signature needn't be checked (OpenID Connect Core 3.1.3.7)."""
    payload = id_token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def exchange_code(code: str) -> tuple[dict, dict]:
    tok = _post_token({"code": code, "client_id": settings.google_client_id,
                       "client_secret": settings.google_client_secret,
                       "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
    if "id_token" not in tok:
        raise SignInError("Google didn't say who signed in")
    return _claims(tok["id_token"]), tok


def _now():
    return datetime.now(timezone.utc)


def sign_in_with_google(db, claims: dict, tokens: dict) -> User:
    email = (claims.get("email") or "").lower()
    if not email or not claims.get("email_verified", False):
        raise SignInError("Google didn't confirm the email address")
    domain = email.rsplit("@", 1)[-1]
    if settings.allowed_domain and domain != settings.allowed_domain and email not in settings.admin_emails:
        raise SignInError(f"Sign in with your @{settings.allowed_domain} account")
    granted = set((tokens.get("scope") or "").split())
    missing = [s.rsplit("/", 1)[-1] for s in SCOPES[3:] if granted and s not in granted]
    if missing:
        raise SignInError("Allow access to Google Classroom and Drive when Google asks "
                          f"(missing: {', '.join(missing)})")
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, role="teacher", status="active" if settings.signup == "open" else "pending")
        db.add(user)
    if email in settings.admin_emails:
        user.role, user.status = "admin", "active"
    user.name = claims.get("name") or user.name or email
    user.picture = claims.get("picture") or ""
    if tokens.get("refresh_token"):
        user.google_token = seal(tokens["refresh_token"])
        _cache.pop(user.id, None)
    user.last_seen_at = _now()
    db.flush()
    if user.is_admin:
        adopt_unowned_courses(db, user)
    return user


def local_admin(db) -> User:
    """The ADMIN_USER / ADMIN_PASSWORD account: an admin, acting through the server's own
    Google token (secrets/token.json) or the demo classroom."""
    email = f"{settings.admin_user}@local"
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, name=settings.admin_user)
        db.add(user)
    user.role, user.status, user.last_seen_at = "admin", "active", _now()
    db.flush()
    adopt_unowned_courses(db, user)
    return user


def adopt_unowned_courses(db, admin: User) -> None:
    """Courses loaded before teachers had accounts belong to the first admin who signs in."""
    for c in db.scalars(select(Course).where(~Course.teachers.any())):
        c.teachers.append(admin)


# ---------------------------------------------------------------- acting as a teacher
_cache: dict[int, tuple[str, float]] = {}
_lock = threading.Lock()


def access_token(user: User) -> str:
    """A fresh access token from the teacher's grant (Google's last about an hour)."""
    with _lock:
        hit = _cache.get(user.id)
        if hit and hit[1] > time.time() + 120:
            return hit[0]
    refresh = unseal(user.google_token)
    if not refresh:
        raise ServiceError(f"{user.name or user.email} hasn't connected Google Classroom: sign out and sign in with Google")
    try:
        tok = _post_token({"client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                           "refresh_token": refresh, "grant_type": "refresh_token"})
    except SignInError as e:
        raise ServiceError(f"Google access for {user.email} stopped working ({e}): sign out and sign in again")
    except httpx.HTTPError as e:
        raise ServiceError(f"cannot reach Google: {e}")
    with _lock:
        _cache[user.id] = (tok["access_token"], time.time() + int(tok.get("expires_in", 3600)))
    return tok["access_token"]


def classroom_for(user: User | None, course: Course | None = None) -> ClassroomClient:
    """The Classroom, as seen by this teacher. For a course they don't teach (an admin
    helping out), as one of its teachers. Without Google sign-in set up, everyone uses the
    server's own account (token.json or the demo classroom)."""
    if not settings.google_login:
        return ClassroomClient()
    who = user
    if course is not None and user is not None and user not in course.teachers:
        who = next((t for t in course.teachers if t.google_token), user)
    if who is not None and who.google_token:
        return ClassroomClient(access_token=access_token(who))
    if user is None or user.is_admin:
        return ClassroomClient()          # the server's own token.json
    raise ServiceError("Connect your Google Classroom: sign out and sign in with Google")
