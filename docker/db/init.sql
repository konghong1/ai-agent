-- ===================================================================
-- AI Agent Platform - MySQL Initialization Script
-- Database: ai_agent
-- Tables: All core tables with proper indexes
-- ===================================================================

-- ── Create Database ─────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS `ai_agent` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `ai_agent`;

-- ── Users ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `hashed_password` VARCHAR(255) NOT NULL,
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_username` (`username`),
    INDEX `idx_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Threads ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `threads` (
    `id` CHAR(36) NOT NULL PRIMARY KEY,
    `user_id` INT NOT NULL,
    `title` VARCHAR(255) NOT NULL DEFAULT '',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_threads` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Messages ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `messages` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `thread_id` CHAR(36) NOT NULL,
    `user_id` INT NOT NULL,
    `role` VARCHAR(20) NOT NULL,
    `content` TEXT NOT NULL DEFAULT '',
    `extra` JSON NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`thread_id`) REFERENCES `threads`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_thread_messages` (`thread_id`, `created_at`),
    INDEX `idx_user_messages` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Media Assets ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `media_assets` (
    `id` CHAR(36) NOT NULL PRIMARY KEY,
    `user_id` INT NOT NULL,
    `message_id` INT NULL,
    `media_type` VARCHAR(20) NOT NULL DEFAULT 'image',
    `object_key` VARCHAR(500) NOT NULL UNIQUE,
    `file_size` INT NULL,
    `mime_type` VARCHAR(100) NULL,
    `width` INT NULL,
    `height` INT NULL,
    `internal_url` VARCHAR(1000) NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'queued',
    `error_message` TEXT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`message_id`) REFERENCES `messages`(`id`) ON DELETE SET NULL,
    INDEX `idx_user_type` (`user_id`, `media_type`),
    INDEX `idx_status_created` (`status`, `created_at`),
    INDEX `idx_object_key` (`object_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Providers ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `providers` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `base_url` VARCHAR(500) NOT NULL DEFAULT '',
    `api_key` VARCHAR(500) NOT NULL DEFAULT '',
    `provider_type` VARCHAR(50) NOT NULL DEFAULT 'openai-compatible',
    `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
    `is_default` BOOLEAN NOT NULL DEFAULT FALSE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_default` (`user_id`, `is_default`),
    INDEX `idx_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Provider Models ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `provider_models` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `provider_id` INT NOT NULL,
    `model_name` VARCHAR(200) NOT NULL,
    `model_type` VARCHAR(50) NOT NULL DEFAULT 'chat',
    FOREIGN KEY (`provider_id`) REFERENCES `providers`(`id`) ON DELETE CASCADE,
    INDEX `idx_provider_type` (`provider_id`, `model_type`),
    INDEX `idx_model_name` (`model_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Agents ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `agents` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(200) NOT NULL,
    `description` TEXT NOT NULL DEFAULT '',
    `system_prompt` TEXT NOT NULL DEFAULT '',
    `model_name` VARCHAR(200) NOT NULL DEFAULT 'gpt-4',
    `provider_id` INT NULL,
    `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`provider_id`) REFERENCES `providers`(`id`) ON DELETE SET NULL,
    INDEX `idx_user_agents` (`user_id`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Knowledge Bases ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `knowledge_bases` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(200) NOT NULL,
    `description` TEXT NOT NULL DEFAULT '',
    `embedding_model` VARCHAR(200) NOT NULL DEFAULT 'text-embedding-3-small',
    `chunk_size` INT NOT NULL DEFAULT 500,
    `chunk_overlap` INT NOT NULL DEFAULT 50,
    `rag_config` JSON NULL,
    `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_kb` (`user_id`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── KB Folders ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `kb_folders` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `kb_id` INT NOT NULL,
    `name` VARCHAR(200) NOT NULL,
    `parent_id` INT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`parent_id`) REFERENCES `kb_folders`(`id`) ON DELETE SET NULL,
    INDEX `idx_kb_folders` (`kb_id`, `parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── KB Documents ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `kb_documents` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `kb_id` INT NOT NULL,
    `folder_id` INT NULL,
    `original_filename` VARCHAR(500) NOT NULL,
    `stored_filename` VARCHAR(500) NOT NULL,
    `file_size` INT NOT NULL,
    `mime_type` VARCHAR(100) NOT NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'uploading',
    `error_message` TEXT NULL,
    `uploaded_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`folder_id`) REFERENCES `kb_folders`(`id`) ON DELETE SET NULL,
    INDEX `idx_kb_docs` (`kb_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── KB Chunks ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `kb_chunks` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `kb_id` INT NOT NULL,
    `document_id` INT NOT NULL,
    `vector_id` VARCHAR(200) NOT NULL UNIQUE,
    `chunk_index` INT NOT NULL,
    `content` TEXT NOT NULL,
    `metadata_` JSON NULL,
    FOREIGN KEY (`kb_id`) REFERENCES `knowledge_bases`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`document_id`) REFERENCES `kb_documents`(`id`) ON DELETE CASCADE,
    INDEX `idx_kb_chunks` (`kb_id`, `document_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Skills ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `skills` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(200) NOT NULL,
    `description` TEXT NOT NULL DEFAULT '',
    `content` TEXT NOT NULL,
    `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_skills` (`user_id`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── MCP Servers ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `mcp_servers` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(120) NOT NULL,
    `transport` VARCHAR(40) NOT NULL DEFAULT 'stdio',
    `command` VARCHAR(260) NOT NULL DEFAULT '',
    `args` JSON,
    `env` JSON,
    `url` VARCHAR(500) NOT NULL DEFAULT '',
    `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
    `auth_type` VARCHAR(20) NOT NULL DEFAULT 'none',
    `api_key` TEXT,
    `headers` TEXT,
    `tool_allowlist` JSON,
    `timeout_ms` INT,
    `max_retries` INT NOT NULL DEFAULT 2,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_mcp` (`user_id`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Hooks（用户自定义生命周期钩子） ──────────────────────────────
CREATE TABLE IF NOT EXISTS `hooks` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `skill_id` INT NULL,
    `event` VARCHAR(40) NOT NULL DEFAULT 'PreToolUse',
    `matcher` VARCHAR(200) NOT NULL DEFAULT '',
    `command` TEXT NOT NULL DEFAULT '',
    `env` JSON,
    `secret_env` TEXT,
    `timeout_ms` INT NOT NULL DEFAULT 30000,
    `on_error` VARCHAR(20) NOT NULL DEFAULT 'block',
    `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`skill_id`) REFERENCES `skills`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_hooks` (`user_id`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Tool Call Audit（审计留痕） ─────────────────────────────────
CREATE TABLE IF NOT EXISTS `tool_call_audit` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `session_id` VARCHAR(120) NOT NULL DEFAULT '',
    `turn_id` VARCHAR(120) NOT NULL DEFAULT '',
    `tool_type` VARCHAR(20) NOT NULL DEFAULT 'mcp',
    `target` VARCHAR(200) NOT NULL DEFAULT '',
    `tool_name` VARCHAR(200) NOT NULL DEFAULT '',
    `input_encrypted` TEXT,
    `output_encrypted` TEXT,
    `duration_ms` INT NOT NULL DEFAULT 0,
    `status` VARCHAR(20) NOT NULL DEFAULT 'ok',
    `hook_decision` VARCHAR(20) NOT NULL DEFAULT '',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_audit` (`user_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── System Settings ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `system_settings` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `key` VARCHAR(200) NOT NULL UNIQUE,
    `value` TEXT NOT NULL,
    `description` TEXT NOT NULL DEFAULT '',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_setting_key` (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Prompt Templates ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `prompt_templates` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `name` VARCHAR(200) NOT NULL,
    `system_prompt` TEXT NOT NULL,
    `enabled` BOOLEAN NOT NULL DEFAULT TRUE,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
    INDEX `idx_user_templates` (`user_id`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Insert Default Data ────────────────────────────────────────

-- Default admin user (password: admin123)
INSERT INTO `users` (`username`, `email`, `hashed_password`, `is_active`)
VALUES ('admin', 'admin@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewH5F5jPHssXwRiG', TRUE)
ON DUPLICATE KEY UPDATE `username`='admin';

-- ── End ────────────────────────────────────────────────────────
