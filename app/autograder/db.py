from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
SessionLocal = sessionmaker(expire_on_commit=False)


def init_engine(url: str):
    global _engine
    kw = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
    _engine = create_engine(url, **kw)
    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _fk(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    SessionLocal.configure(bind=_engine)
    from . import models  # noqa: F401  register tables
    Base.metadata.create_all(_engine)
    _add_missing_columns(_engine)
    return _engine


def _add_missing_columns(eng) -> list[str]:
    """Tiny forward-only migration: add columns that newer versions introduced, so
    upgrading keeps existing data. Every new column must be nullable or have a
    server_default."""
    from sqlalchemy import inspect, text
    insp = inspect(eng)
    added = []
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(dialect=eng.dialect)}'
                if col.server_default is not None:
                    default = col.server_default.arg
                    default = default.compile(dialect=eng.dialect) if hasattr(default, "compile") else default
                    ddl += f" DEFAULT {default}"
                conn.execute(text(ddl))
                added.append(f"{table.name}.{col.name}")
    if added:
        import logging
        logging.getLogger("db").info("added columns: %s", ", ".join(added))
    return added


def engine():
    return _engine


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
