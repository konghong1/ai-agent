# 电商套图修复总结：详情布局 + 提示词按钮 + 文字印图

## 修复内容

### 1. 作品详情弹窗看不到「查看提示词」按钮
- **原因**：`GALLERY_PROMPT_VIEW` 开关默认关闭，前端 `features.show_prompt` 为 false，所以入口没渲染。
- **处理**：在 `docker-compose.yml` 的 `api` 和 `worker` 服务环境变量里统一加了 `GALLERY_PROMPT_VIEW: "1"`，Docker 启动时默认开启。
- **上线时**：去掉该环境变量或设为 `"0"` 即可关闭，符合「上线后不需要」的可配置要求。

### 2. 作品详情布局太粗糙，改为左侧产品图 + 右侧生成图
- **改动**：
  - `web/src/pages/EcommerceGallery/index.tsx`：「作品详情」Modal 改为左右两栏：
    - 左侧：展示当前项目的第一张产品原图（`project.images[0]`），固定 280px 宽度，sticky 顶对齐。
    - 右侧：生成图网格，保留标题、模型信息、放大下载、提示词入口。
  - `web/src/pages/EcommerceGallery/gallery.css`：新增 `.detail-layout`、`.detail-product`、`.detail-right`，调整网格列宽更紧凑。
- **效果**：与您提供的参考图一致——先看产品原图，再看对应生成出的各角度/场景图。

### 3. 生成的图片上仍有文字（如「性价比」）
- **根因**：`app/gallery_service.py` 的 `ai_fill_suggestion()` 只要有核心卖点、且 `copy_need` 为空，就自动把 `copy_need` 填成「核心卖点文案」；前端 `COMMON_DEFAULTS` 也默认带这个值。结果提示词走了「允许按文案需求加少量版面文案」分支，模型把卖点当文字画到图上。
- **处理**：
  - 删除后端的 `copy_need` 自动回填逻辑。
  - 删除前端 `TypeSettingsModal.tsx` 里 `COMMON_DEFAULTS` 的 `copy_need` 默认值，让字段真正留空。
  - 重写 `_build_prompt` 中的文字约束：
    - 核心卖点明确写成「转译为视觉元素来体现，而不是写成图上的文字」。
    - 追加「绝对禁止：本画面中不得出现任何文字、水印、标语、LOGO、价格、促销语、品牌名、产品名或字母/数字标签」。
    - 未指定 `copy_need` 时追加「画面中必须保持零文字、零水印、零标识」。
    - 有参考图时追加「参考图仅用于识别商品外观；如果参考图中带有文字、标签、水印或价格签，请完全忽略它们，不要复制到生成图中」。

## 验证结果
- `py_compile` 通过
- `tsc --noEmit` 通过
- `vite build` 通过
- `_build_prompt` 功能断言通过：无 `copy_need` 时提示词含「绝对禁止/零文字/忽略参考图文字」，不含「核心卖点文案」；有 `copy_need` 时保留文案需求分支。

## 生效方式
- 改了后端 + 前端 + docker-compose，需要重新启动 Docker 栈（或重启 FastAPI）并刷新浏览器 `Ctrl+F5`。
- 已生成的旧图文字问题不会自动消失，只有重新点击「立即生成」后才会用新提示词出图。
