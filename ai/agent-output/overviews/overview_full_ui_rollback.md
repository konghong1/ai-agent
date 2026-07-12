# AI 智能策划台 / 属性设置弹窗回退完成

## 用户发现的问题
- 用户截图显示：属性设置弹窗仍被改成 V2 分组版（产品表达 / 视觉氛围 / 通用继承 / 输出控制），与原始 UI（左侧个性化/通用设置 + 右侧补充说明/出图/参考图片）不一致。
- 用户强调：提示词是后端生成的，前端只是展示配置，不要改前端逻辑。

## 已执行动作
- `git checkout HEAD -- web/src/pages/EcommerceGallery/PlannerDrawer.tsx`（已回退）
- `git checkout HEAD -- web/src/pages/EcommerceGallery/TypeSettingsModal.tsx`（本次追加回退）
- `git checkout HEAD -- web/src/pages/EcommerceGallery/gallery.css`（本次追加回退，清除 V2 死代码）
- 后端 `app/gallery_config.py` / `app/gallery_prompt.py` 保持已批准的修复（COLOR LOCK / 12字段兜底 / 配置版本化），未回退。

## 验证结果
- `tsc --noEmit`：零类型错误
- `vite build`：成功（4289 模块，CSS 从 125KB 恢复到 110KB）
- 当前前端 UI 已完全回到原始设计：
  - 属性设置弹窗：两栏布局（个性化/通用设置 + 补充说明/出图设置/参考图片）
  - AI 智能策划台：简洁类型网格，选好类型加入规划列表

## 关键澄清：为什么不是“随机生成”
- AI 智能策划台本身只把选中的类型加入「出图规划列表」，随后打开属性设置弹窗，**不直接生成图片**。
- 真正出图是用户在规划列表中单独触发的显式动作。
- 提示词由后端 `app/gallery_prompt.py` 生成，且已包含：
  - 主体一致性锚定：参考图即本图要展示的商品，版型/颜色/logo 逐处一致、不得改变
  - COLOR LOCK：颜色锁定在 M1 最强位置，防止背景染产品色
  - 所选类型（hero/detail/angle/usp…）作为侧重点驱动提示词
- 前端 UI 回退不会影响后端提示词逻辑，也不会改变“参考图 + 所选侧重点 → 商品展示”的链路。

## 后续检查项
- 在浏览器中按 **Ctrl+F5** 硬刷新，确认属性设置弹窗回到原始两栏布局。
- 若重新打开后仍有 V2 样式，请检查是否浏览器/前端服务缓存了旧 bundle；可重启本地 vite 或 docker web 服务再试。
- 后端如提示词生成不符合预期（如颜色/品类跑偏），那是后端问题，与本次 UI 回退无关，可单独排查 `gallery_prompt.py`。
