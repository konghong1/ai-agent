from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    id: int
    email: EmailStr
    username: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    role: str | None = Field(default=None, min_length=1, max_length=40)
    enabled: bool | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class AgentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    system_prompt: str | None = None
    model_name: str | None = None
    temperature: float = Field(default=0, ge=0, le=2)
    enabled: bool = True
    knowledge_base_ids: list[int] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    system_prompt: str | None = None
    model_name: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    enabled: bool | None = None
    knowledge_base_ids: list[int] | None = None


class AgentRead(BaseModel):
    id: int
    name: str
    description: str
    system_prompt: str
    model_provider: str
    model_name: str
    temperature: float
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ThreadCreate(BaseModel):
    agent_id: int
    title: str = Field(default="New chat", max_length=180)


class ThreadRead(BaseModel):
    id: str
    agent_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageRead(BaseModel):
    id: int
    thread_id: str
    role: str
    content: str
    extra: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    agent_id: int
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    thread_id: str
    blocks: dict = Field(default_factory=dict)


class McpServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    enabled: bool = True


class McpServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    transport: str | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    url: str | None = None
    enabled: bool | None = None


class McpServerRead(BaseModel):
    id: int
    name: str
    transport: str
    command: str
    args: list[str]
    env: dict[str, str]
    url: str
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    title: str = Field(..., min_length=1, max_length=160)
    description: str = ""
    source_type: str = "local"
    path: str = ""
    enabled: bool = True


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    source_type: str | None = None
    path: str | None = None
    enabled: bool | None = None


class SkillRead(BaseModel):
    id: int
    name: str
    title: str
    description: str
    source_type: str
    path: str
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Knowledge Base Schemas (Task 5)
# ============================================================

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = Field(default=500, ge=100, le=4000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)
    enabled: bool = True


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    embedding_model: str | None = None
    chunk_size: int | None = Field(default=None, ge=100, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=500)
    enabled: bool | None = None


class KnowledgeBaseRead(BaseModel):
    id: int
    name: str
    description: str
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KBFolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    description: str = ""
    parent_id: int | None = None


class KBFolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    parent_id: int | None = None


class KBFolderRead(BaseModel):
    id: int
    kb_id: int
    parent_id: int | None
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    children: list["KBFolderRead"] = Field(default_factory=list)
    document_count: int = Field(default=0)

    model_config = ConfigDict(from_attributes=True)


class KBFolderTreeNode(BaseModel):
    """Recursive tree node for the folder browser."""
    id: int
    name: str
    description: str
    children: list["KBFolderTreeNode"] = Field(default_factory=list)
    document_count: int = Field(default=0)


class KBDocumentRead(BaseModel):
    id: int
    kb_id: int
    folder_id: int | None
    original_filename: str
    file_type: str
    file_size: int
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KBSearchRequest(BaseModel):
    """Request body for searching a knowledge base."""
    query: str = Field(..., min_length=1, max_length=500)
    kb_id: int
    folder_id: int | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class KBSearchResult(BaseModel):
    """A single hit returned by a knowledge-base search."""
    chunk_id: int
    vector_id: str
    document_id: int
    document_name: str
    folder_path: str
    page_number: int | None
    chunk_index: int
    content: str
    score: float

    model_config = ConfigDict(from_attributes=True)


class KBUploadResponse(BaseModel):
    document_id: int
    status: str
    message: str


# ============================================================
# User Management Schemas (Task 6)
# ============================================================

class UserManagementRead(BaseModel):
    id: int
    email: EmailStr
    username: str
    role: str
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# System Setting Schemas (Task 7)
# ============================================================

class SystemSettingCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=120)
    value: str = ""
    description: str = ""


class SystemSettingUpdate(BaseModel):
    value: str | None = None
    description: str | None = None


class SystemSettingRead(BaseModel):
    id: int
    key: str
    value: str
    description: str

    model_config = ConfigDict(from_attributes=True)



# ============================================================
# RAG Configuration Schemas
# ============================================================

class RAGConfigUpdate(BaseModel):
    hybrid_search: bool | None = None
    rerank_enabled: bool | None = None
    rerank_model: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=50)
    rerank_top_k: int | None = Field(default=None, ge=1, le=30)
    mmr_enabled: bool | None = None
    mmr_threshold: float | None = Field(default=None, ge=0, le=1)
    max_context_tokens: int | None = Field(default=None, ge=500, le=16000)
    min_relevance_score: float | None = Field(default=None, ge=0, le=1)
    query_rewrite: bool | None = None
    include_sources: bool | None = None


class RetrievalFeedbackRequest(BaseModel):
    thread_id: str
    chunk_id: int
    is_helpful: bool
    comment: str | None = ""


class RetrievalLogRead(BaseModel):
    id: int
    thread_id: str
    query: str
    rewritten_query: str | None
    kb_id: int
    top_k: int
    hit_count: int
    avg_score: float
    took_ms: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KBStatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    avg_chunks_per_doc: float
    status_breakdown: dict
    hot_queries: list[str]
