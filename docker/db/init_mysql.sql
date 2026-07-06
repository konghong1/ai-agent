-- MySQL initialization for the AI Agent Platform.
-- The application manages its own schema via SQLAlchemy (create_all) on startup,
-- so this script only guarantees the database exists with the correct charset.
-- (Keeping it minimal avoids conflicting with the ORM-managed tables.)

CREATE DATABASE IF NOT EXISTS `ai_agent` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
