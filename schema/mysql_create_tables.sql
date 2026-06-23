
-- ---------------------------------------------------------
-- 1. 用户表 (users)
-- ---------------------------------------------------------
CREATE TABLE `users` (
  `id`              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `email`           VARCHAR(255)  NOT NULL UNIQUE,
  `username`        VARCHAR(80)   NOT NULL UNIQUE,
  `password_hash`   VARCHAR(255)  NOT NULL,
  `role`            VARCHAR(40)   NOT NULL DEFAULT 'user',
  `created_at`      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at`      DATETIME(3)   NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX `idx_users_email` (`email`),
  INDEX `idx_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------
-- 2. Agent 配置表 (agents)
-- ---------------------------------------------------------
CREATE TABLE `agents` (
  `id`               INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id`          INT UNSIGNED NOT NULL,
  `name`             VARCHAR(120) NOT NULL,
  `description`      TEXT         NOT NULL DEFAULT '',
  `system_prompt`    TEXT         NOT NULL,
  `model_provider`   VARCHAR(80)  NOT NULL DEFAULT 'openai-compatible',
  `model_name`       VARCHAR(160) NOT NULL,
  `temperature`      FLOAT        NOT NULL DEFAULT 0,
  `enabled`          TINYINT(1)   NOT NULL DEFAULT 1,
  `created_at`       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at`       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  CONSTRAINT `fk_agents_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  INDEX `idx_agents_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------
-- 3. 会话表 (threads)
-- ---------------------------------------------------------
CREATE TABLE `threads` (
  `id`         VARCHAR(80)    NOT NULL PRIMARY KEY,
  `user_id`    INT UNSIGNED   NOT NULL,
  `agent_id`   INT UNSIGNED   NOT NULL,
  `title`      VARCHAR(180)   NOT NULL DEFAULT 'New chat',
  `created_at` DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  CONSTRAINT `fk_threads_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_threads_agent` FOREIGN KEY (`agent_id`) REFERENCES `agents`(`id`) ON DELETE CASCADE,
  INDEX `idx_threads_user_id` (`user_id`),
  INDEX `idx_threads_agent_id` (`agent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------
-- 4. 消息表 (messages)
-- ---------------------------------------------------------
CREATE TABLE `messages` (
  `id`         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `thread_id`  VARCHAR(80)    NOT NULL,
  `role`       VARCHAR(40)    NOT NULL,
  `content`    TEXT           NOT NULL,
  `extra`      JSON           NOT NULL DEFAULT (JSON_OBJECT()),
  `created_at` DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  CONSTRAINT `fk_messages_thread` FOREIGN KEY (`thread_id`) REFERENCES `threads`(`id`) ON DELETE CASCADE,
  INDEX `idx_messages_thread_id` (`thread_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------
-- 5. MCP Server 配置表 (mcp_servers)
-- ---------------------------------------------------------
CREATE TABLE `mcp_servers` (
  `id`         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id`    INT UNSIGNED   NOT NULL,
  `name`       VARCHAR(120)   NOT NULL,
  `transport`  VARCHAR(40)    NOT NULL DEFAULT 'stdio',
  `command`    VARCHAR(260)   NOT NULL DEFAULT '',
  `args`       JSON           NOT NULL DEFAULT (JSON_ARRAY()),
  `env`        JSON           NOT NULL DEFAULT (JSON_OBJECT()),
  `url`        VARCHAR(500)   NOT NULL DEFAULT '',
  `enabled`    TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at` DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at` DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  CONSTRAINT `fk_mcp_servers_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  INDEX `idx_mcp_servers_user_id` (`user_id`),
  UNIQUE KEY `uq_mcp_user_name` (`user_id`, `name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------
-- 6. Skill 配置表 (skills)
-- ---------------------------------------------------------
CREATE TABLE `skills` (
  `id`            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `user_id`       INT UNSIGNED   NOT NULL,
  `name`          VARCHAR(120)   NOT NULL,
  `title`         VARCHAR(160)   NOT NULL,
  `description`   TEXT           NOT NULL DEFAULT '',
  `source_type`   VARCHAR(40)    NOT NULL DEFAULT 'local',
  `path`          VARCHAR(500)   NOT NULL DEFAULT '',
  `enabled`       TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`    DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  `updated_at`    DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  CONSTRAINT `fk_skills_user` FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  INDEX `idx_skills_user_id` (`user_id`),
  UNIQUE KEY `uq_skill_user_name` (`user_id`, `name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
