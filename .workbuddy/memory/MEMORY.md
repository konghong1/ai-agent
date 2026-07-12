# 项目长期记忆 — AI Agent Platform

## 技术栈
- 后端: FastAPI + uvicorn (端口 8010) + SQLAlchemy + SQLite/MySQL
- 前端: Vite + React + TypeScript (端口 5173)
- AI: LangChain + OpenAI-compatible API (agnes-2.0-flash)
- 向量库: ChromaDB

## 关键架构约束
- **async/sync 混用陷阱**: `async def` 端点中不能直接调用同步阻塞函数，必须用 `asyncio.to_thread()` 包装。普通 `def` 端点 FastAPI 自动放线程池。
- **端口一致性**: .env PORT=8010, Vite 代理目标 127.0.0.1:8010, 启动命令 --port 8010 三者必须一致。
- **数据库驱动**: `app/db_url.py: normalize_db_url()` 统一注入驱动（`mysql+pymysql`/`postgresql+psycopg2`）。三处 `create_engine` 都已改用。模型用 `app/models.py`（MySQL 兼容），PG 模型在 `app/models_pg/`。
- **Pydantic 响应 schema**: 新增数据库列暴露到响应 schema 时**必须声明可空**（`X | None = None`），因为 ALTER TABLE 加的列存量行为 NULL。统一用 PEP 604 写法。

## 存储桶区分
- 用户聊天上传图 → 独立桶 `chat-uploads`（`POST /api/chat/upload`）
- AI 生成图/视频产物 → 默认桶 `ai-agent-minio`
- `inline_reference_image()` 将 by-key 代理 URL 转为 base64 再调远程模型。

## 出网代理韧性（app/http_client.py）
- Docker 注入 `HTTPS_PROXY=host.docker.internal:33210`（WorkBuddy 沙箱代理），可能随时不可达。
- `ensure_proxy_strategy()` 模块导入时探测代理，不可达则清除 env 走直连。
- `request_with_fallback()` / `download_bytes_with_fallback()` 每次调用带直连兜底。
- 已验证宿主机可直接出网。设 `DISABLE_PROXY_AUTOFALLBACK=1` 可保留强制代理。
- 图片生成超时 300s，视频提交 120s，视频轮询 60s，下载 120s。

## 用户协作偏好（重要）
- **不要凭空臆想需求**：用户反对自作主张加「兜底/共享/自动降级」等跨用户逻辑。需求不清楚先问。
- **数据隔离是硬约束**：每用户只能用自己配置的资源，绝不能借用他人资源。
- 修改后端代码后提醒用户**重启 FastAPI 并刷新浏览器（Ctrl+F5）**。

## 电商套图 · 提示词引擎（gallery_prompt.py + gallery_config.py）
- **架构**: 数据驱动流水线 `Resolver → CopyPolicy → Assembler → Linter`。单一事实源。
- **COLOR LOCK (V5)**: 颜色锁定前移到 M1 最强位置。palette 改为"背景色系"措辞，从源头杜绝染产品色。
- **人物判定**: `_wants_human(type_id, personal)` — 试穿/代言/买家秀强制人物；纯产品类型绝不出现人物。
- **主体一致性锚定**: 有参考图时注入最强约束（外观/版型/颜色/材质/logo 逐处一致，不得改变）。
- **通用兜底 (V7)**: M3.5 段注入所有未显式处理的字段，修复 12 个类型字段被静默丢弃的致命 BUG。
- **配置版本化**: `GALLERY_CONFIG_VERSION=8`（V8 已升级），版本变化时强制更新 DB。
- **V8 电商转化视角重构 (2026-07-12)**: 全部推荐类型配置项收敛到 5 个转化维度——价值聚焦 / 视觉强化 / 产品呈现 / 氛围浓度 / 价值暗示；人物类配置项大幅精简，人物基础描述由 `target_market` 市场档案提供。新增 `PRODUCT_PRESENT_VOCAB` 并扩展 `STYLE_VOCAB` / `VALUE_FOCUS_VOCAB` / `VALUE_HINT_VOCAB`，提示词 M3 层按 5 维度量化注入。
- `gallery_service._build_prompt` 为薄委派，签名不变。

## 电商套图 · 环境双栈
- **Docker 正确栈（推荐）**: `http://localhost/`（docker web 映射 80），连 MySQL `ai_agent`（5 个图片模型，能真实出图）。
- **本地误用栈**: 本地 uvicorn 占 8010 连 SQLite `ai_agent.db`（0 个图片模型，走离线降级只留 SVG 占位）。
- 用 vite 开发前需先停掉占 8010 的本地 uvicorn。

## 电商套图 · 前端 UI（2026-07-12 回退后 + Taste Skill 重设计）
- **用户最终诉求**: 去掉"单独商品图"模块；参考 Taste Skill 重新设计套图 UI；**只改样式、不动前后端逻辑**；重点修按钮间距与整体协调。
- **已移除**: `TypeSettingsModal` 的"单独商品图"区块（JSX + 关联 state/handler/import 一并清理，因 `noUnusedLocals` 开启否则编译失败）。`product_image` 在 payload 中保留为 `item?.product_image || ''`，后端逻辑未变。参考图上传仍用同一套 `.ref-upload*` 类，无死 CSS。
- **Taste Skill 样式升级（纯 CSS，gallery.css 末尾精炼层）**:
  - 统一强调色：主操作改品牌橙（去掉刺眼柠檬黄 CTA `#C8E000`）；AI 语义按钮去 `linear-gradient` 紫蓝 glow，改实心靛蓝 `#6E63CF` + 同色调阴影。
  - 按钮全局态：按压下压 `translateY(1px)`、键盘 `:focus-visible` 焦点环、统一 200ms 级过渡（排除 antd 内部按钮）。
  - 操作行间距统一：`df-actions` / `modal-footer` / `plan-actions` / `case-actions` 全部 `gap: var(--gb-s3)` (12px)，按钮基线 `min-height:40px` 对齐。
  - 卡片悬浮微抬升 + 统一品牌色边框（策划台 `dg-card`）。
  - 标题字距收紧 `-.02em`。
- **验证**: `tsc --noEmit` 零错误；`vite build` 4289 模块成功（CSS 112KB）。
- **协作教训**: 用户要"减少配置"时不得自作主张加花活；但用户明确授权"参考 Taste Skill 重设计样式"时可做受控视觉升级，前提是不动逻辑。策划台只加规划列表、不生成图；提示词由后端生成。

## 电商套图 · 图片生成尺寸与参考图一致性（2026-07-12）
- **图片比例**: `app/gallery_service.py` 原硬编码 `size="1024x1024"`，已改为按 `output_settings.ratio` 映射生成尺寸（`_ratio_to_size`）。比例尺寸保持短边 1024、长边取 64 整数倍，兼顾 Agnes/SD 系列模型兼容性。
- **参考图感知**: 提示词引擎 `_resolve_config` 的 `has_reference` 必须包含运行时回退的项目产品图 `effective_product_image`，否则会出现「参考图已传给模型，但提示词没写主体一致性约束」导致生成图与产品无关。`build_prompt` 已增加该参数。
- **前端展示**: 作品详情弹窗中每个 `.detail-img` 按 `record.plan_item_snapshot.output_settings.ratio` 动态设置 `aspect-ratio`，不再一刀切 3:4。
- **验证命令**: `python -m py_compile app/gallery_prompt.py app/gallery_service.py`; `tsc --noEmit`; `vite build`; 新增 `tests/test_gallery_ratio_prompt.py`。
- **操作**: 修改后端后必须重启 `ai-agent-api` + `ai-agent-worker`，前端刷新 Ctrl+F5。

- 所有生成文件归入 `ai/agent-output/`：`overviews/`（总结）、`verify-shots/`（截图）、`logs/`（日志）。
- 不可移动：`agent.db`/`.env`/运行时 SQLite；项目文档（PRD/FDD/README/AGENTS/TASKS）；`designs/`、`疑问/`。
