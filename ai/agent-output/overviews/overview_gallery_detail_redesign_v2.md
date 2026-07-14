# 作品详情弹窗重新设计与人物列表图片比例修复

## 问题确认

通过**真实运行中的 React 应用**截图排查（antd v5 的 Modal 样式是运行时注入的，静态 HTML 无法复现真实标题渲染），发现两个问题根因：

1. **「作品详情」标题显示不全/显窄**：`.g-modal .ant-modal-content { padding: 0 }` 导致 antd 弹窗标题区被压缩成只有 25px 高、padding 为 0，标题直接贴到弹窗边缘，视觉上像被截断。
2. **人物列表/结果列表缩略图被裁成统一方图**：任务结果网格 `.task-cell`、参考图 `.ref-thumb`、项目图片选择器 `.gp-item` 等多处仍使用 `object-fit: cover`，不同比例图片被强制裁剪成方图。

## 修改内容

### 1. 重新设计生成结果详情弹窗

- 弹窗标题由「作品详情」重命名为「生成结果详情」。
- 给弹窗 header 强制加 `padding: 16px 24px`，标题颜色改为 `--gb-ink`，字号 17px，行高 1.5，右侧留出 48px 防止与关闭按钮重叠。
- 关闭按钮调整为与 header 对齐，hover 状态更友好。
- 弹窗主体背景改为 `--gb-bg`，与页面统一。
- 右侧结果图由「横向滚动 flex」改为「响应式网格 `grid-template-columns: repeat(auto-fill, minmax(180px, 1fr))`」，5 张图自动排成 4+1，所有图都可见。
- 每个图片展示框固定高度 220px，图片按自身比例 `contain` 居中，不裁切、不拉伸。
- 左侧产品原图固定展示框 420px，同样 `contain` 居中。

文件：
- `web/src/pages/EcommerceGallery/index.tsx`
- `web/src/pages/EcommerceGallery/gallery.css`

### 2. 全模块图片缩略图统一按自身比例展示

将以下选择器的 `object-fit: cover` 改为 `object-fit: contain`：

- `.gallery-page .task-cell .ant-image-img`（人物列表 / 创作结果网格）
- `.gallery-page .thumb .ant-image-img`（产品原图缩略图）
- `.gallery-page .set-card img`（策划台设置卡片）
- `.gallery-page .rec-card img`（推荐图卡片）
- `.g-modal .ref-thumb img`（参考图缩略图）
- `.g-modal .ref-preview img`（参考图预览）
- `.g-modal .gp-item img`（项目图片选择器）
- `.g-modal .result-grid img`（旧版结果网格）
- `.g-drawer .ctf-preview img`（自定义子任务预览）
- `.g-drawer .template-cover img`（模板封面）
- `.stm-cover-thumb .ant-image-img`（保存模板封面缩略图）
- `.gallery-page .pv-img img`（图片预览）

保留 `.gallery-page .case-strip .cell img` 与 `.gallery-page .pf-pick img`（此前已改为 contain）。

### 3. 验证

- `tsc --noEmit`：零错误。
- `vite build`：4289 模块构建成功。
- 在真实应用里注入 1:1 / 3:4 / 16:9 / 9:16 / 超宽 Banner 五种比例测试图，打开「生成结果详情」弹窗截图：
  - 标题「生成结果详情」padding 充足、不被截断、颜色正确。
  - 5 张图全部按自身比例在固定框内居中展示，无裁剪。
- 任务列表截图确认：缩略图也不再被裁成统一方图，各图比例可见。
- 已清理验证用的种子任务与测试文件，不污染 DB。

## 用户操作

前端已重新构建到 `web/dist`，Docker web 容器挂载该目录，**刷新浏览器（Ctrl+F5）** 生效。
