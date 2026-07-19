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
    # pool_recycle 回收空闲过久的连接，避免 Docker 部署下连接被服务端/
    # 防火墙断开后复用触发 "Can't reconnect until invalid transaction is rolled back"
    # 显式 charset=utf8mb4 防止历史 cp1252/latin1 连接导致中文 double-mojibake
    engine = create_engine(
        _database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"charset": "utf8mb4"},
    )
elif _database_url.startswith("postgresql"):
    engine = create_engine(_database_url, pool_pre_ping=True, pool_recycle=1800)
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
    # users.is_superuser（超级管理员标识）
    if insp.has_table("users"):
        u_cols = {c["name"] for c in insp.get_columns("users")}
        if "is_superuser" not in u_cols:
            with engine.connect() as conn:
                # BOOLEAN 非 TEXT，MySQL 可带默认值，SQLite 同样兼容，避开 1101 坑
                conn.execute(text("ALTER TABLE users ADD COLUMN is_superuser BOOLEAN DEFAULT 0"))
                conn.commit()
                logger.info("Added is_superuser column to users")

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
        # gallery_records.prompt_short / prompt_en_short（最简短场景提示词，用于实际生成降本提速）
        # 同样不加默认值（MySQL 不允许 TEXT 列带 DEFAULT），应用层用 or "" 兜底。
        for col in ("prompt_short", "prompt_en_short"):
            if col not in gr_cols:
                with engine.connect() as conn:
                    conn.execute(text(
                        f"ALTER TABLE gallery_records ADD COLUMN {col} TEXT"
                    ))
                    conn.commit()
                    logger.info(f"Added {col} column to gallery_records")
        # gallery_records.error（失败原因留痕，便于直接查库定位而非翻日志）。
        # 注意：TEXT 列在 MySQL 不允许带 DEFAULT，故不加默认值（列允许 NULL，应用层兜底）。
        if "error" not in gr_cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE gallery_records ADD COLUMN error TEXT"))
                conn.commit()
                logger.info("Added error column to gallery_records")

    # ── gallery_tasks.name（套图任务命名；模型新增列，运行时迁移补齐）──
    # 注意：运行时 init_db 路径此前未对齐该列（仅 CLI sync_model_columns 覆盖），
    # 导致旧库创建新套图任务时触发 "no such column: gallery_tasks.name"。
    # name 可空（模型侧 default="" 在插入时补默认值），故不加 NOT NULL。
    if insp.has_table("gallery_tasks"):
        gt_cols = {c["name"] for c in insp.get_columns("gallery_tasks")}
        if "name" not in gt_cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE gallery_tasks ADD COLUMN name VARCHAR(200)"))
                conn.commit()
                logger.info("Added name column to gallery_tasks")

    # ── MCP Servers 扩展列（MCP/Skill/Hook 扩展，Phase 0）──
    # 注意：TEXT/JSON 在 MySQL 不允许带 DEFAULT，此处一律不加默认值（列允许 NULL，应用层兜底）。
    if insp.has_table("mcp_servers"):
        ms_cols = {c["name"] for c in insp.get_columns("mcp_servers")}
        _mcp_alters = {
            "auth_type": "VARCHAR(20) DEFAULT 'none'",
            "api_key": "TEXT",
            "headers": "TEXT",
            "tool_allowlist": "JSON",
            "timeout_ms": "INTEGER",
            "max_retries": "INTEGER DEFAULT 2",
        }
        for _col, _ddl in _mcp_alters.items():
            if _col not in ms_cols:
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE mcp_servers ADD COLUMN {_col} {_ddl}"))
                    conn.commit()
                    logger.info(f"Added {_col} column to mcp_servers")

    # ── Skills 运行时扩展列（Skill 目录 + use_skill，Phase 4）──
    # 注意：TEXT/JSON 在 MySQL 不允许带 DEFAULT，此处一律不加默认值（列允许 NULL，应用层兜底）。
    if insp.has_table("skills"):
        sk_cols = {c["name"] for c in insp.get_columns("skills")}
        _skill_alters = {
            "content": "TEXT",
            "trigger_words": "JSON",
            "declared_hooks": "JSON",
            "version": "INTEGER DEFAULT 1",
        }
        for _col, _ddl in _skill_alters.items():
            if _col not in sk_cols:
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE skills ADD COLUMN {_col} {_ddl}"))
                    conn.commit()
                    logger.info(f"Added {_col} column to skills")

    # ── ToolCallAudit 扩展（Hook 执行留痕/错误，Phase 4）──
    # 注意：TEXT 在 MySQL 不允许带 DEFAULT，故不加默认值（列允许 NULL）。
    if insp.has_table("tool_call_audit"):
        ta_cols = {c["name"] for c in insp.get_columns("tool_call_audit")}
        if "error" not in ta_cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE tool_call_audit ADD COLUMN error TEXT"))
                conn.commit()
                logger.info("Added error column to tool_call_audit")
