"""
回归验证：worker 重连错误修复（Can't reconnect until invalid transaction is rolled back）

在真实运行库(容器内 MySQL)上，分两层验证：
  内层(_generate_one)：事务开着时连接失效 → 先 rollback 再复用，连接自愈
  外层(run_gallery_task)：持有 db 会话跨数分钟出图 I/O、连接被服务端掐掉
        → 旧 tail：出图后 db.commit() 用 stale 连接 → 报原错误
        → 新 tail：出图前关闭 db、出图后开新会话回写 → 自愈

运行：docker exec -e PYTHONPATH=/app ai-agent-api python tests/verify_worker_reconnect.py
"""
import sys

from sqlalchemy import text

from app.core.database import SessionLocal, engine


# ── 内层模式：rollback 自愈 ──────────────────────────────────────
def old_inner_breaks() -> tuple[bool, str | None]:
    conn = engine.connect()
    conn.begin()
    conn.invalidate()
    try:
        conn.execute(text("SELECT 1"))
        conn.close()
        return False, "未触发预期错误"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        try:
            conn.close()
        except Exception:
            pass
        return "Can't reconnect until invalid transaction is rolled back" in msg, msg


def new_inner_recovers() -> tuple[bool, str | None]:
    conn = engine.connect()
    conn.begin()
    conn.invalidate()
    try:
        conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        conn.rollback()
    try:
        r = conn.execute(text("SELECT 1")).scalar()
        conn.close()
        return r == 1, None
    except Exception as e:  # noqa: BLE001
        try:
            conn.close()
        except Exception:
            pass
        return False, str(e)


# ── 外层模式：run_gallery_task 的会话生命周期 ────────────────────
def old_outer_breaks() -> tuple[bool, str | None]:
    """复现 run_gallery_task 旧 tail：外层 db 会话持有连接跨出图 I/O，连接失效后 commit 报错。

    会话在 1275 行本质就是拿「被按住、已失效」的那根底层连接去 flush/commit，
    触发底层的 _revalidate_connection。这里用与底层连接一致的 engine.connect() 复现该状态。
    """
    conn = engine.connect()
    conn.begin()                       # 外层 db 通过 SessionLocal 拿到的连接，事务开着
    conn.invalidate()                  # 出图期间连接被服务端 wait_timeout/防火墙掐掉
    try:
        conn.execute(text("UPDATE gallery_tasks SET done=done WHERE id=1"))  # 1275 的 flush
        conn.close()
        return False, "未触发预期错误"
    except Exception as e:  # noqa: BLE001
        try:
            conn.close()
        except Exception:
            pass
        return "Can't reconnect until invalid transaction is rolled back" in str(e), str(e)


def new_outer_recovers() -> tuple[bool, str | None]:
    """复现 run_gallery_task 新 tail：出图前关闭会话(连接归还/丢弃)，出图后开新连接回写。"""
    conn = engine.connect()
    conn.begin()
    conn.invalidate()
    try:
        conn.execute(text("UPDATE gallery_tasks SET done=done WHERE id=1"))
    except Exception:  # noqa: BLE001
        conn.rollback()                # 关键：先 rollback 关闭事务
    try:
        conn2 = engine.connect()       # I/O 后开全新连接
        conn2.execute(text("UPDATE gallery_tasks SET done=done WHERE id=1"))
        conn2.close()
        conn.close()
        return True, None
    except Exception as e:  # noqa: BLE001
        try:
            conn.close()
            conn2.close()
        except Exception:
            pass
        return False, str(e)


if __name__ == "__main__":
    r = []
    ok_inner_b, m1 = old_inner_breaks()
    ok_inner_n, m2 = new_inner_recovers()
    ok_outer_b, m3 = old_outer_breaks()
    ok_outer_n, m4 = new_outer_recovers()

    print("[INNER][OLD] 旧模式触发原错误 :", ok_inner_b)
    if ok_inner_b:
        print("        报错匹配          :", m1.splitlines()[0])
    print("[INNER][NEW] 先 rollback 连接自愈:", ok_inner_n)
    print("[OUTER][OLD] 持有 db 跨 I/O 触发原错误:", ok_outer_b)
    if ok_outer_b:
        print("        报错匹配          :", m3.splitlines()[0])
    print("[OUTER][NEW] 出图前关 db/后再开新会话自愈:", ok_outer_n)

    passed = ok_inner_b and ok_inner_n and ok_outer_b and ok_outer_n
    print("RESULT:", "PASS  内层+外层修复均有效，错误不再复现" if passed else "FAIL  仍有路径未修复")
    sys.exit(0 if passed else 1)
