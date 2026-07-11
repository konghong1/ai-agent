# 电商套图模块 · 模型配置接入 AI 提供商（完成 + 验证）

> 资深开发工程师交付记录。基于 `designs/ecommerce-gallery.html` 设计，完成「工作台 › 电商套图」模块的模型配置能力，满足：**模型来源于 AI 提供商的图片生成模型、所有配置都有记录、依据 AI 智能策划台配置生成提示词并出图、高性能高可用、不破坏既有功能**。

## 需求对照

| 用户要求 | 落地方式 |
| --- | --- |
| 模型配置选择「AI 提供商」中的图片生成模型 | 新增 `GET /api/gallery/image-models`，前端下拉框动态加载用户**已启用**的 image 模型（按 provider 分组），替代原先硬编码的 `Banana-pro / Gpt-image-2` 等 |
| 所有配置都需要有记录 | 全局 `output_config` 与条目 `output_settings` 均落库 `provider_id / model_name / model_label`；每条生成结果 `GalleryRecord` 新增 `provider_id / provider_name / model_name` 三字段，提示词中也写入「使用模型：xxx」 |
| 根据 AI 智能策划台配置生成提示词 | `generate()` 按「条目级 > 全局级」解析模型，逐条用 `_build_prompt()` 拼装（卖点 / 个性化 / 市场 / 风格 / 补充说明 / 模型），驱动真实出图或离线降级 |
| 生成图片展示 | 真实出图走 `MediaService.generate_image`（所选 provider+model）；未配置/失败则降级为离线 SVG 占位图，**全流程永不中断（高可用）** |
| 高性能 / 高可用 | 复用既有 `post_with_retry` 代理韧性层；降级路径保证端到端可用；新增列用 inspector 安全 ALTER（兼容 SQLite/MySQL），不影响已有库与现有功能 |

## 改动文件

**后端**
- `app/gallery_service.py` — 新增 `list_image_models`、`_resolve_image_model`；重写 `_real_generate`（使用所选模型并回传元数据）；`generate()` 解析并落库模型；`_build_prompt` 记录模型名
- `app/gallery_routes.py` — 新增 `GET /api/gallery/image-models`；`_rec_to_dict` 补 model 字段
- `app/models.py` — `GalleryRecord` 新增 `provider_id / provider_name / model_name`
- `app/schemas.py` — `GalleryRecordRead` 补三字段
- `app/db/__init__.py` — 新增 `ensure_gallery_record_columns()`，在 `main()` 中调用（解决 `create_all` 不会给已有表补列的问题）

**前端（React 版）**
- `web/src/services/gallery.ts` — 新增 `getImageModels()` 及类型
- `web/src/pages/EcommerceGallery/index.tsx` — 全局「模型」下拉改为动态 provider 图片模型；落库 `output_config`；创作记录显示模型名
- `web/src/pages/EcommerceGallery/TypeSettingsModal.tsx` — 条目级模型选择改为动态来源，默认继承全局
- `web/src/styles/gallery-design-system.css` — 新增 `.rec-model` 样式

## 验证结果（已实跑）

1. **后端编译**：`py_compile` 全部通过。
2. **数据库迁移**：`python -m app.db.init_db` 成功为 `gallery_records` 补齐 `provider_id / provider_name / model_name` 三列。
3. **端到端 API（uvicorn :8010）**：
   - `GET /api/gallery/types` → 18 种策划类型正常
   - `GET /api/gallery/image-models` → 返回用户图片模型（当前库未配置则 `providers:[]`，符合预期）
   - 草稿创建 / 产品图上传 / 策划项创建 / 生成 / 记录查询 全链路 200/201
   - **关键断言「所选模型被记录」**：将 `output_config.provider_id+model_name` 指向一个图片模型后 `generate`，生成记录的 `provider_id=4, model_name=test-image-model` 正确落库；未选模型时走 SVG 降级且 `model_name=None`，无任何报错。
4. **前端**：`tsc --noEmit` 零错误；`vite build` 成功（4287 modules，产出 `dist/`）。

## 使用说明

- 真实出图需在「AI 提供商」中添加**图片类型（model_type=image）**的模型并启用；选中后在电商套图「全局输出配置·模型」或单个类型的「属性设置·模型」里即可选用。
- 未配置可用图片模型时，生成会输出离线示例图（提示词与所选配置仍被完整记录），保证流程不中断。
- 后端验证服务仍在 `http://127.0.0.1:8010` 运行；前端预览：`cd web && npm run dev`（或 `npm run build && npm run preview`）。

## 备注

- 登录接口使用 `email`（非 username）；本机 `agent.db` 无 admin 账户（与本次改动无关，属既有数据），验证时用 `create_access_token(uid)` 直接签 token 绕过登录。
- 既有的上传 / 策划台 / AI 帮填 / 模板 / 热门示例 / 创作记录等功能**均未改动**，仅做能力增强。
