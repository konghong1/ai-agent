# 属性弹窗横排 + 规划列表列表框 — 修改概览

## 修改范围
仅修改 `web/src/pages/EcommerceGallery/gallery.css`，**未改动任何前端组件 JSX 与后端逻辑**。

## 用户反馈与对应修改

### 1. 属性设置弹窗字段要「左右结构」
**截图**：`TypeSettingsModal` 中「价值聚焦、视觉强化、产品呈现」等字段当前是标签在上、输入框在下。

**修改**：
```css
.g-modal .pf-row { display: flex; align-items: flex-start; gap: 12px; }
.g-modal .pf-row > label { flex: 0 0 92px; padding-top: 7px; margin-bottom: 0; }
.g-modal .pf-row .ant-input,
.g-modal .pf-row .ant-select,
.g-modal .pf-row .g-stepper,
.g-modal .pf-row .g-res-btns { flex: 1; min-width: 0; }
```
效果：标签固定 92px 左对齐，输入框/选择框/步进器/分辨率按钮弹性占满右侧。

### 2. 选择框不要下拉箭头
**修改**：
```css
.g-modal .pf-row .ant-select .ant-select-arrow { display: none; }
```
效果：弹窗内所有选择框右侧的 ▼ 箭头隐藏，保持简洁。

### 3. 出图规划列表与 AI 智能策划台「叠在一起」，要列表框
**截图**：规划列表中「首屏视觉图、产品白底图、运输安装」等项与上方「AI 智能策划台」大按钮视觉上混在一起。

**修改**：
- `.plan-actions` 增加 `margin-bottom: var(--gb-s3)`，与列表区域留空。
- `.plan-body:has(.plan-rows)` 增加边框、圆角、`surface-2` 背景，形成独立列表框。
- `.plan-rows` 内边距重置为 0，列表项整齐收纳在列表框内。

效果：按钮区、列表框、使用说明三者层次清晰，不再粘连。

## 验证结果
- `tsc --noEmit`：零错误
- `vite build`：成功（4289 模块，CSS 113 KB）

## 下一步
请 **Ctrl+F5 硬刷新** 后查看属性弹窗与规划列表区域。如果还有具体位置需要再调（例如标签宽度、列表框间距、按钮颜色），继续截图给我即可。