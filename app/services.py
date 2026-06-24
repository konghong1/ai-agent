from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    KBChunk, KBDocument, KBFolder, KnowledgeBase,
    User, SystemSetting,
)
from app.schemas import KBFolderTreeNode
from app.core.security import hash_password, verify_password

logger = logging.getLogger(__name__)

# Where uploaded files live on disk
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ChromaDB persistent directory
CHROMA_DIR = Path(__file__).resolve().parents[1] / "chroma_db"
CHROMA_DIR.mkdir(exist_ok=True)


# ============================================================
# File-type detection
# ============================================================

def detect_file_type(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    mapping = {
        ".pdf": "pdf", ".docx": "docx", ".txt": "txt", ".md": "markdown",
        ".csv": "csv", ".json": "json", ".py": "code", ".js": "code",
        ".ts": "code", ".jsx": "code", ".tsx": "code", ".html": "code",
        ".css": "code", ".java": "code", ".go": "code", ".rs": "code",
        ".yaml": "code", ".yml": "code", ".toml": "code", ".xml": "code",
        ".sh": "code", ".bash": "code",
    }
    return mapping.get(ext, "unknown")


# ============================================================
# Text extraction helpers
# ============================================================

def extract_text_from_file(filepath: str, file_type: str) -> tuple[str, int]:
    if file_type == "pdf":
        return _extract_pdf(filepath)
    if file_type == "docx":
        return _extract_docx(filepath)
    if file_type in ("markdown", "txt", "csv", "json", "code"):
        return _extract_text(filepath)
    return ("", 0)


def _extract_pdf(filepath: str) -> tuple[str, int]:
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(filepath)
        return (text or "", 1)
    except Exception as exc:
        logger.warning("pdfminer failed: %s", exc)
        try:
            import pypdf
            reader = pypdf.PdfReader(filepath)
            pages = [page.extract_text() or "" for page in reader.pages]
            return ("\n\n".join(pages), len(reader.pages))
        except Exception as exc2:
            logger.warning("pypdf also failed: %s", exc2)
            return ("", 0)


def _extract_docx(filepath: str) -> tuple[str, int]:
    try:
        from docx import Document
        doc = Document(filepath)
        text = "\n".join(p.text for p in doc.paragraphs if p.text)
        return (text, 1)
    except Exception as exc:
        logger.warning("python-docx failed: %s", exc)
        return ("", 0)


def _extract_text(filepath: str) -> tuple[str, int]:
    try:
        text = Path(filepath).read_text(encoding="utf-8", errors="replace")
        return (text, 1)
    except Exception as exc:
        logger.warning("text read failed: %s", exc)
        return ("", 0)


# ============================================================
# Chunking
# ============================================================

def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", "。", " ", ""],
        length_function=len,
    )
    docs = splitter.create_documents([text], metadatas=[{}])
    return [{"content": d.page_content, "metadata": d.metadata} for d in docs]


# ============================================================
# Embeddings
# ============================================================

def get_embeddings(model_name: str = "text-embedding-3-small"):
    from app.settings import get_settings
    settings = get_settings()
    return OpenAIEmbeddings(
        model=model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


# ============================================================
# Knowledge Base Service
# ============================================================

class KnowledgeBaseService:
    """All knowledge-base business logic."""

    @staticmethod
    def create_kb(db: Session, user_id: int, name: str, description: str = "",
                  embedding_model: str = "text-embedding-3-small",
                  chunk_size: int = 500, chunk_overlap: int = 50,
                  enabled: bool = True) -> KnowledgeBase:
        kb = KnowledgeBase(
            user_id=user_id, name=name, description=description,
            embedding_model=embedding_model, chunk_size=chunk_size,
            chunk_overlap=chunk_overlap, enabled=enabled,
        )
        db.add(kb)
        db.commit()
        db.refresh(kb)
        return kb

    @staticmethod
    def get_kb(db: Session, kb_id: int, user_id: int) -> KnowledgeBase | None:
        return db.scalar(
            select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id)
        )

    @staticmethod
    def list_kbs(db: Session, user_id: int) -> list[KnowledgeBase]:
        return list(db.scalars(
            select(KnowledgeBase).where(KnowledgeBase.user_id == user_id).order_by(KnowledgeBase.created_at)
        ))

    @staticmethod
    def update_kb(db: Session, kb: KnowledgeBase, **kwargs) -> KnowledgeBase:
        for k, v in kwargs.items():
            if v is not None and hasattr(kb, k):
                setattr(kb, k, v)
        db.commit()
        db.refresh(kb)
        return kb

    @staticmethod
    def delete_kb(db: Session, kb: KnowledgeBase) -> None:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            client.delete_collection(f"kb_{kb.id}")
        except Exception:
            pass
        db.delete(kb)
        db.commit()

    @staticmethod
    def create_folder(db: Session, kb_id: int, name: str, description: str = "",
                      parent_id: int | None = None) -> KBFolder:
        folder = KBFolder(kb_id=kb_id, name=name, description=description, parent_id=parent_id)
        db.add(folder)
        db.commit()
        db.refresh(folder)
        return folder

    @staticmethod
    def delete_folder(db: Session, folder: KBFolder) -> None:
        db.delete(folder)
        db.commit()

    @staticmethod
    def get_folder_tree(db: Session, kb_id: int) -> list[KBFolderTreeNode]:
        folders = db.scalars(
            select(KBFolder).where(KBFolder.kb_id == kb_id).options(joinedload(KBFolder.children))
        ).unique().all()

        def build_node(folder: KBFolder) -> KBFolderTreeNode:
            doc_count = len(folder.documents)
            return KBFolderTreeNode(
                id=folder.id, name=folder.name, description=folder.description,
                children=[build_node(child) for child in folder.children],
                document_count=doc_count,
            )

        return [build_node(f) for f in folders]

    @staticmethod
    def get_folder_path(db: Session, folder: KBFolder) -> str:
        parts: list[str] = []
        current = folder
        while current:
            parts.append(current.name)
            parent = db.get(KBFolder, current.parent_id) if current.parent_id else None
            current = parent
        parts.reverse()
        return " / ".join(parts)

    @staticmethod
    def upload_document(db: Session, kb_id: int, user_id: int, folder_id: int | None,
                        file_bytes: bytes, original_filename: str) -> KBDocument:
        file_type = detect_file_type(original_filename)
        if file_type == "unknown":
            raise ValueError(f"Unsupported file type: {original_filename}")
        safe_name = uuid.uuid4().hex[:12] + "_" + original_filename
        dest = UPLOAD_DIR / safe_name
        dest.write_bytes(file_bytes)
        doc = KBDocument(
            kb_id=kb_id, folder_id=folder_id, user_id=user_id,
            original_filename=original_filename, storage_path=str(dest),
            file_type=file_type, file_size=len(file_bytes), status="pending",
        )
        db.add(doc)
        db.flush()
        return doc

    @staticmethod
    def list_documents(db: Session, kb_id: int, folder_id: int | None = None) -> list[KBDocument]:
        q = select(KBDocument).where(KBDocument.kb_id == kb_id)
        if folder_id is not None:
            q = q.where(KBDocument.folder_id == folder_id)
        return list(db.scalars(q.order_by(KBDocument.created_at.desc())))

    @staticmethod
    def delete_document(db: Session, doc: KBDocument) -> None:
        try:
            Path(doc.storage_path).unlink(missing_ok=True)
        except Exception:
            pass
        chunks = db.scalars(select(KBChunk).where(KBChunk.document_id == doc.id)).all()
        if chunks:
            kb = doc.kb
            try:
                import chromadb
                client = chromadb.PersistentClient(path=str(CHROMA_DIR))
                coll = client.get_collection(f"kb_{kb.id}")
                coll.delete(ids=[c.vector_id for c in chunks])
            except Exception:
                pass
            for c in chunks:
                db.delete(c)
        db.delete(doc)
        db.commit()

    @staticmethod
    def process_document(db: Session, doc_id: int) -> dict:
        doc = db.get(KBDocument, doc_id)
        if not doc:
            raise ValueError(f"Document {doc_id} not found")
        doc.status = "processing"
        db.commit()
        try:
            text, _ = extract_text_from_file(doc.storage_path, doc.file_type)
            if not text.strip():
                doc.status = "failed"
                doc.error_message = "文件内容为空或无法提取文本"
                db.commit()
                return {"status": "failed", "message": "Empty or unreadable file"}

            kb = doc.kb
            chunks_data = chunk_text(text, kb.chunk_size, kb.chunk_overlap)
            if not chunks_data:
                doc.status = "failed"
                doc.error_message = "分块失败"
                db.commit()
                return {"status": "failed", "message": "No chunks produced"}

            embeddings = get_embeddings(kb.embedding_model)
            texts = [c["content"] for c in chunks_data]
            emb_list = embeddings.embed_documents(texts)

            folder = db.get(KBFolder, doc.folder_id) if doc.folder_id else None
            folder_path = KnowledgeBaseService.get_folder_path(db, folder) if folder else ""

            import chromadb
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            coll = client.get_collection(f"kb_{kb.id}")

            chunk_records = []
            for idx, (chunk_data, embedding) in enumerate(zip(chunks_data, emb_list)):
                vector_id = f"{doc.id}_chunk_{idx}_{uuid.uuid4().hex[:8]}"
                coll.upsert(
                    ids=[vector_id],
                    embeddings=[embedding],
                    documents=[chunk_data["content"]],
                    metadatas={
                        "document_id": doc.id, "document_name": doc.original_filename,
                        "folder_path": folder_path, "kb_id": kb.id,
                        "chunk_index": idx, "page_number": None,
                        **(chunk_data.get("metadata") or {}),
                    },
                )
                chunk_records.append(KBChunk(
                    kb_id=kb.id, document_id=doc.id, folder_id=doc.folder_id,
                    vector_id=vector_id, chunk_index=idx,
                    content=chunk_data["content"],
                    metadata_=chunk_data.get("metadata") or {},
                ))

            db.add_all(chunk_records)
            doc.status = "ready"
            doc.error_message = None
            db.commit()
            return {"status": "ready", "message": f"成功处理 {len(chunks_data)} 个分块", "chunks": len(chunks_data)}

        except Exception as exc:
            logger.exception("Failed to process document %d", doc_id)
            doc.status = "failed"
            doc.error_message = str(exc)
            db.commit()
            return {"status": "failed", "message": str(exc)}

    @staticmethod
    def search_knowledge_base(db: Session, kb_id: int, query: str,
                              top_k: int = 5, folder_id: int | None = None) -> list[dict]:
        kb = db.get(KnowledgeBase, kb_id)
        if not kb:
            raise ValueError(f"Knowledge base {kb_id} not found")

        embeddings = get_embeddings(kb.embedding_model)
        query_embedding = embeddings.embed_query(query)

        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        coll = client.get_collection(f"kb_{kb.id}")

        where = {"kb_id": str(kb_id)}
        if folder_id is not None:
            folder = db.get(KBFolder, folder_id)
            if folder:
                folder_path = KnowledgeBaseService.get_folder_path(db, folder)
                where["folder_path"] = folder_path

        results = coll.query(
            query_embeddings=[query_embedding], n_results=top_k,
            where=where, include=["metadatas", "distances"],
        )

        hits = []
        for i in range(len(results["ids"][0])):
            vid = results["ids"][0][i]
            distance = results["distances"][0][i]
            metadata = results["metadatas"][0][i]
            document_id = int(metadata.get("document_id", 0))
            doc = db.scalar(select(KBDocument).where(KBDocument.id == document_id))
            chunk = db.scalar(
                select(KBChunk).where(KBChunk.vector_id == vid, KBChunk.kb_id == kb_id)
            )
            hits.append({
                "vector_id": vid,
                "document_id": document_id,
                "document_name": doc.original_filename if doc else metadata.get("document_name", ""),
                "folder_path": metadata.get("folder_path", ""),
                "page_number": metadata.get("page_number"),
                "chunk_index": metadata.get("chunk_index", 0),
                "content": chunk.content if chunk else "",
                "score": round(1.0 - distance, 4) if distance is not None else 0.0,
            })
        return hits


# ============================================================
# User Management Service (Task 10)
# ============================================================

class UserService:
    @staticmethod
    def list_users(db: Session, user_id: int) -> list[User]:
        """Admin can list all users. Regular users can only see themselves."""
        admin_user = db.get(User, user_id)
        if admin_user and admin_user.role == "admin":
            return list(db.scalars(select(User).order_by(User.created_at)).all())
        return [db.get(User, user_id)]

    @staticmethod
    def update_user(db: Session, target_user: User, current_user_id: int, **kwargs) -> User:
        """Only admins can modify other users."""
        current = db.get(User, current_user_id)
        if current.role != "admin" and current.id != target_user.id:
            raise PermissionError("Only admins can modify other users.")
        for k, v in kwargs.items():
            if v is not None and hasattr(target_user, k):
                setattr(target_user, k, v)
        db.commit()
        db.refresh(target_user)
        return target_user

    @staticmethod
    def delete_user(db: Session, target_user: User, current_user_id: int) -> None:
        current = db.get(User, current_user_id)
        if current.role != "admin":
            raise PermissionError("Only admins can delete users.")
        db.delete(target_user)
        db.commit()


# ============================================================
# System Settings Service (Task 11)
# ============================================================

class SystemSettingService:
    @staticmethod
    def get_setting(db: Session, key: str) -> SystemSetting | None:
        return db.scalar(select(SystemSetting).where(SystemSetting.key == key))

    @staticmethod
    def set_setting(db: Session, key: str, value: str, description: str = "") -> SystemSetting:
        setting = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if setting:
            setting.value = value
            if description:
                setting.description = description
        else:
            setting = SystemSetting(key=key, value=value, description=description)
            db.add(setting)
        db.commit()
        db.refresh(setting)
        return setting

    @staticmethod
    def list_settings(db: Session) -> list[SystemSetting]:
        return list(db.scalars(select(SystemSetting).order_by(SystemSetting.key)).all())

    @staticmethod
    def delete_setting(db: Session, key: str) -> None:
        setting = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
        if setting:
            db.delete(setting)
            db.commit()


# ============================================================
# Original utility functions (kept for backward compatibility)
# ============================================================

DEFAULT_SYSTEM_PROMPT = """You are a practical AI agent.
You can answer normally and call tools when they help.

AVAILABLE TOOLS:
1. calculator - Calculate numeric expressions
2. current_time - Get the current date/time for a timezone
3. list_workspace_files - List files in the project workspace
4. read_workspace_text_file - Read a text file from the workspace
5. search_knowledge_base - Search knowledge bases for relevant information

KNOWLEDGE BASE USAGE:
- When the user asks about company documents, policies, technical specs, or any stored knowledge, use search_knowledge_base.
- You can search all knowledge bases (omit kb_id) or a specific one (provide kb_id).
- Summarize the most relevant findings from the search results in your answer.
- If no knowledge base is available or the search returns nothing, let the user know.

CHOICE INTERACTION:
When you want the user to make a selection, output your response text followed by a <blocks> tag containing a JSON object with a choices array:
<blocks>{"choices": [{"label": "A. ???", "value": "A"}, {"label": "B. ???", "value": "B"}, {"label": "C. ???", "value": "C"}]}</blocks>

The text before <blocks> will be shown as regular message content. The choices will render as clickable buttons. When the user clicks a button, their selection (the value) will be sent as their message. Use labels that are clear and descriptive.
"""


def create_default_agent(db: Session, user_id: int) -> None:
    from app.models import AgentConfig
    from app.settings import get_settings
    settings = get_settings()
    agent = AgentConfig(
        user_id=user_id,
        name="Default Agent",
        description="Default local agent with time, calculator, workspace tools, and knowledge base search.",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        model_name=settings.openai_model,
        temperature=0,
        enabled=True,
    )
    db.add(agent)


def create_user(db: Session, email: str, username: str, password: str) -> User:
    user = User(email=email.lower(), username=username, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    create_default_agent(db, user.id)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


def new_thread_id() -> str:
    return f"thread-{uuid.uuid4().hex[:12]}"
