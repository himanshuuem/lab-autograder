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


settings = Settings()
