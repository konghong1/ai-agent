# 电商套图 AI 策划台弹窗样式丢失 & 列表优化

## 问题

1. 点击左侧「AI 智能策划台」的 `+` 号（或 `AI智能策划台` 按钮）时，弹出的抽屉面板样式丢失，看起来像未加样式的原始 HTML。
2. 添加策划类型后，左侧出图规划列表的参数展示不够精致，影响观感。

## 根因

- **弹窗样式丢失**：`antd` 的 `Drawer` / `Modal` 默认通过 portal 渲染到 `document.body`，完全脱离了 `.gallery-page` 这个 CSS 作用域。原有 `gallery.css` 中所有弹层样式都写成 `.gallery-page .g-drawer ...` / `.gallery-page .modal-...`，且 `--gb-*` 设计变量也只在 `.gallery-page` 上定义；portal 外的弹层因此既匹配不到选择器，也拿不到变量，导致样式全部丢失。
- **列表不美观**：计划行参数使用 `数量 1 | 比例 3:4 | 分辨率 1K` 这种纯文本分隔方式，视觉上比较粗糙，也缺乏层次和状态区分。

## 改动

### 1. 修复弹窗 / 抽屉样式（`gallery.css`）

- 新增 `.g-drawer, .g-modal { ... }` 设计变量镜像，确保 portal 内也能使用 `--gb-*` token。
- 将抽屉内部选择器全部从 `.gallery-page .g-drawer ...` 改成 `.g-drawer ...`：
  - `.g-drawer .ant-drawer-body` / `.g-drawer .drawer-head` / `.g-drawer .drawer-grid` / `.g-drawer .dg-card` / `.g-drawer .drawer-foot` / `.g-drawer .btn-df-*` 等。
- 将弹窗内部选择器全部从 `.gallery-page .g-modal ...` 改成 `.g-modal ...`：
  - `.g-modal .ant-modal-content` / `.g-modal .modal-header` / `.g-modal .modal-body` / `.g-modal .modal-footer` / `.g-modal .btn-confirm` 等。
- 为 `.g-modal` / `.g-drawer` 内的 antd `Input` / `Select` 补一套与主页面一致的重写样式。
- 新增 `.g-modal .btn-template`（属性设置弹窗里的「另存为模板」按钮之前没有样式）。

### 2. 修正内联 token（`index.tsx` / `TypeSettingsModal.tsx`）

- 生成结果预览 Modal 增加 `className="g-modal"`，并把内联 `--ice-text-secondary` / `--g-brand` 改成 `var(--gb-ink-soft)` / `var(--gb-brand)`。
- `TypeSettingsModal` 中的参考图选中 outline 和「请先在左侧上传产品图」提示色从 `--g-brand` / `--ice-text-secondary` 改为 `--gb-brand` / `--gb-ink-faint`。

### 3. 优化列表展示（`gallery.css` + `PlanRow.tsx`）

- 计划行增加左侧彩色强调条：极速出图=紫色，自定义=品牌橙色。
- 新增行入场动画 `prIn`。
- 参数摘要改为精致胶囊标签 `.pr-chip`，显示为「数量 **1**」「比例 **3:4**」「分辨率 **1K**」。
- `PlanRow` 组件渲染 `.plan-row.custom` / `.plan-row.fast` 类名，并输出新的 `.pr-chip` 结构。

## 验证

- `tsc --noEmit` 通过。
- `vite build` 成功（4287 modules）。
- 使用 `grep` 检查编译产物，确认包含：
  - `.g-drawer .ant-drawer-body`
  - `.g-modal .ant-modal-content`
  - `.g-modal .result-grid`
  - `.gallery-page .plan-row.custom`
- Chrome headless 截图验证：
  - 列表：已展示带彩色左条和胶囊参数的计划行。
  - AI 策划台抽屉：已恢复紫色主题、勾选卡片、底部操作栏，样式不再丢失。

## 文件变更

- `web/src/pages/EcommerceGallery/gallery.css`
- `web/src/components/gallery/PlanRow.tsx`
- `web/src/pages/EcommerceGallery/index.tsx`
- `web/src/pages/EcommerceGallery/TypeSettingsModal.tsx`
