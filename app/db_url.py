"""Normalize a SQLAlchemy database URL to include an explicit, installed driver.

The ``docker/.env`` file builds URLs like ``mysql://user:pass@host/db`` without a
driver prefix. SQLAlchemy's *default* MySQL dialect is ``mysql+mysqldb`` — i.e. the
``MySQLdb`` C extension — which is **not** installed in the image. Only ``pymysql``
(pure Python) and ``psycopg2-binary`` ship in ``requirements.txt``.

If we hand ``mysql://...`` to ``create_engine`` it silently falls back to ``MySQLdb``
and crashes with ``ModuleNotFoundError: No module named 'MySQLdb'``. This helper injects
the correct, available driver so the app never depends on an uninstalled one.
"""
from __future__ import annotations

import os


def normalize_db_url(url: str | None = None) -> str:
    """Return *url* with an explicit, available sync driver.

    Mapping (idempotent — already-prefixed URLs are returned unchanged):
        mysql://...            -> mysql+pymysql://...
        postgresql://...       -> postgresql+psycopg2://...
        sqlite://...           -> unchanged
        anything already with a +driver -> unchanged

    If *url* is empty, the value is taken from the ``DATABASE_URL`` env var
    (falling back to the settings default).
    """
    if not url:
        try:
            from app.settings import get_settings

            url = get_settings().database_url
        except Exception:
            url = os.getenv("DATABASE_URL", "")
    if not url:
        return url

    lowered = url.lower()
    # Already carries an explicit driver (e.g. mysql+pymysql) -> leave as-is.
    if "+" in lowered.split("://", 1)[0]:
        return url
    if lowered.startswith("mysql://"):
        return "mysql+pymysql://" + url[len("mysql://"):]
    if lowered.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url
