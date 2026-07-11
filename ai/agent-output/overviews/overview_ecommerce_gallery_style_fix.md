# 电商套图前端样式对齐修复

## 问题
用户反馈「前端页面和 UI 的样式完全不一样」。首屏截图显示页面被嵌入在 `BasicLayout` 的侧边栏 + 顶栏内，整体视觉与设计稿 `designs/ecommerce-gallery.html` 不一致。

## 根因
- `App.tsx` 把 `/ecommerce-gallery` 放在 `BasicLayout` 下，页面自带全局侧边栏和顶栏。
- 页面缺少设计稿中的独立顶部导航条（智图 AI、积分、签到、会员充值）。
- 示例 / 案例图使用了后端返回的占位渐变图，没有 fallback 到设计稿的示例图。

## 修改内容

### 1. 路由独立化（`web/src/App.tsx`）
- 将 `/ecommerce-gallery` 从 `BasicLayout` 嵌套路由中移除。
- 新增同级独立路由，仍然套 `RequireAuth`：
  ```tsx
  <Route path="/ecommerce-gallery" element={<RequireAuth><EcommerceGallery /></RequireAuth>} />
  ```
- 效果：电商套图成为独立全屏工作台，不再显示左侧「AI Agent」导航侧边栏。

### 2. 新增顶部导航条（`web/src/pages/EcommerceGallery/index.tsx`）
- 实现 `TopBar`：智图 AI logo、邀请好友、客服、1280 积分、签到、会员充值。
- 品牌区 logo 可点击返回 `/`（仪表盘）。
- 页面加载状态改为全屏 `100vh` 居中 spinner。

### 3. 示例图片 fallback
- 完整电商套图 · 示例：始终使用设计稿同款 `picsum.photos` 示例图（主图 3:4 + 4 张类型图）。
- 热门套图示例：新增 `isRealImage()` 检测，当后端返回占位/渐变/SVG 时自动 fallback 到 `picsum.photos` 种子图，保证案例卡片与设计稿一致。
- 修正案例条带：原代码只渲染 3 张图，现改为 4 张（原图 + 3 张生成图），最后一张在 total_count > 4 时显示 `+N` 遮罩。

### 4. 样式调整（`web/src/pages/EcommerceGallery/gallery.css`）
- `.gallery-page` 改为 `min-height: 100vh`、`display: flex column`，保证独立路由下占满整个视口。
- `.shell` 高度改为 `calc(100vh - 60px)`，配合新增的 60px sticky topbar。
- `.config-panel` 吸附顶部从 `0` 改为 `60px`。
- 新增 `.topbar`、`.brand`、`.points-pill`、`.btn-vip`、`.ghost-link` 等样式，颜色/圆角/阴影完全复用设计稿 token。

## 验证结果
- `tsc --noEmit`：通过。
- `vite build`：成功（4287 modules，dist 输出正常）。
- 使用 headless Chrome 截取设计稿与运行中的 React 页面做对比：
  - 设计稿：`../verify-shots/design.png`
  - 修复后页面：`../verify-shots/app-final.png`
  - 对比结论：顶栏、2 栏布局、暖色背景、示例套图、热门案例卡片已高度一致。

## 备注
- 临时验证文件（`_auth_helper.html`、`vite.verify.config.ts`）已删除；临时 dev server 与 MySQL API 进程已关闭。
- 测试账号仍为 `test@example.com / Test123456`（MySQL 环境，不影响 Docker 部署）。
- 当后端真实生成图片入库后，`isRealImage()` 会让真实图片自动替换 fallback 示例图。
