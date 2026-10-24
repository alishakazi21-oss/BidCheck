"""
BidCheck - Database session management.

Provides a reusable session factory and a FastAPI dependency for
injecting database sessions into route handlers.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session, sessionmaker

from app.models.database import get_engine, create_tables


# Module-level engine and session factory (created once at import time)
_engine = get_engine()
create_tables(_engine)

SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for database sessions (for use outside FastAPI)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.
    Rolls back on exception; always closes on exit.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
