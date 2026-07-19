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

from sqlalchemy import create_engine, inspect as sa_inspect, text
from sqlalchemy.schema import CreateColumn

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
            if "mysql" in db_url.lower():
                engine = create_engine(db_url, pool_pre_ping=True, connect_args={"charset": "utf8mb4"})
            else:
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
    from app.core.security import hash_password
    from app.models import Provider, User, PromptTemplate
    from app.gallery_config import seed_gallery_config

    agnes_api_key = os.getenv(
        "AGNES_API_KEY", "sk-0T1BpcsI51cKxXgWZejpvONrcUs8vDc1Tqzz7NkObIWAyezd"
    )
    # Password: admin123 (hashed with the same pbkdf2_sha256 context the
    # app uses at runtime — the previous hardcoded bcrypt hash could never
    # be verified, making the default admin account unloginable).
    init_pw = os.getenv("INIT_SUPERUSER_PASSWORD", "admin123")
    admin_pw_hash = hash_password(init_pw)

    db = SessionLocal()
    try:
        init_email = os.getenv("INIT_SUPERUSER_EMAIL", "admin@example.com")
        admin = db.query(User).filter_by(username="admin").first()
        if admin is None:
            admin = User(
                username="admin",
                email=init_email,
                password_hash=admin_pw_hash,
                role="admin",
                is_superuser=True,
                enabled=True,
            )
            db.add(admin)
            db.flush()
            logger.info("Created default admin user (username: admin, password: admin123)")
        else:
            # 历史库已存在 username="admin" 记录（旧 seed / 手工创建的残留）。
            # ADR-028：保证平台主管理员（bootstrap admin）始终为超级管理员，且凭据
            # 对齐到 .env 的 INIT_SUPERUSER_EMAIL / INIT_SUPERUSER_PASSWORD
            # （默认值 admin@example.com / admin123）。仅影响这一条 bootstrap 账号，
            # 绝不触碰其他用户；若管理员已为超级管理员且邮箱已对齐，则保持原密码不变。
            target_email = os.getenv("INIT_SUPERUSER_EMAIL", "admin@example.com")
            align = False
            if not admin.is_superuser:
                admin.is_superuser = True
                align = True  # 首次补提时一并对齐凭据，确保可用 admin@example.com / 配置密码登录
                logger.info("Promoted existing username=admin to superuser (is_superuser=True)")
            if admin.email != target_email:
                admin.email = target_email
                align = True
                logger.info("Aligned bootstrap admin email -> %s", target_email)
            if align:
                # admin_pw_hash 已在上方按 INIT_SUPERUSER_PASSWORD 计算
                admin.password_hash = admin_pw_hash
                logger.info("Aligned bootstrap admin password to INIT_SUPERUSER_PASSWORD")

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

        # 电商套图固定配置落库（策划类型/个性化字段含下拉选项/通用·市场·输出选项/套图种子）
        added = seed_gallery_config(db)
        if added:
            logger.info("Seeded %d gallery config rows into gallery_configs", added)

        # 为所有现有用户补齐个人空间基础权限（PERSONAL_DEFAULT）。
        # 用 backfill_base_permissions 保证基础码（含新增 hook.view/providers.view/prompt.view）
        # 始终存在，避免「权限驱动菜单」切换或默认集扩展后既有用户缺菜单。
        # 权限码统一真源为 resources(type='permission')，由 rbac_seed.seed_rbac_resources
        # 从 CATALOG 常量种子化（见 ADR-031），不再单独维护 permission_catalog 表。
        from app.permissions import backfill_base_permissions
        all_users = db.query(User).all()
        for u in all_users:
            backfill_base_permissions(u.id, db)
        logger.info(
            "Seeded permission catalog and backfilled base permissions for %d users", len(all_users)
        )

        # RBAC v2 地基种子：资源(菜单+权限) / 角色 / 用户-角色回填（幂等）。
        from app.rbac_seed import seed_rbac_resources, seed_rbac_roles, backfill_user_roles

        seed_rbac_resources(db)
        seed_rbac_roles(db)
        backfill_user_roles(db)
        logger.info("Seeded RBAC v2 resources/roles and backfilled user roles")

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


def ensure_indexes() -> None:
    """Idempotently create indexes that accelerate common queries but may be
    absent on databases bootstrapped *before* the index was added to the ORM.

    ``Base.metadata.create_all`` only creates *missing tables* — it never adds an
    index to an already-existing table. So a DB created before
    ``ix_messages_thread_created`` existed would keep doing a filesort on
    ``WHERE thread_id = ? ORDER BY created_at`` and, on MySQL with a small
    ``sort_buffer_size``, raise ``OperationalError (1038, 'Out of sort memory')``
    once a thread accumulates enough messages. This closes that gap without
    touching tables that already have the index.
    """
    from app.core.database import engine
    from sqlalchemy import inspect as sa_inspect, text as sa_text

    desired = [
        (
            "messages",
            "ix_messages_thread_created",
            "CREATE INDEX ix_messages_thread_created ON messages (thread_id, created_at)",
        ),
    ]
    inspector = sa_inspect(engine)
    for table, name, ddl in desired:
        try:
            existing = {idx["name"] for idx in inspector.get_indexes(table, bind=engine)}
        except Exception:
            existing = set()
        if name in existing:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(sa_text(ddl))
            logger.info("ensure_indexes: created %s on %s", name, table)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ensure_indexes: could not create %s on %s: %s", name, table, exc)


def sync_model_columns() -> None:
    """自动对齐 ORM 模型与数据库表的列，避免新增字段在旧库上运行时崩溃。

    SQLAlchemy ``Base.metadata.create_all`` 只会创建缺失的表，不会给已存在的表
    追加新列。随着模型迭代，旧数据库（例如 MySQL 生产库、本地 SQLite 历史库）
    的表结构会落后于 ``app/models.py``。此函数在启动时自动检测并补全缺失列，使
    「代码模型」成为 schema 的唯一可信源，无需手动写 ``ALTER TABLE``。

    策略：
    - 仅追加缺失列，不删除、不修改已有列（保守安全）。
    - 主键列 / 外键约束列跳过（ALTER TABLE 无法追加主键）。
    - 如果模型列是 NOT NULL 且没有默认值，则先以 NULLABLE 追加并告警，避免在
      已存在行上违反 NOT NULL 约束；运营需要时再手动回填数据并改为 NOT NULL。
    - 支持 SQLite / MySQL / PostgreSQL（通过 SQLAlchemy 方言编译类型）。
    """
    from app import models  # noqa: F401  (register all models on Base.metadata)
    from app.core.database import Base, engine

    inspector = sa_inspect(engine)
    for table in Base.metadata.sorted_tables:
        try:
            existing = {c["name"] for c in inspector.get_columns(table.name, bind=engine)}
        except Exception:
            existing = set()

        for column in table.columns:
            if column.name in existing:
                continue
            if column.primary_key:
                logger.warning(
                    "sync_model_columns: skip PK column %s.%s (cannot ADD COLUMN primary key)",
                    table.name,
                    column.name,
                )
                continue

            try:
                col_ddl = str(CreateColumn(column).compile(dialect=engine.dialect))
                # 如果模型是 NOT NULL 且无默认值，在旧库上直接 ADD NOT NULL 会失败；
                # 把它改成 NULLABLE 追加，并记录警告以便后续人工回填。
                if not column.nullable and column.server_default is None and column.default is None:
                    logger.warning(
                        "sync_model_columns: %s.%s is NOT NULL without default; adding as NULLABLE, "
                        "please backfill data and set NOT NULL manually if required",
                        table.name,
                        column.name,
                    )
                    col_ddl = col_ddl.replace("NOT NULL", "NULL")
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {col_ddl}"
                with engine.begin() as conn:
                    conn.execute(text(ddl))
                logger.info(
                    "sync_model_columns: added %s.%s to %s",
                    table.name,
                    column.name,
                    engine.url.drivername,
                )
            except Exception as exc:
                logger.warning(
                    "sync_model_columns: could not add %s.%s: %s",
                    table.name,
                    column.name,
                    exc,
                )


def ensure_gallery_record_columns() -> None:
    """历史兼容：gallery_records 追加过多次后增列，统一由 sync_model_columns 处理。"""
    sync_model_columns()


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

    # Step 2b: Ensure performance indexes exist even on legacy databases
    # (see ensure_indexes for why this matters).
    ensure_indexes()

    # Step 2c: Ensure gallery_records has the model-recording columns even on
    # legacy databases (see ensure_gallery_record_columns for why).
    ensure_gallery_record_columns()

    # Step 3: Seed default data
    seed_database()

    logger.info("Database initialization completed!")


if __name__ == "__main__":
    main()
