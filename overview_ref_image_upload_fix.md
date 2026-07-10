# 移除推荐类型参考图选择 + 修复自定义子任务上传样式

## 改动摘要

### 1. 推荐类型属性设置弹窗移除参考图片选择
- **文件**：`web/src/pages/EcommerceGallery/TypeSettingsModal.tsx`
- 删除了「参考图片」整块 UI（标题、说明、从已上传产品图中选择、空态提示）。
- 清理了随之不再使用的状态与属性：
  - 移除 `GalleryImage` import
  - 移除 `projectImages` prop
  - 移除 `refs` / `setRefs` 状态
  - 移除 `toggleRef` 函数
  - `handleSave` 不再提交 `reference_images` 字段
- **父组件同步**：`web/src/pages/EcommerceGallery/index.tsx` 中调用 `<TypeSettingsModal />` 时不再传入 `projectImages`。

### 2. 自定义子任务上传区样式对齐
- **文件**：`web/src/pages/EcommerceGallery/gallery.css`
- 将 `.ctf-upload` 的 `align-items: center` 改为 `align-items: stretch`，使「本地上传」与「图片库」两个按钮高度一致。
- 「本地上传」按钮补充 `justify-content: center` 与 `flex-shrink: 0`，避免被压缩或内容偏移。
- 「图片库」按钮改为 `display: inline-flex; align-items: center; justify-content: center; padding: 0 16px`，与上传按钮同高并水平居中。
- 整体尺寸略微收薄（90px → 84px，padding 14px → 12px），与当前扁平化列表风格更协调。

## 3. 修复自定义子任务表单字段 label 与控件重叠
- **文件**：`web/src/pages/EcommerceGallery/gallery.css`、`web/src/pages/EcommerceGallery/PlannerDrawer.tsx`
- 问题：截图中「模型 / 分辨率 / 图片比例 / 出图数量」四宫格字段的 label 与下方 Select/Stepper 紧贴，看起来像重叠。
- 修复：
  - `.ctf-field > label` 的 `margin-bottom` 从 8px 增大到 12px，并加 `line-height: 1.4`，避免长说明文字折行时与控件粘连。
  - `.ctf-grid` 的 gap 从 `12px` 改为 `18px 16px`（行间距 18px，列间距 16px），让上下两行字段更宽松。
  - `.ctf-grid` 内的 `.ant-select` 与 `.ctf-stepper` 统一 `min-height: 38px`，保持四宫格高度一致。
  - `PlannerDrawer.tsx` 中模型、分辨率、图片比例三个 `Select` 均加上 `style={{ width: '100%' }}`，在 grid 单元格内占满宽度。

## 4. 参考图片预览移入上传虚线框内
- **文件**：`web/src/pages/EcommerceGallery/PlannerDrawer.tsx`、`web/src/pages/EcommerceGallery/gallery.css`
- 问题：上传图片后，预览图显示在虚线框下方，而不是框内与上传按钮并排。
- 修复：
  - 将 `previews.map(...)` 从 `.ctf-upload` 的兄弟节点移入 `.ctf-upload` 容器内部。
  - `.ctf-upload` 增加 `flex-wrap: wrap`，允许预览图与按钮在同一行排满后折行。
  - `.ctf-preview` 尺寸从 72×72 调整为 84×84，与「本地上传」按钮同高对齐，并加 `flex-shrink: 0` 防止被压缩。

## 5. 修复上传产品图「原图」标签遮挡 + 支持点击放大
- **文件**：`web/src/pages/EcommerceGallery/index.tsx`、`web/src/pages/EcommerceGallery/gallery.css`
- 问题：产品图预览上的「原图」标签背景不透明、位置偏下，几乎遮住整张图；且点击图片无法放大查看。
- 修复：
  - `index.tsx`：从 `antd` 引入 `Image` 组件，将 thumb 内的 `<img>` 替换为 `<Image preview={{ mask: false }} />`，实现点击放大预览。
  - `gallery.css`：
    - `.thumb` 增加 `cursor: zoom-in`，提示可点击放大。
    - `.badge-orig` 改为左上角小角标：`top: 3px; left: 3px`，字体缩小到 9px、padding 1px 4px，背景使用半透明品牌色 `rgba(124, 92, 255, .9)`，并设 `pointer-events: none` 避免遮挡点击。
    - 删除按钮与标签提升 `z-index: 2`，确保浮在图片预览层之上。

## 验证
- `npm run build` 通过，无 TS/CSS 错误。

## 后续建议
- 自定义子任务的参考图片目前仍只能本地上传；图片库按钮暂为占位提示，后续可接入左侧已上传产品图选择逻辑。
- 模型字段 label 中的「（AI 提供商图片模型）」说明较长，若后续仍显拥挤，可将其移到 Select 下方作为独立提示行。
