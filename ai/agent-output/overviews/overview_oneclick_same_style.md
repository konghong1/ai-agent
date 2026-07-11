# 电商套图 · 一键做同款 + 单独商品图 实现与验证

## 一、需求回顾
1. **一键做同款**：在「作品详情」弹窗内点「🎨 一键做同款」，把生成这些图的完整配置（个性化/通用设置、出图设置、备注、参考图、单独商品图）直接回填到左侧规划列表，省去重复配置。
2. **产品图必传**：生成时必须先上传产品图；按配置写出提示词，再调用所选（或默认）图片模型出图。
3. **出图规划子项可单独传图**：在策划项「设置」里可为该类型单独上传一张商品主图；不传则生成时回退使用项目产品图（产品图[0]）。

## 二、分步实现流程

### A. 数据层（后端模型）
- `app/models.py` · `GalleryPlanItem` 新增字段
  `product_image: Mapped[Optional[str]] = mapped_column(String(512), default="")`
  （单独商品图落盘文件名；空字符串表示回退到项目产品图）。
- `app/core/database.py` · `sync_model_columns()` 在启动时自动把缺失列 `ALTER` 到旧库（已验证对 SQLite 历史库生效）。
- `app/schemas.py` · `GalleryPlanItemRead/Create/Update`、`GalleryRecordRead.plan_item_snapshot` 增加 `product_image`。

### B. 服务层（后端逻辑）
- `app/gallery_service.py`
  - 新增 `save_plan_item_image(project_id, data, name)`：**不写入** `GalleryProjectImage` 表，仅落盘到 `projects/{pid}/items/`，返回 `{filename, url}`，避免污染项目产品图列表。
  - `add_plan_item` / `apply_template_to_project` 透传 `product_image`。
  - `generate()` 核心改造：
    ```
    effective = item.product_image or (proj.images[0].filename if proj.images else None)
    ref_files = [effective] + [f for f in item.reference_images if f != effective]
    ```
    单独商品图作为 img2img **主参考**排首位，其余参考图追加；并把 `product_image` 写入 `plan_item_snapshot`。
  - 产品图必传：`if not proj.images: raise ValueError("请先上传至少一张产品原图")`（已有，保留）。

### C. 接口层（后端路由）
- `app/gallery_routes.py` 新增
  `POST /api/gallery/projects/{project_id}/plan-items/upload-image`
  接收单文件，鉴权后调用 `save_plan_item_image`，返回 `{filename, url}`。

### D. 前端
- `web/src/services/gallery.ts`
  - `GalleryPlanItem` / `createPlanItem` / `updatePlanItem` / `plan_item_snapshot` 增加 `product_image`。
  - 新增 `uploadPlanItemImage(projectId, file)`。
- `web/src/pages/EcommerceGallery/TypeSettingsModal.tsx`
  - 「设置」弹窗右栏新增「单独商品图（选填，不传则使用项目产品图）」区块：本地上传 / 从项目图选择，支持预览与移除。
  - 上传走 `uploadPlanItemImage`（不进项目产品图列表）；`buildPayload()` 把 `product_image` 一并带回。
- `web/src/pages/EcommerceGallery/index.tsx`
  - 「生成同款」按钮（创作结果卡片）改为打开「作品详情」弹窗（展示生成效果图），弹窗内「🎨 一键做同款」把配置回填左侧。
  - `handleSameStyle()`：**有意不回填** `product_image`——它指向源项目落盘文件，在当前项目无法解析；留空可正确回退到本项目产品图。
  - `handleCopyItem()` 复制 `product_image`。

## 三、验证结果（均已通过）
| 验证项 | 方式 | 结果 |
|---|---|---|
| 迁移补列 | `python -m app.db.init_db` + PRAGMA | `gallery_plan_items.product_image` 已存在 |
| 后端类型检查 | `py_compile` 5 个文件 | OK |
| 前端类型检查 | `tsc --noEmit` | OK（0 错误） |
| 产品图必传 | service 层 + HTTP `POST /generate` | 无图 → `ValueError` / HTTP 400「请先上传至少一张产品原图」 |
| 单独商品图存储 | service + HTTP `POST plan-items` | `product_image` 正确持久化 |
| 回退逻辑 | monkeypatch `_real_generate` 抓取 `ref_files` | 有图用自身图、无图回退 `images[0]` |
| 提示词由配置生成 | 抓取 `prompt` | 含「为电商商品生成【…】」等配置内容 |
| 快照记录 | `plan_item_snapshot` | 含 `product_image` |
| 新上传接口 | TestClient `POST .../upload-image` | 200，返回 `projects/{pid}/items/...` |

## 四、使用流程（给用户）
1. 进入电商套图，先在左侧上传**至少一张产品图**（必传）。
2. 在「AI 智能策划台」选类型 → 逐条「设置」：可填个性化/通用/出图设置/参考图，并**按需上传该类型的单独商品图**（不传则用项目产品图）。
3. 点「立即生成」→ 按配置写出提示词并调用模型出图。
4. 在「创作结果」卡片点「生成同款」→ 弹出「作品详情」展示效果图 → 点「🎨 一键做同款」把整套配置回填左侧，上传自己的产品图后即可一键再生成。
