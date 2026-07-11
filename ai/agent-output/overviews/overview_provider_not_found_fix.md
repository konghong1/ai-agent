# 图片生成「提供商不存在」排查与修复

## 根因
当前登录账号（admin，id=5）名下的「Agnes AI」提供商（provider_id=3）**只配置了聊天模型，没有配置图片生成模型**。

`/api/gallery/image-models` 只返回当前用户自己的图片模型，因此：
- 模型下拉框为空，显示「尚未配置 AI 提供商的图片生成模型」
- 虽然走离线 SVG 也能生成示例图，但无法调用真实 AI 出图

## 修复内容

### 1. 数据修复：为 admin 的 Agnes AI 提供商补齐图片模型
- 在 `provider_models` 中插入两条记录：
  - `agnes-image-2.1-flash`（默认图片模型）
  - `agnes-image-2.0-flash`
- 复用 provider 3 已有的 Agnes base_url 与 api_key

### 2. 代码加固：管理员兜底使用系统级图片模型（`app/gallery_service.py`）
- `list_image_models`：当用户没有自己的图片模型且为管理员时，兜底返回系统中任意已启用的图片模型
- `_resolve_image_model`：
  - 显式选择时，管理员可解析任意已启用图片模型
  - 未选择模型时，先找自己的默认图片模型；管理员无默认模型时兜底系统默认
- 非管理员用户保持原有「仅使用自己的图片模型」行为

## 验证
- `py_compile app/gallery_service.py`：通过
- `tsc --noEmit`：通过
- TestClient `/api/gallery/image-models`（admin）：返回 `Agnes AI · agnes-image-2.1-flash`
- 生成流程验证：未选择模型时，记录 `provider_id=3, model_name=agnes-image-2.1-flash`，配置可正确解析

## 注意事项
- 修改了后端代码，**请重启 FastAPI 服务**后刷新页面生效
- 若之后使用非管理员账号，仍需在「AI 提供商」中为该账号添加图片模型；管理员账号已可正常使用
