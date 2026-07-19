"""一次性脚本：在 MySQL 中为用户 1(admin) 创建一个待确认记忆候选，供浏览器 E2E 验证 accept。
注意：必须在 ai-agent-api 容器内运行（继承容器 MySQL DATABASE_URL），否则会连到 SQLite。
"""
import sys
from app.core.database import SessionLocal
from app.models import PendingMemory


def main() -> None:
    db = SessionLocal()
    try:
        existing = (
            db.query(PendingMemory)
            .filter_by(user_id=1, status="pending")
            .all()
        )
        for e in existing:
            db.delete(e)
        db.commit()

        cand = PendingMemory(
            user_id=1,
            candidate="计划评审时间: 每日上午十点做计划评审",
            status="pending",
        )
        db.add(cand)
        db.commit()
        db.refresh(cand)
        print("SEEDED_ID=%d" % cand.id)
    finally:
        db.close()


if __name__ == "__main__":
    main()
