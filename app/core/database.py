from __future__ import annotations

import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.db_url import normalize_db_url
from app.settings import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


settings = get_settings()
_database_url = normalize_db_url(settings.database_url)

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

    # ── Lightweight SQLite migration: add columns that create_all can't ──
    _migrate_sqlite_columns()


def _migrate_sqlite_columns() -> None:
    """Add new columns to existing SQLite tables (create_all only creates new tables)."""
    from sqlalchemy import text, inspect

    insp = inspect(engine)
    if not insp.has_table("knowledge_bases"):
        return

    existing_cols = {c["name"] for c in insp.get_columns("knowledge_bases")}

    if "rag_config" not in existing_cols:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE knowledge_bases ADD COLUMN rag_config JSON DEFAULT '{}' "
            ))
            conn.commit()
            logger.info("Added rag_config column to knowledge_bases")

    # gallery_plan_items.product_image（策划项单独商品图）
    if insp.has_table("gallery_plan_items"):
        gpi_cols = {c["name"] for c in insp.get_columns("gallery_plan_items")}
        if "product_image" not in gpi_cols:
            with engine.connect() as conn:
                # 注意：SQLite 对已有数据的表不允许直接 ADD NOT NULL 列，
                # 因此此处加可空列（模型侧 default="" 会在插入时补默认值）。
                conn.execute(text(
                    "ALTER TABLE gallery_plan_items ADD COLUMN product_image VARCHAR(512)"
                ))
                conn.commit()
                logger.info("Added product_image column to gallery_plan_items")

    # gallery_records.task_id（关联异步生成任务）
    if insp.has_table("gallery_records"):
        gr_cols = {c["name"] for c in insp.get_columns("gallery_records")}
        if "task_id" not in gr_cols:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE gallery_records ADD COLUMN task_id INTEGER"
                ))
                conn.commit()
                logger.info("Added task_id column to gallery_records")
        # gallery_records.prompt_en（英文版生成提示词）
        if "prompt_en" not in gr_cols:
            with engine.connect() as conn:
                # 注意：MySQL 不允许 TEXT/BLOB 列带 DEFAULT，故此处不加默认值（SQLite 同样兼容）
                conn.execute(text(
                    "ALTER TABLE gallery_records ADD COLUMN prompt_en TEXT"
                ))
                conn.commit()
                logger.info("Added prompt_en column to gallery_records")
        # gallery_records.prompt_source（提示词来源：ai / template）
        if "prompt_source" not in gr_cols:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE gallery_records ADD COLUMN prompt_source VARCHAR(16) DEFAULT 'template'"
                ))
                conn.commit()
                logger.info("Added prompt_source column to gallery_records")
        # gallery_records.prompt_input / prompt_raw（提示词溯源：喂给模型的输入 & 模型原始输出）
        # 用 inspect 结果判断，SQLite 与 MySQL 通用（MySQL 重复 ADD COLUMN 会报错，故先检查）。
        # 注意：MySQL 不允许 TEXT/BLOB 列带 DEFAULT，故此处一律不加默认值（列允许 NULL，应用层用 or "" 兜底）。
        for col in ("prompt_input", "prompt_raw"):
            if col not in gr_cols:
                with engine.connect() as conn:
                    conn.execute(text(
                        f"ALTER TABLE gallery_records ADD COLUMN {col} TEXT"
                    ))
                    conn.commit()
                    logger.info(f"Added {col} column to gallery_records")
