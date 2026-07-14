"""迁移：为 gallery_showcases 增加 payload 列并清理 seed 假数据。

背景：
- 旧版 seed_showcases 向 gallery_showcases 注入了 6 条 SVG 占位图（假数据），
  创作案例只展示这些假图。本迁移删除这些假数据，只保留用户真实发布的成图。
- 同时新增 payload(JSON) 列，用于存储发布时携带的源任务配置，
  使「生成同款」能一键回填参数。

兼容 SQLite（本地）与 MySQL（Docker）：
- 列类型按方言选择；不写 server_default（MySQL 不允许 TEXT/JSON 带默认值）。
- 幂等：列已存在则跳过；删除仅针对 original_url 以 .svg 结尾的 seed 行。
"""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, inspect, text


def main() -> None:
    # 复用 app 的数据库 URL（sqlite:///./agent.db 或 mysql...）
    try:
        from app.db_url import normalize_db_url

        db_url = normalize_db_url()
    except Exception:
        db_url = "sqlite:///./agent.db"

    engine = create_engine(db_url, future=True)
    insp = inspect(engine)
    dialect = engine.dialect.name

    with engine.begin() as conn:
        cols = insp.get_columns("gallery_showcases")
        col_names = {c["name"] for c in cols}

        if "payload" not in col_names:
            col_type = "JSON NULL" if dialect == "mysql" else "TEXT"
            conn.execute(text(f"ALTER TABLE gallery_showcases ADD COLUMN payload {col_type}"))
            print(f"[migrate] 已为 gallery_showcases 增加 payload 列（{col_type}）")
        else:
            print("[migrate] payload 列已存在，跳过加列")

        # 清理 seed 注入的 SVG 假数据（original_url 以 .svg 结尾），保留真实发布
        res = conn.execute(
            text("DELETE FROM gallery_showcases WHERE original_url LIKE '%.svg'")
        )
        deleted = res.rowcount if res.rowcount is not None else 0
        print(f"[migrate] 已删除假数据(seed SVG) 行数: {deleted}")

    print("[migrate] 完成")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[migrate] 失败: {e}", file=sys.stderr)
        sys.exit(1)
