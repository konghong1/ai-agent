from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import JSON as SA_JSON

from app.core.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ============================================================
# User (Task 4: add enabled field)
# ============================================================

class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), default="user")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    chunking_strategy: Mapped[str] = mapped_column(String(80), default="recursive_character")
    chunking_config: Mapped[dict] = mapped_column(SA_JSON, default=dict)
    rag_config: Mapped[dict] = mapped_column(SA_JSON, default=dict)

    agents: Mapped[list["AgentConfig"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    prompt_templates: Mapped[list["PromptTemplate"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    providers: Mapped[list["Provider"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# ============================================================
# AgentConfig (with relationships to KB/MCP/Skill)
# ============================================================

class AgentConfig(TimestampMixin, Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text)
    model_provider: Mapped[str] = mapped_column(String(80), default="openai-compatible")
    model_name: Mapped[str] = mapped_column(String(160))
    temperature: Mapped[float] = mapped_column(Float, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped[User] = relationship(back_populates="agents")
    threads: Mapped[list["Thread"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(
        secondary="agent_knowledge_bases", back_populates="agents"
    )


# ============================================================
# Thread & Message (unchanged)
# ============================================================

class Thread(TimestampMixin, Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(180))

    agent: Mapped[AgentConfig] = relationship(back_populates="threads")
    messages: Mapped[list["Message"]] = relationship(back_populates="thread", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(SA_JSON, default=dict)

    thread: Mapped[Thread] = relationship(back_populates="messages")

    # Composite index so `WHERE thread_id = ? ORDER BY created_at` (loading a
    # thread's messages) is satisfied by the index instead of a filesort. On
    # MySQL a large messages table without this can hit "Out of sort memory".
    __table_args__ = (
        Index("ix_messages_thread_created", "thread_id", "created_at"),
    )


# ============================================================
# McpServer & Skill (unchanged)
# ============================================================

class McpServer(TimestampMixin, Base):
    __tablename__ = "mcp_servers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    transport: Mapped[str] = mapped_column(String(40), default="stdio")
    command: Mapped[str] = mapped_column(String(260), default="")
    args: Mapped[list] = mapped_column(SA_JSON, default=list)
    env: Mapped[dict] = mapped_column(SA_JSON, default=dict)
    url: Mapped[str] = mapped_column(String(500), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_mcp_user_name"),)


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(40), default="local")
    path: Mapped[str] = mapped_column(String(500), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_skill_user_name"),)


# ============================================================
# Agent-KnowledgeBase association table (Task 2)
# ============================================================

class AgentKnowledgeBase(Base):
    """Links an Agent to one or more Knowledge Bases."""
    __tablename__ = "agent_knowledge_bases"

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    kb_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), primary_key=True
    )


# ============================================================


# ============================================================
# PromptTemplate (Task: Replace Agent in chat with template selector)
# ============================================================

class PromptTemplate(TimestampMixin, Base):
    """A reusable system prompt template."""
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    system_prompt: Mapped[str] = mapped_column(Text)
    variables: Mapped[list] = mapped_column(SA_JSON, default=list)
    category: Mapped[str] = mapped_column(String(80), default="general")
    description: Mapped[str] = mapped_column(String(300), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="prompt_templates")


# ============================================================
# Provider & ProviderModel (AI Provider Management)
# ============================================================

class Provider(TimestampMixin, Base):
    """An AI provider (e.g. OpenAI, Azure, SiliconFlow)."""
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(500), default="")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    provider_type: Mapped[str] = mapped_column(String(40), default="openai-compatible")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="providers")
    models: Mapped[list["ProviderModel"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class ProviderModel(TimestampMixin, Base):
    """A model registered under a provider (chat or embedding)."""
    __tablename__ = "provider_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("providers.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(200))
    model_type: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default_chat: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default_embedding: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default_video: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default_image: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(String(300), default="")

    provider: Mapped[Provider] = relationship(back_populates="models")

    __table_args__ = (UniqueConstraint("provider_id", "model_name", name="uq_provider_model"),)

# SystemSetting (Task 3)
# ============================================================

class SystemSetting(Base):
    """Global key-value configuration."""
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(String(300), default="")


# ============================================================
# Knowledge Base Module (Tasks 2-4 continued)
# ============================================================

class KnowledgeBase(TimestampMixin, Base):
    """A user-owned knowledge base (top-level container)."""
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    embedding_model: Mapped[str] = mapped_column(String(160), default="text-embedding-3-small")
    chunk_size: Mapped[int] = mapped_column(Integer, default=500)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=50)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # RAG pipeline configuration (retrieval strategy, rerank, MMR, etc.)
    rag_config: Mapped[dict] = mapped_column(SA_JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="knowledge_bases")
    folders: Mapped[list["KBFolder"]] = relationship(back_populates="kb", cascade="all, delete-orphan")
    agents: Mapped[list["AgentConfig"]] = relationship(
        secondary="agent_knowledge_bases", back_populates="knowledge_bases"
    )


class KBFolder(TimestampMixin, Base):
    """Recursive folder inside a knowledge base 鈥?forms a tree."""
    __tablename__ = "kb_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("kb_folders.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")

    kb: Mapped[KnowledgeBase] = relationship(back_populates="folders")
    parent: Mapped["KBFolder | None"] = relationship(back_populates="children", remote_side=[id])
    children: Mapped[list["KBFolder"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    documents: Mapped[list["KBDocument"]] = relationship(back_populates="folder", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("kb_id", "parent_id", "name", name="uq_kb_folder_name"),)


class KBDocument(TimestampMixin, Base):
    """A physical file registered inside a KB folder."""
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("kb_folders.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    original_filename: Mapped[str] = mapped_column(String(500))
    storage_path: Mapped[str] = mapped_column(String(1000))
    file_type: Mapped[str] = mapped_column(String(40))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    folder: Mapped["KBFolder | None"] = relationship(back_populates="documents")

    # NOTE: storage_path can be up to VARCHAR(1000); a full-column unique index would
    # exceed MySQL/InnoDB's 3072-byte key limit (1000 * 4 utf8mb4 bytes). Use a prefix
    # index so the constraint still fits while remaining effectively unique for real paths.
    __table_args__ = (
        Index("uq_kb_doc_path", "kb_id", "storage_path", unique=True, mysql_length={"storage_path": 255}),
    )


class KBChunk(TimestampMixin, Base):
    """A text chunk derived from a document, stored in the vector store."""
    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    vector_id: Mapped[str] = mapped_column(String(200))
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(SA_JSON, default=dict)

    __table_args__ = (UniqueConstraint("document_id", "chunk_index", "vector_id", name="uq_kb_chunk_vec"),)


# ============================================================
# KBFeedback (RAG feedback tracking)
# ============================================================

class KBFeedback(Base):
    """User feedback on retrieval results."""
    __tablename__ = "kb_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    thread_id: Mapped[str] = mapped_column(String(80))
    chunk_id: Mapped[int] = mapped_column(ForeignKey("kb_chunks.id", ondelete="CASCADE"))
    is_helpful: Mapped[bool]
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# RetrievalLog (RAG search logging)
# ============================================================

class RetrievalLog(Base):
    """Logs each retrieval operation for analysis and optimization."""
    __tablename__ = "retrieval_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String(80))
    query: Mapped[str] = mapped_column(Text)
    rewritten_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"))
    top_k: Mapped[int]
    hit_count: Mapped[int]
    avg_score: Mapped[float]
    took_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# MediaAsset (background worker downloads CDN media -> object storage)
# ============================================================


class MediaAsset(TimestampMixin, Base):
    """Tracks a media asset being downloaded/served by the worker.

    MySQL-compatible port of the model (the PostgreSQL variant used a UUID PK with
    ``gen_random_uuid()``; here we use a ``String`` PK defaulting to a uuid4).
    """

    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(
        String(80), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    media_type: Mapped[str] = mapped_column(String(20), default="image")
    object_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    internal_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


# ============================================================
# 电商套图模块 (E-commerce Gallery)
#   低耦合：与 Agent/KB 等业务无外键关联，仅关联 user。
#   高扩展：策划项的内容(个性化/通用/出图设置)均为 JSON，schema 演进不迁表。
# ============================================================

class GalleryProject(TimestampMixin, Base):
    """一个套图工作项目（草稿 → 生成中 → 已完成）。"""

    __tablename__ = "gallery_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="未命名套图")
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # 核心卖点文本
    selling_points: Mapped[str] = mapped_column(Text, default="")
    # 市场配置：{platform, market, language, style}
    market_config: Mapped[dict] = mapped_column(SA_JSON, default=dict)
    # 全局输出配置：{model, resolution, per_type_count, ratio}
    output_config: Mapped[dict] = mapped_column(SA_JSON, default=dict)
    # 估算成本（由策划项聚合，落库以便展示）
    estimated_points: Mapped[int] = mapped_column(Integer, default=0)
    estimated_minutes: Mapped[float] = mapped_column(Float, default=0)

    images: Mapped[list["GalleryProjectImage"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="GalleryProjectImage.order"
    )
    plan_items: Mapped[list["GalleryPlanItem"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="GalleryPlanItem.order"
    )
    records: Mapped[list["GalleryRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="GalleryRecord.created_at"
    )
    tasks: Mapped[list["GalleryTask"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="GalleryTask.created_at"
    )


class GalleryProjectImage(TimestampMixin, Base):
    """上传到项目中的产品原图（多视角）。"""

    __tablename__ = "gallery_project_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("gallery_projects.id", ondelete="CASCADE"), index=True)
    # 落盘文件名（位于 uploads/gallery/ 下），用于 /api/gallery/files/{filename} 回显
    filename: Mapped[str] = mapped_column(String(500), index=True)
    url: Mapped[str] = mapped_column(String(1000), default="")
    original: Mapped[bool] = mapped_column(Boolean, default=False)
    order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped["GalleryProject"] = relationship(back_populates="images")

    __table_args__ = (
        Index("uq_gallery_img", "project_id", "filename", unique=True, mysql_length={"filename": 255}),
    )


class GalleryPlanItem(TimestampMixin, Base):
    """策划台中的一个出图类型条目（如：首屏视觉图 ×1）。"""

    __tablename__ = "gallery_plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("gallery_projects.id", ondelete="CASCADE"), index=True)
    type_id: Mapped[str] = mapped_column(String(40), index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    # 个性化设置：{field_label: value, ...}
    personal_settings: Mapped[dict] = mapped_column(SA_JSON, default=dict)
    # 通用设置：{copy_language, target_market, ecommerce_platform, visual_style, copy_need, tone_tendency}
    common_settings: Mapped[dict] = mapped_column(SA_JSON, default=dict)
    # 出图设置：{model, resolution, count, ratio}
    output_settings: Mapped[dict] = mapped_column(SA_JSON, default=dict)
    # 补充说明（≤2000 字）
    note: Mapped[str] = mapped_column(Text, default="")
    # 参考图文件名列表（落盘于 uploads/gallery/）
    reference_images: Mapped[list] = mapped_column(SA_JSON, default=list)
    # 单独商品图（仅本策划项使用的主图）：落盘文件名；为空则生成时回退到项目产品图[0]
    product_image: Mapped[Optional[str]] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    project: Mapped["GalleryProject"] = relationship(back_populates="plan_items")


class GalleryTemplate(TimestampMixin, Base):
    """用户保存的策划模板（另存为模板）。"""

    __tablename__ = "gallery_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    # 模板内容：{plan_items:[{type_id, personal_settings, common_settings, output_settings, note}], market_config, output_config, selling_points}
    payload: Mapped[dict] = mapped_column(SA_JSON, default=dict)


class GalleryRecord(TimestampMixin, Base):
    """一次生成产生的单张结果图（创作记录的最小单元）。"""

    __tablename__ = "gallery_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("gallery_projects.id", ondelete="CASCADE"), index=True)
    plan_item_id: Mapped[int | None] = mapped_column(ForeignKey("gallery_plan_items.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type_id: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    # 生成结果图（落盘文件名 + 回显 url）
    result_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # 实际发送给模型的提示词（中文版，便于排查与展示）
    prompt: Mapped[str] = mapped_column(Text, default="")
    # 实际用于图片模型生成的紧凑英文提示词
    prompt_en: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
    # 提示词来源：ai=由 Agnes 多模态大模型生成；template=降级到旧模板引擎
    prompt_source: Mapped[str] = mapped_column(String(16), default="template", server_default="template")
    # 提示词溯源：喂给大模型生成提示词的「完整意图描述」（用户配置 + 参考图说明，非最终提示词）
    # 注意：MySQL 不允许 TEXT 列带 server_default，故只用 Python 层 default 兜底
    prompt_input: Mapped[str] = mapped_column(Text, default="")
    # 提示词溯源：大模型原始返回文本（解析前的 JSON 字符串）；模板降级路径为空串
    prompt_raw: Mapped[str] = mapped_column(Text, default="")
    # 最简短场景提示词（由 AI 批量提示词引擎额外产出）：中文展示版 / 纯英文生成版。
    # 实际出图优先使用 prompt_en_short 降本提速；完整版 prompt_en 保留用于展示与溯源。
    # 注意：MySQL 不允许 TEXT 列带 server_default，故只用 nullable、不加默认值。
    prompt_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_en_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 生成该图所用的 AI 提供商图片模型（确保所有配置都有记录）
    provider_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    provider_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 生成时刻的 plan_item 完整配置快照，便于「一键做同款」复用
    plan_item_snapshot: Mapped[dict | None] = mapped_column(SA_JSON, nullable=True, default=None)
    # 关联的异步生成任务（每次「立即生成」对应一个任务）
    task_id: Mapped[int | None] = mapped_column(ForeignKey("gallery_tasks.id", ondelete="SET NULL"), nullable=True, index=True)

    project: Mapped["GalleryProject"] = relationship(back_populates="records")
    task: Mapped["GalleryTask"] = relationship(back_populates="records")


class GalleryTask(TimestampMixin, Base):
    """一次「立即生成」对应的异步任务。

    在后台 worker 中执行，逐步生成图片并写入 GalleryRecord（带 task_id），
    前端轮询该任务的进度（done/total）与已生成图片。
    """

    __tablename__ = "gallery_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("gallery_projects.id", ondelete="CASCADE"), index=True)
    # pending -> running -> completed / failed / partial
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    # 任务名称（用户可重命名）
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 计划生成的总图数 / 已完成 / 失败
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["GalleryProject"] = relationship(back_populates="tasks")
    records: Mapped[list["GalleryRecord"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="GalleryRecord.created_at"
    )


class GalleryShowcase(TimestampMixin, Base):
    """热门套图示例（种子数据，可编辑扩展）。"""

    __tablename__ = "gallery_showcases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(200))
    original_url: Mapped[str] = mapped_column(String(1000), default="")
    image_urls: Mapped[list] = mapped_column(SA_JSON, default=list)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    # 发布时携带的源任务参数（用于「生成同款」回填）：
    # { plan_items:[plan_item_snapshot...], market_config, output_config, selling_points }
    # 仅存储配置，不存储源项目的落盘文件（product_image 等在当前项目无法解析）。
    payload: Mapped[dict] = mapped_column(SA_JSON, default=dict)


class GalleryConfig(TimestampMixin, Base):
    """电商套图模块的「固定配置」持久化表（落库）。

    原本所有策划类型 / 个性化字段（含下拉选项）/ 通用·市场·输出选项 / 套图种子
    都硬编码在 ``app.gallery_config`` 的 Python 常量里。一旦镜像或运行环境重置、
    或需要可运营编辑，配置就「消失」。本表把这份固定配置落库，成为唯一可恢复的来源：

    - ``config_key`` 唯一，如 ``plan_types`` / ``type_personal`` / ``common_options`` /
      ``market_options`` / ``output_options`` / ``showcase_categories``
    - ``config_value`` 存对应 Python 常量的 JSON 序列化值
    - 启动时由 ``seed_gallery_config`` 幂等写入；运行时优先从本表读取，缺失时回退代码常量
    """

    __tablename__ = "gallery_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_key: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    config_value: Mapped[dict] = mapped_column(SA_JSON, default=dict)
    description: Mapped[str] = mapped_column(String(200), default="")


