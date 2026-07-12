# 电商套图 UI · 去掉「单独商品图」+ Taste Skill 重设计（仅样式）

## 完成内容

### 1. 移除「单独商品图」模块
- 文件：`web/src/pages/EcommerceGallery/TypeSettingsModal.tsx`
- 删除属性设置弹窗中的「单独商品图」区块（选填上传/从项目图选择/预览）。
- 一并清理失效引用（因 `tsconfig` 开启了 `noUnusedLocals`，否则编译失败）：
  - 移除 `galleryMode` / `productFileRef` / `productImage` / `productImageUrl` / `productUploading` 等 state
  - 移除 `handleProductImageUpload` / `removeProductImage` 函数
  - 移除 `uploadPlanItemImage` 与 `useRef` import
- **逻辑未变**：保存时 `product_image` 仍写入 `item?.product_image || ''`，后端行为一致；参考图上传复用同一套 `.ref-upload*` 样式，无死代码。

### 2. Taste Skill 重设计（纯 CSS，仅改样式）
文件：`web/src/pages/EcommerceGallery/gallery.css`（末尾新增「精炼层」）

按 Taste Skill 审计清单落地，重点解决"丑/不协调 + 按钮间距"：

| 维度 | 改动 |
|---|---|
| **强调色统一** | 主操作（生成 / 设置完成）由刺眼柠檬黄 `#C8E000` 改为品牌橙 `#FF4D2E`；全站单一主操作色 |
| **去 AI 紫蓝 glow** | AI 语义按钮（`btn-plan-ai` / `btn-df-confirm` / `btn-aifill` / `prompt-copy-btn`）的 `linear-gradient` 紫蓝渐变 → 实心靛蓝 `#6E63CF` + 同色调阴影，去饱和更克制 |
| **按钮间距** | 所有操作行（抽屉底部 `df-actions`、弹窗底部 `modal-footer`、规划行 `plan-actions`、用例 `case-actions`）统一 `gap: 12px`；按钮 `min-height:40px` 主/次基线对齐 |
| **按钮态** | 全局按压下压 `translateY(1px)`、键盘 `:focus-visible` 焦点环、统一 200ms 级过渡（排除 antd 内部按钮） |
| **卡片** | 策划台类型卡 `.dg-card` 悬浮微抬升 + 品牌色边框，选中态高亮 |
| **排版** | 标题字距收紧 `-.02em`，层级更清晰 |

## 验证
- `tsc --noEmit`：零类型错误
- `vite build`：成功（4289 模块，CSS 112KB）
- **前端逻辑、后端 `gallery_config.py` / `gallery_prompt.py` 均未改动**

## 设计读（按 Taste Skill 0.B）
Reading this as: internal creator tool (电商套图工作台) for 运营/设计师, with a calm premium-tool language, leaning toward the existing warm-neutral token system + single brand-orange accent + restrained indigo for AI affordances.

## 下一步
浏览器 **Ctrl+F5 硬刷新** 查看：属性设置弹窗已无「单独商品图」；按钮间距统一、按压有反馈、AI 按钮不再发光、主操作统一为橙色。
