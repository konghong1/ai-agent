from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
_database_url = settings.database_url

# Detect dialect from the database URL prefix.
if _database_url.startswith("sqlite"):
    # SQLite needs check_same_thread=False for single-threaded apps.
    engine = create_engine(_database_url, connect_args={"check_same_thread": False})
elif _database_url.startswith("mysql"):
    engine = create_engine(_database_url, pool_pre_ping=True)
elif _database_url.startswith("postgresql"):
    engine = create_engine(_database_url, pool_pre_ping=True)
else:
    engine = create_engine(_database_url)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
