from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
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

    agents: Mapped[list["AgentConfig"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    knowledge_bases: Mapped[list["KnowledgeBase"]] = relationship(back_populates="user", cascade="all, delete-orphan")


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
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
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

    user: Mapped[User] = relationship(back_populates="knowledge_bases")
    folders: Mapped[list["KBFolder"]] = relationship(back_populates="kb", cascade="all, delete-orphan")
    agents: Mapped[list["AgentConfig"]] = relationship(
        secondary="agent_knowledge_bases", back_populates="knowledge_bases"
    )


class KBFolder(TimestampMixin, Base):
    """Recursive folder inside a knowledge base – forms a tree."""
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

    __table_args__ = (UniqueConstraint("kb_id", "storage_path", name="uq_kb_doc_path"),)


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
