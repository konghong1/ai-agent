"""P2–P7 长期记忆子系统单元测试（临时 sqlite，假 embed/vector，无网络）。

不触碰真实 agent.db / ai_agent.db；所有外部依赖（embedding、向量库）均注入假实现。
"""
import math

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Message, PendingMemory, Thread, ThreadContextState, User, UserMemory
from app.memory import MemoryEnricher, MemoryStore, MemoryWriter, normalize_key
from app.context_service import BuildOptions, ContextService


# ────────────────────────────────────────────────────────────
# 假向量库 + 假 embedding（确定性、按字符频率，可算余弦相似度）
# ────────────────────────────────────────────────────────────
class FakeVectorStore:
    def __init__(self):
        self.data: dict = {}

    def _coll(self, name):
        return self.data.setdefault(name, {"ids": [], "embeddings": [], "documents": [], "metadatas": []})

    def upsert(self, collection_name, ids, embeddings, documents, metadatas):
        coll = self._coll(collection_name)
        for i, vid in enumerate(ids):
            if vid in coll["ids"]:
                idx = coll["ids"].index(vid)
                coll["documents"][idx] = documents[i]
                coll["metadatas"][idx] = metadatas[i]
                coll["embeddings"][idx] = embeddings[i]
            else:
                coll["ids"].append(vid)
                coll["documents"].append(documents[i])
                coll["metadatas"].append(metadatas[i])
                coll["embeddings"].append(embeddings[i])

    def query(self, collection_name, query_embeddings, n_results=10, where=None):
        coll = self.data.get(collection_name)
        if not coll or not coll["ids"]:
            return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}
        import numpy as np

        q = np.array(query_embeddings[0], dtype=float)
        qn = np.linalg.norm(q) or 1.0
        scores, ids, docs, metas = [], coll["ids"], coll["documents"], coll["metadatas"]
        for emb in coll["embeddings"]:
            e = np.array(emb, dtype=float)
            en = np.linalg.norm(e) or 1.0
            scores.append(float(np.dot(q, e) / (qn * en)))
        order = sorted(range(len(scores)), key=lambda i: -scores[i])[:n_results]
        return {
            "ids": [[ids[i] for i in order]],
            "distances": [[1.0 - scores[i] for i in order]],
            "documents": [[docs[i] for i in order]],
            "metadatas": [[metas[i] for i in order]],
        }

    def delete(self, collection_name, ids):
        coll = self.data.get(collection_name)
        if not coll:
            return
        kill = set(ids)
        keep = [i for i, vid in enumerate(coll["ids"]) if vid not in kill]
        coll["ids"] = [coll["ids"][i] for i in keep]
        coll["documents"] = [coll["documents"][i] for i in keep]
        coll["metadatas"] = [coll["metadatas"][i] for i in keep]
        coll["embeddings"] = [coll["embeddings"][i] for i in keep]

    def delete_collection(self, collection_name):
        self.data.pop(collection_name, None)

    def collection_exists(self, collection_name):
        return collection_name in self.data

    def ensure_collection(self, collection_name):
        self._coll(collection_name)


def fake_embed(text: str) -> list[float]:
    dim = 64
    vec = [0.0] * dim
    for ch in text:
        vec[ord(ch) % dim] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def make_store():
    return MemoryStore(embed_fn=fake_embed, vector_store=FakeVectorStore())


# ────────────────────────────────────────────────────────────
# 测试辅助
# ────────────────────────────────────────────────────────────
def _user(db, email="u1@test.com", username="u1"):
    u = User(email=email, username=username, password_hash="x", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _thread(db, user_id):
    from uuid import uuid4

    t = Thread(id=str(uuid4()), user_id=user_id, title="t", agent_id=1)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ────────────────────────────────────────────────────────────
# P2: MemoryStore / Writer 显式写入 + 实体归一
# ────────────────────────────────────────────────────────────
def test_memory_store_upsert_query():
    store = make_store()
    store.upsert(1, 10, "项目A", "是一个电商项目")
    hits = store.query(1, "项目A的进度", k=2)
    assert hits and "项目A" in hits[0]["content"]


def test_writer_add_explicit_creates_and_merges():
    db = SessionLocal()
    try:
        u = _user(db)
        w = MemoryWriter(db, make_store())
        m1 = w.add_explicit(u.id, "语言偏好", "简体中文", layer=1, importance=0.8)
        # 同归一 key（"老鲍" 与 "Bob" 归一不同，但这里用相同 key 验证合并）
        m2 = w.add_explicit(u.id, "语言偏好", "繁体中文", layer=1, importance=0.8)
        rows = w.list_memories(u.id)
        assert len(rows) == 1, "同 key 应合并为一条"
        assert rows[0].value == "繁体中文", "应更新为最新值"
        assert m1.id == m2.id
    finally:
        db.close()


def test_writer_soft_delete():
    db = SessionLocal()
    try:
        u = _user(db, "d@test.com", "d")
        w = MemoryWriter(db, make_store())
        m = w.add_explicit(u.id, "k", "v")
        assert w.delete_memory(m.id, u.id) is True
        rows = w.list_memories(u.id)
        assert len(rows) == 0, "软删后 active 列表为空"
        archived = db.scalars(select(UserMemory).where(UserMemory.id == m.id)).first()
        assert archived.status == "archived"
    finally:
        db.close()


# ────────────────────────────────────────────────────────────
# P5: 隐式提取候选 + 晋升/驳回
# ────────────────────────────────────────────────────────────
def test_writer_extract_promote_reject():
    db = SessionLocal()
    try:
        u = _user(db, "p@test.com", "p")
        w = MemoryWriter(db, make_store())

        def ext(text):
            return ["语言偏好: 英文", "时区: 北京"]

        w.extract_candidates(u.id, "对话内容", ext)
        pend = w.list_pending(u.id)
        assert len(pend) == 2

        mem = w.promote(pend[0].id, u.id)
        assert mem is not None and mem.source == "extracted"
        accepted = db.scalars(select(PendingMemory).where(PendingMemory.id == pend[0].id)).first()
        assert accepted.status == "accepted"

        assert w.reject_pending(pend[1].id, u.id) is True
        rejected = db.scalars(select(PendingMemory).where(PendingMemory.id == pend[1].id)).first()
        assert rejected.status == "rejected"
    finally:
        db.close()


# ────────────────────────────────────────────────────────────
# P6: MemoryEnricher 去重/矛盾/衰减/晋升
# ────────────────────────────────────────────────────────────
def test_enricher_dedup_and_conflict():
    db = SessionLocal()
    try:
        u = _user(db, "e@test.com", "e")
        # 直接插入重复行（绕过 add_explicit 的合并），验证富集器去重/矛盾检测
        db.add(UserMemory(user_id=u.id, layer=1, mem_type="preference",
                          key="语言偏好", value="中文", importance=0.9, status="active"))
        db.add(UserMemory(user_id=u.id, layer=1, mem_type="preference",
                          key="语言偏好", value="英文", importance=0.9, status="active"))
        db.add(UserMemory(user_id=u.id, layer=1, mem_type="preference",
                          key="时区", value="北京", importance=0.5, status="active"))
        db.add(UserMemory(user_id=u.id, layer=1, mem_type="preference",
                          key="时区", value="北京", importance=0.5, status="active"))
        db.commit()
        w = MemoryWriter(db, make_store())
        stats = MemoryEnricher.run_once(db, make_store())
        active = w.list_memories(u.id)
        assert len(active) == 2, active
        assert stats["archived_conflict"] >= 1
        assert stats["merged"] >= 1
    finally:
        db.close()


def test_enricher_decay():
    db = SessionLocal()
    try:
        u = _user(db, "dec@test.com", "dec")
        from datetime import datetime, timedelta

        m = UserMemory(user_id=u.id, layer=1, mem_type="preference",
                       key="冷门偏好", value="xxx", importance=0.5, status="active")
        m.last_accessed = datetime.utcnow() - timedelta(days=120)
        db.add(m)
        db.commit()
        MemoryEnricher.run_once(db, make_store())
        db.refresh(m)
        assert m.importance < 0.5, "长期未访问应衰减"
    finally:
        db.close()


def test_enricher_promotion():
    db = SessionLocal()
    try:
        u = _user(db, "prom@test.com", "prom")
        t = _thread(db, u.id)
        st = ThreadContextState(thread_id=t.id, user_id=u.id,
                                 summary="用户在本会话讨论了电商套图的多角度拍摄方案。")
        db.add(st)
        db.commit()
        stats = MemoryEnricher.run_once(db, make_store())
        promoted = db.scalars(select(UserMemory).where(
            UserMemory.user_id == u.id, UserMemory.source == "promoted")).all()
        assert len(promoted) == 1, "会话摘要应晋升为 L3"
        assert stats["promoted"] == 1
    finally:
        db.close()


# ────────────────────────────────────────────────────────────
# P2/P4: ContextService 记忆注入（core / reflex / recall / RRF / gap）
# ────────────────────────────────────────────────────────────
def _seed_thread(db, user_id, turns=2):
    t = _thread(db, user_id)
    for i in range(turns):
        db.add(Message(thread_id=t.id, role="user", content=f"用户第{i}轮"))
        db.add(Message(thread_id=t.id, role="assistant", content=f"助手第{i}轮"))
    db.commit()
    return t


def test_context_core_and_reflex():
    db = SessionLocal()
    try:
        u = _user(db, "cr@test.com", "cr")
        w = MemoryWriter(db, make_store())
        w.add_explicit(u.id, "姓名", "张三", layer=0, mem_type="identity", importance=0.9)
        w.add_explicit(u.id, "语言偏好", "简体中文", layer=1, importance=0.8)
        store = make_store()
        # 让 reflex 也能命中：再写一条（同一 store 不重要，reflex 走 SQL）
        t = _seed_thread(db, u.id)
        cs = ContextService(db, store=store)
        opts = BuildOptions(enable_reflex=True, summarizer=lambda x: "S")
        msgs = cs.build(thread=t, user_id=u.id, current_text="我喜欢用简体中文回复",
                        system_prompt="SYS", opts=opts, model_name="gpt-4o")
        joined = "\n".join(m["content"] for m in msgs if m["role"] == "system")
        assert "用户身份" in joined, "L0 身份应常驻"
        assert "简体中文" in joined, "Reflex 应命中语言偏好"
    finally:
        db.close()


def test_context_semantic_recall():
    db = SessionLocal()
    try:
        u = _user(db, "rc@test.com", "rc")
        store = make_store()
        w = MemoryWriter(db, store)
        w.add_explicit(u.id, "项目A", "是一个电商项目", layer=3, mem_type="episodic", importance=0.5)
        t = _seed_thread(db, u.id)
        cs = ContextService(db, store=store)
        opts = BuildOptions(enable_memory_recall=True, summarizer=lambda x: "S")
        msgs = cs.build(thread=t, user_id=u.id, current_text="项目A的进度如何",
                        system_prompt="SYS", opts=opts, model_name="gpt-4o")
        joined = "\n".join(m["content"] for m in msgs if m["role"] == "system")
        assert "项目A" in joined, "语义回忆应召回项目A"
    finally:
        db.close()


def test_context_rrf_fusion():
    db = SessionLocal()
    try:
        u = _user(db, "rrf@test.com", "rrf")
        store = make_store()
        w = MemoryWriter(db, store)
        w.add_explicit(u.id, "语言偏好", "简体中文", layer=1, importance=0.8)
        w.add_explicit(u.id, "项目A", "是一个电商项目", layer=3, mem_type="episodic", importance=0.5)
        t = _seed_thread(db, u.id)
        cs = ContextService(db, store=store)
        opts = BuildOptions(enable_reflex=True, enable_memory_recall=True, enable_rrf=True,
                            summarizer=lambda x: "S")
        msgs = cs.build(thread=t, user_id=u.id, current_text="我喜欢简体中文，项目A进展怎样",
                        system_prompt="SYS", opts=opts, model_name="gpt-4o")
        joined = "\n".join(m["content"] for m in msgs if m["role"] == "system")
        assert "融合检索" in joined, "RRF 应将 reflex+recall 融合为单块"
    finally:
        db.close()


def test_context_gap_analysis():
    db = SessionLocal()
    try:
        u = _user(db, "gap@test.com", "gap")
        store = make_store()
        t = _seed_thread(db, u.id)
        cs = ContextService(db, store=store)
        opts = BuildOptions(enable_gap_analysis=True, enable_reflex=True,
                            summarizer=lambda x: "S")
        msgs = cs.build(thread=t, user_id=u.id, current_text="我喜欢喝咖啡",
                        system_prompt="SYS", opts=opts, model_name="gpt-4o")
        joined = "\n".join(m["content"] for m in msgs if m["role"] == "system")
        assert "无已知用户偏好" in joined, "召回不足应注入诚实提示"
    finally:
        db.close()


def test_preview_memory():
    db = SessionLocal()
    try:
        u = _user(db, "pv@test.com", "pv")
        w = MemoryWriter(db, make_store())
        w.add_explicit(u.id, "语言偏好", "简体中文", layer=1, importance=0.8)
        cs = ContextService(db, store=make_store())
        opts = BuildOptions(enable_reflex=True, enable_gap_analysis=True)
        out = cs.preview_memory(u.id, "我喜欢简体中文", opts)
        assert "reflex" in out
        assert "简体中文" in out["reflex"]
    finally:
        db.close()


def test_normalize_key():
    assert normalize_key("Bob") == normalize_key("bob")
    assert normalize_key("老鲍") == normalize_key("老鲍 ")
