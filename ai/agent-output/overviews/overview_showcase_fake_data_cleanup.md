# 清理「创作案例」残留假数据 + 修复部署遗漏

## 背景
用户反馈：①「立即生成」仍报 worker error；②创作案例里还有假数据。

排查发现根因是**上一轮清理清错了数据库 + 容器没重启**：
- 迁移脚本 `showcase_payload.py` 用 `create_engine(normalize_db_url())` 自建引擎，解析到 `.env` 的 SQLite（`agent.db`，0 行），而运行时是 Docker/MySQL（`ai_agent`）。于是「删了 0 行」却误以为已清完。
- 删除条件 `original_url LIKE '%.svg'` 漏掉了种子行（种子行 `original_url` 是 `/api/gallery/files/showcase/<hex>`，无 `.svg` 后缀，只有 `image_urls` 里才是 `.svg`）。
- 上一轮 worker 重连修复改了 `gallery_service.py` 但**未重启容器**，旧代码仍在跑 → 用户仍看到 worker error。

## 实际状态（进容器查证）
- MySQL `gallery_showcases` 共 7 行：
  - id=1–6 = 6 条种子假数据（original 在 `showcase/`、image_urls 全 `.svg`）→ 应删
  - id=7 = 真实发布的「测试」（original 在 `projects/`、image_urls 是 `.png`）→ 保留
- 磁盘 `uploads/gallery/showcase/` 堆 96 个孤儿 SVG（约 885B，Jul 7–10 生成），无任何代码/DB 再引用。

## 改动
| 文件 | 改动 |
|------|------|
| `migrations/showcase_payload.py` | ①复用 `app.core.database.engine`（连运行时真库，不再自建 SQLite 引擎）；②删除条件改为 `original_url LIKE '%.svg' OR original_url LIKE '%/showcase/%'`（精准命中种子行，不误删 `projects/`/`results/` 下的真实数据）；③顶部加项目根到 `sys.path`（docker exec 跑脚本能 import app） |
| `app/gallery_service.py` | 移除死代码 `write_result_svg` + `_make_svg` + `_hue_from_key` + `_esc`（整簇无调用点，是「假图生成能力」本身） |
| `uploads/gallery/showcase/` | 删 96 个孤儿 SVG（先备份 `.trash-showcase-bak/`，再清理，目录归 0） |
| 容器 | `docker restart ai-agent-api ai-agent-worker` 部署（含上一轮 worker 重连修复 + 本轮死代码移除） |

## MySQL 实际清理（手动执行于容器内）
```sql
DELETE FROM gallery_showcases WHERE original_url LIKE '%.svg' OR original_url LIKE '%/showcase/%';
-- 删除 6 行，保留 id=7（真实发布）
```

## 验证
- 容器内迁移：`payload 列已存在，跳过加列` + `已删除假数据 行数: 0`（幂等正确，连对 MySQL）。
- `gallery_showcases` 最终 **1 行**（id=7 真实）。`uploads/gallery/showcase/` **0 文件**。
- `tests/test_gallery_prompt.py` **27 passed**；`py_compile` 通过。
- 容器 `ai-agent-api` / `ai-agent-worker` 重启后状态 `Up`。

## 给团队的教训（资深开发视角）
1. **迁移脚本必须与运行时连同一个库**：用 `app.core.database.engine`，绝不用 `normalize_db_url()` 另建引擎（会被 `.env` 带偏到 SQLite）。
2. **删除条件要看真实数据形状**，不能想当然：种子行的 original 不带 `.svg`，得按 `showcase/` 路径区分。
3. **改完后端必须重启容器**，否则用户看到的是旧代码（worker error 反复出现就是这么来的）。
4. **死代码就是隐患**：`write_result_svg` 一簇是「假图生成能力」，留着迟早再被人误用；发现无调用点立即删。
5. **清理磁盘孤儿文件**：DB 行删了，磁盘上的种子 SVG 还在，必须一并清，并先备份再删。
