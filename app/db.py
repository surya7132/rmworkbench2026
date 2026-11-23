"""Database access: one short-lived connection per request."""
import sqlite3
from contextlib import contextmanager

from . import config


def ensure_db():
    """Build the demo database on first start (about 2 seconds)."""
    if not config.DB_PATH.exists():
        rebuild()


def rebuild():
    """Throw the database away and rebuild it from the seed. Used by 'Reset demo'."""
    from seed.build_db import build
    import shutil
    shutil.rmtree(config.UPLOAD_DIR, ignore_errors=True)   # uploaded reports belong to the old database
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    build(str(config.DB_PATH), config.DEMO_PASSWORD)
    from . import clock
    clock.restart()


@contextmanager
def connection():
    """Commit on success, roll back on error, always close."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
