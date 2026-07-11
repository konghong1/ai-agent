# 电商套图 · 每张图查看提示词（可配置开关）

## 需求
1. 在生成的**每张图片**上新增「查看当前图片提示词」的功能。
2. 该功能做成**可配置项**：上线后默认**不需要（关闭）**，本地可临时开启验证。

## 现状（数据链路早已具备）
- `GalleryRecord.prompt` 字段（app/models.py）早已存在。
- `run_gallery_task`（gallery_service.py:862 计算、:898 写入）每张图生成时就把 `_build_prompt()` 的结果存进该字段。
- `GalleryRecordRead.prompt`（schemas.py）已暴露给前端。
- 真正缺的只是：**前端 UI 入口** + **可配置开关**。

## 改动清单

### 后端（可配置开关）
- `app/gallery_config.py`
  - `import os`
  - 新增 `GALLERY_FEATURES = {"show_prompt": os.getenv("GALLERY_PROMPT_VIEW", "0") == "1"}`（默认关闭）
- `app/schemas.py`
  - `GalleryTypesResponse` 新增 `features: dict = Field(default_factory=dict)`
- `app/gallery_routes.py`
  - `get_types` 返回 `features=GALLERY_FEATURES`

### 前端（查看提示词 UI）
- `web/src/services/gallery.ts`
  - `getTypes()` 返回类型加 `features?: { show_prompt?: boolean }`（`GalleryRecord.prompt` 已存在）
- `web/src/pages/EcommerceGallery/index.tsx`
  - 新增 `features` state，`loadAll()` 中 `setFeatures(t.features ?? {})`
  - 新增 `PromptBadge` 组件：💡 提示词按钮 → 弹 Modal 展示该图 prompt，支持一键复制
  - 在「创作结果任务卡片图片网格」与「作品详情弹窗」每张图下方渲染：
    `{features.show_prompt && rec.prompt && <PromptBadge prompt={rec.prompt} />}`
  - 创作案例详情无 prompt 字段，不加入口
- `web/src/pages/EcommerceGallery/gallery.css`
  - `.prompt-badge` / `.prompt-text` 样式
  - `.task-cell` 有 `overflow:hidden` 会裁掉普通流 badge，故 `.task-cell .prompt-badge` 用 `position:absolute` 浮于图片左下角

## 验证结果
| 项 | 结果 |
|---|---|
| 后端 py_compile | ✅ OK |
| 开关逻辑 sanity（默认 False / `GALLERY_PROMPT_VIEW=1` → True / schema 含 features） | ✅ OK |
| 前端 tsc --noEmit | ✅ OK |
| 前端 vite build | ✅ OK（4289 模块） |

## 开关用法（重要）
- **本地验证开启**：设环境变量 `GALLERY_PROMPT_VIEW=1`
  - Docker：`docker-compose.yml` 的 `api` / `worker` 服务 `environment` 各加一行 `GALLERY_PROMPT_VIEW=1`
  - 本地裸跑：`set GALLERY_PROMPT_VIEW=1 && uvicorn app.server:app ...`
- **上线默认关闭**：不设该变量或设为 `0` 即可（符合「上线后不需要」的要求）

## 生效方式
改了后端 + 前端，**重启 FastAPI 服务并刷新浏览器（Ctrl+F5）** 即可；新生成（或已生成且含 prompt 字段）的图会出现「💡 提示词」入口。

## 关于「多出图计划是否每张独立提示词」
当前实现：同一出图条目（plan_item）内的多张图**共用同一条提示词**（模型采样随机性产生差异）；不同条目之间提示词才不同。即「按条目独立、按张不独立」。
