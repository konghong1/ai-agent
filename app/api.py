from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import ask_agent
from app.core.database import get_db
from app.core.security import create_access_token
from app.deps import get_current_user
from app.models import (
    KBFeedback, RetrievalLog,
AgentConfig, AgentKnowledgeBase, KnowledgeBase, KBFolder, KBDocument,
Message, Skill, Thread, User, McpServer, SystemSetting,
)
from app.schemas import (
    KBStatsResponse,
AgentCreate, AgentRead, AgentUpdate,
ChatRequest, ChatResponse,
KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate,
KBFolderCreate, KBFolderRead, KBFolderUpdate,
KBDocumentRead, KBSearchRequest, KBSearchResult, KBUploadResponse,
McpServerCreate, McpServerRead, McpServerUpdate,
MessageRead,
SkillCreate, SkillRead, SkillUpdate,
ThreadCreate, ThreadRead,
TokenResponse, UserCreate, UserLogin, UserRead,
UserUpdate as UserUpdateSchema, UserManagementRead,
SystemSettingCreate, SystemSettingRead, SystemSettingUpdate,
)
from app.services import (
    HybridRetriever, ContextBuilder, RAG_SYSTEM_PROMPT, QueryRewriter,
DEFAULT_SYSTEM_PROMPT, authenticate_user, create_user, new_thread_id,
KnowledgeBaseService, UserService, SystemSettingService,
)
from app.settings import get_settings


router = APIRouter()


# ============================================================
# Auth
# ============================================================

@router.post("/auth/register", response_model=TokenResponse)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(select(User).where((User.email == payload.email.lower()) | (User.username == payload.username)))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email or username already exists.")
    user = create_user(db, payload.email, payload.username, payload.password)
    return TokenResponse(access_token=create_access_token(str(user.id)), user=UserRead.model_validate(user))


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    return TokenResponse(access_token=create_access_token(str(user.id)), user=UserRead.model_validate(user))


@router.get("/auth/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


# ============================================================
# Agents
# ============================================================

@router.get("/agents", response_model=list[AgentRead])
def list_agents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[AgentConfig]:
    return list(db.scalars(select(AgentConfig).where(AgentConfig.user_id == current_user.id).order_by(AgentConfig.created_at)))


@router.post("/agents", response_model=AgentRead)
def create_agent(payload: AgentCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentConfig:
    settings = get_settings()
    agent = AgentConfig(
        user_id=current_user.id, name=payload.name, description=payload.description,
        system_prompt=payload.system_prompt or DEFAULT_SYSTEM_PROMPT,
        model_name=payload.model_name or settings.openai_model,
        temperature=payload.temperature, enabled=payload.enabled,
    )
    db.add(agent)
    db.flush()

    # Bind knowledge bases
    if payload.knowledge_base_ids:
        kbs = db.scalars(select(KnowledgeBase).where(KnowledgeBase.id.in_(payload.knowledge_base_ids), KnowledgeBase.user_id == current_user.id)).all()
        for kb in kbs:
            db.add(AgentKnowledgeBase(agent_id=agent.id, kb_id=kb.id))

    db.commit()
    db.refresh(agent)
    return agent


@router.patch("/agents/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: int, payload: AgentUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentConfig:
    agent = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == current_user.id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "knowledge_base_ids":
            # Replace all KB bindings
            db.execute(select(AgentKnowledgeBase).where(AgentKnowledgeBase.agent_id == agent_id))
            for kb_id in value:
                kb = db.scalar(select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id))
                if kb:
                    db.add(AgentKnowledgeBase(agent_id=agent_id, kb_id=kb.id))
        else:
            setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/agents/{agent_id}", status_code=204)
def delete_agent(agent_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    agent = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == current_user.id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    db.delete(agent)
    db.commit()


# ============================================================

@router.get("/agents/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentConfig:
    agent = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == current_user.id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent


@router.get("/agents/{agent_id}/threads", response_model=list[ThreadRead])
def list_agent_threads(agent_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Thread]:
    agent = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == current_user.id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return list(db.scalars(select(Thread).where(Thread.agent_id == agent_id).order_by(Thread.updated_at.desc())))

# Threads & Messages
# ============================================================

@router.get("/threads", response_model=list[ThreadRead])
def list_threads(agent_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Thread]:
    query = select(Thread).where(Thread.user_id == current_user.id)
    if agent_id is not None:
        query = query.where(Thread.agent_id == agent_id)
    return list(db.scalars(query.order_by(Thread.updated_at.desc())))


@router.post("/threads", response_model=ThreadRead)
def create_thread(payload: ThreadCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Thread:
    agent = db.scalar(select(AgentConfig).where(AgentConfig.id == payload.agent_id, AgentConfig.user_id == current_user.id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    thread = Thread(id=new_thread_id(), user_id=current_user.id, agent_id=agent.id, title=payload.title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


@router.get("/threads/{thread_id}/messages", response_model=list[MessageRead])
def get_thread_messages(thread_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Message]:
    thread = db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == current_user.id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return list(db.scalars(select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)))


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ChatResponse:
    try:
        answer, thread_id, blocks = ask_agent(db=db, user_id=current_user.id, agent_id=payload.agent_id, message=payload.message, thread_id=payload.thread_id)
        return ChatResponse(answer=answer, thread_id=thread_id, blocks=blocks)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


# ============================================================
# MCP Servers
# ============================================================

@router.get("/mcp-servers", response_model=list[McpServerRead])
def list_mcp_servers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[McpServer]:
    return list(db.scalars(select(McpServer).where(McpServer.user_id == current_user.id).order_by(McpServer.created_at)))


@router.post("/mcp-servers", response_model=McpServerRead)
def create_mcp_server(payload: McpServerCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> McpServer:
    server = McpServer(user_id=current_user.id, **payload.model_dump())
    db.add(server)
    db.commit()
    db.refresh(server)
    return server


@router.patch("/mcp-servers/{server_id}", response_model=McpServerRead)
def update_mcp_server(server_id: int, payload: McpServerUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> McpServer:
    server = db.scalar(select(McpServer).where(McpServer.id == server_id, McpServer.user_id == current_user.id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(server, key, value)
    db.commit()
    db.refresh(server)
    return server


@router.delete("/mcp-servers/{server_id}", status_code=204)
def delete_mcp_server(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    server = db.scalar(select(McpServer).where(McpServer.id == server_id, McpServer.user_id == current_user.id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    db.delete(server)
    db.commit()


@router.post("/mcp-servers/{server_id}/test")
def test_mcp_server(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    server = db.scalar(select(McpServer).where(McpServer.id == server_id, McpServer.user_id == current_user.id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    if server.transport == "stdio" and not server.command:
        raise HTTPException(status_code=400, detail="stdio MCP server requires a command.")
    if server.transport in {"sse", "http"} and not server.url:
        raise HTTPException(status_code=400, detail="remote MCP server requires a url.")
    return {"status": "configured", "message": "MCP runtime connection will be enabled in the next integration step."}


# ============================================================
# Skills
# ============================================================

@router.get("/skills", response_model=list[SkillRead])
def list_skills(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Skill]:
    return list(db.scalars(select(Skill).where(Skill.user_id == current_user.id).order_by(Skill.created_at)))


@router.post("/skills", response_model=SkillRead)
def create_skill(payload: SkillCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Skill:
    skill = Skill(user_id=current_user.id, **payload.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.patch("/skills/{skill_id}", response_model=SkillRead)
def update_skill(skill_id: int, payload: SkillUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Skill:
    skill = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == current_user.id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(skill, key, value)
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    skill = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == current_user.id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    db.delete(skill)
    db.commit()


# ============================================================

@router.get("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseRead)
def get_kb(kb_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> KnowledgeBase:
    kb = db.scalar(select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == current_user.id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    return kb

# Knowledge Base Routes (Task 14)
# ============================================================

@router.get("/knowledge-bases", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[KnowledgeBase]:
    return list(KnowledgeBaseService.list_kbs(db, current_user.id))


@router.post("/knowledge-bases", response_model=KnowledgeBaseRead)
def create_knowledge_base(payload: KnowledgeBaseCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> KnowledgeBase:
    kb = KnowledgeBaseService.create_kb(
        db, user_id=current_user.id, name=payload.name,
        description=payload.description, embedding_model=payload.embedding_model,
        chunk_size=payload.chunk_size, chunk_overlap=payload.chunk_overlap,
        enabled=payload.enabled,
    )
    return kb


@router.patch("/knowledge-bases/{kb_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base(kb_id: int, payload: KnowledgeBaseUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> KnowledgeBase:
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    return KnowledgeBaseService.update_kb(db, kb, **payload.model_dump(exclude_unset=True))


@router.delete("/knowledge-bases/{kb_id}", status_code=204)
def delete_knowledge_base(kb_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    KnowledgeBaseService.delete_kb(db, kb)


# ---- Folders ----

@router.post("/knowledge-bases/{kb_id}/folders", response_model=KBFolderRead)
def create_folder(kb_id: int, payload: KBFolderCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> KBFolder:
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    folder = KnowledgeBaseService.create_folder(db, kb_id=kb_id, name=payload.name, description=payload.description, parent_id=payload.parent_id)
    return folder


@router.delete("/knowledge-bases/{kb_id}/folders/{folder_id}", status_code=204)
def delete_folder(kb_id: int, folder_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    folder = db.get(KBFolder, folder_id)
    if not folder or folder.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="Folder not found.")
    KnowledgeBaseService.delete_folder(db, folder)


@router.get("/knowledge-bases/{kb_id}/folders/tree", response_model=list[KBFolderRead])
def get_folder_tree(kb_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[KBFolder]:
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    tree = KnowledgeBaseService.get_folder_tree(db, kb_id)
    return tree


# ---- Documents ----

@router.post("/knowledge-bases/{kb_id}/upload", response_model=KBUploadResponse)
def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    folder_id: int | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KBUploadResponse:
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    try:
        file_bytes = file.file.read()
        doc = KnowledgeBaseService.upload_document(db, kb_id=kb_id, user_id=current_user.id,
                                                     folder_id=folder_id, file_bytes=file_bytes,
                                                     original_filename=file.filename or "unknown")
        result = KnowledgeBaseService.process_document(db, doc.id)
        return KBUploadResponse(document_id=doc.id, status=result["status"], message=result["message"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}")


@router.get("/knowledge-bases/{kb_id}/documents", response_model=list[KBDocumentRead])
def list_documents(kb_id: int, folder_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[KBDocument]:
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    return KnowledgeBaseService.list_documents(db, kb_id, folder_id=folder_id)


@router.delete("/knowledge-bases/{kb_id}/documents/{doc_id}", status_code=204)
def delete_document(kb_id: int, doc_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    doc = db.get(KBDocument, doc_id)
    if not doc or doc.kb_id != kb_id:
        raise HTTPException(status_code=404, detail="Document not found.")
    KnowledgeBaseService.delete_document(db, doc)


# ---- Search ----

@router.post("/knowledge-bases/search", response_model=list[KBSearchResult])
def search_knowledge_bases(payload: KBSearchRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[KBSearchResult]:
    if payload.kb_id:
        kb = KnowledgeBaseService.get_kb(db, payload.kb_id, current_user.id)
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found.")
        hits = KnowledgeBaseService.search_knowledge_base(db, payload.kb_id, payload.query, top_k=payload.top_k, folder_id=payload.folder_id)
    else:
        kbs = KnowledgeBaseService.list_kbs(db, current_user.id)
        hits = []
        for kb in kbs:
            hits.extend(KnowledgeBaseService.search_knowledge_base(db, kb.id, payload.query, top_k=payload.top_k))
    return [KBSearchResult(**h) for h in hits]


# ============================================================
# User Management Routes (Task 15)
# ============================================================

@router.get("/users", response_model=list[UserManagementRead])
def list_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[User]:
    users = UserService.list_users(db, current_user.id)
    return users


@router.patch("/users/{user_id}", response_model=UserManagementRead)
def update_user(user_id: int, payload: UserUpdateSchema, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    try:
        return UserService.update_user(db, target, current_user.id, **payload.model_dump(exclude_unset=True))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    try:
        UserService.delete_user(db, target, current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


# ============================================================
# System Settings Routes (Task 16)
# ============================================================

@router.get("/settings", response_model=list[SystemSettingRead])
def list_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SystemSetting]:
    return SystemSettingService.list_settings(db)


@router.post("/settings", response_model=SystemSettingRead)
def create_setting(payload: SystemSettingCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SystemSetting:
    return SystemSettingService.set_setting(db, payload.key, payload.value, payload.description)


@router.patch("/settings/{key}", response_model=SystemSettingRead)
def update_setting(key: str, payload: SystemSettingUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SystemSetting:
    return SystemSettingService.set_setting(db, key, payload.value or "", payload.description or "")


@router.delete("/settings/{key}", status_code=204)
def delete_setting(key: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    SystemSettingService.delete_setting(db, key)

# ---- RAG Statistics ----

@router.get("/knowledge-bases/{kb_id}/stats", response_model=KBStatsResponse)
def get_kb_stats(
    kb_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get knowledge base statistics for RAG quality monitoring."""
    kb = KnowledgeBaseService.get_kb(db, kb_id, current_user.id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    total_docs = db.scalar(select(func.count(KBDocument.id)).where(KBDocument.kb_id == kb_id)) or 0
    total_chunks = db.scalar(select(func.count(KBChunk.id)).where(KBChunk.kb_id == kb_id)) or 0
    status_rows = db.execute(
        select(KBDocument.status, func.count(KBDocument.id))
        .where(KBDocument.kb_id == kb_id)
        .group_by(KBDocument.status)
    ).all()
    status_breakdown = {row[0]: row[1] for row in status_rows}

    hot_queries = db.execute(
        select(RetrievalLog.query, func.count(RetrievalLog.id).label('cnt'))
        .where(RetrievalLog.kb_id == kb_id)
        .group_by(RetrievalLog.query)
        .order_by(desc('cnt'))
        .limit(10)
    ).all()
    hot = [str(r.query) for r in hot_queries]

    return KBStatsResponse(
        total_documents=total_docs,
        total_chunks=total_chunks,
        avg_chunks_per_doc=round(total_chunks / max(total_docs, 1), 1),
        status_breakdown=status_breakdown,
        hot_queries=hot,
    )


# ---- Retrieval Feedback ----

@router.post("/retrieval-feedback")
def submit_feedback(
    payload: RetrievalFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit user feedback on retrieval results."""
    feedback = KBFeedback(
        user_id=current_user.id,
        thread_id=payload.thread_id,
        chunk_id=payload.chunk_id,
        is_helpful=payload.is_helpful,
        comment=payload.comment,
    )
    db.add(feedback)
    db.commit()
    return {"status": "ok"}


# ---- Update KB RAG Config ----

@router.patch("/knowledge-bases/{kb_id}/rag-config")
def update_kb_rag_config(
    kb_id: int,
    payload: RAGConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update RAG configuration for a knowledge base."""
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    if kb.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    for key, value in payload.model_dump(exclude_unset=True).items():
        kb.rag_config[key] = value

    db.commit()
    db.refresh(kb)
    return {"status": "ok", "rag_config": kb.rag_config}



