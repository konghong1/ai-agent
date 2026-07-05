"""
PostgreSQL models for AI Agent Platform.

All SQLAlchemy ORM models that work with PostgreSQL.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────


class MediaType(enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class MediaStatus(enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Models ───────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    threads = relationship("Thread", back_populates="user", cascade="all, delete-orphan")


class Thread(Base):
    __tablename__ = "threads"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), server_default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="threads")
    messages = relationship("Message", back_populates="thread", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(UUID, ForeignKey("threads.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, server_default="")
    extra = Column(JSONB, server_default="{}")  # blocks, metadata
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    thread = relationship("Thread", back_populates="messages")
    user = relationship("User", back_populates="messages")


class MediaAsset(Base):
    """Stores metadata about uploaded/downloaded media assets.
    
    All media files are stored in MinIO with the object_key pointing
    to the file location within the bucket.
    """
    __tablename__ = "media_assets"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    
    # Asset classification
    media_type = Column(String(20), nullable=False, default="image")  # image / video
    
    # Storage location
    object_key = Column(String(500), nullable=False, unique=True, index=True)  # MinIO key
    file_size = Column(Integer, nullable=True)  # bytes
    mime_type = Column(String(100), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    
    # CDN/Proxy URL (internal path, not external CDN)
    internal_url = Column(String(1000), nullable=True)
    
    # Status tracking
    status = Column(String(20), nullable=False, default="queued", index=True)
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User")
    message = relationship("Message")

    __table_args__ = (
        Index("idx_user_type", "user_id", "media_type"),
        Index("idx_status_created", "status", "created_at"),
    )


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    base_url = Column(String(500), server_default="")
    api_key = Column(String(500), server_default="")
    provider_type = Column(String(50), server_default="openai-compatible")
    enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_user_default", "user_id", "is_default"),
    )


class ProviderModel(Base):
    __tablename__ = "provider_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False)
    model_name = Column(String(200), nullable=False)
    model_type = Column(String(50), server_default="chat")  # chat / image / video / embedding
    
    __table_args__ = (
        Index("idx_provider_type", "provider_id", "model_type"),
        Index("idx_model_name", "model_name"),
    )


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, server_default="")
    embedding_model = Column(String(200), server_default="text-embedding-3-small")
    chunk_size = Column(Integer, server_default="500")
    chunk_overlap = Column(Integer, server_default="50")
    rag_config = Column(JSONB, server_default="{}")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class KBFolder(Base):
    __tablename__ = "kb_folders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    name = Column(String(200), nullable=False)
    parent_id = Column(Integer, ForeignKey("kb_folders.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    folder_id = Column(Integer, ForeignKey("kb_folders.id"), nullable=True)
    original_filename = Column(String(500), nullable=False)
    stored_filename = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    status = Column(String(20), server_default="uploading")  # uploading / parsing / ready / failed
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now())


class KBChunk(Base):
    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    kb_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    document_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=False)
    vector_id = Column(String(200), nullable=False, unique=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column(JSONB, server_default="{}")


class AgentConfig(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, server_default="")
    system_prompt = Column(Text, server_default="")
    model_name = Column(String(200), server_default="gpt-4")
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Skill(Base):
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, server_default="")
    content = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class McpServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    config = Column(JSONB, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(200), nullable=False, unique=True)
    value = Column(Text, nullable=False)
    description = Column(Text, server_default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    system_prompt = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
