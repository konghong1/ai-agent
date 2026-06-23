from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent import ask_agent
from app.core.database import get_db
from app.core.security import create_access_token
from app.deps import get_current_user
from app.models import AgentConfig, McpServer, Message, Skill, Thread, User
from app.schemas import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    ChatRequest,
    ChatResponse,
    McpServerCreate,
    McpServerRead,
    McpServerUpdate,
    MessageRead,
    SkillCreate,
    SkillRead,
    SkillUpdate,
    ThreadCreate,
    ThreadRead,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.services import DEFAULT_SYSTEM_PROMPT, authenticate_user, create_user, new_thread_id
from app.settings import get_settings


router = APIRouter()


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


@router.get("/agents", response_model=list[AgentRead])
def list_agents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[AgentConfig]:
    return list(db.scalars(select(AgentConfig).where(AgentConfig.user_id == current_user.id).order_by(AgentConfig.created_at)))


@router.post("/agents", response_model=AgentRead)
def create_agent(payload: AgentCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentConfig:
    settings = get_settings()
    agent = AgentConfig(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        system_prompt=payload.system_prompt or DEFAULT_SYSTEM_PROMPT,
        model_name=payload.model_name or settings.openai_model,
        temperature=payload.temperature,
        enabled=payload.enabled,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.patch("/agents/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: int, payload: AgentUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> AgentConfig:
    agent = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == current_user.id))
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")
    for key, value in payload.model_dump(exclude_unset=True).items():
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
def list_messages(thread_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Message]:
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
