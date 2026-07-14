# 作品详情弹窗移除「提示词」按钮

## 问题
用户反馈：作品详情弹窗（查看详情 / 一键做同款）中出现了「+提示词」按钮，且本次需求仅要求调整详情样式与图片展示比例，不应新增或保留提示词功能。

## 改动
仅修改 `web/src/pages/EcommerceGallery/index.tsx`：

- 移除了作品详情弹窗中每个生成图卡片上的 `PromptBadge` 渲染：
  ```tsx
  // 已删除
  {features.show_prompt && r.prompt && <PromptBadge prompt={r.prompt} />}
  ```
- 未改动后端提示词生成逻辑。
- 未改动任务卡片（任务列表）上的提示词入口（若其原本存在）。
- 未改动任何提示词引擎相关代码。

## 验证
- `tsc --noEmit` 零错误 ✅
- `vite build` 成功（4289 模块）✅
- Playwright 高保真还原截图（`detail_no_prompt.png`）确认：
  - 详情弹窗所有图片卡片上均无「+提示词」按钮。
  - 图片继续按自身原始比例居中展示（3:4 竖图、16:9 横图、1:1 方图、超宽 Banner 比例明显不同）。
  - 标题、类型、模型信息完整展示。

## 用户操作
前端已重新构建到 `web/dist`，Docker web 容器挂载的就是该目录，刷新浏览器（Ctrl+F5）即可生效。
