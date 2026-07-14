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

import os
import sys

# 确保无论从哪个工作目录执行都能 import app（docker exec 跑脚本时只把
# 脚本所在目录加入 sys.path，不会包含项目根）。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from sqlalchemy import inspect, text


def main() -> None:
    # 复用 app 运行时真正连接的 engine（sqlite 本地 / mysql Docker），
    # 不要用 normalize_db_url() 自建 engine —— 后者会解析到 .env 的 SQLite，
    # 而 Docker 运行库是 MySQL，导致「删了 0 行」却以为清理完成。
    try:
        from app.core.database import engine

        insp = inspect(engine)
        dialect = engine.dialect.name
    except Exception as e:
        print(f"[migrate] 无法加载 app engine: {e}", file=sys.stderr)
        sys.exit(1)

    with engine.begin() as conn:
        cols = insp.get_columns("gallery_showcases")
        col_names = {c["name"] for c in cols}

        if "payload" not in col_names:
            col_type = "JSON NULL" if dialect == "mysql" else "TEXT"
            conn.execute(text(f"ALTER TABLE gallery_showcases ADD COLUMN payload {col_type}"))
            print(f"[migrate] 已为 gallery_showcases 增加 payload 列（{col_type}）")
        else:
            print("[migrate] payload 列已存在，跳过加列")

        # 清理 seed 注入的 SVG 假数据。
        # 注意：种子行的 original_url 形如 /api/gallery/files/showcase/<hex>
        # （无 .svg 后缀，只有 image_urls 里才是 .svg），因此必须同时按
        # '%/showcase/%' 命中；真实发布的 original_url 在 projects/ 或 results/ 下，
        # 绝不会落在 showcase/ 目录，故可按 original_url 精准区分、不误删真实数据。
        res = conn.execute(
            text(
                "DELETE FROM gallery_showcases "
                "WHERE original_url LIKE '%.svg' OR original_url LIKE '%/showcase/%'"
            )
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
