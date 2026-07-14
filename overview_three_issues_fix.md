# 电商套图 · 三处严重问题修复总结

> 修复时间：2026-07-14 ｜ 范围：AI 提示词生成慢 / 生成结果变占位图 / 规格参数图留白+note 上图

## 问题一：AI 生成提示词运行得很慢

### 根因（重新定位）
你的日志关键证据：两次提示词调用是**各自独立的单条调用**（cn=351、cn=567，不是一次批量）、且**相隔 ~32 秒**，中间后端没有任何 AI 活动（前端每 1.5s 轮询很轻量，不是瓶颈）。

- 默认 `AI_PROMPT_BATCH_MODE=1`（单次批量调用）**实际退化成「逐条调用」兜底路径**；
- 两条连续调用被 AI 提供商限流（约 30s 冷却）串行卡住 → 这就是体感「慢」的来源；
- 墙钟大头其实是**出图阶段**：原 `run_gallery_task` 逐张串行生成（每张 `generate_image` 超时上限 300s）。
- **结论：与批量 A/B 切换无关。**

### 改动
- `app/gallery_service.py`
  - `_build_prompts_for_plan`：兜底逐条 `_build_prompt` → 改用 `ThreadPoolExecutor(max_workers=4)` **并发**生成。
  - `run_gallery_task` 阶段 2：逐张串行出图 → **线程池并发**（每线程独立 `SessionLocal()`；预取可序列化字段，避免跨线程访问主会话对象）；`max_workers = min(4, len(plan))`。

## 问题二：生成后展示默认占位图（没出图）

### 根因
`_real_generate` 在两处**静默**返回 `None`：
1. 解析不到图片模型/提供商（`gallery_service.py:916-917`）——**无任何日志**；
2. 模型返回空 / 异常（`gallery_service.py:955-971`）。
上层据此写离线占位 SVG，你只看到占位图、不知为何失败。

### 改动
- `_real_generate` 改为返回 `{"error": 可读原因}`（不再返回 `None`）；两处静默分支补原因日志；
- 新增自动兜底：
  - `prompt_en` 超 1500 字符自动截断（避免部分模型拒绝）；
  - 带参考图失败 → 自动**去掉参考图重试一次**（参考图格式/大小/不被支持是常见原因）。
- `run_gallery_task._generate_one`：成功判据改 `real and real.get("url")`；失败则 `rec.status="failed"` + `rec.error=原因`，**不再给占位图**。
- 前端：
  - `web/src/services/gallery.ts`：`GalleryRecord` 接口加 `error?: string | null`；
  - `web/src/pages/EcommerceGallery/index.tsx`：失败 cell 显示 `rec.error`；
  - `web/src/pages/EcommerceGallery/gallery.css`：新增 `.cell-failed-err` 样式。

### 待你确认
重跑一次真实生成，看界面/日志报错原因（**未配置图片模型** 还是 **参考图/超时**），以确认是否需再加「模型可用性自检」。

## 问题三：规格参数图只留白，note 还被画在图上

### 根因（重新定位）
- 原 spec 系统提示词**明令禁止画测量引导线** → AI 只产出「干净无文字」产品图，整体显空；
- `spec_overlay.py` 又把「补充说明 **note**」**直接渲染成图上文字**——这正是你反对的。

需求澄清：**note 只进 AI 提示词指导构图、绝不画在图上**；画面应画出产品特性/尺寸标注（对齐你的参考图：衣长/胸围/袖长箭头 + 尺码表 + 比例剪影），不要留白。

### 改动
- `app/gallery_prompt_ai.py`
  - `_PROMPT_SYSTEM` 六、+ `build_user_config_text` spec 段 + 批量提示词系统提示词/per-item：从「禁止测量线」改为「**允许淡淡测量引导线/指示点（无文字），右侧留浅灰面板，可含人体剪影；严禁文字/数字/表格**」；
  - note 仍经 `build_user_config_text`（261-264）/ 批量（588-590）注入 prompt 指导构图。
- `app/spec_overlay.py`
  - 删除 `overlay_spec` / `overlay_spec_image` 中**渲染 note** 的代码块；
  - `_draw_measurement_lines`：标注线加粗（`width 2→3`、`head 10→12`）、改靛蓝更显眼；
  - 新增 `_draw_scale_silhouette()`：右侧面板底部画淡灰人体/比例剪影 + 「比例参考」标注（非用户文字）。

## 验证状态
- ✅ 后端 `py_compile`：`gallery_service.py` / `spec_overlay.py` / `gallery_prompt_ai.py` 全通过；
- ✅ 前端 `npm run build` 成功（修了 `GalleryRecord` 缺 `error` 字段的 TS 报错）；
- ⚠️ `spec_overlay` 运行时渲染测试因本地无 PIL/全量依赖栈未能跑，需在 **Docker / 应用 venv** 实测；
- ⏳ 问题二的真实根因需你提供一次真实生成的报错（界面提示或 `docker logs ai-agent-api`）。

## 部署提醒
- 后端改动需重启 api（`docker restart ai-agent-api`；bind mount 免 rebuild）；
- 前端仍需 `cd web && npm install && npm run build` 才能看到「失败原因展示」与规格图改动；
- 浏览器侧务必 **Ctrl+F5** 强刷。
