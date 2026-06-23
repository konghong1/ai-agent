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


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    system_prompt: str | None = None
    model_name: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    enabled: bool | None = None


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
