from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./autograder.db"))
    data_dir: str = field(default_factory=lambda: _env("DATA_DIR", "./data"))
    mcp_url: str = field(default_factory=lambda: _env("MCP_URL", "http://localhost:8200/mcp"))
    mcp_token: str = field(default_factory=lambda: _env("MCP_TOKEN"))
    sandbox_url: str = field(default_factory=lambda: _env("SANDBOX_URL", "http://localhost:8100"))
    sandbox_token: str = field(default_factory=lambda: _env("SANDBOX_TOKEN"))
    admin_user: str = field(default_factory=lambda: _env("ADMIN_USER", "ta"))
    admin_password: str = field(default_factory=lambda: _env("ADMIN_PASSWORD", "change-me"))
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", "dev-secret-change-me"))
    grading_workers: int = field(default_factory=lambda: int(_env("GRADING_WORKERS", "4")))
    start_worker: bool = field(default_factory=lambda: _env("START_WORKER", "1") == "1")
    cookie_secure: bool = field(default_factory=lambda: _env("COOKIE_SECURE", "0") == "1")
    # Sign in with Google, one account per teacher (see README, "Sharing with colleagues")
    google_client_id: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_SECRET"))
    public_url: str = field(default_factory=lambda: _env("PUBLIC_URL", "http://localhost:8000").rstrip("/"))
    allowed_domain: str = field(default_factory=lambda: _env("ALLOWED_DOMAIN").lower().lstrip("@"))
    admin_emails: list = field(default_factory=lambda: [e.strip().lower() for e in _env("ADMIN_EMAILS").split(",")
                                                         if e.strip()])
    # approve: a new teacher waits until an admin lets them in; open: anyone from the domain
    signup: str = field(default_factory=lambda: _env("SIGNUP", "approve").lower())
    # the ADMIN_USER / ADMIN_PASSWORD form (always an admin); 0 hides it once Google sign-in works
    local_login: bool = field(default_factory=lambda: _env("LOCAL_LOGIN", "1") == "1")

    @property
    def google_login(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


settings = Settings()
