-- ===================================================================
-- AI Agent Platform - PostgreSQL Initialization Script
-- Database: ai_agent
-- Tables: Mapped from app/models.py with SQLAlchemy semantics
-- ===================================================================

-- ── Create Database (runs via docker-compose volume mount, not in here) ──

-- ── Users ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(40) NOT NULL DEFAULT 'user',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    chunking_strategy VARCHAR(80) NOT NULL DEFAULT 'recursive_character',
    chunking_config JSONB NOT NULL DEFAULT '{}',
    rag_config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_valid_json CHECK (jsonb_typeof(chunking_config) = 'object' OR chunking_config IS NULL),
    CONSTRAINT chk_valid_rag CHECK (jsonb_typeof(rag_config) = 'object' OR rag_config IS NULL)
);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);

-- ── Threads ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id INTEGER REFERENCES agents(id) ON DELETE SET NULL,
    title VARCHAR(180) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_threads_user ON threads(user_id, created_at);
CREATE INDEX idx_threads_agent ON threads(agent_id);

-- ── Messages ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role VARCHAR(40) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    extra JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_valid_extra CHECK (jsonb_typeof(extra) = 'object' OR extra IS NULL)
);
CREATE INDEX idx_messages_thread ON messages(thread_id, created_at);

-- ── Providers ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS providers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    base_url VARCHAR(500) NOT NULL DEFAULT '',
    api_key VARCHAR(500) NOT NULL DEFAULT '',
    provider_type VARCHAR(40) NOT NULL DEFAULT 'openai-compatible',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_providers_user_default ON providers(user_id, is_default);
CREATE INDEX idx_providers_name ON providers(name);

-- ── Provider Models ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS provider_models (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    model_name VARCHAR(200) NOT NULL,
    model_type VARCHAR(40) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_default_chat BOOLEAN NOT NULL DEFAULT FALSE,
    is_default_embedding BOOLEAN NOT NULL DEFAULT FALSE,
    is_default_video BOOLEAN NOT NULL DEFAULT FALSE,
    is_default_image BOOLEAN NOT NULL DEFAULT FALSE,
    description VARCHAR(300) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_provider_model UNIQUE (provider_id, model_name)
);
CREATE INDEX idx_provider_models_type ON provider_models(provider_id, model_type);

-- ── Agents ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL,
    model_provider VARCHAR(80) NOT NULL DEFAULT 'openai-compatible',
    model_name VARCHAR(160) NOT NULL,
    temperature FLOAT NOT NULL DEFAULT 0,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agents_user ON agents(user_id, enabled);

-- ── Knowledge Bases ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    embedding_model VARCHAR(160) NOT NULL DEFAULT 'text-embedding-3-small',
    chunk_size INTEGER NOT NULL DEFAULT 500,
    chunk_overlap INTEGER NOT NULL DEFAULT 50,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    rag_config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_valid_kb_rag CHECK (jsonb_typeof(rag_config) = 'object' OR rag_config IS NULL)
);
CREATE INDEX idx_kb_user ON knowledge_bases(user_id, enabled);

-- ── KB Folders ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_folders (
    id SERIAL PRIMARY KEY,
    kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES kb_folders(id) ON DELETE CASCADE,
    name VARCHAR(300) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_kb_folder_name UNIQUE (kb_id, parent_id, name)
);
CREATE INDEX idx_kb_folders_tree ON kb_folders(kb_id, parent_id);

-- ── KB Documents ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_documents (
    id SERIAL PRIMARY KEY,
    kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    folder_id INTEGER REFERENCES kb_folders(id) ON DELETE SET NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_filename VARCHAR(500) NOT NULL,
    storage_path VARCHAR(1000) NOT NULL,
    file_type VARCHAR(40) NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(40) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_kb_doc_path UNIQUE (kb_id, storage_path)
);
CREATE INDEX idx_kb_docs ON kb_documents(kb_id, status);
CREATE INDEX idx_kb_docs_user ON kb_documents(user_id);

-- ── KB Chunks ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_chunks (
    id SERIAL PRIMARY KEY,
    kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    folder_id INTEGER,
    vector_id VARCHAR(200) NOT NULL,
    page_number INTEGER,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    metadata_ JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_kb_chunk_vec UNIQUE (document_id, chunk_index, vector_id),
    CONSTRAINT chk_valid_chunk_meta CHECK (jsonb_typeof(metadata_) = 'object' OR metadata_ IS NULL)
);
CREATE INDEX idx_kb_chunks ON kb_chunks(kb_id, document_id);

-- ── Agent-KnowledgeBase Association ────────────────────────────
CREATE TABLE IF NOT EXISTS agent_knowledge_bases (
    agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    kb_id INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, kb_id)
);

-- ── Skills ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    title VARCHAR(160) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_type VARCHAR(40) NOT NULL DEFAULT 'local',
    path VARCHAR(500) NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_skill_user_name UNIQUE (user_id, name)
);
CREATE INDEX idx_skills_user ON skills(user_id, enabled);

-- ── MCP Servers ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mcp_servers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(120) NOT NULL,
    transport VARCHAR(40) NOT NULL DEFAULT 'stdio',
    command VARCHAR(260) NOT NULL DEFAULT '',
    args JSONB NOT NULL DEFAULT '[]',
    env JSONB NOT NULL DEFAULT '{}',
    url VARCHAR(500) NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_mcp_user_name UNIQUE (user_id, name),
    CONSTRAINT chk_valid_args CHECK (jsonb_typeof(args) = 'array' OR args IS NULL),
    CONSTRAINT chk_valid_env CHECK (jsonb_typeof(env) = 'object' OR env IS NULL)
);
CREATE INDEX idx_mcp_user ON mcp_servers(user_id, enabled);

-- ── Prompt Templates ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prompt_templates (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(120) NOT NULL UNIQUE,
    system_prompt TEXT NOT NULL,
    variables JSONB NOT NULL DEFAULT '[]',
    category VARCHAR(80) NOT NULL DEFAULT 'general',
    description VARCHAR(300) NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_valid_vars CHECK (jsonb_typeof(variables) = 'array' OR variables IS NULL)
);
CREATE INDEX idx_ptemplates_user ON prompt_templates(user_id, enabled);

-- ── System Settings ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(120) NOT NULL UNIQUE,
    value TEXT NOT NULL DEFAULT '',
    description VARCHAR(300) NOT NULL DEFAULT ''
);
CREATE INDEX idx_sys_settings_key ON system_settings(key);

-- ── KB Feedback ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS kb_feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT NOT NULL,
    chunk_id INTEGER REFERENCES kb_chunks(id) ON DELETE CASCADE,
    is_helpful BOOLEAN NOT NULL,
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Retrieval Logs ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS retrieval_logs (
    id SERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    query TEXT NOT NULL,
    rewritten_query TEXT,
    kb_id INTEGER REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    top_k INTEGER NOT NULL,
    hit_count INTEGER NOT NULL,
    avg_score FLOAT NOT NULL,
    took_ms INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Default Data ───────────────────────────────────────────────

-- Admin user (password: admin123)
INSERT INTO users (username, email, password_hash, role, enabled)
VALUES ('admin', 'admin@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewH5F5jPHssXwRiG', 'admin', TRUE)
ON CONFLICT (username) DO UPDATE SET username = EXCLUDED.username;

-- ── End ────────────────────────────────────────────────────────
