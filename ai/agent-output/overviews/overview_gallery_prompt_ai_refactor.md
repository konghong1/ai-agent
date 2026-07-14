# 电商套图 · 提示词工程重构：模板拼装 → Agnes 多模态 AI 生成

## 问题
旧引擎 `gallery_prompt.py`（Resolver→CopyPolicy→Assembler→Linter，86 项配置硬编码拼装）产出的提示词与用户配置**强耦合、弱产品感知**：选同样的配置项 → 输出几乎相同的提示词 → 出图千篇一律，无法适配任意产品图。

## 新思路（已与用户对齐）
把「**用户配置 + 核心卖点 + 参考图**」交给 **Agnes 2.0 Flash 多模态大模型**（图片理解能力），由 AI 看懂产品外观并写出差异化、贴合产品的提示词。我们只把用户配置与输入作为 AI 的上下文，**不再自己拼接提示词**。

降级策略：**AI 为主 + 模板兜底**（Agnes 不可达/超时/解析异常时降级旧引擎，保证系统不挂）。参考图以 **base64 内联**传入。

## 改动清单

### 后端
- **新增 `app/gallery_prompt_ai.py`（核心引擎）**
  - `generate_prompt_via_ai(project, item, ...)`：多模态调用 Agnes → 解析 JSON `{prompt_cn, prompt_en}`，英文版 `_strip_cjk` 清中文；失败降级模板引擎。返回 `{prompt, prompt_en, prompt_source}`。
  - `ai_write_selling_points(...)`：据产品图输出结构化卖点（产品名称/核心卖点/适用人群/期望场景/具体参数）。
  - `ai_write_type_config(...)`：据产品图 + 已选类型，帮判断该类型各配置项怎么选更优。
  - `build_user_config_text(...)`：仅把用户配置整理成自然语言意图描述（非提示词拼装）。
  - 复用 `app/settings` 的 `OPENAI_BASE_URL/OPENAI_MODEL/OPENAI_API_KEY`，`httpx.AsyncClient(proxy=None)` 直连，`timeout=90/75s`。
- **`app/gallery_service.py`**：`_build_prompt` → 调 `generate_prompt_via_ai`（带 `ratio`）；`run_gallery_task` 预建 record 写入 `prompt_source`；`ai_fill_suggestion` → 调 `ai_write_type_config`（AI 帮写类型配置）。
- **`app/gallery_routes.py`**：新增 `POST /api/gallery/projects/{id}/ai-write-selling-points`；`/ai-fill` 经 service 已变 AI 帮写。
- **`app/models.py`**：`GalleryRecord` 加 `prompt_source VARCHAR(16)`。
- **`app/core/database.py`**：`_migrate_sqlite_columns` 加对应 ALTER（SQLite/MySQL 兼容）。
- **`app/schemas.py`**：`GalleryRecordRead` 加 `prompt_source: str = "template"`。

### 前端
- **`web/src/services/gallery.ts`**：加 `aiWriteSellingPoints()` 与 `AiSellingPoints` 类型；`GalleryRecord` 加 `prompt_source?`。
- **`web/src/pages/EcommerceGallery/index.tsx`**：核心卖点「AI 帮写」按钮改为真实调用并回填文本框；`PromptBadge` 加 `promptSource` 属性与「AI」徽标；两处调用点传 `promptSource`。
- **`web/src/pages/EcommerceGallery/gallery.css`**：新增 `.prompt-badge-ai` 徽标样式。

## 验证结果
- ✅ **后端单测** `tests/test_gallery_prompt_ai.py`：**7/7 PASS**（AI 正常解析 / 坏 JSON 降级 / 异常降级 / 卖点结构 / 配置结构 / 英文零中文 / JSON 提取）。
- ✅ **真实 Agnes 多模态**：直接调用成功返回合法 JSON（图片理解正常）；整链在 Agnes 偶发 503（服务端瞬时过载）时正确降级模板、**不崩溃**。
- ✅ **前端** `tsc --noEmit` 零错误；`vite build` 4289 模块成功。
- ✅ **接线烟雾测试**：路由含 `/ai-write-selling-points` + `/ai-fill`；`_build_prompt` 已含 `generate_prompt_via_ai`。

## 生效步骤
1. 重启 `ai-agent-api` + `ai-agent-worker`。
2. 前端刷新（Ctrl+F5）。
3. Agnes 偶发 503 时提示词走模板兜底属预期降级，服务器恢复后自动转 AI。

## 备注
- 「AI 帮写」两类已落地：①卖点帮写（新产品图理解）②类型配置帮写（属性设置弹窗「AI帮填」）。
- 市场配置区的「AI 推荐」按钮仍为占位提示，未接入（非本次「提示词内容」诉求范围，可后续扩展）。
