# 电商套图：恢复侧边栏目录树

## 问题

用户反馈：点击"电商套图"时目录树不应该消失，应该是保留目录树、右侧内容区显示电商套图页面。

## 根因

前一步为了还原设计稿 `designs/ecommerce-gallery.html` 的"独立全屏工具"观感，把 `/ecommerce-gallery` 从 `BasicLayout` 提到独立路由，导致侧边栏/目录树整条消失。

## 修正内容

### 1. 路由恢复嵌套（`web/src/App.tsx`）

将 `/ecommerce-gallery` 重新放回 `BasicLayout` 的嵌套路由，与 `dashboard`、`media-library` 等同级：

```tsx
<Route path="/" element={<RequireAuth><BasicLayout /></RequireAuth>}>
  ...
  <Route path="media-library" element={<MediaLibrary />} />
  <Route path="ecommerce-gallery" element={<EcommerceGallery />} />
  <Route path="settings" element={<SettingsPage />} />
</Route>
```

### 2. 移除独立顶栏（`web/src/pages/EcommerceGallery/index.tsx`）

删除新增的 `TopBar` 组件及 `<TopBar />` 渲染，避免与 `BasicLayout` 的全局顶栏叠成两层。加载占位高度由 `100vh` 改为 `100%`。

### 3. 适配 BasicLayout 内容区高度（`web/src/pages/EcommerceGallery/gallery.css`）

`BasicLayout` 的右侧 `Content` 高度为 `calc(100vh - 64px)`，因此：

- `.gallery-page`：`min-height: 100vh` → `height: 100%; min-height: 100%`
- `.shell`：`min-height: calc(100vh - 60px)` → `min-height: 100%`
- `.config-panel`：`top: 60px` → `top: 0`；`height: calc(100vh - 60px)` → `height: calc(100vh - 64px)`

这样左侧配置面板仍在 `Content` 滚动容器内吸顶，右侧内容可独立滚动。

## 验证

- `tsc --noEmit`：通过
- `vite build`：成功（4287 modules，dist 产出）

## 说明

- 设计稿的暖色主题、两栏布局、示例图片等样式仍然保留；只是不再独占整个窗口，而是嵌套在带侧边栏的 `BasicLayout` 中，符合"点击菜单出现页面"的产品结构。
- `gallery.css` 中旧的 `.topbar` 样式块现在无对应 DOM，属于死代码，后续可清理。
- 认证后的完整交互验证需在 Docker MySQL 后端环境中进行（本地 SQLite 预览缺少可登录账号）。
