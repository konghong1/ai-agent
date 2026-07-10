# 自定义子任务模型与图片比例选项改造

## 改动摘要

1. **图片比例选项统一调整**  
   后端 `app/gallery_config.py` 中的 `OUTPUT_OPTIONS.ratio` 与 `OUTPUT_OPTIONS.promo_ratio` 已统一改为截图中的 8 项：
   - 自适应尺寸
   - 方图 1:1
   - 竖图 3:4
   - 竖图 4:5
   - 竖图 9:16
   - 竖图 2:3
   - 横图 16:9
   - 横图 4:3

   由于前端所有「图片比例」下拉框均读取 `options.output.ratio`（全局设置、自定义子任务、属性弹窗回显等），修改后端配置后所有相关入口会自动生效。

2. **自定义子任务模型改为 AI 提供商图片模型**  
   - `web/src/pages/EcommerceGallery/PlannerDrawer.tsx`：新增 `imageModels` 属性，模型下拉框从静态 `OUTPUT_OPTIONS.model` 改为动态读取 `/api/gallery/image-models`，与右侧属性设置弹窗（TypeSettingsModal）保持同一数据结构与交互规则（`__default__` + `providerId::modelName`）。
   - `web/src/pages/EcommerceGallery/index.tsx`：向 `PlannerDrawer` 传入 `imageModels`；`createCustomTask` 回调中把 `provider_id` / `model_name` / `model_label` 写入策划项的 `output_settings`，与 Service 层的真实出图逻辑对齐。

3. **属性弹窗默认值同步**  
   `TypeSettingsModal.tsx` 中 `hasResolution` 类型的默认 ratio 从旧值「自动」改为新选项首项「自适应尺寸」，避免保存已不存在的默认值。

## 质量验证

- `npm run build` 通过（tsc + vite build），无 TS/CSS 错误。
- 后端 `app/gallery_config.py` 为纯数据配置，无需编译，重启 API 即可生效。
- 生成链路 `gallery_service.py` 已原生支持 `output_settings.provider_id` / `model_name`，前端改造后可直接命中真实出图模型。

## 团队建议

- 当前图片比例仅作为配置项保存，真实生成时 `_real_generate` 仍写死 `size="1024x1024"`。后续如需按所选比例输出，可在 `_real_generate` 或 `MediaService.generate_image` 中根据 `ratio` 解析分辨率。
- 设计稿目录 `designs/` 中仍有旧比例选项的静态 HTML，仅作历史参考，不影响线上；如需保持一致，可统一刷新设计稿。
