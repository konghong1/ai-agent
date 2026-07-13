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
- **双语生成 (V13)**: `build_prompt_bilingual()` 返回 `{prompt: 中文展示版, prompt_en: 英文生成版}`；**生成时以 `prompt_en` 送图像模型**（经 `run_gallery_task` → `_real_generate`）。UI `PromptBadge` 中/英 Tab 展示。
- **angle 类型语义硬约束（2026-07-13 用户纠正）**: `产品多角度` = 一张图内展示产品多个视角（提示词 `multi-angle collage`），**绝不可拆成多张单角度图**。`run_gallery_task` 对所有类型统一按 `output_settings.count`（默认 1）生成单图；不要为 angle 特判多图，也不要把「角度数量」映射成张数。曾误加 `resolve_angle_views`/`build_angle_prompts` 拆多图，已全量回退删除。
- **英文版零中文规则（硬约束）**: `_t()` 对未命中 `OPTIONS_EN` 的中文值会原样泄漏；任何新选项值/类型标题/平台名/修图串若进入英文路径，必须在 `OPTIONS_EN` 或专用 `*_EN` 词典（`VALUE_FOCUS_VOCAB_EN`/`STYLE_VOCAB_EN`/`PRODUCT_PRESENT_VOCAB_EN`/`VALUE_HINT_VOCAB_EN`/`FABRIC_VOCAB_EN`/`CRAFT_VOCAB_EN`）中有英文映射，且 `_DEFAULT_PLATFORM` 兜底必须是英文。唯一允许的中文是用户自己写的 `selling_points`。改提示词引擎后必须重跑 `tests/audit_bilingual.py` + `tests/test_gallery_prompt.py` 验证零泄漏。

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

## 电商套图 · 提示词工程 = Agnes 多模态 AI 生成（2026-07-13 重构）

**架构定调**: 提示词**不再**用 `gallery_prompt.py` 的 86 项硬编码拼装（已降级为兜底）。主路径由 **Agnes 2.0 Flash 多模态**（`OPENAI_BASE_URL`=https://apihub.agnes-ai.com/v1，model=agnes-2.0-flash，复用 `settings`）根据「用户配置+卖点+参考图(base64 内联)」生成差异化提示词。

- **核心引擎**: `app/gallery_prompt_ai.py` — `generate_prompt_via_ai`(生成图提示词, 返回 `{prompt,prompt_en,prompt_source}`)、`ai_write_selling_points`(卖点帮写: 产品名称/核心卖点/适用人群/期望场景/具体参数)、`ai_write_type_config`(类型配置帮写)。
- **降级**: AI 不可达/超时/解析失败 → 降级旧 `gallery_prompt.build_prompt_bilingual`，`prompt_source` 标 `template`（用户明确选"AI 为主+模板兜底"）。Agnes 偶发 503(server memory overloaded) 属服务端瞬时过载，走兜底是预期行为。
- **英文零中文**: `prompt_en` 经 `_strip_cjk` 兜底清中文（硬约束）。
- **落库**: `gallery_records.prompt_source`(VARCHAR16) 记录来源；`core/database._migrate_sqlite_columns` 已加 ALTER（SQLite/MySQL 兼容）。
- **前端**: `gallery.ts` 的 `aiWriteSellingPoints()`；`index.tsx` 卖点「AI 帮写」回填文本框、`PromptBadge` 加「AI」徽标（`promptSource` 属性）；`TypeSettingsModal`「AI帮填」后端已变 AI，前端不改。
- **验证**: `python tests/test_gallery_prompt_ai.py`(7 passed)；`tsc --noEmit` 零错误；`vite build` 4289 模块。
- **生效**: 后端改 → 重启 `ai-agent-api`+`ai-agent-worker`；前端 Ctrl+F5。

## Docker 前端白屏/登录不上 = nginx sendfile bug（重要排错项）
- **现象**: 浏览器打开 `localhost`(Docker web 容器 :80) 白屏、登录页点不动；`curl` 从**宿主**访问 `/assets/*.js|css` 返回 `Content-Length` 正确但**响应体 0 字节**；容器内 `curl 127.0.0.1` 却完整。后端 `/api/auth/login` 一直正常（401=正确校验）。
- **根因**: `docker/nginx.conf` 作为 `default.conf` 挂进 `ai-agent-web`，base `nginx.conf` 的 `http` 块默认 `sendfile on`；`../web/dist` 是**从 Windows 宿主机 bind mount** 进容器的。Docker Desktop 下 `sendfile()` 对挂载卷文件向**外部客户端**发 0 字节体（容器内回环正常，所以自测发现不了）。
- **修复**: 在 `docker/nginx.conf` 的 `server` 块加 `sendfile off;`（持久化，覆盖 http 级 on），`docker restart ai-agent-web` 生效。改后宿主可完整下发 js(2.8MB)/css(120KB)。
- **快速诊断命令**: `docker exec ai-agent-web curl -s -o /dev/null -w '%{size_download}' http://127.0.0.1:80/assets/<hash>.js`（容器内）对比宿主 `curl -s -o /dev/null -w '%{size_download}' http://localhost/assets/<hash>.js`（宿主）；不一致即此 bug。
- **注意**: `sendfile off` 后偶发 reload 瞬间仍 0 字节，等容器完全起来再测；若仍 0 字节可能是 Docker Desktop 网络抖动，重启 web 容器即可。
