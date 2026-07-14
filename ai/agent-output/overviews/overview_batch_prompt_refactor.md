# 批量提示词重构：去逐方向重复指令 + 综合指令 + 最简短场景提示词

## 问题
`app/gallery_prompt_ai.py` 的 `build_batch_user_config_text` 在循环每个出图方向时，都追加一句：

> `要求：基于该类型和上述配置，写出贴合该方向的差异化提示词。`

但整批提示词是**一次 AI 调用**生成的——逐方向重复这句指令是冗余的「轮询式」重复：
- 浪费输入 token；
- 让模型误以为每个方向都要单独被「要求」一遍，反而稀释了「系列套图统一风格」的整体意图；
- 用户明确希望：既然一起生成，就不要在每一项后面都放，应放在整段提示词末尾作为综合指令。

用户还希望模型额外产出「最简短、且符合场景」的提示词（降本提速），并问有没有「非轮询、性能好」的方式。

## 改动

### 1. 提示词组装（gallery_prompt_ai.py）
- **删除** per-item 的 `要求：…` 重复行。
- 结尾 `【输出要求】` 升级为 **`【综合提示词要求】`**：
  - 明确「不再对每个方向重复笼统指令」；
  - 要求每个方向额外产出 `prompt_cn_short` / `prompt_en_short`（最简短场景提示词，长度≈完整版 1/3，只留主体+场景+关键风格/角度，但仍须让图像模型生成符合该场景的结果）。
- `_PROMPT_BATCH_SYSTEM` 的 JSON 契约新增 `prompt_cn_short` / `prompt_en_short` 字段与说明。
- `generate_prompts_batch_mode_1` 解析时捕获 `prompt_short` / `prompt_en_short` 随结果返回。

### 2. 数据模型与迁移（models.py / core/database.py）
- `GalleryRecord` 新增 `prompt_short` / `prompt_en_short`（`Text`，**可空、不加默认值**，兼容 MySQL 对 TEXT 列禁默认值的约束）。
- 启动迁移：`_migrate_sqlite_columns`（SQLite）与 `sync_model_columns`（MySQL，启动自愈）自动 ALTER 加列。

### 3. 生成链路（gallery_service.py · run_gallery_task）
- 建 `GalleryRecord` 时写入 `prompt_short` / `prompt_en_short`；`plan` / `jobs` 透传 `prompt_en_short`。
- `_generate_one` 实际出图改用：
  ```python
  gen_prompt = job.get("prompt_en_short") or job["prompt_en"]
  ```
  **优先用最简短场景提示词降本提速**；完整版 `prompt_en` 仍保留用于展示与溯源。

## 性能收益（回应用户「非轮询 / 性能好」）
1. **提示词组装**：不再逐方向重复指令 → 输入 token 更少、模型意图更聚焦（这正是「非逐方向轮询」的写法）。
2. **实际出图**：改用 `prompt_en_short`（最简短场景提示词）→ 送给图像模型的 token 更少、出图更快/更省，且仍贴合该场景。

> 状态查询层面：当前前端仍按 `GET /api/gallery/task/{id}` **轮询**任务状态。若需进一步降低延迟，可改 SSE/WebSocket 服务端推送（worker 进度即推），属独立优化，本次未实施。

## 验证
- 新增 `tests/verify_batch_short_prompt.py`：
  - 断言 `build_batch_user_config_text` **不再含**逐方向重复指令、含 `【综合提示词要求】` 与 short 字段；
  - monkeypatch `_run_async` 断言 `generate_prompts_batch_mode_1` 正确解析回传 short 字段。
  - **容器内运行 `RESULT: PASS`**。
- `docker restart ai-agent-api ai-agent-worker`：`sync_model_columns` 日志确认已 ADD `prompt_short` / `prompt_en_short` 到 MySQL；`/health` 返回 200。

## 影响面 / 注意
- 单条路径（`generate_prompt_via_ai` / 模板 `_build_prompt`）不产生 short 字段，走 `or job["prompt_en"]` 兜底，行为不变。
- 前端未改：short 提示词目前仅服务端用于生成 + DB 留痕，未在前端展示（如需展示需 web build）。
