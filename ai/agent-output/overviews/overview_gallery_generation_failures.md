# 电商套图「很多图片生成失败」诊断与修复

> 用户质疑：很多图片生成失败，是否「批量提示词 + short 出图」重构引入？重构之前不会？
> 结论先行：**失败主因是 spec 类型缺 PIL（镜像依赖未 rebuild）+ 部分 prompt 触发模型内容拒绝，均与 short 重构无直接因果**；但我的 short 重构功能未生效（模型没返回 short 字段），且上一轮验证只用了假数据、没验真实模型返回与端到端出图——这是我该认的疏漏。

## 1. 真实失败根因（查 DB + 容器日志，非猜测）

总记录：`completed 21 / failed 17`（失败率 ~45%，确实高）。失败分两类：

| 类型 | 真实错误 | 根因 |
|------|----------|------|
| spec（规格参数图） | `No module named 'PIL'`（rec=119） | 生成后叠加 `overlay_spec` 需 Pillow，但运行容器基于**加 Pillow 到 requirements 之前构建的旧镜像**跑的，之后只 `restart` 未 `rebuild`，依赖没更新 |
| 非 spec 个别 | `Unable to generate this content. Please modify your prompt...` | 图像模型对部分 prompt 触发内容拒绝（如 prompt 含疑似品牌仿冒描述 `small dark interlock` 双C徽标） |

补充 bug：`gallery_records` 表**没有 `error` 列**，但代码在写 `rec.error`——失败原因根本写不进 DB，每次排查都得翻日志。

## 2. 与「重构」的关系（诚实）

- **失败主因与 short 重构无直接因果**：
  - short 重构只改了「提示词组装方式」（去逐方向重复指令 + 结尾综合指令）和「出图优先用 `prompt_en_short`」；但当时 `prompt_en_short` **全空**（见下），出图回退完整 `prompt_en`，**实际送图像模型的 prompt 内容同重构前**。
  - 真实失败日志时间 `13:57` **早于**我的 short 重构部署（`21:xx`）。
- **但我的 short 重构确实有 bug，且上一轮验证不充分**：
  - 查 `gallery_records.prompt_raw`（真实模型返回）证实：模型只回了 `item_index/prompt_cn/prompt_en`，**根本没有 `prompt_cn_short`/`prompt_en_short` 字段**——「最简短场景提示词」功能没生效。
  - 我上一轮 `tests/verify_batch_short_prompt.py` 只用了**假 JSON**（手工构造含 short 字段）断言解析，没验证真实模型返回格式，也没验证端到端出图成功率。这是我的疏漏，认。

## 3. 已修复（实弹，非嘴硬）

1. **PIL 热装**到 `ai-agent-api` + `ai-agent-worker` 运行容器（Pillow 12.3.0）。验证：`import PIL` 成功；`overlay_spec()` 成功返回输出路径，不再 `ImportError` → spec 类型硬伤解除。
2. **short 字段后端兜底**：模型不返回 short 时，从完整版按逗号切分提炼前 N 个短语，保证 `prompt_en_short` 非空，**出图降本逻辑真正生效**。同时强化系统提示把 short 标为「必填」。
3. **error 列补进启动迁移**（`sync_model_columns`）：失败原因现可落库直接查，不再靠翻日志。

## 4. 验证证据

- `docker exec ai-agent-api python tests/verify_batch_short_prompt.py` → 3 用例 PASS（含「模型省略 short 字段时后端兜底提炼生效」）。
- `docker logs ai-agent-api | grep "Added error column"` → 迁移已执行。
- `SELECT id,status,error FROM gallery_records WHERE status='failed'` → error 列可查（历史失败为 NULL，因失败发生在加列前；今后新失败会落因）。

## 5. 待办 / 建议（未改，独立项）

- **镜像持久化**：当前运行容器已热修 Pillow；`requirements.txt` 已含 `Pillow>=10.0.0`，下次 `docker compose build` 会自动带上，无需额外动作。若团队习惯只 `restart` 不 `rebuild`，请记住这次是手动热装。
- **模型拒绝类失败**：建议优化 prompt 去掉明显品牌仿冒描述（如双C徽标），降低内容策略拒绝率。独立优化，本次未动。
- **状态轮询改 SSE/WebSocket 推送**：用户此前提过，独立待办。
