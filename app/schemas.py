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
    agent_id: int | None = None
    title: str = Field(default="New chat", max_length=180)


class ThreadRead(BaseModel):
    id: str
    agent_id: int | None
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ThreadUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=180)


class MessageRead(BaseModel):
    id: int
    thread_id: str
    role: str
    content: str
    extra: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessagesPage(BaseModel):
    """Paginated message list (newest-last ordering within ``messages``).

    ``has_more`` is True when older messages exist before ``oldest_id``; the
    client passes ``oldest_id`` back as ``before`` to fetch the next (older)
    page on scroll-up. This cursor scheme avoids offset drift when new messages
    arrive during pagination.
    """

    messages: list[MessageRead]
    has_more: bool
    oldest_id: int | None = None
    limit: int


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    agent_id: int | None = None
    thread_id: str | None = None
    template_id: int | None = None
    provider_id: int | None = None
    provider_type: str | None = Field(default=None, description="LLM provider type (e.g. 'openai-compatible', 'qwen')")
    model_name: str | None = None
    # ── Reference images (图生图 / 图生视频) ──
    # Each entry is a base64 data URL, an http(s) URL, or an internal
    # by-key URL (which the backend inlines as a data URL before sending
    # to the provider). Sent by the chat UI when the user attaches images.
    reference_images: list[str] | None = None
    # Optional generation overrides (only used by image/video models).
    size: str | None = None
    n: int | None = None
    width: int | None = None
    height: int | None = None
    num_frames: int | None = None
    frame_rate: int | None = None
    mode: str | None = None
    negative_prompt: str | None = None
    seed: int | None = None
    tags: list[str] | None = None


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



# ============================================================
# Prompt Template Schemas
# ============================================================

class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(None, max_length=120)
    system_prompt: str = Field(..., min_length=1)
    variables: list[str] = Field(default_factory=list)
    category: str = "general"
    description: str = ""
    enabled: bool = True
    is_default: bool = False


class PromptTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=120)
    system_prompt: str | None = None
    variables: list[str] | None = None
    category: str | None = None
    description: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None


class PromptTemplateRead(BaseModel):
    id: int
    user_id: int
    name: str
    slug: str
    system_prompt: str
    variables: list[str]
    category: str
    description: str
    enabled: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Provider Management Schemas
# ============================================================

class ProviderModelCreate(BaseModel):
    model_name: str = Field(..., min_length=1, max_length=200)
    model_type: str = Field(..., pattern="^(chat|embedding|video|image)$")
    enabled: bool = True
    is_default_chat: bool = False
    is_default_embedding: bool = False
    is_default_video: bool = False
    is_default_image: bool = False
    description: str = ""


class ProviderModelUpdate(BaseModel):
    model_name: str | None = Field(default=None, min_length=1, max_length=200)
    model_type: str | None = None
    enabled: bool | None = None
    is_default_chat: bool | None = None
    is_default_embedding: bool | None = None
    is_default_video: bool | None = None
    is_default_image: bool | None = None
    description: str | None = None


class ProviderModelRead(BaseModel):
    id: int
    provider_id: int
    model_name: str
    model_type: str
    enabled: bool
    is_default_chat: bool
    is_default_embedding: bool
    is_default_video: bool
    is_default_image: bool
    description: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProviderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    base_url: str = ""
    api_key: str = ""
    provider_type: str = "openai-compatible"
    enabled: bool = True
    is_default: bool = False


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = None
    api_key: str | None = None
    provider_type: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None


class ProviderRead(BaseModel):
    id: int
    user_id: int
    name: str
    base_url: str
    api_key: str
    provider_type: str
    enabled: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime
    models: list[ProviderModelRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DefaultModelResponse(BaseModel):
    chat_model: str | None
    embedding_model: str | None
    video_model: str | None = None
    image_model: str | None = None
    provider_id: int | None
    provider_name: str | None

class RemoteModelEntry(BaseModel):
    """A single model entry with its suggested type."""
    name: str
    suggested_type: str = "chat"  # chat | image | video | embedding


class RemoteModelsResponse(BaseModel):
    """Response from fetching available models from a provider's /v1/models API."""
    models: list[RemoteModelEntry] = Field(default_factory=list)
    error: str | None = None


class RemoteModelsFetchRequest(BaseModel):
    """Request to fetch models using arbitrary base_url + api_key (e.g. before a provider is saved)."""
    base_url: str
    api_key: str

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


# ============================================================
# 电商套图模块 Schemas
# ============================================================

class GalleryProjectImageRead(BaseModel):
    id: int
    project_id: int
    filename: str
    url: str
    original: bool
    order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GalleryPlanItemRead(BaseModel):
    id: int
    project_id: int
    type_id: str
    order: int
    personal_settings: dict = Field(default_factory=dict)
    common_settings: dict = Field(default_factory=dict)
    output_settings: dict = Field(default_factory=dict)
    note: str = ""
    reference_images: list = Field(default_factory=list)
    status: str

    model_config = ConfigDict(from_attributes=True)


class GalleryRecordRead(BaseModel):
    id: int
    project_id: int
    plan_item_id: int | None
    type_id: str
    title: str
    result_filename: str | None
    result_url: str | None
    status: str
    prompt: str
    provider_id: int | None = None
    provider_name: str | None = None
    model_name: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GalleryShowcaseRead(BaseModel):
    id: int
    category: str
    name: str
    original_url: str
    image_urls: list = Field(default_factory=list)
    total_count: int

    model_config = ConfigDict(from_attributes=True)


class GalleryTemplateRead(BaseModel):
    id: int
    user_id: int
    name: str
    payload: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GalleryProjectRead(BaseModel):
    id: int
    user_id: int
    name: str
    status: str
    selling_points: str
    market_config: dict = Field(default_factory=dict)
    output_config: dict = Field(default_factory=dict)
    estimated_points: int
    estimated_minutes: float
    images: list[GalleryProjectImageRead] = Field(default_factory=list)
    plan_items: list[GalleryPlanItemRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GalleryProjectCreate(BaseModel):
    name: str = Field(default="未命名套图", max_length=200)


class GalleryProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    selling_points: str | None = None
    market_config: dict | None = None
    output_config: dict | None = None
    status: str | None = None


class GalleryPlanItemCreate(BaseModel):
    type_id: str = Field(..., min_length=1, max_length=40)
    personal_settings: dict = Field(default_factory=dict)
    common_settings: dict = Field(default_factory=dict)
    output_settings: dict = Field(default_factory=dict)
    note: str = ""
    reference_images: list = Field(default_factory=list)


class GalleryPlanItemUpdate(BaseModel):
    type_id: str | None = Field(default=None, max_length=40)
    personal_settings: dict | None = None
    common_settings: dict | None = None
    output_settings: dict | None = None
    note: str | None = None
    reference_images: list | None = None
    order: int | None = None


class GalleryPlanReorder(BaseModel):
    ordered_ids: list[int] = Field(default_factory=list)


class GalleryTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    payload: dict = Field(default_factory=dict)


class GalleryGenerateResponse(BaseModel):
    project_id: int
    status: str
    total_images: int
    total_points: int
    total_minutes: float
    records: list[GalleryRecordRead] = Field(default_factory=list)


class GalleryTypesResponse(BaseModel):
    types: list[dict] = Field(default_factory=list)
    options: dict = Field(default_factory=dict)


class GalleryEstimateResponse(BaseModel):
    total_points: int
    total_minutes: float
    total_images: int


