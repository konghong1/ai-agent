"""
Database initialization module — runs on API container startup.

This script:
1. Waits for the configured database to be ready
2. Creates initial tables if they don't exist (via SQLAlchemy)
3. Seeds default data (admin user, default provider)

Supported DATABASE_URL prefixes: mysql, postgresql, sqlite

Usage:
    python -m app.db.init_db
"""
from __future__ import annotations

import logging
import os
import sys
import time

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


def _detect_db_type() -> str:
    """Detect database type from DATABASE_URL environment variable."""
    db_url = os.getenv("DATABASE_URL", "")
    if "mysql" in db_url.lower():
        return "mysql"
    elif "postgresql" in db_url.lower():
        return "postgresql"
    elif "sqlite" in db_url.lower():
        return "sqlite"
    return "unknown"


def wait_for_database(max_retries: int = 30, retry_delay: int = 2) -> bool:
    """Wait for the configured database to be ready.

    Automatically detects the database type from DATABASE_URL prefix.
    """
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logger.error("DATABASE_URL environment variable is not set!")
        return False

    db_type = _detect_db_type()
    logger.info("Detected database type: %s", db_type)

    for i in range(max_retries):
        try:
            engine = create_engine(db_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("%s database is ready!", db_type.upper())
            return True
        except Exception as e:
            logger.info("Waiting for %s... (%d/%d)", db_type, i + 1, max_retries)
            time.sleep(retry_delay)

    logger.error("%s database not ready after %d retries", db_type.upper(), max_retries)
    return False


def seed_database():
    """Insert default data if not exists."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logger.warning("DATABASE_URL not set, skipping seed")
        return

    db_type = _detect_db_type()
    engine = create_engine(db_url, pool_pre_ping=True)

    with engine.begin() as conn:
        # Check if admin user exists
        result = conn.execute(text("SELECT COUNT(*) FROM users WHERE username='admin'"))
        count = result.scalar()

        if count == 0:
            logger.info("Creating default admin user...")
            # Password: admin123
            hashed_pw = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewH5F5jPHssXwRiG"

            if db_type == "postgresql":
                # PostgreSQL boolean literals are lowercase
                conn.execute(text("""
                    INSERT INTO users (username, email, password_hash, role, enabled)
                    VALUES ('admin', 'admin@example.com', :password, 'admin', TRUE)
                """), {"password": hashed_pw})
            else:
                conn.execute(text("""
                    INSERT INTO users (username, email, password_hash, role, enabled)
                    VALUES ('admin', 'admin@example.com', :password, 'admin', TRUE)
                """), {"password": hashed_pw})

            logger.info("Admin user created (username: admin, password: admin123)")

        # Insert default provider if not exists
        result = conn.execute(text("SELECT COUNT(*) FROM providers WHERE name='Agnes AI'"))
        count = result.scalar()

        if count == 0:
            logger.info("Creating default Agnes AI provider...")
            agnes_api_key = os.getenv("AGNES_API_KEY", "sk-0T1BpcsI51cKxXgWZejpvONrcUs8vDc1Tqzz7NkObIWAyezd")

            if db_type == "postgresql":
                conn.execute(text("""
                    INSERT INTO providers (user_id, name, base_url, api_key, provider_type, is_default, enabled)
                    SELECT u.id, 'Agnes AI', 'https://apihub.agnes-ai.com/v1', :api_key, 'openai-compatible', TRUE, TRUE
                    FROM users u WHERE u.username='admin'
                """), {"api_key": agnes_api_key})
            else:
                conn.execute(text("""
                    INSERT INTO providers (user_id, name, base_url, api_key, provider_type, is_default, enabled)
                    SELECT u.id, 'Agnes AI', 'https://apihub.agnes-ai.com/v1', :api_key, 'openai-compatible', TRUE, TRUE
                    FROM users u WHERE u.username='admin'
                """), {"api_key": agnes_api_key})
            logger.info("Default provider created")


def main():
    """Run database initialization."""
    logging.basicConfig(level=logging.INFO)

    logger.info("=" * 60)
    logger.info("Starting database initialization...")
    logger.info("=" * 60)

    # Step 1: Wait for DB
    if not wait_for_database():
        logger.error("Failed to connect to database")
        sys.exit(1)

    # Step 2: Seed database
    seed_database()

    logger.info("Database initialization completed!")


if __name__ == "__main__":
    main()
