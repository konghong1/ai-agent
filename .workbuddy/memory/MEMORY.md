# 项目长期记忆 — AI Agent Platform（精简合并版）

> 维护规则：每次大改后追加到当日 `YYYY-MM-DD.md`；本文件只保留**跨会话仍有用**的硬约束/坑/架构事实，定期去重。

## 技术栈
- 后端: FastAPI + uvicorn (8010) + SQLAlchemy + SQLite(本地)/MySQL(Docker `ai_agent`)
- 前端: Vite + React 19 + TS (dev 5173)；Docker 正确栈 `http://localhost/`(web:80) 连 MySQL
- AI: OpenAI-compatible API，agnes-2.0-flash(推理/出图提示词) / agnes-image-2.x / agnes-video-v2.0
- 向量库 ChromaDB；存储桶 `chat-uploads`(聊天上传) / `ai-agent-minio`(生成产物)

## 关键架构约束（硬坑）
- **列表排序**：会话/任务等列表排序方向必须**按用户需求明确确认**（正序/倒序、新在上/新在下），不能靠猜。聊天会话列表最终按**创建时间正序**(`created_at.asc()`)——最新创建的会话排在最下面（历史会话在上），不要用 `updated_at.desc()` 把新建项挤动（2026-07-16 实踩并修正）。
- **🔥 时间戳必须带时区（输出 `Z`）**：DB `DateTime(timezone=True)`+`func.now()` 存的是朴素 UTC；序列化出不带 `Z` 的字符串时，浏览器 `new Date()` 在 GMT+8 下当本地时间解析→算成 8h 前。规则：Pydantic 用 `field_serializer` 输出 `...Z`；前端解析一律按 UTC（无后缀补 `Z`），**绝不直接 `new Date(naiveUtc)`**；判“卡死/超时”优先用 `updated_at`(最后进度)。
- **🔥 MySQL 迁移 TEXT 列禁带默认值**：`ADD COLUMN x TEXT DEFAULT ''` 在 MySQL8 报 1101 → api 崩溃重启循环。TEXT 列不写 `DEFAULT ''`/`server_default`，允许 NULL，应用层兜底；VARCHAR 可带默认值。改完必在 Docker 验证。
- **端口一致**：.env/代理/启动命令三者均 8010。
- **DB 驱动**：`app/db_url.py: normalize_db_url()` 统一注入；模型用 `app/models.py`(MySQL 兼容)。
- **Pydantic 响应 schema 新增列必须可空** `X | None = None`（ALTER 加的列存量 NULL）。
- **🔥 绝不在 FastAPI startup 事件里做会阻塞/可能失败的网络调用**（pip/外部HTTP）——曾导致后端整挂。自愈放后台 daemon 线程，subprocess env 剥离 `*_proxy` 走直连。
- **🔥 绝把请求作用域的 ORM 实例传入后台线程/异步任务**（电商套图「重做」实踩 2026-07-16）：`get_db` 请求返回后即 `close()`，此时 `User`/`Record` 等对象变 detached/expired；后台线程再读其属性会触发 lazy-load → `DetachedInstanceError` 或 `InvalidRequestError: This session is provisioning a new connection`。正确做法：在**主线程会话还活着时**把后台要用的标量字段（`user.id`/`rec.title`/`rec.type_id`…）先取成普通变量再闭包传入（参考 `gallery_service.py` line 1606 / 1330 写法）。后台线程一律用 `SessionLocal()` 或 `Session(engine)` 新开独立会话，绝不复用请求会话。
- **Docker 前端白屏 = nginx sendfile bug**：`docker/nginx.conf` `server` 块加 `sendfile off;`（Windows bind mount 发 0 字节体）。

## 出网代理韧性（app/http_client.py）
Docker 注入 `HTTPS_PROXY=host.docker.internal:33210`（可能不可达）；`ensure_proxy_strategy()` 探测不可达走直连；`request/download_with_fallback()` 每次直连兜底。设 `DISABLE_PROXY_AUTOFALLBACK=1` 保留强制代理。图片生成超时 300s/视频提交120s/轮询60s/下载120s。

## 用户协作偏好（重要）
- **不凭空臆想需求**：反对自作主张加「兜底/共享/自动降级」等跨用户逻辑；需求不清先问。
- **数据隔离硬约束**：每用户只用自己配置的资源，绝不借用他人。
- **🔴 改动必须测试/回归通过才能回复（用户 2026-07-16 硬性要求）**：改完每个功能及相关代码须跑通测试/回归，不能只靠“构建成功”宣布完成。前端交互改动须用真实浏览器(Playwright 无头)点一遍验证行为确实发生；后端改动须有单元/接口级验证。
- **🔥 前端 UI 修改必须浏览器预览验证后才能回复**：改完 CSS/组件须实际打开页面确认视觉符合预期。
- **🔴 浏览器真机回归工作流（可复用）**：Playwright+chromium 注入 localStorage `agent-auth`=`{state:{token,user,isAuthenticated},version:0}` 免登录进任意页。拿 token：admin 登录 `POST /api/auth/login {"email":"admin@example.com","password":"admin123"}` → admin `POST /api/auth/reset-password?email=<邮箱>&new_password=<新密>` → 该用户登录拿 token。脚本参考 `D:/workspace/ai-agent/playwright_delete_e2e.cjs`；截图放 `verify-shots/`。managed node 装包在 `C:/Users/admin/.workbuddy/binaries/node/workspace`，运行加 `NODE_PATH=.../node_modules`。
- 改后端后提醒用户**重启 FastAPI + 刷新浏览器(Ctrl+F5)**；Docker 栈改后端 `docker restart ai-agent-api`（bind mount 免 rebuild）。

## 前端架构坑（React 19 + antd 兼容）🔥
- **致命坑（2026-07-16 实锤）**：`react@19.2.7` + `antd@5.15.4`（antd v5 为 React18 构建）。**未装 `@ant-design/v5-patch-for-react-19` 时，antd 静态 `message.xxx`/`Modal.confirm` 静默失效**——点击触发、handler 执行，但既不弹框也不报错，表现为“按钮点了没反应”。修复：`npm i @ant-design/v5-patch-for-react-19`，在 `web/src/main.tsx` **第一行** import（须在 import antd 之前）。
- **判定口诀**：前端“某按钮点击后毫无反应、无弹框无 toast、控制台零报错” → 优先怀疑 antd 静态方法在 React19 下失效，而非查业务 onClick。

## 电商套图（合并精简）
- **提示词引擎**：数据驱动 `Resolver→CopyPolicy→Assembler→Linter`，事实源 `gallery_config.py`+`gallery_prompt.py`(模板兜底)。**双语生成** `build_prompt_bilingual()`→`{prompt:中文展示, prompt_en:英文生成}`（生成以 `prompt_en` 送模型）。**英文版零中文**：新选项/类型/平台名须有 `*_EN` 映射，唯一允许中文是用户 `selling_points`。**angle 语义**：`产品多角度`=单图内多视角，绝不拆多图。`custom=True` 原样透传。
- **🔥 agnes-2.0-flash 是带思维链推理模型**：`max_tokens` 太小思考占满→`content` 空→误判降级。规则 `AI_PROMPT_MAX_TOKENS`≥4096，空/失败重试上调 6144/8192，绝写死小值。
- **规格参数图中文乱码 = 方案 A**：扩散模型写汉字必乱码 → 图像模型只出无文字视觉，所有中文(尺码表/标注/补充说明)由 `app/spec_overlay.py` 用真实 CJK 字体(`app/assets/fonts/simhei.ttf`，回退 NotoSansCJK)叠加。约束：`allow_text=False`、模板 spec 段无文字、`note` 不进图像提示词、prompt_en 纯英文。
- **生成图存储 = MinIO(`ai-agent-minio`)**：成图经 `gallery_service._save_to_storage()` 上传 `gallery/results/{uuid}{ext}`；页面走同源 `/api/gallery/files/{key}`(先 MinIO 后本地回退)。
- **🔴 删除任务硬约束**：进行中(pending/running)禁止删 → `delete_task` `raise ValueError`→路由 400。**卡死(running 且 created>30min 孤儿)例外放行**（worker 进程内存队列，`docker restart` 清空变僵尸）。删除用 antd `Modal.confirm`（须 React19 补丁）→ 同步删 MinIO 对象+本地文件+级联 `GalleryRecord`。前端按钮始终可点击，活跃任务点选 `message.warning` 不弹框。
- **🔥 电商套图 gallery worker 必须在 app startup 启动（非仅 enqueue_task 懒启动）**：`gallery_worker.start_worker()` 已加入 `server.py` 的 `startup()`（只启线程+查本地DB，无网络调用，符合 startup 不联网硬约束）。否则 api 重启后若无人创建新任务，worker 线程与孤儿恢复永不行 → 历史 running 任务永久卡死「创作中」。孤儿恢复 `_recover_orphans` 判定已改为 `running AND updated_at < PROCESS_START-120s`（按最后进度时间，活跃任务不被误抢）。
- **🔥 run_gallery_task resume 必须跳过 chat 提示词生成**：孤儿/resume 场景任务已有 record（自带 `prompt_en`），阶段1 的 `_build_prompts_for_plan`（调 agnes chat 接口，`AI_PROMPT_TIMEOUT=120s`）**绝不能**在 resume 时执行——否则上游 chat 不可用时历史任务也卡死 120s。resume 直接用 `rec.prompt_en` 出图（image 接口正常即可）。gallery worker 已改 `ThreadPoolExecutor(max_workers=2)` 并发消费队列，单任务卡顿不冻全局。
- **上游 agnes 不稳定（外部因素，2026-07-16 观察）**：chat 接口(`/chat/completions`, agnes-2.0-flash)偶发不可达/卡（单请求等满 120s 超时）；image 接口(`/v1/images/generations`)间歇 `SSLEOFError` + `queue-full` 503。代码侧已加 chat `max_retries=1` + resume 绕过 + 并发 worker + `media_retry` 重试兜住；个别图仍可能 failed（用户点「重做」用原提示词可绕过 chat 重新出图）。
- **CSS 双文件陷阱**：`.pr-*`/`.plan-row`/`.prompt-badge` 样式只在 `web/src/styles/gallery-design-system.css`（App.tsx 全局导入，真正生效）改；`gallery.css` 不再重复定义。改完 `rm -rf node_modules/.vite dist && npm run build` + `docker restart ai-agent-web` + 无头截图。
- **PlanRow 布局硬约束**：类型名称完整展示不可截断；「自定义」/「极速出图」标签在标题同行右侧、不挤压名称。

## 通用
- 生成文件归入 `ai/agent-output/`：`overviews/`(总结) `verify-shots/`(截图) `logs/`(日志)。
- 不可移动：`agent.db`/`.env`/运行时SQLite；项目文档(PRD/FDD/README/AGENTS/TASKS)；`designs/`、`疑问/`。
