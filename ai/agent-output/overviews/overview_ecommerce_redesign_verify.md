# 电商套图配置页重设计 · 收尾与验证

## 完成的修改

针对用户反馈「全局输出配置 + 出图规划列表样式都丢失了」以及「AI 智能策划台加号需极速添加到列表」，在 `web/src/pages/EcommerceGallery/` 完成以下实现：

### 1. 全局输出配置（卡片化重设计）
- `index.tsx`：`output-config` 加 `config-section` 卡片类。
- `gallery.css`：白底卡片 + 强边框 + 阴影；每个 `cfg-field` 独立卡片（浅底 + 描边 + 圆角内边距）。
- **关键修复**：`.cfg-grid` 由 `1fr 1fr` 改为 `repeat(2, minmax(0, 1fr))`。
  - 原因：`1fr` 轨道会撑大到内容最小宽度（模型 Select 的长选项），把第二列（分辨率/比例）挤出卡片并被 `overflow:hidden` 裁掉。
  - 结果（CDP 实测）：`gridTemplateColumns = 146.5px 146.5px`，4 个配置项全部等宽 147px 可见，无撑破、无裁切。

### 2. 出图规划列表（增强）
- `.plan-section` 白卡 + 阴影；`.plan-count` 改深色胶囊徽标。
- 空状态加图标框 + 提示文案「点击 ✦ AI 智能策划台 选择类型，或用 ⚡ 极速添加 一键生成」。
- `.pr-name` 单行省略 → 2 行截断；`.pr-chip` 加 🖼/⬜/📐 图标。

### 3. AI 智能策划台 · 极速添加
- `PlannerDrawer.tsx`：抽屉底部新增「⚡ 极速添加 (n)」按钮。
- `index.tsx`：`quickAddDrawer()` 直接 `createPlanItem` 写入规划列表（去重 + 成功 toast），通过 `onQuickAdd` 接线。

## 验证结果
- `npm run build` 通过（CSS 85.56 kB，无 TypeScript 错误）。
- Headless Chrome + CDP DOM 检查（dev 5173 + backend 8010，admin 登录）：
  - 2 列网格等宽，4 个配置项全部可见 ✓
  - 规划区为默认项目空状态（无 plan_items），空状态正常渲染 ✓
- 已移除临时调试代码（`lime/red/blue` 背景、`FIELD COUNT` 调试块）与临时验证页 `public/_verify_auth.html`（含有效 JWT，不应留仓库）。

## 截图（见 Artifacts）
- `section_output_config.png` — 全局输出配置卡片
- `section_plan_list.png` — 出图规划列表（空状态）
- `full_page.png` — 整页

## 备注
- 默认 admin 项目无 plan_items，故 chips / 带图标行样式需有数据时才可见；结构与样式已编译验证通过。
- 可复用的无头验证脚本保留于 `C:\Users\admin\AppData\Local\Temp\cdp_verify.py`。
