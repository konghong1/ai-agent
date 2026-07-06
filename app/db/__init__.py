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

from app.db_url import normalize_db_url

logger = logging.getLogger(__name__)


def _detect_db_type() -> str:
    """Detect database type from DATABASE_URL environment variable."""
    db_url = normalize_db_url()
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
    db_url = normalize_db_url()
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
    """Insert default data (admin user + default provider) if not present.

    Uses the ORM so model-level defaults (e.g. ``chunking_strategy``) are applied,
    which avoids raw-SQL NOT-NULL violations on columns that only have a Python-side
    default.
    """
    from app.core.database import SessionLocal
    from app.models import Provider, User, PromptTemplate

    agnes_api_key = os.getenv(
        "AGNES_API_KEY", "sk-0T1BpcsI51cKxXgWZejpvONrcUs8vDc1Tqzz7NkObIWAyezd"
    )
    # Password: admin123
    admin_pw_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewH5F5jPHssXwRiG"

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").first()
        if admin is None:
            admin = User(
                username="admin",
                email="admin@example.com",
                password_hash=admin_pw_hash,
                role="admin",
                enabled=True,
            )
            db.add(admin)
            db.flush()
            logger.info("Created default admin user (username: admin, password: admin123)")

        provider_exists = (
            db.query(Provider).filter_by(name="Agnes AI").first() is not None
        )
        if not provider_exists:
            db.add(
                Provider(
                    user_id=admin.id,
                    name="Agnes AI",
                    base_url="https://apihub.agnes-ai.com/v1",
                    api_key=agnes_api_key,
                    provider_type="openai-compatible",
                    enabled=True,
                    is_default=True,
                )
            )
            logger.info("Created default Agnes AI provider")

        # Seed default prompt templates so the chat "提示词" dropdown is usable
        tmpl_count = db.query(PromptTemplate).count()
        if tmpl_count == 0:
            db.add_all([
                PromptTemplate(
                    user_id=admin.id,
                    name="通用助手",
                    slug="general-assistant",
                    system_prompt="你是一个乐于助人的 AI 助手，用简洁、准确的中文回答用户的问题。",
                    variables=[],
                    category="通用",
                    description="默认通用对话助手",
                    enabled=True,
                    is_default=True,
                ),
                PromptTemplate(
                    user_id=admin.id,
                    name="代码专家",
                    slug="code-expert",
                    system_prompt="你是一名资深软件工程师，善于用 {{language}} 等语言编写清晰、可维护的代码，并解释关键设计。",
                    variables=["language"],
                    category="编程",
                    description="编程与代码帮手",
                    enabled=True,
                    is_default=False,
                ),
                PromptTemplate(
                    user_id=admin.id,
                    name="翻译官",
                    slug="translator",
                    system_prompt="你是一名专业翻译，将用户的内容翻译为 {{target_lang}}，保持原意与语气。",
                    variables=["target_lang"],
                    category="翻译",
                    description="多语言翻译",
                    enabled=True,
                    is_default=False,
                ),
                PromptTemplate(
                    user_id=admin.id,
                    name="写作助手",
                    slug="writer",
                    system_prompt="你是一名写作助手，帮助用户撰写结构清晰、有感染力的文章与文案。",
                    variables=[],
                    category="写作",
                    description="文章与文案写作",
                    enabled=True,
                    is_default=False,
                ),
                PromptTemplate(
                    user_id=admin.id,
                    name="数据分析师",
                    slug="data-analyst",
                    system_prompt="你是一名数据分析师，擅长解读数据、给出图表建议并用通俗语言解释结论。",
                    variables=[],
                    category="数据分析",
                    description="数据分析与解读",
                    enabled=True,
                    is_default=False,
                ),
            ])
            logger.info("Created 5 default prompt templates")

        db.commit()
    finally:
        db.close()


def create_tables() -> None:
    """Create all tables from the ORM models (idempotent).

    The MySQL-compatible models in ``app.models`` are the source of truth for the
    schema. Running this on every startup guarantees the tables exist (and match
    the code) regardless of whether the docker SQL init script has run yet.
    """
    from app.core.database import Base, engine
    from app import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    logger.info("Ensured database schema exists")


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

    # Step 2: Ensure schema exists (idempotent; matches ORM models exactly)
    create_tables()

    # Step 3: Seed default data
    seed_database()

    logger.info("Database initialization completed!")


if __name__ == "__main__":
    main()
