# 修复记录：图片比例与参考图一致性

## 修复内容

### 1. 不同比例设置但生成图尺寸一样

**根因**：`app/gallery_service.py` 的 `_real_generate` 在调用真实图片模型时把 `size` 硬编码为 `"1024x1024"`，导致无论用户选择什么比例都出正方形图。

**改动**：
- 新增 `_ratio_to_size()` 映射函数，把前端 `output_settings.ratio` 映射为对应像素尺寸：
  - 方图 1:1 → 1024x1024
  - 竖图 3:4 → 768x1024
  - 竖图 4:5 → 832x1024
  - 竖图 9:16 → 576x1024
  - 竖图 2:3 → 704x1024
  - 横图 16:9 → 1024x576
  - 横图 4:3 → 1024x768
  - 自适应尺寸/未知 → 1024x1024
- `run_gallery_task` 读取每个 plan_item 的 `output_settings.ratio`，生成对应尺寸，并把 `size` 透传给 `_real_generate` 与 `MediaService.generate_image`。
- 提示词里新增「画面比例：严格按 X:Y 构图，不得改变比例或额外留白」，让模型在文本层面也感知比例要求。

**前端展示**：作品详情弹窗中每个生成图卡片现在按 `plan_item_snapshot.output_settings.ratio` 动态设置 `aspect-ratio`，不再一刀切 3:4。

### 2. 生成图与参考图（产品原图）不相关

**根因**：提示词引擎 `_resolve_config` 的 `has_reference` 仅检查 `item.product_image or item.reference_images`，但运行时当 `item.product_image` 为空会回退到项目产品图 `proj.images[0]`。这导致「参考图已传给模型，但提示词里却没有写主体一致性约束」，模型容易按自己的理解出图，结果与产品无关。

**改动**：
- `_build_prompt` / `build_prompt` / `_resolve_config` 增加 `effective_product_image` 参数。
- `run_gallery_task` 在构造完实际参考图列表后，把 `effective_product_image` 传入 `_build_prompt`。
- `_resolve_config` 的 `has_reference` 改为 `bool(item.product_image or item.reference_images or effective_product_image)`，确保回退到项目产品图时也能触发最强主体一致性 + 颜色锁定锚定块。

## 验证

- `python -m py_compile app/gallery_prompt.py app/gallery_service.py` 通过。
- `tsc --noEmit` 通过，无类型错误。
- `vite build` 成功（4289 模块）。
- 新增 `tests/test_gallery_ratio_prompt.py`：
  - 验证 `_ratio_to_size` 全部 8 种比例映射正确。
  - 验证 `effective_product_image` 为空时 `has_reference` 为 False；仅项目产品图回退时 `has_reference` 为 True。
  - 验证 `output_settings.ratio` 被正确读入配置。
- 在 Docker 容器内执行测试全部通过。
- 重启 `ai-agent-api` 与 `ai-agent-worker` 容器，API 登录正常。
- Playwright 静态验证：作品详情弹窗中 1:1、3:4、9:16、16:9 等不同比例卡片按各自比例显示，未再统一裁剪。

## 用户操作

前端已重新构建到 `web/dist`，Docker web 容器挂载的就是该目录，直接刷新浏览器即可（Ctrl+F5）。后端 API / worker 已重启，新任务会按设置比例生成并在提示词中强制锁定参考图商品。
