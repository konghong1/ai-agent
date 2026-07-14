# 创作结果详情 / 创作案例图片展示修复

## 修复目标

1. **创作结果「查看详情」/「一键做同款」弹窗**：标题不折行、生成图被强制统一比例，看起来全都一样大小。
2. **发布到创作案例后的图片展示**：图片被强制拉伸/裁切成统一比例，显得「超大」或不符合生成时的实际比例。

用户明确反馈：展示图片时**不要自己规定比例**，要**按生成的图片自身比例居中展示**到展示区域里。

## 修改文件

- `web/src/pages/EcommerceGallery/gallery.css`
- `web/src/pages/EcommerceGallery/index.tsx`

## 关键改动

### 1. 详情弹窗图片容器改为「自然比例居中」

旧写法：`.detail-img` 强制 `aspect-ratio: 3 / 4`，图片 `absolute` + `object-fit: cover` 填充，导致所有图片都被裁成 3:4。

新写法：

```css
.g-modal.detail-modal .detail-img {
  position: relative;
  height: clamp(220px, 34vh, 320px);  /* 固定展示舞台高度 */
  display: flex;
  align-items: center;
  justify-content: center;             /* 图片居中 */
  background: var(--gb-surface-2);
  overflow: hidden;
}
.g-modal.detail-modal .detail-img .ant-image,
.g-modal.detail-modal .detail-img .ant-image-img,
.g-modal.detail-modal .detail-img img {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
  object-fit: contain;                 /* 不裁切、不拉伸，保持原比例 */
  display: block;
}
```

- 产品原图也去掉 3:4 强制：`aspect-ratio: auto`。
- 同时把创作案例缩略图条 `.case-strip .cell img` 从 `cover` 改为 `contain`。

### 2. 移除前端强制比例代码

删除 `index.tsx` 中的 `ratioStyle(...)` 内联调用和函数定义。用户要求展示时不要由前端再规定比例，直接按图片自身比例显示。

### 3. 标题折行更健壮

```css
.g-modal.detail-modal .detail-title {
  overflow-wrap: anywhere;
  word-break: break-word;
  white-space: normal;
  min-width: 0;
}
.g-modal.detail-modal .detail-item { min-width: 0; }
```

避免超长无空格字符串或 grid 子项撑破布局，保证中英文超长标题都能完整折行展示。

## 验证

- `tsc --noEmit` ✅ 零错误
- `vite build` ✅ 4289 模块构建成功
- Playwright 高保真还原：生成 1:1 / 3:4 / 16:9 / 超宽 Banner 四张图，复刻真实 DOM 结构，引用构建出的真实 CSS。截图中不同比例图片明显区分、各自居中、无裁切；超长标题完整折行。
- Playwright 真实应用：登录 → 切换到创作案例 → 打开详情，弹窗正常、按钮可见、不再「超大」。

## 用户操作

前端已重新构建到 `web/dist`，Docker web 容器挂载的就是该目录。请刷新浏览器（Ctrl+F5）即可看到新的展示效果。后端无需重启（本次只改前端样式与组件）。
