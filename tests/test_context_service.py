"""ContextService 单元测试（ADR-021/022/023）。

运行：python -m pytest tests/test_context_service.py -v
数据库指向临时 sqlite（conftest 设置），不触碰真实数据。
tiktoken 缺失时 estimate_tokens 自动回退中文-aware 启发式，不影响断言。
"""

import os

from app.core.database import SessionLocal, init_db
from app.models import Message, Thread, ThreadContextState, User, UserMemory
from app.context_service import BuildOptions, ContextService, estimate_tokens, model_window


def _user(db, uid):
    u = db.get(User, uid)
    if u is None:
        u = User(id=uid, email=f"u{uid}@x.com", username=f"u{uid}",
                 password_hash="x", role="user")
        db.add(u)
        db.commit()
    return u


def _thread(db, uid):
    t = Thread(id=f"t_{os.urandom(4).hex()}", user_id=uid, title="t")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _big(n=200):
    return "内容" * n  # 启发式 ~ n*2 tokens（CJK 每字 1 token）


# ----------------------------------------------------------------------
# 分词
# ----------------------------------------------------------------------
def test_estimate_tokens_chinese_aware():
    zh = "这是一段中文测试文本用于验证分词准确性是否对中文友好处理"
    en = "this is an english test text for checking tokenizer friendliness ok"
    assert estimate_tokens(zh) >= estimate_tokens(en)


def test_model_window_mapping():
    assert model_window("gpt-4o-mini") == 128_000
    assert model_window("gpt-3.5-turbo") == 16_385
    assert model_window("some-unknown-model") == 128_000  # settings 兜底


# ----------------------------------------------------------------------
# 短会话：全部原样保留
# ----------------------------------------------------------------------
def test_short_thread_keeps_all():
    db = SessionLocal()
    try:
        _user(db, 1)
        t = _thread(db, 1)
        for i in range(3):
            db.add(Message(thread_id=t.id, role="user", content=f"用户消息{i}"))
            db.add(Message(thread_id=t.id, role="assistant", content=f"助手回复{i}"))
        db.commit()

        opts = BuildOptions(recent_turns=20, summarizer=lambda x: "SUM")
        msgs = ContextService(db).build(t, 1, "用户消息2", "SYS", opts, model_name="gpt-4o")
        conv = [m for m in msgs if m["role"] in ("user", "assistant")]
        assert len(conv) == 6
        assert any(m["content"] == "用户消息2" for m in conv)
        # 未触发压缩：无摘要块
        assert not any("[早期对话摘要]" in m["content"] for m in msgs if m["role"] == "system")
    finally:
        db.close()


# ----------------------------------------------------------------------
# 长会话：触发增量压缩
# ----------------------------------------------------------------------
def test_long_thread_compacts():
    db = SessionLocal()
    try:
        _user(db, 2)
        t = _thread(db, 2)
        for _ in range(40):
            db.add(Message(thread_id=t.id, role="user", content=_big()))
            db.add(Message(thread_id=t.id, role="assistant", content=_big()))
        db.commit()

        calls = {"n": 0}

        def summarizer(text):
            calls["n"] += 1
            return "SUMMARY_TEXT"

        # 用 gpt-3.5-turbo(16385) 强制超预算
        opts = BuildOptions(recent_turns=4, summarizer=summarizer)
        msgs = ContextService(db).build(t, 2, _big(), "SYS", opts, model_name="gpt-3.5-turbo")

        conv = [m for m in msgs if m["role"] in ("user", "assistant")]
        # 旧轮被折叠，仅保留最近 4 条原样
        assert len(conv) == 4
        # 摘要块出现且含压缩结果
        summary_blocks = [m["content"] for m in msgs if m["role"] == "system"
                          and "[早期对话摘要]" in m["content"]]
        assert summary_blocks and "SUMMARY_TEXT" in summary_blocks[0]
        # 状态已持久化（可逆：清空即恢复）
        state = db.get(ThreadContextState, t.id)
        assert state is not None and state.summary == "SUMMARY_TEXT"
        assert state.last_compacted_msg_id is not None
        assert calls["n"] >= 1
    finally:
        db.close()


# ----------------------------------------------------------------------
# 压缩 summarizer 异常：滑动窗口降级，绝不阻塞用户
# ----------------------------------------------------------------------
def test_compaction_failure_falls_back_to_sliding_window():
    db = SessionLocal()
    try:
        _user(db, 3)
        t = _thread(db, 3)
        for _ in range(40):
            db.add(Message(thread_id=t.id, role="user", content=_big()))
            db.add(Message(thread_id=t.id, role="assistant", content=_big()))
        db.commit()

        def summarizer(text):
            raise RuntimeError("llm unavailable")

        opts = BuildOptions(recent_turns=4, summarizer=summarizer)
        # 不应抛异常
        msgs = ContextService(db).build(t, 3, _big(), "SYS", opts, model_name="gpt-3.5-turbo")

        conv = [m for m in msgs if m["role"] in ("user", "assistant")]
        assert len(conv) == 4  # 旧轮被丢弃
        # 未生成摘要（降级路径不写 summary）
        assert not any("[早期对话摘要]" in m["content"] for m in msgs if m["role"] == "system")
    finally:
        db.close()


# ----------------------------------------------------------------------
# Retrieval Reflex（gbrain，零 LLM 指针层）
# ----------------------------------------------------------------------
def test_retrieval_reflex_injects_pointer():
    db = SessionLocal()
    try:
        _user(db, 4)
        t = _thread(db, 4)
        db.add(Message(thread_id=t.id, role="user", content="你好"))
        db.add(Message(thread_id=t.id, role="assistant", content="你好，有什么可以帮你？"))
        db.add(UserMemory(
            user_id=4, layer=1, mem_type="preference",
            key="语言偏好", value="用户希望用简体中文回复",
            importance=0.9, status="active", source="explicit",
        ))
        db.commit()

        opts = BuildOptions(recent_turns=20, enable_reflex=True, summarizer=lambda x: "S")
        msgs = ContextService(db).build(t, 4, "我喜欢用中文回复", "SYS", opts, model_name="gpt-4o")
        mem_blocks = [m["content"] for m in msgs if m["role"] == "system"
                      and "用户记忆" in m["content"]]
        assert mem_blocks, "Retrieval Reflex 应注入记忆指针"
        assert "语言偏好" in mem_blocks[0]
        assert "用户希望用简体中文回复"[:120] in mem_blocks[0]
        # 指针而非全文：不应把整段对话灌进来
        assert "[记忆]" in mem_blocks[0]
    finally:
        db.close()


def test_retrieval_reflex_off_no_memory_block():
    db = SessionLocal()
    try:
        _user(db, 5)
        t = _thread(db, 5)
        db.add(Message(thread_id=t.id, role="user", content="你好"))
        db.commit()
        opts = BuildOptions(recent_turns=20, enable_reflex=False, summarizer=lambda x: "S")
        msgs = ContextService(db).build(t, 5, "我喜欢用中文回复", "SYS", opts, model_name="gpt-4o")
        assert not any("用户记忆" in m["content"] for m in msgs if m["role"] == "system")
    finally:
        db.close()
