from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import queue as _queue
import threading as _threading
import urllib.request
import uuid
from datetime import datetime
from urllib.parse import urlparse, unquote

import requests as _requests

# Logging — INFO level keeps useful diagnostics without the massive
# overhead of DEBUG (httpx/openai produce thousands of lines at DEBUG).
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.orm import Session

from app.agent import ask_agent, _get_or_create_thread, ask_agent_stream_gen, ask_agent_sync
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.deps import get_current_user, get_current_user_sse, require_superuser, require_team_admin
from app.media import MediaService
from app.storage import get_storage_backend_for_bucket
from app.models import (
    KBFeedback, RetrievalLog,
AgentConfig, AgentKnowledgeBase, KnowledgeBase, KBFolder, KBDocument,
Message, Provider, ProviderModel, Skill, Thread, User, McpServer, SystemSetting,
PromptTemplate, UserMemory, PendingMemory, Hook, ToolCallAudit,
TeamAdminScope, UserPermission, Team, TeamMember, ApprovalLog,
TeamJoinRequest, TeamInvite, Resource, Role, RolePermission, UserRole,
)
from app.schemas import (
    KBStatsResponse,
AgentCreate, AgentRead, AgentUpdate,
ChatRequest, ChatResponse,
KnowledgeBaseCreate, KnowledgeBaseRead, KnowledgeBaseUpdate,
KBFolderCreate, KBFolderRead, KBFolderUpdate,
KBDocumentRead, KBSearchRequest, KBSearchResult, KBUploadResponse,
McpServerCreate, McpServerRead, McpServerUpdate,
MessageRead, MessagesPage,
SkillCreate, SkillRead, SkillUpdate, SkillDetailRead,
ThreadCreate, ThreadRead, ThreadUpdate,
TokenResponse, UserCreate, UserLogin, UserRead,
UserUpdate as UserUpdateSchema, UserManagementRead,
SystemSettingCreate, SystemSettingRead, SystemSettingUpdate,
PromptTemplateCreate, PromptTemplateRead, PromptTemplateUpdate,
    ProviderCreate, ProviderRead, ProviderUpdate,
    ProviderModelCreate, ProviderModelRead, ProviderModelUpdate,
    DefaultModelResponse, RemoteModelsResponse, RemoteModelEntry, RemoteModelsFetchRequest,
    HookCreate, HookUpdate, HookRead, ToolCallAuditRead,
)

from app.core.crypto import encrypt_secret, encrypt_json
from app.security_gate import run_security_gate, SecurityReport
from app.settings import get_settings
from app.services import (
    HybridRetriever, ContextBuilder, RAG_SYSTEM_PROMPT, QueryRewriter,
DEFAULT_SYSTEM_PROMPT, authenticate_user, create_user, new_thread_id,
KnowledgeBaseService, UserService, SystemSettingService, ProviderService,
)
from app.settings import get_settings
from app.memory import MemoryWriter, MemoryStore
from app.context_service import ContextService, BuildOptions
from app.permissions import (
    PERSONAL_DEFAULT,
    can, get_user_permissions, get_role_permissions, get_team_admin_scope, is_team_admin,
    ensure_personal_defaults,
    PERM_ADMIN_PERMISSIONS_MANAGE, PERM_ADMIN_USERS_MANAGE,
)


router = APIRouter(prefix="/api")


# ============================================================
# Media Proxy — route external CDN content through the backend
# to avoid client-side proxy/network restrictions.
# ============================================================

_MEDIA_PROXY_ALLOWED_DOMAINS = {
    "platform-outputs.agnes-ai.space",
}


@router.get("/media/proxy")
def proxy_media(
    url: str,
    request: Request,
):
    """Proxy external CDN media content to bypass client proxy/network issues.

    Supports HTTP Range requests for video seeking.

    NOTE: intentionally has NO auth dependency. Media elements (<img>/<video>)
    loaded directly by the browser cannot attach a Bearer token, so requiring
    authentication would always return 401 for them. Access is restricted by
    the domain whitelist below (SSRF protection), which is sufficient for an
    internal tool.
    """
    target_url = unquote(url)

    parsed = urlparse(target_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")

    # SSRF protection: only allow whitelisted CDN domains
    if parsed.hostname not in _MEDIA_PROXY_ALLOWED_DOMAINS:
        raise HTTPException(status_code=403, detail="Domain not allowed")

    # Forward Range header for video seek support
    fwd_headers: dict[str, str] = {}
    range_header = request.headers.get("range")
    if range_header:
        fwd_headers["Range"] = range_header

    try:
        resp = _requests.get(target_url, stream=True, timeout=30, headers=fwd_headers)
        resp.raise_for_status()
    except _requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch media: {exc}")

    content_type = resp.headers.get("content-type", "application/octet-stream")
    filename = parsed.path.split("/")[-1] or "media"

    # Pass through status code (200 or 206 Partial Content) and Range headers
    status_code = resp.status_code
    resp_headers: dict[str, str] = {
        "Cache-Control": "public, max-age=3600",
        "Content-Disposition": f'inline; filename="{filename}"',
        "Accept-Ranges": "bytes",
    }
    if "content-range" in resp.headers:
        resp_headers["Content-Range"] = resp.headers["content-range"]
    if "content-length" in resp.headers:
        resp_headers["Content-Length"] = resp.headers["content-length"]

    def stream_content():
        try:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        finally:
            resp.close()

    return StreamingResponse(
        stream_content(),
        media_type=content_type,
        status_code=status_code,
        headers=resp_headers,
    )


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


@router.post("/auth/reset-password")
def reset_password(
    email: str,
    new_password: str,
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    """Superuser-only: reset any user's password."""
    if len(new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 6 characters.")
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.password_hash = hash_password(new_password)
    db.commit()
    return {"ok": True, "message": f"Password reset for {user.email}"}


@router.post("/admin/users/{user_id}/promote")
def promote_user(
    user_id: int,
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    """Superuser-only: grant superuser to a user."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    u.is_superuser = True
    db.commit()
    return {"ok": True, "user": UserRead.model_validate(u)}


@router.post("/admin/users/{user_id}/demote")
def demote_user(
    user_id: int,
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    """Superuser-only: revoke superuser (cannot demote self or the last superuser)."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if u.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能降级自己")
    if not db.scalars(select(User).where(User.is_superuser, User.id != u.id)).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="至少保留一位超级管理员")
    u.is_superuser = False
    db.commit()
    return {"ok": True, "user": UserRead.model_validate(u)}


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

    return list(db.scalars(select(Thread).where(Thread.agent_id == agent_id).order_by(Thread.created_at.asc())))


@router.post('/agents/{agent_id}/threads', response_model=ThreadRead)
def create_agent_thread(agent_id: int, payload: ThreadCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    agent = db.scalar(select(AgentConfig).where(AgentConfig.id == agent_id, AgentConfig.user_id == current_user.id))
    if not agent:
        raise HTTPException(status_code=404, detail='Agent not found.')
    thread = Thread(id=new_thread_id(), user_id=current_user.id, agent_id=agent.id, title=payload.title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread

# Threads & Messages
# ============================================================

@router.get("/threads", response_model=list[ThreadRead])
def list_threads(agent_id: int | None = None, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Thread]:
    query = select(Thread).where(Thread.user_id == current_user.id)
    if agent_id is not None:
        query = query.where(Thread.agent_id == agent_id)
    return list(db.scalars(query.order_by(Thread.created_at.asc())))


@router.post("/threads", response_model=ThreadRead)
def create_thread(payload: ThreadCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Thread:
    # Support creating threads without agent (new chat flow)
    agent = None
    if payload.agent_id:
        agent = db.scalar(select(AgentConfig).where(AgentConfig.id == payload.agent_id, AgentConfig.user_id == current_user.id))
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found.")
    thread = Thread(id=new_thread_id(), user_id=current_user.id, agent_id=agent.id if agent else None, title=payload.title)
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread



@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(thread_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    thread = db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == current_user.id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    # Bulk-delete child rows by thread_id. Query.delete() issues a direct
    # `DELETE ... WHERE thread_id = ?` with NO ORDER BY / filesort, which avoids
    # "Out of sort memory" (MySQL 1038) when a thread has many messages.
    # We deliberately do NOT call db.delete(thread): that triggers the ORM
    # cascade, which lazy-loads thread.messages with `ORDER BY created_at` and
    # blows the MySQL sort buffer, rolling back the whole delete.
    db.query(Message).filter(Message.thread_id == thread_id).delete(synchronize_session=False)
    # RAG feedback / retrieval logs reference thread_id but have no FK cascade.
    db.query(KBFeedback).filter(KBFeedback.thread_id == thread_id).delete(synchronize_session=False)
    db.query(RetrievalLog).filter(RetrievalLog.thread_id == thread_id).delete(synchronize_session=False)
    # Finally remove the thread row itself (bulk delete bypasses ORM cascade load).
    db.query(Thread).filter(Thread.id == thread_id, Thread.user_id == current_user.id).delete(synchronize_session=False)
    db.commit()



@router.patch("/threads/{thread_id}", response_model=ThreadRead)
def rename_thread(thread_id: str, payload: ThreadUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Thread:
    """Rename a thread (session)."""
    thread = db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == current_user.id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")
    thread.title = payload.title
    db.commit()
    db.refresh(thread)
    return thread


@router.get("/threads/{thread_id}/messages", response_model=MessagesPage)
def get_thread_messages(
    thread_id: str,
    limit: int = 20,
    before: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessagesPage:
    """Return a *page* of messages for a thread, newest-last within the page.

    - No ``before`` -> the most recent ``limit`` messages (initial load). The
      client shows these and starts scrolled to the bottom.
    - ``before=<id>`` -> the ``limit`` messages immediately *older* than that
      cursor (scroll-up history loading). We compare on ``(created_at, id)`` so
      ties at the same timestamp stay deterministic and offset-free.

    ``has_more`` / ``oldest_id`` let the client page further back with the same
    ``before`` cursor. The query is bounded by ``LIMIT`` so it never sorts the
    whole table (which on MySQL can hit "Out of sort memory").
    """
    thread = db.scalar(select(Thread).where(Thread.id == thread_id, Thread.user_id == current_user.id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found.")

    limit = max(1, min(int(limit), 50))

    # (created_at, id) < (ref_created_at, ref_id) — the cursor comparison.
    def cursor_lt(ref_created_at, ref_id):
        return or_(
            Message.created_at < ref_created_at,
            and_(Message.created_at == ref_created_at, Message.id < ref_id),
        )

    if before is None:
        # Newest page: take the last `limit` messages in ascending order.
        rows = list(
            db.scalars(
                select(Message)
                .where(Message.thread_id == thread.id)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
            )
        )
        rows.reverse()  # newest-last
        total = db.scalar(
            select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
        ) or 0
        has_more = total > len(rows)
        oldest = rows[0] if rows else None
    else:
        ref = db.get(Message, before)
        # Unknown / foreign cursor -> fall back to the newest page.
        if ref is None or ref.thread_id != thread.id:
            rows = list(
                db.scalars(
                    select(Message)
                    .where(Message.thread_id == thread.id)
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(limit)
                )
            )
            rows.reverse()
            total = db.scalar(
                select(func.count()).select_from(Message).where(Message.thread_id == thread.id)
            ) or 0
            has_more = total > len(rows)
            oldest = rows[0] if rows else None
        else:
            # The `limit` messages strictly older than the cursor, newest-last.
            rows = list(
                db.scalars(
                    select(Message)
                    .where(Message.thread_id == thread.id)
                    .where(cursor_lt(ref.created_at, ref.id))
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(limit)
                )
            )
            rows.reverse()
            oldest = rows[0] if rows else None
            if oldest is None:
                has_more = False
            else:
                older_count = db.scalar(
                    select(func.count())
                    .select_from(Message)
                    .where(Message.thread_id == thread.id)
                    .where(cursor_lt(oldest.created_at, oldest.id))
                ) or 0
                has_more = older_count > 0

    # Defensive: older rows may have extra=NULL in the DB, but MessageRead.extra
    # is a required dict. Coerce None -> {} so response validation never fails.
    for m in rows:
        if m.extra is None:
            m.extra = {}

    return MessagesPage(
        messages=rows,
        has_more=has_more,
        oldest_id=oldest.id if oldest else None,
        limit=limit,
    )


# Dedicated bucket for user-uploaded chat images — kept separate from
# generated media (ai-agent-minio) per the storage design.
CHAT_UPLOAD_BUCKET = os.getenv("CHAT_UPLOAD_BUCKET", "chat-uploads")


@router.post("/chat/upload", response_model=dict)
def upload_chat_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a user-attached chat image to a dedicated MinIO bucket.

    Flow (per requirement): user image -> MinIO (separate ``chat-uploads``
    bucket) -> returns a same-origin proxy URL -> frontend sends that URL to
    the model. Because MinIO is on a private/local address the remote model
    cannot fetch it, so ``ask_agent`` inlines it as base64 before the call.
    """
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")

    original = file.filename or ""
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    mime = file.content_type or mimetypes.guess_type(original)[0] or "image/png"
    if not ext:
        ext = (mime.split("/")[-1] if "/" in mime else "png").lower()

    now = datetime.now()
    key = f"uploads/{current_user.id}/{now:%Y/%m/%d}/{uuid.uuid4().hex}.{ext}"
    backend = get_storage_backend_for_bucket(CHAT_UPLOAD_BUCKET)
    backend.put(data, key, mime_type=mime)

    url = f"/api/media/assets/by-key/{key}?bucket={CHAT_UPLOAD_BUCKET}"
    return {"object_key": key, "bucket": CHAT_UPLOAD_BUCKET, "url": url, "mime_type": mime}


# ============================================================
# Media generation helpers (image / video)
# ============================================================

def _resolve_provider_model(db: Session, provider_id: int, model_name: str) -> ProviderModel | None:
    """Look up a ProviderModel by provider_id + model_name."""
    return db.scalar(
        select(ProviderModel).where(
            ProviderModel.provider_id == provider_id,
            ProviderModel.model_name == model_name,
        )
    )


def _normalize_num_frames(n: int | None, default: int = 121, max_frames: int = 241) -> int:
    """The video model requires num_frames to equal 8*n + 1
    (e.g. 1, 9, 17, 25, 33, ...). Round any incoming value to the nearest
    valid form. This is a server-side guard so a malformed client request can
    never produce an HTTP 400 from the provider."""
    if not n or n < 1:
        return default
    k = round((n - 1) / 8)
    if k < 0:
        k = 0
    frames = 8 * k + 1
    if frames > max_frames:
        max_k = (max_frames - 1) // 8
        frames = 8 * max_k + 1
    return frames


def _normalize_error(err: object | None) -> str:
    """Coerce a provider error (which may be a dict/list from a JSON body,
    or already a string) into a clean, display-safe string. Storing a dict in
    blocks.error would crash the React UI ("Objects are not valid as a React
    child") and blank the entire chat."""
    if err is None:
        return ""
    if isinstance(err, str):
        return err
    if isinstance(err, (dict, list)):
        try:
            return json.dumps(err, ensure_ascii=False)
        except Exception:
            return str(err)
    return str(err)


def _handle_image_generation(
    db: Session,
    provider: Provider,
    model: ProviderModel,
    payload: ChatRequest,
    current_user: User,
) -> ChatResponse:
    """Generate an image and store the result as a chat message."""
    result = MediaService.generate_image(
        provider=provider,
        model_name=model.model_name,
        prompt=payload.message,
        size=payload.size or "1024x768",
        n=payload.n or 1,
        reference_images=payload.reference_images,
        tags=payload.tags,
        seed=payload.seed,
    )

    images = result.get("data", [])
    image_url = images[0].get("url", "") if images else ""
    error = _normalize_error(result.get("error"))

    thread = _get_or_create_thread(db, current_user.id, payload.agent_id, payload.message, payload.thread_id)
    db.add(Message(
        thread_id=thread.id, role="user", content=payload.message,
        extra={"blocks": {"reference_images": payload.reference_images}} if payload.reference_images else None,
    ))

    if error:
        answer = f"Image generation failed: {error}"
        blocks = {"type": "image", "error": error, "reference_images": payload.reference_images}
    elif image_url:
        # Persist the image into object storage (MinIO) so it is served via an
        # internal by-key URL rather than depending on the external CDN. Falls
        # back to the original URL (which still works through the proxy) on
        # any failure, so generation never breaks because of storage issues.
        served_url = image_url
        try:
            if image_url.startswith("http"):
                stored = MediaService._download_and_store(
                    image_url, "image", user_id=current_user.id
                )
                if stored.get("object_key"):
                    served_url = stored["url"]
                    logger.info("Image uploaded to object storage: key=%s", stored["object_key"])
                    # Persist a management record for the hosted asset.
                    try:
                        from app.models import MediaAsset
                        db.add(MediaAsset(
                            user_id=current_user.id,
                            media_type="image",
                            object_key=stored["object_key"],
                            internal_url=served_url,
                            mime_type=stored.get("mime_type"),
                            file_size=stored.get("file_size"),
                            status="completed",
                        ))
                        db.flush()
                    except Exception as rec_exc:
                        logger.warning("Image MediaAsset record skipped: %s", rec_exc)
        except Exception as exc:  # pragma: no cover - best-effort
            logger.warning("Image store skipped (using CDN url): %s", exc)

        answer = f"![Generated Image]({served_url})"
        blocks = {"type": "image", "image_url": served_url, "images": images, "reference_images": payload.reference_images}
    else:
        answer = "Image generation completed but no image URL returned."
        blocks = {"type": "image", "raw_result": result, "reference_images": payload.reference_images}

    db.add(Message(
        thread_id=thread.id, role="assistant", content=answer,
        extra={"blocks": blocks},
    ))
    db.commit()
    return ChatResponse(answer=answer, thread_id=thread.id, blocks=blocks)


def _handle_video_generation(
    db: Session,
    provider: Provider,
    model: ProviderModel,
    payload: ChatRequest,
    current_user: User,
) -> ChatResponse:
    """Submit a video generation task and store the result as a chat message."""
    result = MediaService.generate_video(
        provider=provider,
        model_name=model.model_name,
        prompt=payload.message,
        width=payload.width or 1152,
        height=payload.height or 768,
        num_frames=_normalize_num_frames(payload.num_frames),
        frame_rate=payload.frame_rate or 24,
        reference_images=payload.reference_images,
        mode=payload.mode,
        negative_prompt=payload.negative_prompt,
        seed=payload.seed,
    )

    task_id = result.get("id") or result.get("task_id", "")
    video_id = result.get("video_id", "")
    error = _normalize_error(result.get("error"))

    thread = _get_or_create_thread(db, current_user.id, payload.agent_id, payload.message, payload.thread_id)
    db.add(Message(
        thread_id=thread.id, role="user", content=payload.message,
        extra={"blocks": {"reference_images": payload.reference_images}} if payload.reference_images else None,
    ))

    if error:
        answer = f"Video generation failed: {error}"
        blocks = {"type": "video", "status": "failed", "error": error, "reference_images": payload.reference_images}
    else:
        answer = f"正在生成视频..."
        blocks = {
            "type": "video",
            "task_id": task_id,
            "video_id": video_id,
            "status": "processing",
            "provider_id": provider.id,
            "reference_images": payload.reference_images,
        }

    db.add(Message(
        thread_id=thread.id, role="assistant", content=answer,
        extra={"blocks": blocks},
    ))
    db.commit()
    return ChatResponse(answer=answer, thread_id=thread.id, blocks=blocks)


# ============================================================
# Chat endpoints
# ============================================================

@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ChatResponse:
    try:
        # ── Model-type routing: detect non-chat models and dispatch ──
        if payload.provider_id and payload.model_name:
            provider = db.get(Provider, payload.provider_id)
            if provider and provider.user_id == current_user.id and provider.enabled:
                provider_model = _resolve_provider_model(db, payload.provider_id, payload.model_name)
                if provider_model:
                    if provider_model.model_type == "video":
                        return _handle_video_generation(db, provider, provider_model, payload, current_user)
                    elif provider_model.model_type == "image":
                        return _handle_image_generation(db, provider, provider_model, payload, current_user)
                    # chat / embedding: fall through to existing flow

        # Determine which system prompt and model to use
        system_prompt = None
        model_name = None
        provider_id = None
        provider_base_url = None
        
        # Priority: template > agent
        if payload.template_id:
            template = db.get(PromptTemplate, payload.template_id)
            if template and template.user_id == current_user.id and template.enabled:
                system_prompt = template.system_prompt
        
        if system_prompt is None and payload.agent_id:
            agent = db.get(AgentConfig, payload.agent_id)
            if agent and agent.user_id == current_user.id and agent.enabled:
                system_prompt = agent.system_prompt
                model_name = agent.model_name
        
        # Override with explicit provider/model selection
        if payload.provider_id:
            provider = db.get(Provider, payload.provider_id)
            if provider and provider.user_id == current_user.id and provider.enabled:
                provider_base_url = provider.base_url
                if payload.model_name:
                    model_name = payload.model_name
                elif provider.is_default:
                    # Find default model for this provider
                    default_model = db.scalar(select(ProviderModel).where(
                        ProviderModel.provider_id == provider.id,
                        ProviderModel.is_default_chat == True,
                        ProviderModel.model_type == "chat",
                        ProviderModel.enabled == True,
                    ))
                    if default_model:
                        model_name = default_model.model_name
                elif provider.models:
                    model_name = provider.models[0].model_name if provider.models[0].model_type == "chat" else None
        
        # Call ask_agent with the resolved parameters
        answer, thread_id, blocks = ask_agent_sync(
            db=db,
            user_id=current_user.id,
            agent_id=payload.agent_id,
            message=payload.message,
            thread_id=payload.thread_id,
            system_prompt=system_prompt,
            model_name=model_name,
            provider_base_url=provider_base_url,
            provider_type=payload.provider_type,
            provider_id=payload.provider_id,
            reference_images=payload.reference_images,
        )
        return ChatResponse(answer=answer, thread_id=thread_id, blocks=blocks)
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Chat error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


# ============================================================
# SSE Streaming Chat
# ============================================================


def _run_text_chat(user_id, agent_id, message, thread_id, system_prompt, model_name,
                   provider_base_url, provider_type, provider_id, reference_images):
    """Run ask_agent in a worker thread with its OWN database session.

    The session is created and closed entirely inside the worker thread, so a
    client disconnect (which cancels the SSE generator) can never close the
    session mid-commit. This guarantees the user + assistant messages are
    always persisted — even if the user switches tabs or conversations while
    the model is still generating a reply.
    """
    from app.agent import ask_agent_sync
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        return ask_agent_sync(
            db=db,
            user_id=user_id,
            agent_id=agent_id,
            message=message,
            thread_id=thread_id,
            system_prompt=system_prompt,
            model_name=model_name,
            provider_base_url=provider_base_url,
            provider_type=provider_type,
            provider_id=provider_id,
            reference_images=reference_images,
        )
    finally:
        db.close()


def _run_media_chat(media_kind: str, provider_id, model_name, payload, user_id):
    """Run image/video generation in a worker thread with its OWN DB session.

    Same rationale as ``_run_text_chat``: the session is owned by the thread so
    a client disconnect can't abort the commit that persists the chat messages
    (user prompt + the generated image/video assistant message).
    """
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        provider = db.get(Provider, provider_id)
        if not (provider and provider.user_id == user_id and provider.enabled):
            return None
        provider_model = _resolve_provider_model(db, provider_id, model_name)
        if not provider_model:
            return None
        user = db.get(User, user_id)
        if media_kind == "video":
            return _handle_video_generation(
                db=db, provider=provider, model=provider_model,
                payload=payload, current_user=user,
            )
        return _handle_image_generation(
            db=db, provider=provider, model=provider_model,
            payload=payload, current_user=user,
        )
    finally:
        db.close()


@router.post("/chat-stream")
def chat_stream(payload: ChatRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    """Stream chat response using Server-Sent Events."""
    import asyncio
    import json
    import uuid
    
    async def event_generator():
        from app.agent import ask_agent_sync
        _logger = logging.getLogger(__name__)
        try:
            # ── Model-type routing: detect non-chat models and dispatch ──
            if payload.provider_id and payload.model_name:
                provider = db.get(Provider, payload.provider_id)
                if provider and provider.user_id == current_user.id and provider.enabled:
                    provider_model = _resolve_provider_model(db, payload.provider_id, payload.model_name)
                    if provider_model:
                        if provider_model.model_type == "video":
                            result = await asyncio.to_thread(_run_media_chat, "video", payload.provider_id, payload.model_name, payload, current_user.id)
                            if result is None:
                                yield f"data: {json.dumps({'error': 'provider or model not available'})}\n\n"
                                return
                            yield f"data: {json.dumps({'answer': result.answer, 'thread_id': result.thread_id, 'blocks': result.blocks})}\n\n"
                            return
                        elif provider_model.model_type == "image":
                            result = await asyncio.to_thread(_run_media_chat, "image", payload.provider_id, payload.model_name, payload, current_user.id)
                            if result is None:
                                yield f"data: {json.dumps({'error': 'provider or model not available'})}\n\n"
                                return
                            yield f"data: {json.dumps({'answer': result.answer, 'thread_id': result.thread_id, 'blocks': result.blocks})}\n\n"
                            return

            # Determine which system prompt and model to use (same logic as /chat)
            system_prompt = None
            model_name = None
            provider_base_url = None
            
            if payload.template_id:
                template = db.get(PromptTemplate, payload.template_id)
                if template and template.user_id == current_user.id and template.enabled:
                    system_prompt = template.system_prompt
            
            if system_prompt is None and payload.agent_id:
                agent = db.get(AgentConfig, payload.agent_id)
                if agent and agent.user_id == current_user.id and agent.enabled:
                    system_prompt = agent.system_prompt
                    model_name = agent.model_name

            if payload.provider_id:
                provider = db.get(Provider, payload.provider_id)
                if provider and provider.user_id == current_user.id and provider.enabled:
                    provider_base_url = provider.base_url
                    if payload.model_name:
                        model_name = payload.model_name

            _logger.info(
                "chat-stream request: provider_id=%s model=%s base_url=%s type=%s agent_id=%s",
                payload.provider_id, model_name, provider_base_url, payload.provider_type, payload.agent_id,
            )
            
            # Build the request
            request_data = {
                "message": payload.message,
                "thread_id": payload.thread_id,
                "template_id": payload.template_id,
                "provider_id": payload.provider_id,
                "provider_type": payload.provider_type,
                "model_name": model_name,
                "agent_id": payload.agent_id,
            }
            
            # Send initial event with thread_id
            thread_info = {"event": "thread_ready", "data": json.dumps({"thread_id": request_data.get("thread_id")})}
            yield f"event: thread_ready\ndata: {thread_info['data']}\n\n"
            
            # For now, we use ask_agent which returns a single response
            # In the future, we can integrate async streaming adapters here
            
            # ── Stream tokens via a worker thread that owns its OWN DB session. ──
            # ask_agent_stream_gen runs in a daemon thread (so a client
            # disconnect cancelling this generator can never close its session
            # mid-commit) and pushes events into an asyncio.Queue via
            # call_soon_threadsafe (thread-safe). This generator pulls from the
            # asyncio.Queue and emits SSE events, giving true token-by-token
            # streaming while keeping messages persisted.
            _loop = asyncio.get_event_loop()
            import asyncio as _aio
            _q: "_aio.Queue" = _aio.Queue()

            def _produce() -> None:
                """Background thread: call agent, push events to asyncio.Queue."""
                try:
                    # ── Architecture selection: V2 (model-driven) or V1 (legacy) ──
                    from app.agent_v2 import should_use_v2_architecture, ask_agent_v2_stream_gen
                    
                    if should_use_v2_architecture():
                        _logger.info("Using V2 architecture (model-driven agent loop)")
                        _gen = ask_agent_v2_stream_gen(
                            current_user.id, payload.agent_id, payload.message,
                            request_data.get("thread_id"), system_prompt, model_name,
                            provider_base_url, payload.provider_type, payload.provider_id,
                            payload.reference_images,
                        )
                    else:
                        _gen = ask_agent_stream_gen(
                            current_user.id, payload.agent_id, payload.message,
                            request_data.get("thread_id"), system_prompt, model_name,
                            provider_base_url, payload.provider_type, payload.provider_id,
                            payload.reference_images,
                        )
                    
                    for _item in _gen:
                        # Use call_soon_threadsafe to safely push to asyncio.Queue
                        _loop.call_soon_threadsafe(_q.put_nowait, _item)
                except Exception as _e:  # pragma: no cover - defensive
                    _loop.call_soon_threadsafe(
                        _q.put_nowait,
                        ("error", f"{type(_e).__name__}: {_e}"),
                    )
                finally:
                    _loop.call_soon_threadsafe(_q.put_nowait, None)

            _threading.Thread(target=_produce, daemon=True).start()

            # ── 双保险超时监控 ──
            # 1) chunk_timeout: 60秒无新chunk视为卡死（精准判定）
            # 2) total_timeout: 180秒总时间兜底（防无限跑）
            # 收到delta时重置chunk计时，容忍"慢但有响应"的多步任务
            _start_time = _loop.time()
            _last_chunk_time = _start_time
            _chunk_timeout = 60  # 60秒无chunk视为卡死
            _total_timeout = 180  # 3分钟总超时兜底
            _heartbeat_interval = 10  # 每10秒发一次心跳

            while True:
                try:
                    # 直接 await asyncio.Queue.get - 这是 async-native 方式，不会丢失事件
                    # 用 wait_for 实现可中断的等待（用于心跳检查和超时判定）
                    _item = await _aio.wait_for(_q.get(), timeout=1.0)
                except _aio.TimeoutError:
                    _now = _loop.time()
                    _elapsed = _now - _start_time
                    _no_chunk = _now - _last_chunk_time

                    # 优先判断卡死（更精准）
                    if _no_chunk > _chunk_timeout:
                        _logger.warning("Chat stream stall: no chunk for %ds (total %ds)", _no_chunk, _elapsed)
                        yield f"data: {json.dumps({'error': 'LLM响应超时，请稍后重试。'})}\n\n"
                        break

                    # 兜底：总超时
                    if _elapsed > _total_timeout:
                        _logger.warning("Chat stream total timeout after %ds", _elapsed)
                        yield f"data: {json.dumps({'error': '请求超时，请稍后重试。'})}\n\n"
                        break

                    # 发送心跳（让用户知道还在处理）
                    if int(_elapsed) % _heartbeat_interval == 0 and int(_elapsed) > 0:
                        yield f"data: {json.dumps({'status': f'正在处理中...({int(_elapsed)}秒)'})}\n\n"
                    continue

                if _item is None:
                    break

                # 只有收到 delta 时才重置 chunk 计时
                if _item[0] == "delta":
                    _last_chunk_time = _loop.time()
                    yield f"data: {json.dumps({'delta': _item[1]})}\n\n"
                elif _item[0] == "status":
                    yield f"data: {json.dumps({'status': _item[1]})}\n\n"
                elif _item[0] == "token_usage":
                    # Token 用量统计（前端圆环组件）
                    _total = _item[1].get('total', '?') if isinstance(_item[1], dict) else '?'
                    _logger.info("Yielding token_usage to SSE: total=%s", _total)
                    yield f"data: {json.dumps({'token_usage': _item[1]})}\n\n"
                elif _item[0] == "warning":
                    # 警告（如 max_tokens 截断）
                    yield f"data: {json.dumps({'warning': _item[1]})}\n\n"
                elif _item[0] == "done":
                    yield f"data: {json.dumps({'answer': _item[3], 'thread_id': _item[1], 'blocks': _item[2]})}\n\n"
                elif _item[0] == "error":
                    # 友好化错误提示
                    _err_msg = _item[1]
                    if "timeout" in _err_msg.lower() or "timed out" in _err_msg.lower():
                        _err_msg = "网络请求超时，请检查网络连接后重试。"
                    elif "connection" in _err_msg.lower():
                        _err_msg = "无法连接到 AI 服务，请稍后重试。"
                    elif "api" in _err_msg.lower() and ("key" in _err_msg.lower() or "auth" in _err_msg.lower()):
                        _err_msg = "API 认证失败，请检查您的 API 配置。"
                    yield f"data: {json.dumps({'error': _err_msg})}\n\n"
                
        except Exception as exc:
            import traceback
            _logger = logging.getLogger(__name__)
            tb_str = traceback.format_exc()
            _logger.error("Chat stream error: %s\n%s", exc, tb_str)
            yield f"data: {json.dumps({'error': f'{type(exc).__name__}: {exc}', 'traceback': tb_str[-2000:]})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================
# ============================================================
# Provider Management
# ============================================================
@router.get("/providers", response_model=list[ProviderRead])
def list_providers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Provider]:
    providers = db.scalars(
        select(Provider).where(Provider.user_id == current_user.id).order_by(Provider.created_at)
    ).all()
    result = []
    for p in providers:
        pm = ProviderRead.model_validate(p)
        pm.models = db.scalars(
            select(ProviderModel).where(
                ProviderModel.provider_id == p.id
            ).order_by(ProviderModel.model_type, ProviderModel.model_name)
        ).all()
        result.append(pm)
    return result
@router.post("/providers", response_model=ProviderRead)
def create_provider(payload: ProviderCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Provider:
    provider = Provider(user_id=current_user.id, **payload.model_dump())
    db.add(provider)
    db.flush()
    if payload.is_default:
        db.execute(
            update(Provider).where(
                Provider.user_id == current_user.id, Provider.is_default == True
            ).values(is_default=False)
        )
    db.commit()
    db.refresh(provider)
    return provider
@router.patch("/providers/{provider_id}", response_model=ProviderRead)
def update_provider(provider_id: int, payload: ProviderUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Provider:
    provider = db.scalar(select(Provider).where(Provider.id == provider_id, Provider.user_id == current_user.id))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    data = payload.model_dump(exclude_unset=True)
    if "is_default" in data and data["is_default"]:
        db.execute(
            update(Provider).where(
                Provider.user_id == current_user.id, Provider.id != provider_id, Provider.is_default == True
            ).values(is_default=False)
        )
    provider = ProviderService.update_provider(db, provider, **data)
    return provider
@router.delete("/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    provider = db.scalar(select(Provider).where(Provider.id == provider_id, Provider.user_id == current_user.id))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    ProviderService.delete_provider(db, provider)
# ---- Provider Models ----
@router.get("/providers/{provider_id}/models", response_model=list[ProviderModelRead])
def list_provider_models(provider_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ProviderModel]:
    provider = db.scalar(select(Provider).where(Provider.id == provider_id, Provider.user_id == current_user.id))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    return ProviderService.get_provider_models(db, provider_id)
@router.post("/providers/{provider_id}/models", response_model=ProviderModelRead)
def create_provider_model(provider_id: int, payload: ProviderModelCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProviderModel:
    provider = db.scalar(select(Provider).where(Provider.id == provider_id, Provider.user_id == current_user.id))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    try:
        return ProviderService.create_model(db, provider_id=provider_id, **payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"模型 '{payload.model_name}' 已存在")
@router.patch("/providers/{provider_id}/models/{model_id}", response_model=ProviderModelRead)
def update_provider_model(provider_id: int, model_id: int, payload: ProviderModelUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProviderModel:
    model = db.scalar(select(ProviderModel).where(ProviderModel.id == model_id, ProviderModel.provider_id == provider_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")
    return ProviderService.update_model(db, model, **payload.model_dump(exclude_unset=True))
@router.delete("/providers/{provider_id}/models/{model_id}", status_code=204)
def delete_provider_model(provider_id: int, model_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    model = db.scalar(select(ProviderModel).where(ProviderModel.id == model_id, ProviderModel.provider_id == provider_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")
    ProviderService.delete_model(db, model)
# ── Helper: guess model type from name ──

# ── Type hint keyword sets (substring-matched, lowercased) ──
_IMAGE_HINTS = (
    "dall-e", "dalle", "image", "imagen", "stable-diffusion", "sd-", "sd1", "sd2",
    "sd3", "sd35", "sdxl", "midjourney", "flux", "cogview", "ideogram", "recraft",
    "kolors", "playcartoon", "dreamshaper", "juggernaut", "anything", "deliberate",
    "epicrealism", "realisticvision", "chilloutmix", "abyssorange", "meina", "anime",
    "ponydiffusion", "revanimated", "counterfeit", "dreamlike", "lyriel", "protogen",
    "breakdomain", "edges", "analog", "rcnz", "openjourney", "toonyou", "aom", "hasdx",
    "shonin", "gape", "f222", "niji", "noobai", "illustrious", "pony", "draw", "paint",
    "cartoon", "illustration", "portrait", "sketch", "design", "pixel", "avatar",
    "art", "painting", "render", "gen", "gpt-image", "vision",
)
_VIDEO_HINTS = (
    "sora", "video", "kling", "cogvideo", "runway", "pika", "luma", "veo",
    "hunyuanvideo", "hunyuan-video", "wan", "wan2", "mochi", "minimax-video",
    "lightricks", "ltx", "trellis", "viv", "moonvalley", "haiper", "step-video",
    "t2v", "i2v", "anim", "movie", "film", "seedance", "hailuo", "vido", "dream",
    "video", "video-", "hunyuanvideo",
)
_EMBEDDING_HINTS = (
    "embedding", "bge", "text-embedding", "e5-", "gte-", "stella", "m3e", "bce",
    "acge", "jina-embed", "voyage", "cohere-embed", "embed", "uae", "nv-embed",
)
_TTS_HINTS = (
    "tts", "whisper", "speech", "audio", "voice", "music", "suno", "udio",
    "seed-tts", "cosyvoice", "fish", "bark", "audiocraft", "musicgen",
)
_TYPE_VALUES_IMAGE = ("image", "images", "text-to-image", "image-generation")
_TYPE_VALUES_VIDEO = ("video", "videos", "text-to-video", "video-generation", "ttv")
_TYPE_VALUES_EMBEDDING = ("embedding", "embeddings", "text-embedding")


def _suggest_model_type(model_id: str, raw: dict | None = None) -> str:
    """Heuristically guess the model type from its ID string and any metadata.

    Returns one of: chat | image | video | embedding.
    Order matters — image/video/embedding are checked before the generic "chat"
    fallback so that multimodal models are not silently swallowed as chat models.

    Strategy:
      1. Trust explicit provider metadata (type/category/capabilities/modality/
         architecture.modality) when present — this is the most reliable signal.
      2. Fall back to keyword heuristics on the model id.
    """
    lower = (model_id or "").lower()

    # ── 1) Trust explicit provider metadata when present ──
    if isinstance(raw, dict):
        for key in ("type", "category", "model_type"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                v = val.strip().lower()
                if v in _TYPE_VALUES_IMAGE:
                    return "image"
                if v in _TYPE_VALUES_VIDEO:
                    return "video"
                if v in _TYPE_VALUES_EMBEDDING:
                    return "embedding"

        # list/tuple capabilities or modality fields (e.g. ["image", "text"])
        for key in ("capabilities", "modality", "modalities", "input_modalities", "output_modalities"):
            val = raw.get(key)
            joined = ""
            if isinstance(val, (list, tuple)):
                joined = " ".join(str(x).lower() for x in val)
            elif isinstance(val, str):
                joined = val.lower()
            if joined:
                if any(k in joined for k in ("image", "images", "vision", "text-to-image", "image-generation")):
                    return "image"
                if any(k in joined for k in ("video", "videos", "text-to-video", "video-generation")):
                    return "video"
                if any(k in joined for k in ("embedding", "embed")):
                    return "embedding"

        # OpenRouter-style architecture.modality, e.g. "text+image->text"
        arch = raw.get("architecture")
        if isinstance(arch, dict):
            modality = arch.get("modality") or arch.get("input_modalities") or ""
            if isinstance(modality, (list, tuple)):
                modality = " ".join(str(x) for x in modality)
            modality = (modality or "").lower()
            if "image" in modality:
                return "image"
            if "video" in modality:
                return "video"
            if "audio" in modality:
                return "chat"

    # ── 2) Keyword heuristics (image/video/embedding before chat fallback) ──
    if any(k in lower for k in _IMAGE_HINTS):
        return "image"

    if any(k in lower for k in _VIDEO_HINTS):
        return "video"

    if any(k in lower for k in _EMBEDDING_HINTS):
        return "embedding"

    # TTS / audio / music — not separately managed yet, keep as chat fallback
    if any(k in lower for k in _TTS_HINTS):
        return "chat"

    return "chat"


# ── Remote model fetching endpoints ──


def _fetch_models_from_api(base_url: str, api_key: str) -> tuple[list[RemoteModelEntry], str | None]:
    """Call /v1/models and return typed model entries."""
    models_url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(
        models_url,
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode())
        entries = []
        for m in body.get("data", []):
            mid = m.get("id")
            if not mid:
                continue
            entries.append(RemoteModelEntry(
                name=mid,
                suggested_type=_suggest_model_type(mid, m),
            ))
        return entries, None


@router.get("/providers/{provider_id}/remote-models", response_model=RemoteModelsResponse)
def fetch_remote_models(provider_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RemoteModelsResponse:
    """Fetch available model names from a provider's /v1/models endpoint, with suggested types."""
    provider = db.scalar(select(Provider).where(Provider.id == provider_id, Provider.user_id == current_user.id))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")
    if not provider.base_url or not provider.api_key:
        return RemoteModelsResponse(error="请先配置 Base URL 和 API Key")

    try:
        entries, _err = _fetch_models_from_api(provider.base_url, provider.api_key)
        return RemoteModelsResponse(models=entries)
    except Exception as e:
        return RemoteModelsResponse(error=f"无法连接: {e}")


@router.post("/providers/fetch-remote-models", response_model=RemoteModelsResponse)
def fetch_remote_models_preview(payload: RemoteModelsFetchRequest) -> RemoteModelsResponse:
    """Fetch available model names from an arbitrary /v1/models endpoint before saving a provider."""
    base_url = payload.base_url.strip()
    api_key = payload.api_key.strip()
    if not base_url or not api_key:
        return RemoteModelsResponse(error="请先填写 Base URL 和 API Key")

    try:
        entries, _err = _fetch_models_from_api(base_url, api_key)
        return RemoteModelsResponse(models=entries)
    except Exception as e:
        return RemoteModelsResponse(error=f"无法连接: {e}")


@router.get("/providers/default-model", response_model=DefaultModelResponse)
def get_default_model(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DefaultModelResponse:
    return ProviderService.get_default_model(db, current_user.id)
# MCP Servers
# ============================================================

def _to_mcp_read(server: McpServer) -> McpServerRead:
    return McpServerRead(
        id=server.id, name=server.name, transport=server.transport,
        command=server.command, args=server.args, env=server.env, url=server.url,
        enabled=server.enabled, auth_type=server.auth_type,
        tool_allowlist=server.tool_allowlist or [],
        timeout_ms=server.timeout_ms, max_retries=server.max_retries,
        has_api_key=bool(server.api_key), has_headers=bool(server.headers),
    )


@router.get("/mcp-servers", response_model=list[McpServerRead])
def list_mcp_servers(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[McpServerRead]:
    rows = db.scalars(select(McpServer).where(McpServer.user_id == current_user.id).order_by(McpServer.created_at))
    return [_to_mcp_read(s) for s in rows]


@router.post("/mcp-servers", response_model=McpServerRead)
def create_mcp_server(payload: McpServerCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> McpServerRead:
    data = payload.model_dump()
    api_key = data.pop("api_key", "")
    headers = data.pop("headers", {})
    server = McpServer(user_id=current_user.id, **data)
    server.api_key = encrypt_secret(api_key)
    server.headers = encrypt_json(headers)
    db.add(server)
    db.commit()
    db.refresh(server)
    # §1.1 工具池事件失效：新增 server 后下一轮聊天重建工具。
    from app.mcp_tools import invalidate_tool_pool as _invalidate_mcp_pool
    from app.tool_pool import invalidate_tool_pool as _invalidate_tool_pool_v2
    
    _invalidate_mcp_pool(current_user.id)
    _invalidate_tool_pool_v2(current_user.id, reason="mcp_server_created")
    return _to_mcp_read(server)


@router.patch("/mcp-servers/{server_id}", response_model=McpServerRead)
def update_mcp_server(server_id: int, payload: McpServerUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> McpServerRead:
    server = db.scalar(select(McpServer).where(McpServer.id == server_id, McpServer.user_id == current_user.id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    data = payload.model_dump(exclude_unset=True)
    api_key = data.pop("api_key", None)
    headers = data.pop("headers", None)
    for key, value in data.items():
        setattr(server, key, value)
    if api_key is not None:
        server.api_key = encrypt_secret(api_key)
    if headers is not None:
        server.headers = encrypt_json(headers)
    db.commit()
    db.refresh(server)
    # §1.1 工具池事件失效：配置变更（allowlist/enabled/name 等）后重建工具。
    from app.mcp_tools import invalidate_tool_pool as _invalidate_mcp_pool
    from app.tool_pool import invalidate_tool_pool as _invalidate_tool_pool_v2
    
    _invalidate_mcp_pool(current_user.id)
    _invalidate_tool_pool_v2(current_user.id, reason="mcp_server_updated")
    return _to_mcp_read(server)


@router.delete("/mcp-servers/{server_id}", status_code=204)
def delete_mcp_server(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    server = db.scalar(select(McpServer).where(McpServer.id == server_id, McpServer.user_id == current_user.id))
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    db.delete(server)
    db.commit()
    # §1.1 工具池事件失效：删除 server 后重建工具。
    from app.mcp_tools import invalidate_tool_pool as _invalidate_mcp_pool
    from app.tool_pool import invalidate_tool_pool as _invalidate_tool_pool_v2
    
    _invalidate_mcp_pool(current_user.id)
    _invalidate_tool_pool_v2(current_user.id, reason="mcp_server_deleted")


def _get_mcp_owner(server_id: int, current_user: User, db: Session) -> McpServer:
    s = db.scalar(select(McpServer).where(McpServer.id == server_id, McpServer.user_id == current_user.id))
    if not s:
        raise HTTPException(status_code=404, detail="MCP server not found.")
    return s


@router.post("/mcp-servers/{server_id}/security-check", response_model=SecurityReport)
def security_check_mcp(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SecurityReport:
    server = _get_mcp_owner(server_id, current_user, db)
    return run_security_gate("mcp", server)


@router.post("/mcp-servers/{server_id}/enable")
def enable_mcp_server(server_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    server = _get_mcp_owner(server_id, current_user, db)
    if get_settings().enable_security_gate:
        report = run_security_gate("mcp", server)
        if not report.passed:
            raise HTTPException(status_code=400, detail={"message": "安全闸门未通过", "report": report.to_dict()})
    server.enabled = True
    db.commit()
    return {"status": "enabled", "id": server.id}


# ============================================================
# Hooks（用户自定义生命周期钩子）
# ============================================================

def _to_hook_read(hook: Hook) -> HookRead:
    return HookRead(
        id=hook.id, user_id=hook.user_id, skill_id=hook.skill_id, event=hook.event,
        matcher=hook.matcher, command=hook.command, env=hook.env,
        has_secret_env=bool(hook.secret_env), timeout_ms=hook.timeout_ms,
        on_error=hook.on_error, enabled=hook.enabled,
    )


@router.get("/hooks", response_model=list[HookRead])
def list_hooks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[HookRead]:
    rows = db.scalars(select(Hook).where(Hook.user_id == current_user.id).order_by(Hook.created_at))
    return [_to_hook_read(h) for h in rows]


@router.post("/hooks", response_model=HookRead)
def create_hook(payload: HookCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> HookRead:
    data = payload.model_dump()
    secret_env = data.pop("secret_env", {})
    hook = Hook(user_id=current_user.id, **data)
    hook.secret_env = encrypt_json(secret_env)
    db.add(hook)
    db.commit()
    db.refresh(hook)
    return _to_hook_read(hook)


@router.patch("/hooks/{hook_id}", response_model=HookRead)
def update_hook(hook_id: int, payload: HookUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> HookRead:
    hook = db.scalar(select(Hook).where(Hook.id == hook_id, Hook.user_id == current_user.id))
    if not hook:
        raise HTTPException(status_code=404, detail="Hook not found.")
    data = payload.model_dump(exclude_unset=True)
    secret_env = data.pop("secret_env", None)
    for key, value in data.items():
        setattr(hook, key, value)
    if secret_env is not None:
        hook.secret_env = encrypt_json(secret_env)
    db.commit()
    db.refresh(hook)
    return _to_hook_read(hook)


@router.delete("/hooks/{hook_id}", status_code=204)
def delete_hook(hook_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    hook = db.scalar(select(Hook).where(Hook.id == hook_id, Hook.user_id == current_user.id))
    if not hook:
        raise HTTPException(status_code=404, detail="Hook not found.")
    db.delete(hook)
    db.commit()


@router.post("/hooks/{hook_id}/security-check", response_model=SecurityReport)
def security_check_hook(hook_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SecurityReport:
    hook = db.scalar(select(Hook).where(Hook.id == hook_id, Hook.user_id == current_user.id))
    if not hook:
        raise HTTPException(status_code=404, detail="Hook not found.")
    return run_security_gate("hook", hook)


@router.post("/hooks/{hook_id}/enable")
def enable_hook(hook_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    hook = db.scalar(select(Hook).where(Hook.id == hook_id, Hook.user_id == current_user.id))
    if not hook:
        raise HTTPException(status_code=404, detail="Hook not found.")
    if get_settings().enable_security_gate:
        report = run_security_gate("hook", hook)
        if not report.passed:
            raise HTTPException(status_code=400, detail={"message": "安全闸门未通过", "report": report.to_dict()})
    hook.enabled = True
    db.commit()
    return {"status": "enabled", "id": hook.id}


# ============================================================
# Tool Call Audit（只读）
# ============================================================

@router.get("/tool-call-audits", response_model=list[ToolCallAuditRead])
def list_audits(current_user: User = Depends(get_current_user), db: Session = Depends(get_db), limit: int = 100) -> list[ToolCallAuditRead]:
    rows = db.scalars(
        select(ToolCallAudit)
        .where(ToolCallAudit.user_id == current_user.id)
        .order_by(ToolCallAudit.created_at.desc())
        .limit(min(limit, 500))
    )
    return list(rows)


# ============================================================
# 扩展层可观测性（万级并发容量评估 / 排障）
# ============================================================

@router.get("/extensions/metrics")
def extensions_metrics(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """返回 MCP 连接池、Hook 失败率、审计总量等运行指标（租户隔离）。"""
    from app.mcp_client import MCPConnectionManager

    # MCP 连接池指标
    mcp_metrics = MCPConnectionManager.get_metrics()

    # 本租户 Hook 审计聚合（最近 1000 条）
    audits = db.scalars(
        select(ToolCallAudit)
        .where(ToolCallAudit.user_id == current_user.id)
        .order_by(ToolCallAudit.created_at.desc())
        .limit(1000)
    ).all()
    total = len(audits)
    blocked = sum(1 for a in audits if a.status == "blocked")
    errored = sum(1 for a in audits if a.status == "error")
    hook_failure_rate = round((blocked + errored) / total, 4) if total else 0.0

    # 本租户资源计数
    mcp_count = db.scalar(
        select(func.count()).select_from(McpServer).where(McpServer.user_id == current_user.id)
    ) or 0
    skill_count = db.scalar(
        select(func.count()).select_from(Skill).where(Skill.user_id == current_user.id, Skill.enabled.is_(True))
    ) or 0
    hook_count = db.scalar(
        select(func.count()).select_from(Hook).where(Hook.user_id == current_user.id, Hook.enabled.is_(True))
    ) or 0

    return {
        "user_id": current_user.id,
        "deploy_mode": get_settings().deploy_mode,
        "mcp_pool": mcp_metrics,
        "hook_audit": {
            "total": total,
            "blocked": blocked,
            "errored": errored,
            "failure_rate": hook_failure_rate,
        },
        "enabled_resources": {
            "mcp_servers": mcp_count,
            "skills": skill_count,
            "hooks": hook_count,
        },
        "note": "API 无状态，可 docker compose up --scale api=N 水平扩容；MCP 池按副本分片。",
    }


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
    enabled_toggle = payload.enabled if "enabled" in payload.model_dump(exclude_unset=True) else None
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(skill, key, value)
    # 启用/停用切换时同步声明式 Hook（声明钩子随技能一并激活/休眠）。
    if enabled_toggle is not None:
        from app.skill_runtime import apply_skill_enabled

        apply_skill_enabled(db, skill, bool(enabled_toggle))
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


@router.get("/skills/{skill_id}", response_model=SkillDetailRead)
def get_skill(skill_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Skill:
    skill = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == current_user.id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return skill


@router.post("/skills/{skill_id}/security-check", response_model=SecurityReport)
def security_check_skill(skill_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SecurityReport:
    skill = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == current_user.id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return run_security_gate("skill", skill)


@router.post("/skills/{skill_id}/enable")
def enable_skill(skill_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    skill = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.user_id == current_user.id))
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    if get_settings().enable_security_gate:
        report = run_security_gate("skill", skill)
        if not report.passed:
            raise HTTPException(status_code=400, detail={"message": "安全闸门未通过", "report": report.to_dict()})
    # 启用技能并同步其声明式 Hook（声明钩子随技能一并激活）。
    from app.skill_runtime import apply_skill_enabled

    apply_skill_enabled(db, skill, True)
    linked = db.scalars(select(Hook).where(Hook.skill_id == skill.id, Hook.enabled.is_(True))).all()
    db.commit()
    return {"status": "enabled", "id": skill.id, "linked_hooks": len(linked)}


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
# Prompt Template Routes (Task: Replace Agent in chat)
# ============================================================

@router.get("/prompt-templates", response_model=list[PromptTemplateRead])
def list_prompt_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> list[PromptTemplate]:
    return list(db.scalars(
        select(PromptTemplate).where(
            PromptTemplate.user_id == current_user.id
        ).order_by(desc(PromptTemplate.created_at))
    ))


@router.post("/prompt-templates", response_model=PromptTemplateRead, status_code=status.HTTP_201_CREATED)
def create_prompt_template(
    payload: PromptTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PromptTemplate:
    import re
    import uuid as _uuid

    # Auto-generate a slug on the backend when the client didn't supply one.
    def _slugify(value: str) -> str:
        s = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", value.strip().lower()).strip("_")
        return s or f"tpl_{_uuid.uuid4().hex[:8]}"

    base = payload.slug or _slugify(payload.name)
    slug = base
    # Ensure slug uniqueness (append numeric suffix on collision).
    n = 1
    while db.scalar(select(PromptTemplate).where(PromptTemplate.slug == slug)):
        n += 1
        slug = f"{base}_{n}"

    template = PromptTemplate(
        user_id=current_user.id,
        name=payload.name,
        slug=slug,
        system_prompt=payload.system_prompt,
        variables=payload.variables,
        category=payload.category,
        description=payload.description,
        enabled=payload.enabled,
        is_default=payload.is_default,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.patch("/prompt-templates/{template_id}", response_model=PromptTemplateRead)
def update_prompt_template(
    template_id: int,
    payload: PromptTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PromptTemplate:
    template = db.get(PromptTemplate, template_id)
    if not template or template.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Template not found.")
    
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)
    
    db.commit()
    db.refresh(template)
    return template


@router.delete("/prompt-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> None:
    template = db.get(PromptTemplate, template_id)
    if not template or template.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Template not found.")
    db.delete(template)
    db.commit()


@router.get("/prompt-templates/default", response_model=PromptTemplateRead)
def get_default_prompt_template(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> PromptTemplate:
    template = db.scalar(select(PromptTemplate).where(
        PromptTemplate.user_id == current_user.id,
        PromptTemplate.is_default == True,
        PromptTemplate.enabled == True,
    ))
    if not template:
        # Return first enabled template as fallback
        template = db.scalar(select(PromptTemplate).where(
            PromptTemplate.user_id == current_user.id,
            PromptTemplate.enabled == True,
        ).limit(1))
    if not template:
        raise HTTPException(status_code=404, detail="No default template found.")
    return template


# ============================================================
# Simplified Provider/Model endpoint for chat selector
# ============================================================

@router.get("/providers-chat")
def get_providers_for_chat(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return all enabled providers with their models grouped by type (chat/video/image) for the chat UI selector."""
    providers = db.scalars(
        select(Provider).where(
            Provider.user_id == current_user.id,
            Provider.enabled == True,
        ).order_by(Provider.is_default.desc(), Provider.name)
    ).all()

    def _model_entry(m: ProviderModel) -> dict:
        return {
            "id": m.id,
            "name": m.model_name,
            "is_default": (
                m.is_default_chat if m.model_type == "chat"
                else m.is_default_image if m.model_type == "image"
                else m.is_default_video if m.model_type == "video"
                else m.is_default_embedding
            ),
        }

    result = []
    for p in providers:
        models_by_type: dict[str, list[dict]] = {"chat": [], "video": [], "image": []}
        for m in p.models:
            if not m.enabled or m.model_type not in models_by_type:
                continue
            models_by_type[m.model_type].append(_model_entry(m))

        # Build type-grouped response with defaults
        grouped = {}
        for mtype, models in models_by_type.items():
            default = next((m for m in models if m["is_default"]), models[0] if models else None)
            grouped[mtype] = {
                "models": models,
                "default": {"id": default["id"], "name": default["name"]} if default else None,
            }

        result.append({
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "provider_type": p.provider_type,
            "models_by_type": grouped,
        })

    return {"providers": result}


@router.get("/providers-all")
def get_all_providers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Return all enabled providers with their models grouped by type (chat/video/image/embedding)."""
    providers = db.scalars(
        select(Provider).where(
            Provider.user_id == current_user.id,
            Provider.enabled == True,
        ).order_by(Provider.is_default.desc(), Provider.name)
    ).all()

    result = []
    for p in providers:
        models_by_type: dict = {"chat": [], "image": [], "video": [], "embedding": []}
        for m in p.models:
            if not m.enabled:
                continue
            entry = {
                "id": m.id,
                "name": m.model_name,
                "is_default": (
                    m.is_default_chat if m.model_type == "chat"
                    else m.is_default_image if m.model_type == "image"
                    else m.is_default_video if m.model_type == "video"
                    else m.is_default_embedding
                ),
            }
            bucket = models_by_type.setdefault(m.model_type, [])
            bucket.append(entry)

        result.append({
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "models": models_by_type,
        })

    return {"providers": result}


# ── Video task status ──


def _record_video_asset(db: Session, user_id: int, result: dict) -> None:
    """Persist a completed video as a ``MediaAsset`` so it shows up in the
    media library. Idempotent: skips if the object_key already exists."""
    key = result.get("object_key")
    if not key:
        return
    from app.models import MediaAsset

    try:
        existing = db.scalar(
            select(MediaAsset).where(MediaAsset.object_key == key)
        )
        if existing:
            return
        db.add(MediaAsset(
            user_id=user_id,
            media_type="video",
            object_key=key,
            internal_url=result.get("video_url") or result.get("stored_video_url"),
            mime_type="video/mp4",
            file_size=result.get("file_size") or 0,
            status="completed",
        ))
        db.flush()
    except Exception as rec_exc:  # pragma: no cover - best-effort bookkeeping
        logger.warning("Video MediaAsset record skipped: %s", rec_exc)


@router.get("/videos/{task_id}/status")
def get_video_status(
    task_id: str,
    provider_id: int,
    video_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Poll the status of a video generation task.

    Also persists the completed / failed status into the corresponding
    chat message so history survives page refreshes.
    """
    provider = db.scalar(
        select(Provider).where(
            Provider.id == provider_id,
            Provider.user_id == current_user.id,
            Provider.enabled == True,
        )
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")

    result = MediaService.get_video_status(provider, task_id)

    # Persist completed / failed status to the chat message
    status = result.get("status") or result.get("state", "")
    # Normalize status values from various providers
    normalized_status = status.lower().strip() if status else ""
    if normalized_status in ("done", "success", "finished", "ready", "available"):
        status = "completed"
    elif normalized_status in ("failed", "error", "cancelled", "canceled"):
        status = "failed"
    video_url = (
        result.get("remixed_from_video_id")
        or result.get("video_url")
        or result.get("output")
        or result.get("url")
        or ""
    )
    error = result.get("error", "")

    # Record the hosted video asset so it appears in the media library.
    if result.get("object_key") and status in ("completed", "succeeded"):
        _record_video_asset(db, current_user.id, result)

    if status in ("completed", "succeeded", "failed", "error") or video_url:
        _persist_video_status(db, current_user.id, task_id, status, video_url, error)
        db.commit()

    return result


@router.get("/videos/{task_id}/watch")
def watch_video_status(
    task_id: str,
    provider_id: int,
    video_id: str | None = None,
    current_user: User = Depends(get_current_user_sse),
    db: Session = Depends(get_db),
):
    """SSE endpoint that pushes video status changes in real time.

    The client opens this as an EventSource and receives ``data:`` events
    whenever the video transitions through queued → processing →
    completed / failed.  No client-side polling needed.
    """
    provider = db.scalar(
        select(Provider).where(
            Provider.id == provider_id,
            Provider.user_id == current_user.id,
            Provider.enabled == True,
        )
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found.")

    import asyncio
    import json

    POLL_INTERVAL = 3       # seconds between internal polls
    MAX_POLLS = 200         # ~10 minutes timeout
    HEARTBEAT_INTERVAL = 1  # seconds between heartbeat comments

    async def event_generator():
        # Send an immediate heartbeat so the client knows the connection is live
        yield f": connected\n\n"

        poll_count = 0
        last_heartbeat = asyncio.get_event_loop().time()

        while poll_count < MAX_POLLS:
            # ── Run the blocking HTTP poll in a thread to avoid
            #    blocking the event loop (the #1 cause of "stuck loading"). ──
            try:
                result = await asyncio.to_thread(
                    MediaService.get_video_status, provider, task_id
                )
            except Exception as exc:
                logger.warning("Video status poll error: %s", exc)
                result = {"error": str(exc)}

            poll_count += 1

            status = result.get("status") or result.get("state", "")
            # Normalize status values from various providers
            normalized_status = status.lower().strip() if status else ""
            if normalized_status in ("done", "success", "finished", "ready", "available"):
                status = "completed"
            elif normalized_status in ("failed", "error", "cancelled", "canceled"):
                status = "failed"
            video_url = (
                result.get("video_url")
                or result.get("output")
                or result.get("url")
                or ""
            )
            # Agnes AI: "remixed_from_video_id" is a video ID, not a URL —
            # only use it if it looks like a URL (starts with http)
            remixed = result.get("remixed_from_video_id", "")
            if not video_url and remixed and str(remixed).startswith("http"):
                video_url = remixed

            error = _normalize_error(result.get("error"))

            if status in ("completed", "succeeded") or (video_url and status not in ("failed", "error")):
                _record_video_asset(db, current_user.id, result)
                _persist_video_status(db, current_user.id, task_id,
                                       status if status else "completed",
                                       video_url, "")
                db.commit()
                yield f"data: {json.dumps({'status': 'completed', 'video_url': video_url, 'poll_count': poll_count})}\n\n"
                return

            if status in ("failed", "error"):
                _persist_video_status(db, current_user.id, task_id,
                                       status, "", error or "")
                db.commit()
                yield f"data: {json.dumps({'status': 'failed', 'error': error or '视频生成失败'})}\n\n"
                return

            # Push a status update so the frontend can show progress
            yield f"data: {json.dumps({'status': status or 'processing', 'poll_count': poll_count})}\n\n"

            # Wait before next poll, sending periodic heartbeats to keep
            # the SSE connection alive through proxies.
            await asyncio.sleep(POLL_INTERVAL)

        # Timeout
        _persist_video_status(db, current_user.id, task_id,
                               "failed", "", "视频生成超时")
        db.commit()
        yield f"data: {json.dumps({'status': 'failed', 'error': '视频生成超时，请重试'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def _persist_video_status(
    db: Session,
    user_id: int,
    task_id: str,
    status: str,
    video_url: str,
    error: str,
) -> None:
    """Update the DB message whose extra.blocks.task_id matches."""
    from sqlalchemy.orm.attributes import flag_modified

    # Find the assistant message with this video task_id (search recent
    # messages belonging to threads owned by this user).
    msg = db.scalar(
        select(Message)
        .join(Thread, Message.thread_id == Thread.id)
        .where(
            Thread.user_id == user_id,
            Message.role == "assistant",
        )
        .order_by(Message.created_at.desc())
        .limit(200)
    )
    # Walk through until we find the matching task_id
    while msg:
        blocks = msg.extra.get("blocks") if isinstance(msg.extra, dict) else None
        if isinstance(blocks, dict) and blocks.get("task_id") == task_id:
            break
        # fetch next — in practice we could batch this, but for small
        # datasets walking sequentially is fine.
        msg = db.scalar(
            select(Message)
            .join(Thread, Message.thread_id == Thread.id)
            .where(
                Thread.user_id == user_id,
                Message.role == "assistant",
                Message.created_at < msg.created_at,
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )

    if msg is None:
        return

    if not isinstance(msg.extra, dict):
        msg.extra = {}

    blocks = msg.extra.setdefault("blocks", {})
    if not isinstance(blocks, dict):
        blocks = msg.extra["blocks"] = {}

    if status in ("completed", "succeeded"):
        blocks["status"] = "completed"
        if video_url:
            blocks["video_url"] = video_url
    elif status in ("failed", "error"):
        blocks["status"] = "failed"
        if error:
            blocks["error"] = error

    flag_modified(msg, "extra")
    db.commit()


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


# ============================================================
# Memory API（ADR-022 / 023：跨会话长期记忆 + 隐式候选）
# ============================================================
from pydantic import BaseModel


def _memory_to_dict(m: "UserMemory") -> dict:
    return {
        "id": m.id, "user_id": m.user_id, "layer": m.layer,
        "mem_type": m.mem_type, "key": m.key, "value": m.value,
        "importance": m.importance, "confidence": m.confidence,
        "status": m.status, "source": m.source,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _pending_to_dict(p: "PendingMemory") -> dict:
    return {
        "id": p.id, "user_id": p.user_id, "candidate": p.candidate,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


class MemoryCreate(BaseModel):
    key: str
    value: str
    layer: int = 1
    mem_type: str = "preference"
    importance: float = 0.5
    confidence: float = 1.0


class MemoryUpdate(BaseModel):
    key: str | None = None
    value: str | None = None
    layer: int | None = None
    mem_type: str | None = None
    importance: float | None = None
    confidence: float | None = None


@router.get("/memories")
def list_memories(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """列出当前用户的 active 长期记忆。"""
    return [_memory_to_dict(m) for m in MemoryWriter(db).list_memories(current_user.id, status="active")]


@router.post("/memories")
def create_memory(
    payload: MemoryCreate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """显式写入一条记忆（零幻觉，优先路径）。实体归一：同 key 自动合并。"""
    if not payload.key.strip() or not payload.value.strip():
        raise HTTPException(status_code=400, detail="key 与 value 均不可为空")
    m = MemoryWriter(db).add_explicit(
        current_user.id, payload.key.strip(), payload.value.strip(),
        layer=payload.layer, mem_type=payload.mem_type,
        importance=payload.importance, confidence=payload.confidence,
    )
    return _memory_to_dict(m)


@router.put("/memories/{mem_id}")
def update_memory(
    mem_id: int, payload: MemoryUpdate,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    m = MemoryWriter(db).update_memory(mem_id, current_user.id, **payload.model_dump(exclude_unset=True))
    if m is None:
        raise HTTPException(status_code=404, detail="记忆不存在或无权限")
    return _memory_to_dict(m)


@router.delete("/memories/{mem_id}")
def delete_memory(
    mem_id: int,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """软删除（status=archived），绝不硬删（项目铁律）。"""
    if not MemoryWriter(db).delete_memory(mem_id, current_user.id):
        raise HTTPException(status_code=404, detail="记忆不存在或无权限")
    return {"status": "ok"}


@router.get("/memories/pending")
def list_pending(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """列出待确认的隐式提取候选。"""
    return [_pending_to_dict(p) for p in MemoryWriter(db).list_pending(current_user.id)]


@router.post("/memories/pending/{pending_id}/accept")
def accept_pending(
    pending_id: int,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    mem = MemoryWriter(db).promote(pending_id, current_user.id)
    if mem is None:
        raise HTTPException(status_code=404, detail="候选不存在或已处理")
    return _memory_to_dict(mem)


@router.post("/memories/pending/{pending_id}/reject")
def reject_pending(
    pending_id: int,
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not MemoryWriter(db).reject_pending(pending_id, current_user.id):
        raise HTTPException(status_code=404, detail="候选不存在")
    return {"status": "ok"}


@router.get("/memories/preview")
def preview_memory(
    text: str = "",
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """诊断：返回各记忆块文本（无需 LLM），验证注入是否正确。"""
    s = get_settings()
    opts = BuildOptions(
        recent_turns=s.context_service_recent_turns,
        reflex_cap=s.context_service_reflex_cap,
        recall_k=s.context_service_recall_k,
        enable_reflex=getattr(s, "enable_retrieval_reflex", False),
        enable_memory_recall=getattr(s, "enable_memory_recall", False),
        enable_gap_analysis=getattr(s, "enable_gap_analysis", False),
        enable_rrf=getattr(s, "enable_rrf", False),
    )
    return ContextService(db).preview_memory(current_user.id, text or "", opts)


# ============================================================
# Permission System — 两级委派（超管 → 团队管理员 → 用户）
# ============================================================
from pydantic import BaseModel

class PermissionAssignRequest(BaseModel):
    permission_codes: list[str]

class TeamAdminSetRequest(BaseModel):
    user_id: int
    permission_codes: list[str]


@router.get("/permissions/catalog")
def get_permission_catalog(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """权限目录（最细粒度）。超管见全部；团队管理员另标 grantable（自己 scope 内可授予项）。"""
    held = get_user_permissions(current_user.id, None, db)
    scope = get_team_admin_scope(current_user.id, db) if is_team_admin(current_user, db) else set()
    items = []
    for r in db.query(Resource).filter_by(type="permission").order_by(Resource.sort_order, Resource.code).all():
        items.append({
            "code": r.code,
            "name": r.name,
            "category": r.category,
            "description": r.description or "",
            "sort_order": r.sort_order,
            "is_system": r.is_system,
            "held": r.code in held,
            "grantable": bool(current_user.is_superuser) or (r.code in scope),
        })
    return {"items": items}


@router.get("/me/permissions")
def get_my_permissions(
    team_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户在指定空间的有效权限码（前端菜单/按钮过滤用）。

    返回 角色权限 ∪ 个人/团队显式授权 的加性并集。
    """
    perms = get_user_permissions(current_user.id, team_id, db)
    perms |= get_role_permissions(current_user.id, db)
    # 超管恒有全部权限（与 can() 的 is_superuser 短路一致，权限列表也反映全集）
    if current_user.is_superuser:
        perms |= _perm_resource_codes(db)
    return {
        "permissions": sorted(perms),
        "is_superuser": current_user.is_superuser,
        "is_team_admin": is_team_admin(current_user, db),
    }


@router.get("/system/menus")
def get_system_menus(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户可见的菜单树（动态菜单，由 resources(type='menu') 驱动）。

    - 菜单可见性由节点的 permission_code 决定：超管全可见；其他用户需持有该权限码，
      或无权限码（始终可见），或含有可见子节点。
    - 返回 antd Menu 可直接消费的树形结构。
    """
    menus = db.query(Resource).filter_by(type="menu", is_visible=True).all()

    if current_user.is_superuser:
        perms = _perm_resource_codes(db)
    else:
        perms = get_user_permissions(current_user.id, None, db) | get_role_permissions(current_user.id, db)

    children: dict = {}
    perm_by_code = {m.code: m.permission_code for m in menus}
    for m in menus:
        node = {
            "key": m.path or m.code,
            "label": m.name,
            "icon": m.icon,
            "path": m.path,
            "code": m.code,
            "sort_order": m.sort_order or 0,
            "_perm": perm_by_code.get(m.code),
            "children": [],
        }
        children.setdefault(m.parent_code, []).append(node)

    def build(parent_code):
        out = []
        for n in sorted(children.get(parent_code, []), key=lambda x: x["sort_order"]):
            n["children"] = build(n["code"])
            has_visible_child = len(n["children"]) > 0
            pc = n.get("_perm")
            own_visible = (pc is None) or (pc in perms)
            if not has_visible_child and not own_visible:
                continue
            n.pop("_perm", None)
            out.append(n)
        return out

    tree = build(None)
    return {"menus": tree}


# ============================================================
# 系统管理：资源 / 角色 / 用户-角色（RBAC v2 管理面）
# 守卫：资源与角色管理需 admin.permissions.manage（仅超管持有）；
#       用户-角色分配需 admin.users.manage（仅超管持有）。
# ============================================================

def _require_perm(user: User, db: Session, perm: str) -> None:
    if not can(user, perm, db=db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足，需要管理员权限。")


def _perm_resource_codes(db: Session) -> set[str]:
    """权限码统一真源：resources(type='permission')（ADR-031）。"""
    return {r.code for r in db.query(Resource).filter_by(type="permission").all()}


def _system_perm_codes(db: Session) -> set[str]:
    """系统级（仅超管可授）权限码集合。"""
    return {r.code for r in db.query(Resource).filter_by(type="permission", is_system=True).all()}


def _resource_json(r: Resource) -> dict:
    return {
        "id": r.id, "code": r.code, "name": r.name, "type": r.type,
        "category": r.category, "parent_code": r.parent_code, "path": r.path,
        "component": r.component, "icon": r.icon, "sort_order": r.sort_order,
        "permission_code": r.permission_code, "is_visible": r.is_visible,
        "is_system": r.is_system, "description": r.description,
    }


def _role_json(r: Role, db: Session) -> dict:
    perms = sorted(db.scalars(
        select(RolePermission.permission_code).where(RolePermission.role_id == r.id)
    ).all())
    return {
        "id": r.id, "code": r.code, "name": r.name, "description": r.description,
        "is_system": r.is_system, "is_default": r.is_default, "sort_order": r.sort_order,
        "permissions": perms, "permission_count": len(perms),
    }


class ResourceCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    type: str = "menu"                       # 'menu' | 'permission' | 'api'
    category: str = "general"
    parent_code: str | None = None
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    sort_order: int = 0
    permission_code: str | None = None
    is_visible: bool = True


class ResourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    type: str | None = None
    category: str | None = None
    parent_code: str | None = None
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    permission_code: str | None = None
    is_visible: bool | None = None


class RoleCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    is_default: bool = False


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_default: bool | None = None


class RolePermSet(BaseModel):
    codes: list[str]


class UserRoleAssign(BaseModel):
    role_id: int
    team_id: int | None = None


@router.get("/system/resources")
def list_system_resources(
    type: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """资源列表（菜单/权限/API）。超管可见全部。"""
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    q = select(Resource)
    if type:
        q = q.where(Resource.type == type)
    rows = db.scalars(q.order_by(Resource.type, Resource.sort_order, Resource.code)).all()
    return {"items": [_resource_json(r) for r in rows]}


@router.post("/system/resources", status_code=201)
def create_system_resource(
    payload: ResourceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    if db.query(Resource).filter_by(code=payload.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "资源 code 已存在。")
    r = Resource(
        code=payload.code, name=payload.name, type=payload.type,
        category=payload.category, parent_code=payload.parent_code, path=payload.path,
        component=payload.component, icon=payload.icon, sort_order=payload.sort_order,
        permission_code=payload.permission_code, is_visible=payload.is_visible,
        is_system=False, description=payload.description,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"item": _resource_json(r)}


@router.put("/system/resources/{code}")
def update_system_resource(
    code: str,
    payload: ResourceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    r = db.query(Resource).filter_by(code=code).first()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在。")
    data = payload.model_dump(exclude_unset=True)
    # 系统资源：禁止改类型（菜单/权限分类不可变），仅允许调名称/层级/可见性等展示字段
    if r.is_system and "type" in data and data["type"] != r.type:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统资源不可更改类型。")
    for k, v in data.items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return {"item": _resource_json(r)}


@router.delete("/system/resources/{code}")
def delete_system_resource(
    code: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    r = db.query(Resource).filter_by(code=code).first()
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "资源不存在。")
    if r.is_system:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统资源不可删除。")
    if db.query(Resource).filter_by(parent_code=code).first():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该资源下仍有子项，请先删除子项。")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/system/roles")
def list_system_roles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """角色列表（含各自权限码）。超管可见全部。"""
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    roles = db.scalars(select(Role).order_by(Role.sort_order, Role.id)).all()
    return {"items": [_role_json(r, db) for r in roles]}


@router.post("/system/roles", status_code=201)
def create_system_role(
    payload: RoleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    if db.query(Role).filter_by(code=payload.code).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "角色 code 已存在。")
    r = Role(
        code=payload.code, name=payload.name, description=payload.description,
        is_default=payload.is_default, is_system=False, sort_order=100,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    # 设为默认角色：即时授予所有既有用户（新注册用户由 create_user 自动授予）
    if r.is_default:
        for u in db.query(User).all():
            from app.rbac_seed import assign_default_roles_to_user
            assign_default_roles_to_user(db, u.id)
        db.commit()
    return {"item": _role_json(r, db)}


@router.put("/system/roles/{role_id}")
def update_system_role(
    role_id: int,
    payload: RoleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")
    data = payload.model_dump(exclude_unset=True)
    if r.is_system and ("code" in data or "is_system" in data):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统角色不可更改 code / is_system。")
    was_default = r.is_default
    for k, v in data.items():
        setattr(r, k, v)
    if r.is_default and not was_default:
        for u in db.query(User).all():
            from app.rbac_seed import assign_default_roles_to_user
            assign_default_roles_to_user(db, u.id)
    db.commit()
    db.refresh(r)
    return {"item": _role_json(r, db)}


@router.delete("/system/roles/{role_id}")
def delete_system_role(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")
    if r.is_system:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统角色不可删除。")
    # role_permissions / user_roles 通过外键 ON DELETE CASCADE 级联清理
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/system/roles/{role_id}/permissions")
def get_role_permissions_endpoint(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")
    perms = sorted(db.scalars(
        select(RolePermission.permission_code).where(RolePermission.role_id == role_id)
    ).all())
    return {"role_id": role_id, "permissions": perms}


@router.put("/system/roles/{role_id}/permissions")
def set_role_permissions_endpoint(
    role_id: int,
    payload: RolePermSet,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_perm(current_user, db, PERM_ADMIN_PERMISSIONS_MANAGE)
    r = db.get(Role, role_id)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")
    valid = _perm_resource_codes(db)
    invalid = [c for c in payload.codes if c not in valid]
    if invalid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"未知权限码：{invalid}")
    # 整集替换（纯加性模型下，收回=删关联行）
    db.query(RolePermission).where(RolePermission.role_id == role_id).delete()
    for code in payload.codes:
        db.add(RolePermission(role_id=role_id, permission_code=code, granted_by_user_id=current_user.id))
    db.commit()
    return {"role_id": role_id, "permissions": sorted(payload.codes)}


@router.get("/users/{user_id}/roles")
def get_user_roles_endpoint(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取某用户已分配的角色（global: team_id 恒 NULL）。"""
    _require_perm(current_user, db, PERM_ADMIN_USERS_MANAGE)
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在。")
    rows = db.scalars(select(UserRole).where(UserRole.user_id == user_id)).all()
    out = []
    for ur in rows:
        role = db.get(Role, ur.role_id)
        out.append({
            "role_id": ur.role_id,
            "role_code": role.code if role else None,
            "role_name": role.name if role else None,
            "is_system": role.is_system if role else False,
            "team_id": ur.team_id,
        })
    return {"user_id": user_id, "roles": out}


@router.post("/users/{user_id}/roles")
def assign_user_role_endpoint(
    user_id: int,
    payload: UserRoleAssign,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """给用户分配角色（当前仅全局角色，team_id 必须为 NULL）。"""
    _require_perm(current_user, db, PERM_ADMIN_USERS_MANAGE)
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在。")
    role = db.get(Role, payload.role_id)
    if not role:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "角色不存在。")
    if payload.team_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "当前角色为全局角色，team_id 必须为 NULL。")
    existing = db.query(UserRole).filter_by(user_id=user_id, role_id=payload.role_id, team_id=None).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户已拥有该角色。")
    db.add(UserRole(
        user_id=user_id, role_id=payload.role_id, team_id=None,
        granted_by_user_id=current_user.id,
    ))
    db.commit()
    return {"ok": True}


@router.delete("/users/{user_id}/roles/{role_id}")
def unassign_user_role_endpoint(
    user_id: int,
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """撤销用户角色。base 角色可被撤销（但不影响该用户既有 user_permissions override）。"""
    _require_perm(current_user, db, PERM_ADMIN_USERS_MANAGE)
    ur = db.query(UserRole).filter_by(user_id=user_id, role_id=role_id, team_id=None).first()
    if not ur:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户未持有该角色。")
    db.delete(ur)
    db.commit()
    return {"ok": True}


@router.get("/admin/team-admins")
def list_team_admins(current_user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    """列出所有团队管理员及其可授予范围(scope)。"""
    admins = db.scalars(select(User).where(User.is_team_admin.is_(True))).all()
    result = []
    for u in admins:
        result.append({
            "user_id": u.id,
            "email": u.email,
            "username": u.username,
            "is_team_admin": u.is_team_admin,
            "scope": sorted(get_team_admin_scope(u.id, db)),
        })
    return {"team_admins": result}


@router.get("/admin/team-admins/{uid}/scope")
def get_team_admin_scope_endpoint(uid: int, current_user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    target = db.get(User, uid)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    return {"user_id": uid, "is_team_admin": target.is_team_admin, "scope": sorted(get_team_admin_scope(uid, db))}


@router.post("/admin/team-admins")
def set_team_admin(req: TeamAdminSetRequest, current_user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    """将某用户设为团队管理员，并分配其可授予范围(scope)。

    - scope 中权限码必须合法且非系统级（团队管理员不可授予 admin.*）。
    - 同步将其个人空间权限对齐为 PERSONAL_DEFAULT ∪ scope（能管即能用）。
    """
    target = db.get(User, req.user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    if target.id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "不能对自己执行该操作")
    valid = _perm_resource_codes(db)
    invalid = [c for c in req.permission_codes if c not in valid]
    if invalid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"无效权限码: {invalid}")
    system_codes = _system_perm_codes(db)
    forbidden = [c for c in req.permission_codes if c in system_codes]
    if forbidden:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"团队管理员不可授予系统级权限: {forbidden}")

    # 替换 scope
    for s in db.scalars(select(TeamAdminScope).where(TeamAdminScope.team_admin_user_id == target.id)).all():
        db.delete(s)
    for code in req.permission_codes:
        db.add(TeamAdminScope(team_admin_user_id=target.id, team_id=None, permission_code=code, granted_by_user_id=current_user.id))

    # 对齐个人空间权限 = PERSONAL_DEFAULT ∪ scope
    ensure_personal_defaults(target.id, db)
    desired = set(PERSONAL_DEFAULT) | set(req.permission_codes)
    current_personal = get_user_permissions(target.id, None, db)
    for code in desired:
        if code not in current_personal:
            db.add(UserPermission(user_id=target.id, team_id=None, permission_code=code, granted_by_user_id=current_user.id))
    for up in db.scalars(select(UserPermission).where(UserPermission.user_id == target.id, UserPermission.team_id.is_(None))).all():
        if up.permission_code not in desired and up.permission_code not in system_codes:
            db.delete(up)

    target.is_team_admin = True
    db.commit()
    return {"ok": True, "user_id": target.id, "scope": sorted(req.permission_codes), "is_team_admin": True}


@router.delete("/admin/team-admins/{uid}")
def remove_team_admin(uid: int, current_user: User = Depends(require_superuser), db: Session = Depends(get_db)):
    """撤销某用户的团队管理员身份（仅移除 scope 与标志，保留其已有 user_permissions）。"""
    target = db.get(User, uid)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    for s in db.scalars(select(TeamAdminScope).where(TeamAdminScope.team_admin_user_id == uid)).all():
        db.delete(s)
    target.is_team_admin = False
    db.commit()
    return {"ok": True, "user_id": uid}


@router.get("/teams/{tid}/members/{uid}/permissions")
def get_member_permissions(tid: int, uid: int, current_user: User = Depends(require_team_admin), db: Session = Depends(get_db)):
    """查看团队成员在某团队内的权限。"""
    team = db.get(Team, tid)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    member = db.scalar(select(TeamMember).where(TeamMember.team_id == tid, TeamMember.user_id == uid, TeamMember.status == "active"))
    if not member:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该用户不是团队活跃成员")
    return {"user_id": uid, "team_id": tid, "permissions": sorted(get_user_permissions(uid, tid, db))}


@router.post("/teams/{tid}/members/{uid}/permissions")
def set_member_permissions(tid: int, uid: int, req: PermissionAssignRequest, current_user: User = Depends(require_team_admin), db: Session = Depends(get_db)):
    """团队管理员在自身 scope 内为成员分配团队权限（超管无限制）。"""
    team = db.get(Team, tid)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    member = db.scalar(select(TeamMember).where(TeamMember.team_id == tid, TeamMember.user_id == uid, TeamMember.status == "active"))
    if not member:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "该用户不是团队活跃成员，无法分配权限（请先将其加入团队）")
    valid = _perm_resource_codes(db)
    bad = [c for c in req.permission_codes if c not in valid]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"无效权限码: {bad}")
    if not current_user.is_superuser:
        scope = get_team_admin_scope(current_user.id, db)
        over = [c for c in req.permission_codes if c not in scope]
        if over:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"超出你的可授予范围: {over}")

    for up in db.scalars(select(UserPermission).where(UserPermission.user_id == uid, UserPermission.team_id == tid)).all():
        db.delete(up)
    for code in req.permission_codes:
        db.add(UserPermission(user_id=uid, team_id=tid, permission_code=code, granted_by_user_id=current_user.id))
    db.commit()
    return {"ok": True, "user_id": uid, "team_id": tid, "permissions": sorted(req.permission_codes)}


@router.delete("/teams/{tid}/members/{uid}/permissions")
def clear_member_permissions(tid: int, uid: int, current_user: User = Depends(require_team_admin), db: Session = Depends(get_db)):
    """清空成员在该团队的权限。"""
    for up in db.scalars(select(UserPermission).where(UserPermission.user_id == uid, UserPermission.team_id == tid)).all():
        db.delete(up)
    db.commit()
    return {"ok": True, "user_id": uid, "team_id": tid}


@router.get("/teams")
def list_teams(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """列出当前用户可见的团队。

    - 超管：全部团队。
    - 团队管理员：全部团队（可管理任意团队成员权限）。
    - 普通成员：仅自己所在的团队。
    """
    if current_user.is_superuser or is_team_admin(current_user, db):
        teams = db.scalars(select(Team)).all()
    else:
        ids = db.scalars(select(TeamMember.team_id).where(TeamMember.user_id == current_user.id, TeamMember.status == "active")).all()
        teams = db.scalars(select(Team).where(Team.id.in_(ids))).all() if ids else []
    return {"teams": [
        {"id": t.id, "name": t.name, "slug": t.slug, "description": t.description, "owner_id": t.owner_id, "enabled": t.enabled}
        for t in teams
    ]}


@router.get("/teams/{tid}/members")
def list_team_members(tid: int, current_user: User = Depends(require_team_admin), db: Session = Depends(get_db)):
    """列出团队成员及其在该团队内的权限。"""
    team = db.get(Team, tid)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    members = db.scalars(select(TeamMember).where(TeamMember.team_id == tid, TeamMember.status == "active")).all()
    out = []
    for m in members:
        u = db.get(User, m.user_id)
        out.append({
            "user_id": m.user_id,
            "username": u.username if u else "?",
            "email": u.email if u else "?",
            "role": m.role,
            "permissions": sorted(get_user_permissions(m.user_id, tid, db)),
        })
    return {"team_id": tid, "members": out}


# ============================================================
# Phase B — 入团审批流（用户自申请需管理员审批 / 管理员拉人需用户本人同意）
# 设计见 designs/plan-permission-rbac.md §5。审批全程写入 approval_logs 留痕。
# ============================================================

def _ensure_team_member(db: Session, team_id: int, user_id: int, role: str = "member") -> TeamMember:
    """幂等建立/恢复活跃团队成员。已存在则恢复 active。"""
    existing = db.scalar(select(TeamMember).where(
        TeamMember.team_id == team_id, TeamMember.user_id == user_id))
    if existing:
        if existing.status != "active":
            existing.status = "active"
            existing.role = role
            db.flush()
        return existing
    m = TeamMember(team_id=team_id, user_id=user_id, role=role, status="active")
    db.add(m)
    db.flush()
    return m


def _grant_base_team_perms(db: Session, team_id: int, user_id: int, actor_id: int) -> None:
    """给新成员授基础团队权限（PERSONAL_DEFAULT），团队管理员后续可在控制台调整。幂等。"""
    existing = set(db.scalars(select(UserPermission.permission_code).where(
        UserPermission.user_id == user_id, UserPermission.team_id == team_id)).all())
    for code in PERSONAL_DEFAULT:
        if code not in existing:
            db.add(UserPermission(user_id=user_id, team_id=team_id, permission_code=code, granted_by_user_id=actor_id))
    db.flush()


class JoinRequestCreate(BaseModel):
    message: str = ""


class JoinRequestReview(BaseModel):
    action: str  # approve | reject
    comment: str = ""


class InviteCreate(BaseModel):
    email: str
    role: str = "member"
    message: str = ""


class InviteRespond(BaseModel):
    action: str  # accept | decline
    comment: str = ""


@router.post("/teams/{tid}/join-requests")
def create_join_request(tid: int, req: JoinRequestCreate,
                        current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """用户自申请加入团队。已是活跃成员 / 已有 pending 申请则拒绝（幂等）。"""
    team = db.get(Team, tid)
    if not team or not team.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "团队不存在或已禁用")
    if db.scalar(select(TeamMember).where(TeamMember.team_id == tid, TeamMember.user_id == current_user.id, TeamMember.status == "active")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你已是该团队活跃成员")
    if db.scalar(select(TeamJoinRequest).where(TeamJoinRequest.team_id == tid, TeamJoinRequest.user_id == current_user.id, TeamJoinRequest.status == "pending")):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "你已提交过加入申请，请等待审批")
    jr = TeamJoinRequest(team_id=tid, user_id=current_user.id, message=req.message, status="pending")
    db.add(jr)
    db.commit()
    return {"ok": True, "id": jr.id, "status": "pending"}


@router.get("/teams/discover")
def discover_teams(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """列出当前用户可申请的团队（启用且非其活跃成员）。"""
    member_ids = db.scalars(select(TeamMember.team_id).where(
        TeamMember.user_id == current_user.id, TeamMember.status == "active")).all()
    conds = [Team.enabled.is_(True)]
    if member_ids:
        conds.append(Team.id.notin_(member_ids))
    teams = db.scalars(select(Team).where(*conds)).all()
    return {"teams": [{"id": t.id, "name": t.name, "slug": t.slug, "description": t.description} for t in teams]}


@router.get("/me/join-requests")
def my_join_requests(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """我的加入申请列表（含团队名与状态）。"""
    rows = db.scalars(select(TeamJoinRequest).where(TeamJoinRequest.user_id == current_user.id)).all()
    out = []
    for r in rows:
        t = db.get(Team, r.team_id)
        out.append({"id": r.id, "team_id": r.team_id, "team_name": t.name if t else "?",
                    "status": r.status, "message": r.message, "review_comment": r.review_comment,
                    "created_at": r.created_at.isoformat() if r.created_at else None})
    return {"join_requests": out}


@router.get("/teams/{tid}/join-requests")
def list_join_requests(tid: int, current_user: User = Depends(require_team_admin), db: Session = Depends(get_db)):
    """团队管理员查看该团队的待审加入申请（含申请人信息）。"""
    team = db.get(Team, tid)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    rows = db.scalars(select(TeamJoinRequest).where(TeamJoinRequest.team_id == tid, TeamJoinRequest.status == "pending")).all()
    out = []
    for r in rows:
        u = db.get(User, r.user_id)
        out.append({"id": r.id, "user_id": r.user_id, "username": u.username if u else "?",
                    "email": u.email if u else "?", "message": r.message,
                    "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None})
    return {"join_requests": out}


@router.post("/teams/{tid}/join-requests/{rid}/review")
def review_join_request(tid: int, rid: int, req: JoinRequestReview,
                        current_user: User = Depends(require_team_admin), db: Session = Depends(get_db)):
    """团队管理员审批加入申请。approve → 建成员 + 授基础团队权限；写审批审计。"""
    team = db.get(Team, tid)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    jr = db.get(TeamJoinRequest, rid)
    if not jr or jr.team_id != tid:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "申请不存在")
    if jr.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"该申请已处理（{jr.status}）")
    if req.action not in ("approve", "reject"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action 必须为 approve 或 reject")
    jr.status = "approved" if req.action == "approve" else "rejected"
    jr.reviewed_by = current_user.id
    jr.reviewed_at = datetime.utcnow()
    jr.review_comment = req.comment
    db.add(ApprovalLog(team_id=tid, target_type="join_request", target_id=jr.id,
                       action=req.action, actor_id=current_user.id, comment=req.comment))
    if req.action == "approve":
        _ensure_team_member(db, tid, jr.user_id, "member")
        _grant_base_team_perms(db, tid, jr.user_id, current_user.id)
    db.commit()
    return {"ok": True, "status": jr.status}


@router.post("/teams/{tid}/invites")
def create_invite(tid: int, req: InviteCreate,
                  current_user: User = Depends(require_team_admin), db: Session = Depends(get_db)):
    """团队管理员拉人（按邮箱）。邀请 pending，需被邀请用户本人同意。"""
    team = db.get(Team, tid)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    email = (req.email or "").strip().lower()
    if not email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邮箱不能为空")
    dup = db.scalar(select(TeamInvite).where(TeamInvite.team_id == tid, TeamInvite.email == email, TeamInvite.status == "pending"))
    if dup:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "已向该邮箱发送过待接受邀请")
    inv = TeamInvite(team_id=tid, email=email, token=uuid.uuid4().hex, role=req.role,
                     invited_by=current_user.id, status="pending", message=req.message or None)
    db.add(inv)
    db.commit()
    return {"ok": True, "id": inv.id, "status": "pending", "email": email}


@router.get("/teams/{tid}/invites")
def list_invites(tid: int, current_user: User = Depends(require_team_admin), db: Session = Depends(get_db)):
    team = db.get(Team, tid)
    if not team:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Team not found.")
    rows = db.scalars(select(TeamInvite).where(TeamInvite.team_id == tid)).all()
    return {"invites": [{"id": r.id, "email": r.email, "role": r.role, "status": r.status,
                         "message": r.message, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}


@router.get("/me/invites")
def my_invites(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """我收到的待接受邀请（按当前用户邮箱匹配）。"""
    rows = db.scalars(select(TeamInvite).where(TeamInvite.email == current_user.email.lower(), TeamInvite.status == "pending")).all()
    out = []
    for r in rows:
        t = db.get(Team, r.team_id)
        out.append({"id": r.id, "team_id": r.team_id, "team_name": t.name if t else "?",
                    "role": r.role, "message": r.message, "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None})
    return {"invites": out}


@router.post("/invites/{iid}/respond")
def respond_invite(iid: int, req: InviteRespond,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """被邀请用户本人响应（同意/拒绝）。accept → 建成员 + 授基础团队权限；写审计。"""
    inv = db.get(TeamInvite, iid)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "邀请不存在")
    if inv.email != current_user.email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "只能响应发给本人的邀请")
    if inv.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"该邀请已处理（{inv.status}）")
    if req.action not in ("accept", "decline"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "action 必须为 accept 或 decline")
    inv.status = "accepted" if req.action == "accept" else "declined"
    inv.responded_at = datetime.utcnow()
    inv.comment = req.comment
    db.add(ApprovalLog(team_id=inv.team_id, target_type="invite", target_id=inv.id,
                       action=req.action, actor_id=current_user.id, comment=req.comment))
    if req.action == "accept":
        _ensure_team_member(db, inv.team_id, current_user.id, inv.role or "member")
        _grant_base_team_perms(db, inv.team_id, current_user.id, current_user.id)
    db.commit()
    return {"ok": True, "status": inv.status}