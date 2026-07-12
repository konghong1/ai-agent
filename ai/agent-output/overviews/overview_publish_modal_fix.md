# 修复「发布到创作案例」弹窗图片过大

## 问题
点击「发布到创作案例」后，弹窗中的图片被撑得非常大，单张图几乎占满整个弹窗，无法正常选择。

## 根因
antd Modal 通过 portal 渲染到 `document.body`，不在 `.gallery-page` 节点下。但 `gallery.css` 中 `.pf-picks` / `.pf-pick` 等选择器都带了 `.gallery-page` 前缀，导致 portal 内的发布弹窗完全匹配不到这些样式，`.pf-pick` 退化为 `position:static` 的 button，图片按 intrinsic 尺寸撑开。

## 修复
- `web/src/pages/EcommerceGallery/index.tsx`：给发布 Modal 增加 `className="g-modal publish-modal"`。
- `web/src/pages/EcommerceGallery/gallery.css`：将 `.pf-picks` / `.pf-pick` / `.pf-field` 等选择器从 `.gallery-page` 前缀改为 `.publish-modal` 前缀；并把 `.pf-pick` 固定为 `140px × 140px` 的 contain 舞台框。

## 验证
- `tsc --noEmit` 零错误；`vite build` 成功。
- Playwright 驱动真实应用：弹窗内 `.pf-pick` 计算尺寸为 `140px × 140px`，`object-fit: contain`，不再溢出。
- 截图：`ai/agent-output/verify-publish-modal/publish_modal.png`

## 用户操作
请在浏览器中按 `Ctrl + F5` 硬刷新查看最新效果。
