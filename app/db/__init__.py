"""
Database initialization script — runs on API container startup.

This script:
1. Waits for MySQL to be ready
2. Creates initial tables if they don't exist
3. Seeds default data (admin user, default provider)
4. Runs migrations if needed

Usage:
    python -m app.db.init_db
"""
from __future__ import annotations

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)


def wait_for_mysql(max_retries: int = 30, retry_delay: int = 2) -> bool:
    """Wait for MySQL to be ready."""
    from sqlalchemy import create_engine, text
    
    db_url = os.getenv("DATABASE_URL", "mysql+pymysql://ai_agent:ai_agent_secure_2026@mysql:3306/ai_agent")
    
    for i in range(max_retries):
        try:
            engine = create_engine(db_url, pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("MySQL is ready!")
            return True
        except Exception as e:
            logger.info(f"Waiting for MySQL... ({i+1}/{max_retries})")
            time.sleep(retry_delay)
    
    logger.error("MySQL not ready after %d retries", max_retries)
    return False


def seed_database():
    """Insert default data if not exists."""
    from sqlalchemy import create_engine, text
    from app.core.security import hash_password
    
    db_url = os.getenv("DATABASE_URL", "mysql+pymysql://ai_agent:ai_agent_secure_2026@mysql:3306/ai_agent")
    engine = create_engine(db_url, pool_pre_ping=True)
    
    with engine.begin() as conn:
        # Check if admin user exists
        result = conn.execute(text("SELECT COUNT(*) FROM users WHERE username='admin'"))
        count = result.scalar()
        
        if count == 0:
            logger.info("Creating default admin user...")
            hashed_pw = hash_password("admin123")
            conn.execute(text("""
                INSERT INTO users (username, email, hashed_password, is_active)
                VALUES ('admin', 'admin@example.com', :password, TRUE)
            """), {"password": hashed_pw})
            logger.info("Admin user created (username: admin, password: admin123)")
        
        # Insert default provider if not exists
        result = conn.execute(text("SELECT COUNT(*) FROM providers WHERE name='Agnes AI'"))
        count = result.scalar()
        
        if count == 0:
            logger.info("Creating default Agnes AI provider...")
            agnes_api_key = os.getenv("AGNES_API_KEY", "sk-0T1BpcsI51cKxXgWZejpvONrcUs8vDc1Tqzz7NkObIWAyezd")
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
    
    # Step 1: Wait for MySQL
    if not wait_for_mysql():
        logger.error("Failed to connect to MySQL")
        sys.exit(1)
    
    # Step 2: Seed database
    seed_database()
    
    logger.info("Database initialization completed!")


if __name__ == "__main__":
    main()
