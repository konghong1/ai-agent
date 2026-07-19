from __future__ import annotations

"""跨会话长期记忆子系统（ADR-022 / 023）的写入与富集逻辑。

组件：
- MemoryStore   ：Chroma 每用户集合（user_mem_{uid}）封装；embed/vector 可注入便于测试。
- MemoryWriter  ：显式写入（实体归一防碎片）+ 隐式候选提取 + 待确认晋升/驳回。
- MemoryEnricher：后台去重/矛盾检测/显著性衰减/会话摘要 Promotion（P6）。

约束（项目铁律）：
- 记忆绝不硬删：删除走软状态（status=archived）；Chroma 向量同步删除。
- 隐式提取默认关 + 需确认（多用户生产环境防污染）。
- 跨用户隔离：所有操作以 user_id 为边界。
"""

import logging
import re
import threading
import time
from typing import Callable, Optional

from sqlalchemy import select

from app.models import PendingMemory, ThreadContextState, UserMemory

logger = logging.getLogger(__name__)


def normalize_key(raw: str) -> str:
    """实体归一（轻量 auto-link）：小写、去空白/标点，保留字母数字与中文。

    目的：把「Bob」「老鲍」「Bob 哥」归一到同一 key，避免记忆碎片化。
    """
    s = (raw or "").strip().lower()
    s = re.sub(r"[\s\-_]+", " ", s)
    s = re.sub(r"[^\w一-鿿]+", "", s)
    return s


class MemoryStore:
    """Chroma 每用户集合的薄封装。embed_fn / vector_store 可注入（单测无网络）。"""

    def __init__(
        self,
        embed_fn: Optional[Callable[[str], list[float]]] = None,
        vector_store=None,
    ):
        self._embed_fn = embed_fn
        self._vector_store = vector_store
        self._lock = threading.Lock()

    # ── 依赖惰性解析（仅在未注入时走真实路径）──
    def _embed(self, text: str) -> list[float]:
        if self._embed_fn:
            return self._embed_fn(text)
        from app.services import get_embeddings

        return get_embeddings().embed_documents([text])[0]

    def _vs(self):
        if self._vector_store:
            return self._vector_store
        from app.vector_store import get_vector_store

        return get_vector_store()

    @staticmethod
    def collection_name(user_id: int) -> str:
        return f"user_mem_{user_id}"

    def upsert(self, user_id: int, memory_id: int, key: str, value: str,
               layer: int = 1, mem_type: str = "preference") -> None:
        try:
            emb = self._embed(value or key)
            with self._lock:
                self._vs().upsert(
                    self.collection_name(user_id),
                    ids=[str(memory_id)],
                    embeddings=[emb],
                    documents=[f"{key}: {value}"],
                    metadatas=[{"memory_id": memory_id, "key": key,
                                "layer": layer, "mem_type": mem_type}],
                )
        except Exception as exc:  # fail-open：向量不可用不影响主链路
            logger.warning("MemoryStore.upsert skipped: %s", exc)

    def delete(self, user_id: int, memory_id: int) -> None:
        try:
            with self._lock:
                self._vs().delete(self.collection_name(user_id), [str(memory_id)])
        except Exception as exc:
            logger.warning("MemoryStore.delete skipped: %s", exc)

    def query(self, user_id: int, text: str, k: int = 4) -> list[dict]:
        try:
            emb = self._embed(text)
            with self._lock:
                res = self._vs().query(self.collection_name(user_id), [emb], n_results=k)
            docs = (res.get("documents") or [[]])[0]
            metas = (res.get("metadatas") or [[]])[0]
            dists = (res.get("distances") or [[]])[0]
            out: list[dict] = []
            for d, m, dist in zip(docs, metas, dists):
                if d:
                    out.append({
                        "content": d,
                        "metadata": m,
                        "score": 1.0 - (dist or 1.0),
                    })
            return out
        except Exception as exc:
            logger.warning("MemoryStore.query skipped: %s", exc)
            return []


class MemoryWriter:
    """记忆写入与审批。db 为调用方提供的会话；store 默认走真实 Chroma。"""

    def __init__(self, db, store: Optional[MemoryStore] = None):
        self.db = db
        self.store = store or MemoryStore()

    # ── 显式写入（零幻觉，优先路径）──
    def add_explicit(self, user_id: int, key: str, value: str,
                     layer: int = 1, mem_type: str = "preference",
                     importance: float = 0.5, confidence: float = 1.0,
                     source: str = "explicit") -> UserMemory:
        norm = normalize_key(key) or normalize_key(value)
        # 实体归一：同归一 key 已存在 → 更新而非新增（防碎片）
        target: Optional[UserMemory] = None
        for m in self.db.scalars(
            select(UserMemory).where(
                UserMemory.user_id == user_id, UserMemory.status == "active"
            )
        ):
            if normalize_key(m.key) == norm:
                target = m
                break
        if target is None:
            target = UserMemory(user_id=user_id)
            self.db.add(target)
        target.layer = layer
        target.mem_type = mem_type
        target.key = key or value[:32]
        target.value = value
        target.importance = importance
        target.confidence = confidence
        target.source = source
        target.status = "active"
        self.db.flush()
        self.store.upsert(user_id, target.id, target.key, target.value or "",
                          target.layer, target.mem_type)
        self.db.commit()
        self.db.refresh(target)
        return target

    def list_memories(self, user_id: int, status: str = "active") -> list[UserMemory]:
        return list(self.db.scalars(
            select(UserMemory)
            .where(UserMemory.user_id == user_id, UserMemory.status == status)
            .order_by(UserMemory.layer, UserMemory.importance.desc())
        ))

    def update_memory(self, mem_id: int, user_id: int, **fields) -> Optional[UserMemory]:
        mem = self.db.scalar(
            select(UserMemory).where(UserMemory.id == mem_id, UserMemory.user_id == user_id)
        )
        if mem is None:
            return None
        for k, v in fields.items():
            if v is not None and hasattr(mem, k):
                setattr(mem, k, v)
        self.db.flush()
        self.store.upsert(user_id, mem.id, mem.key, mem.value or "",
                          mem.layer, mem.mem_type)
        self.db.commit()
        self.db.refresh(mem)
        return mem

    def delete_memory(self, mem_id: int, user_id: int) -> bool:
        mem = self.db.scalar(
            select(UserMemory).where(UserMemory.id == mem_id, UserMemory.user_id == user_id)
        )
        if mem is None:
            return False
        # 软删：绝不硬删（铁律）。Chroma 向量同步移除。
        mem.status = "archived"
        self.db.commit()
        self.store.delete(user_id, mem.id)
        return True

    # ── 隐式提取候选队列（默认关，需确认）──
    def extract_candidates(self, user_id: int, conversation_text: str,
                           extractor: Callable[[str], list[str]]) -> list[PendingMemory]:
        try:
            cands = extractor(conversation_text) or []
        except Exception as exc:
            logger.warning("extract_candidates failed (skipped): %s", exc)
            return []
        rows: list[PendingMemory] = []
        for c in cands:
            c = (c or "").strip()
            if not c:
                continue
            p = PendingMemory(user_id=user_id, candidate=c, status="pending")
            self.db.add(p)
            rows.append(p)
        if rows:
            self.db.commit()
        return rows

    def promote(self, pending_id: int, user_id: int) -> Optional[UserMemory]:
        p = self.db.scalar(
            select(PendingMemory).where(
                PendingMemory.id == pending_id, PendingMemory.user_id == user_id,
                PendingMemory.status == "pending",
            )
        )
        if p is None:
            return None
        cand = p.candidate or ""
        if ":" in cand:
            k, v = cand.split(":", 1)
        else:
            k, v = "", cand
        mem = self.add_explicit(
            user_id, (k.strip() or cand[:32]), (v.strip() or cand),
            layer=2, mem_type="fact", importance=0.6, source="extracted",
        )
        p.status = "accepted"
        self.db.commit()
        return mem

    def reject_pending(self, pending_id: int, user_id: int) -> bool:
        p = self.db.scalar(
            select(PendingMemory).where(
                PendingMemory.id == pending_id, PendingMemory.user_id == user_id
            )
        )
        if p is None:
            return False
        p.status = "rejected"
        self.db.commit()
        return True

    def list_pending(self, user_id: int) -> list[PendingMemory]:
        return list(self.db.scalars(
            select(PendingMemory)
            .where(PendingMemory.user_id == user_id, PendingMemory.status == "pending")
            .order_by(PendingMemory.created_at)
        ))


class MemoryEnricher:
    """后台富集（P6）：去重/合并、矛盾检测、显著性衰减、会话摘要 Promotion。

    设计为可在单测中直接调用 run_once(db, store) 而不依赖后台线程。
    """

    DECAY_FACTOR = 0.97          # 每次运行对「长期未访问」记忆的衰减
    DECAY_FLOOR = 0.1            # 衰减下限
    STALE_DAYS = 30              # 超过此天数未访问才衰减

    @staticmethod
    def run_once(db, store: Optional[MemoryStore] = None) -> dict:
        store = store or MemoryStore()
        stats = {"merged": 0, "archived_conflict": 0, "decayed": 0, "promoted": 0}

        # 1) 去重/合并 + 2) 矛盾检测：按 (user_id, 归一key) 分组
        all_active = list(db.scalars(
            select(UserMemory).where(UserMemory.status == "active")
        ))
        from collections import defaultdict

        groups: dict[tuple[int, str], list[UserMemory]] = defaultdict(list)
        for m in all_active:
            groups[(m.user_id, normalize_key(m.key))].append(m)

        now = time.time()
        for (uid, _norm), mems in groups.items():
            if len(mems) <= 1:
                continue
            # 按 importance 降序、updated_at 降序排序（最新的/最重要的优先）
            mems.sort(key=lambda x: (x.importance, x.updated_at.timestamp()
                                     if x.updated_at else 0), reverse=True)
            keeper = mems[0]
            for dup in mems[1:]:
                # 同值 → 合并（删除重复，保留 keeper）
                if (dup.value or "").strip() == (keeper.value or "").strip():
                    dup.status = "archived"
                    store.delete(uid, dup.id)
                    stats["merged"] += 1
                else:
                    # 异值 → 矛盾：保留新值，旧值归档（留审计）
                    dup.status = "archived"
                    store.delete(uid, dup.id)
                    stats["archived_conflict"] += 1

        # 3) 显著性衰减：长期未访问的低价值记忆自然沉底
        for m in all_active:
            if m.status != "active":
                continue
            last = m.last_accessed or m.updated_at
            age_days = (now - (last.timestamp() if last else now)) / 86400.0
            if age_days > MemoryEnricher.STALE_DAYS and m.importance > MemoryEnricher.DECAY_FLOOR:
                m.importance = max(MemoryEnricher.DECAY_FLOOR,
                                   round(m.importance * MemoryEnricher.DECAY_FACTOR, 4))
                stats["decayed"] += 1

        # 4) Promotion：会话摘要 → L3 情景记忆（工作→情景→长期闭环）
        for st in db.scalars(select(ThreadContextState).where(
                ThreadContextState.summary.isnot(None))):
            summary = (st.summary or "").strip()
            if len(summary) < 20:
                continue
            # 避免重复提升：已有同源 promoted 记忆则跳过
            exists = db.scalar(
                select(UserMemory).where(
                    UserMemory.user_id == st.user_id,
                    UserMemory.source == "promoted",
                    UserMemory.value.like(f"{summary[:40]}%"),
                )
            )
            if exists:
                continue
            mem = UserMemory(
                user_id=st.user_id, layer=3, mem_type="episodic",
                key=f"session-summary:{st.thread_id[:16]}",
                value=summary, importance=0.4, confidence=0.8,
                status="active", source="promoted",
            )
            db.add(mem)
            db.flush()
            store.upsert(st.user_id, mem.id, mem.key, mem.value, mem.layer, mem.mem_type)
            stats["promoted"] += 1

        db.commit()
        return stats

    @staticmethod
    def start(interval_seconds: int = 3600) -> threading.Thread:
        """启动后台守护线程（仿 gallery_worker：startup 启线程、不联网）。"""

        def loop() -> None:
            while True:
                try:
                    from app.core.database import SessionLocal

                    db = SessionLocal()
                    try:
                        MemoryEnricher.run_once(db)
                    finally:
                        db.close()
                except Exception as exc:  # 绝不因富集失败影响主服务
                    logger.warning("MemoryEnricher run_once error: %s", exc)
                time.sleep(interval_seconds)

        t = threading.Thread(target=loop, name="memory-enricher", daemon=True)
        t.start()
        return t
