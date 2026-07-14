# 项目长期记忆 — AI Agent Platform（已精简合并）

> 维护规则：每次大改后追加到当日 `YYYY-MM-DD.md`；本文件只保留**跨会话仍有用**的硬约束/坑/架构事实，定期去重。

## 技术栈
- 后端: FastAPI + uvicorn (8010) + SQLAlchemy + SQLite(本地)/MySQL(Docker)
- 前端: Vite + React + TS (5173)；Docker 正确栈 `http://localhost/`(web:80) 连 MySQL `ai_agent`
- AI: OpenAI-compatible API，agnes-2.0-flash(推理模型, 出图提示词) / agnes-image-2.x / agnes-video-v2.0
- 向量库 ChromaDB；存储桶 `chat-uploads`(聊天上传) / `ai-agent-minio`(生成产物)

## 关键架构约束（硬坑）
- **async/sync 混用**: `async def` 端点内调同步阻塞必须用 `asyncio.to_thread()`。
- **端口一致**: .env/代理/启动命令三者均 8010。
- **DB 驱动**: `app/db_url.py: normalize_db_url()` 统一注入；模型用 `app/models.py`(MySQL 兼容)。
- **Pydantic 响应 schema 新增列必须可空** `X | None = None`（ALTER 加的列存量 NULL）。
- **🔥 MySQL 迁移 TEXT 列禁带默认值**: `ADD COLUMN x TEXT DEFAULT ''` 在 MySQL8 报 1101，致 api 崩溃 restart loop。规则：TEXT 列 ALTER 与 `mapped_column` 都**不得**写 `DEFAULT ''`/`server_default`，列允许 NULL，应用层 `default=""` 或读取 `or ""` 兜底。VARCHAR 可带默认值。改完必在 Docker 验证迁移。
- **Docker 前端白屏 = nginx sendfile bug**: `docker/nginx.conf` 的 `server` 块加 `sendfile off;`（因 `../web/dist` 是 Windows bind mount，sendfile 向外部发 0 字节体）。`docker restart ai-agent-web` 生效。
- **🔥 绝不在 FastAPI startup 事件里做会阻塞/可能失败的网络调用**（pip 安装、外部 HTTP）。曾因 `_ensure_pillow()` 同步 `subprocess.run(pip install)` 阻塞启动，且容器内默认 `http_proxy=127.0.0.1:33210` 不可达导致 pip 永远连不上 PyPI → uvicorn 绑不上端口 → 后端整挂、用户数据加载不出。规则：自愈必须在**后台 daemon 线程**，且 subprocess env 必须**剥离 `*_proxy`** 走直连（容器内直连 PyPI 可达）。旧镜像无 Pillow，`force-recreate` 会丢，应择机 `docker compose build` 烤进镜像。

## 出网代理韧性（app/http_client.py）
- Docker 注入 `HTTPS_PROXY=host.docker.internal:33210`，可能不可达；`ensure_proxy_strategy()` 探测不可达则走直连；`request/download_with_fallback()` 每次带直连兜底。设 `DISABLE_PROXY_AUTOFALLBACK=1` 可保留强制代理。图片生成超时 300s / 视频提交 120s / 轮询 60s / 下载 120s。

## 用户协作偏好（重要）
- **不凭空臆想需求**：反对自作主张加「兜底/共享/自动降级」等跨用户逻辑；需求不清先问。
- **数据隔离硬约束**：每用户只能用自己配置的资源，绝不借用他人。
- 改后端后提醒用户**重启 FastAPI + 刷新浏览器(Ctrl+F5)**；Docker 栈改后端 `docker restart ai-agent-api`（bind mount 免 rebuild）。

## 电商套图 · 提示词引擎
- 架构：数据驱动 `Resolver → CopyPolicy → Assembler → Linter`，单一事实源 `gallery_config.py` + `gallery_prompt.py`(模板兜底)。
- **双语生成(V13)**: `build_prompt_bilingual()` 返回 `{prompt: 中文展示版, prompt_en: 英文生成版}`；**生成时以 `prompt_en` 送图像模型**。
- **angle 语义硬约束**: `产品多角度`= 一张图内多视角(`multi-angle collage`)，绝不可拆多图；`run_gallery_task` 统一按 `count`(默认1) 生成单图。
- **英文版零中文(硬约束)**: 任何新选项值/类型标题/平台名进入英文路径必须在 `OPTIONS_EN` 或 `*_EN` 词典有映射；唯一允许中文是用户自己写的 `selling_points`。改后跑 `tests/audit_bilingual.py` + `tests/test_gallery_prompt.py`。
- **自定义子任务**: `custom=True` 类型原样透传用户文本，不走 AI、不翻译。
- **补充说明(note)**: `build_user_config_text` 已读 `item.note` 注入 AI 输入（含溯源 `prompt_input`）；模板 `_assemble` 中文也注入，spec 类型除外（交由叠加层）。

## 电商套图 · Agnes 多模态 AI 生成（主路径）
- 引擎 `app/gallery_prompt_ai.py`：`generate_prompt_via_ai` / `ai_write_selling_points` / `ai_write_type_config`。降级 → 模板引擎，`prompt_source=template`。
- **🔥 agnes-2.0-flash 是带思维链推理模型**: `max_tokens` 太小思考占满 → `content` 空 → 误判降级。**规则**: `AI_PROMPT_MAX_TOKENS` 默认 ≥4096；`generate_prompt_via_ai` 对空/解析失败重试并上调到 6144/8192。绝不可写死小值。
- **溯源留痕**: 返回并落库 `prompt_input`(喂给模型的配置意图) / `prompt_raw`(模型原始 JSON)；前端 PromptBadge「提示词溯源」展示（前端需 build 才可见）。

## 电商套图 · 规格参数图中文乱码修复 = 方案 A（纯视觉图 + 后端文字叠加）
- **根因**: 扩散模型对汉字字形渲染极弱，让模型在画面写尺码表/标注必乱码。
- **方案**: 图像模型只生成干净无文字视觉（产品居左 60%、右侧预留浅灰空白面板、可含极简测量引导线/人体剪影）；所有中文(尺码表/标注/补充说明)由 `app/spec_overlay.py` 用真实 CJK 字体叠加。
- `app/spec_overlay.py`: `resolve_spec_font()`(优先捆绑 `app/assets/fonts/simhei.ttf`，系统回退 NotoSansCJK，最终 PIL 默认) / `parse_spec_data(text)`(按 `；/\n` 分行识别尺码+数值) / `overlay_spec(result_path, spec_text, note, title, category)`(合成左产品+右面板表+左尺寸图例，存新 png) / `overlay_spec_image`(内存版供测试)。
- **约束联动**: spec 类型 `_decide_copy_policy` → `allow_text=False`；`_PROMPT_SYSTEM` 第6条与模板 `_assemble`/`_assemble_en` 的 spec 段均改为无文字视觉；`_strip_cjk` 已**去掉 spec 例外**(prompt_en 必须纯英文)；`note` 对 spec 不进图像提示词(改由叠加层渲染)。
- **挂载点**: `gallery_service.run_gallery_task` 中 spec 且 `real` 有 filename 时调用 `overlay_spec` 并更新 `result_filename/result_url`。
- **字体前提**: 容器原本零 CJK 字体，必须捆绑；simhei 为 Windows 专有，生产建议换 OFL 的 Noto Sans SC（代码已优先尝试 NotoSansCJK 路径，装了即自动切换）。

## 电商套图 · 图片尺寸/参考图一致性
- 生成尺寸按 `output_settings.ratio` 映射(`_ratio_to_size`，短边1024、长边64整数倍)；`has_reference` 必须含 `effective_product_image`，否则生成图与产品无关。

## 通用
- 生成文件归入 `ai/agent-output/`：`overviews/`(总结) `verify-shots/`(截图) `logs/`(日志)。
- 不可移动：`agent.db`/`.env`/运行时SQLite；项目文档(PRD/FDD/README/AGENTS/TASKS)；`designs/`、`疑问/`。
