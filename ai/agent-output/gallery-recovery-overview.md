# 创作结果不显示 — 根因定位与修复总结

## 一句话结论
之前两轮修复都改在了**本地 SQLite（agent.db）**，但线上跑的是 **Docker MySQL（ai_agent）**——两套独立数据。真正的根因是 gallery 记录被**外键级联删除**整批清空了，我已在 MySQL 里把孤儿图片重新关联回原任务，现在「创作结果」全部恢复。

## 根因
`gallery_records.plan_item_id` 原外键是 `ON DELETE CASCADE`。某次策划项（plan_items）被重建/删除时，其下所有 `GalleryRecord` 被连带删除，只留 161 个 PNG 在磁盘、仅 18 个被引用 → **143 个孤儿图**（即用户历史生成图，图还在，记录没了）。task 1–29 全部中招，task 30 因生成时机靠后才幸免。

## 已做的修复（均落在 MySQL / 容器内）
1. **外键改 SET NULL**：`GalleryRecord.plan_item_id` 改为 `ON DELETE SET NULL`（plan_items 没了记录保留，图不再丢）；并加 `ix_gallery_records_task_id` 索引。未来重建策划不再误删记录。
2. **孤儿图恢复（直接解决“看不到图”）**：按生成时间窗口把孤儿 PNG 重新关联回原 task（仅 project=1/user=2，每个 task capped at `total`，不超额；早于任何 task 的 seed 批与重复图自然落选；已完整的 task 30 跳过）。结果：**task 1–29 共插入 81 条** `GalleryRecord`（status=completed，result_url=`/api/gallery/files/results/<uuid>.png`），0 文件缺失。
3. **顺手修了一个路由 bug**：`GET/PATCH /tasks/{task_id: int}` 的转换器带空格（Starlette 要求无空格 `{task_id:int}`），导致详情接口 404、任务重命名失效。已改为 `{task_id:int}` 并 `force-recreate api` 生效。

## 端到端验证（用真实 API 实测）
- `GET /api/gallery/tasks`（前端创作结果页实际消费的数据）返回 25 个任务，**task 26→5、27→5、28→4、29→5、…、task 1→1 张图全部回来了**（task 15 为空是因它本就是失败任务 done=0/4，从未生成图）。
- `GET /api/gallery/files/results/<uuid>.png` 返回完整 1.2MB PNG（content-length 正确）。
- `GET /tasks/26` 详情 → 200（修复前 404）；SSE `/tasks/stream` → 200。

## 你需要做的
浏览器打开 `http://localhost/` ，**强制刷新（Ctrl+F5）** 清缓存，进入「创作结果」即可看到历史生成图。提示词/重作按钮的 UI 优化（分段操作条 + 加载失败降级卡）也已在 dist 中。

## 回滚手段（如需）
`DELETE FROM gallery_records WHERE task_id BETWEEN 1 AND 29 AND status='completed';`（这些 task 恢复前本就是 0 条，删了即回到恢复前，不影响 task 30）。
