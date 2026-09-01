"""Database connection and session management for RecoverOS."""

import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://recoveros:recoveros_dev_2024@localhost:5432/recoveros")

# Create engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_engine():
    """Get the database engine."""
    return engine


def get_db_session() -> Generator[Session, None, None]:
    """Get a database session for dependency injection."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_db_session_context():
    """Get a database session as a context manager."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# For backward compatibility with seed script
get_db_session = get_db_session_context


class Base:
    """Base class for all ORM models."""
    pass
