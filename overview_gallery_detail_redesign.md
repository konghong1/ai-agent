# 作品详情弹窗重新设计说明

## 修改目标

按用户参考图重新设计「作品详情」与「创作案例详情」弹窗：

- 每个图片都在**统一大小的展示框**内，按图片自身比例 `contain` 居中，不裁切、不拉伸、不强制统一比例。
- 左侧放大展示产品原图，右侧横向排列生成图卡片。
- 标题、类型标签完整可见，不被父容器裁切。
- 底部「一键做同款」/「复制分享链接」等操作按钮始终可见，弹窗不再显示不全。

## 修改文件

### 1. `web/src/pages/EcommerceGallery/index.tsx`

- 作品详情 Modal 宽度从 1080px 加宽到 **1200px**。
- 创作案例详情 Modal 宽度从 960px 加宽到 **1200px**，并改为左侧原图 + 右侧生成图的横向布局，与作品详情一致。
- 移除详情卡片里主动写死的比例 `ratioStyle`，完全由 CSS 统一控制展示框。
- 生成图卡片标题下方只保留类型标签和模型名，信息更紧凑。

### 2. `web/src/pages/EcommerceGallery/gallery.css`

重新设计 `.g-modal.detail-modal` 样式：

- `.detail-modal-body`：最大高度 `calc(100vh - 140px)`，整体可滚动，底部操作按钮始终可见。
- `.detail-layout`：左侧产品原图（固定 320px）+ 右侧生成图区域（可横向滚动）。
- `.detail-product`：左侧产品原图卡片，图片展示框固定高度 420px，下方居中显示「产品原图」。
- `.detail-right`：右侧区域可横向滚动，生成图卡片横向 flex 排列。
- `.detail-item`：固定宽度 200px，包含图片框、标题、类型标签。
- `.detail-img`：固定高度 260px，`display:flex; align-items:center; justify-content:center;`，图片 `max-width:100%; max-height:100%; object-fit:contain`，按自身比例居中显示。
- `.detail-title`：`overflow-wrap:anywhere; word-break:break-word; white-space:normal; text-align:center`，超长中英文标题都完整折行。
- `.detail-meta`：类型标签和模型名居中小字 pill 展示。
- `.detail-actions`：底部居中，按钮最小宽度 180px，始终可见。

额外修复：
- `.gallery-page .pf-pick img` 从 `object-fit: cover` 改为 `object-fit: contain`，解决「发布到创作案例」选择缩略图时图片被裁切/显大的问题。

## 验证结果

- `tsc --noEmit`：零错误 ✅
- `vite build`：成功（4289 模块）✅
- 高保真静态测试：生成 1:1 / 3:4 / 16:9 / 超宽 Banner 四张不同比例图片，放入真实 DOM 结构并使用构建后的真实 CSS，各图均按自身比例在固定框中居中展示，不裁切；超长标题完整换行；底部按钮可见。
- 真实应用截图：登录 → 电商套图 → 创作案例 → 查看详情，弹窗成功打开，左侧原图、右侧生成图横向排列，按钮可见，无内容被裁切。

## 用户操作

前端已重新构建到 `web/dist`，Docker web 容器挂载的就是该目录，**刷新浏览器（Ctrl+F5）** 即可看到新效果。
