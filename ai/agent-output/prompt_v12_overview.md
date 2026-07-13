# 电商套图 · 提示词生成引擎 V12.5 总览

> 重构目标（用户原话）：按「AI 商品图提示词完整 8 大创作维度」结构重组提示词生成模块；
> 不同推荐类型各有侧重、随用户选择实时变化；结合网络优秀经验，沉淀为简洁优雅的提示词工程。
>
> V12.5 在 V12 基础上，针对用户实际反馈进一步做「选择驱动、去噪音、强约束」打磨：
> 视觉风格词库按「产品/人物」场景区分、45° 俯角与自适应比例给出强制约束、相机信息未配置时不再塞入具体型号、自适应比例推断不再强依赖 Pillow。

## 一、8 大维度 → 8 分桶结构

引擎（`app/gallery_prompt.py` `_assemble`）严格对齐用户定义的电商 8 大创作维度，
输出顺序固定、空桶自动跳过：

| 分桶 key | 段落标题 | 对应维度 | 主要来源 |
|---|---|---|---|
| `FOUNDATION` | 【画面基础定位】 | 一、用途/版式+比例+景别视角+构图 | 类型语义 + 平台 + 市场 + `TYPE_LAYOUT` + `RATIO_FORMAT` |
| `SUBJECT` | 【核心商品主体】 | 二、品类/材质/颜色/细节卖点 | 参考图一致性 + `产品呈现` + 核心卖点 + 逐 label 路由 |
| `PERSON` | 【人物/模特】 | 三、人物/模特 | 仅人物类型；基础描述来自 `MARKET_PROFILES[subject]` |
| `SCENE` | 【场景环境】 | 四、场景环境 | `bg_mode` 权威约束（白底/中性/实景）+ 市场背景 |
| `LIGHT` | 【光影】 | 五、光影 | 用户 `光影*` 设置 → `BUCKET_ROUTING` |
| `COLOR` | 【色彩调性】 | 六、色彩整体调性 | `bg_mode` 权威约束 + 用户 `色调倾向`/项目 `tone` |
| `CAMERA` | 【画风·相机·画质】 | 七、画风·相机&画质渲染 | `TYPE_CAMERA` / 轻量默认 + `GLOBAL_RETROUCH`/`RETOUCH_NO_HUMAN` + 视觉风格映射 + 媒介 |
| `POSTER` | 【附加商业元素】 | 八、附加商业元素 | 仅海报/卖点类（`COPY_LABELS`） |
| — | 【正向增强与约束】 | 品质增强 + 文字约束 + 参考图约束 | 固定收尾，全正向 |
| — | 【负面提示词】 | 九、负面固定维度 | `NEGATIVE_BASE` 三维：商品瑕疵/人像崩坏/画面问题 |

## 二、不同类型各有侧重（TYPE_SEMANTICS.lead）

`TYPE_SEMANTICS` 为每类定义 `bg_mode`（white/neutral/scene）、`person`
（forbidden/optional/forced）、`medium`、`lead`（最侧重的桶）：

- **商品图类**（bg/amz/detail/angle/detail2/design/spec/pkg/ship）→ `lead=SUBJECT`，白底/中性背景、强调商品本体精准还原。
- **场景类**（hero/scene/cmp/custom/pain）→ `lead=SCENE`，生活化场景 + 市场调色板。
- **人物强制类**（tryon/model/buyer）→ `lead=PERSON`，人物基础描述由市场档案提供。
- **营销类**（promo/usp）→ `lead=POSTER`，附加商业元素 / 卖点视觉化。

## 三、随选择实时变化（数据驱动路由）

86 个 SeeAny 配置项经 `BUCKET_ROUTING` 路由进 8 个分桶；14 个纯文案 label 走
`COPY_LABELS`（仅允许文字的类型进 `POSTER`）；4 个转化维度词（价值聚焦/视觉强化/
氛围浓度/价值暗示）经 `_DIM_VOCAB` 语义映射注入对应桶，不裸输出。
→ 用户选了什么，就进哪个桶；选了就变，且按类型性质生成不同提示词。

## 四、网络优秀经验沉淀（矛盾消解 + 简洁优雅）

- **颜色锁定（COLOR LOCK）**：有参考图时，所有「色调/配色/色系」描述被声明为
  **仅作用于背景与场景氛围，绝不改变商品本体颜色/图案/logo**；商品颜色始终以参考图为唯一标准。
- **人物护栏**：纯产品类型即便误选「真人穿着」也降级为「平铺展示」并跳过人物项；
  禁止人物类型的人物类 label 一律跳过，根治「产品图也带人物」与「无人物+真人穿着」冲突。
- **正/负分离**：正向增强与约束独立成块，负面提示词按三维度组织，无混杂。
- **比例跟随**：白底/场景类比例跟随 `output_settings.ratio`（`RATIO_FORMAT`），
  「自适应尺寸」按参考图比例自适应，不再写死 1:1，也不任由模型默认出方图。
- **无 Pillow 也能自适应**：`gallery_service._infer_size_from_reference` 在 Pillow 缺失时
  通过文件头解析 PNG/JPEG/GIF/WebP 真实宽高，仍可按参考图比例推断生成尺寸，
  避免测试/精简环境回退到模型默认方图。
- **零文字 vs 允许文字**：`COPY_ALLOWED_TYPES`（promo/usp/detail2）允许少量版面文案，
  其余类型零文字，卖点仅以视觉元素体现（`_lint` 强制校验，杜绝自相矛盾）。
- **风格词按场景区分**：`STYLE_VOCAB` 默认产品/场景通用，避免产品图中冒出「肤质 / 面料」；
  人物类型（tryon/model/buyer）通过 `HUMAN_STYLE_VOCAB` override 还原人物质感表达。
- **相机信息按需输出**：白底/产品图未选择特写/对焦/拍摄距离等相机字段时，
  不输出具体型号镜头，改用「商业产品摄影，标准棚拍布光」轻量描述，减少未配置噪音。

## 五、V12.5 重点修复（按用户截图设置实际验证）

1. **`GLOBAL_RETROUCH` 去「面料」化**：人物类修图描述由 `面料色彩1:1真实还原`
   改为 `所展示商品色彩1:1真实还原`，对非服饰试戴（腕表/首饰）同样准确；与
   `RETOUCH_NO_HUMAN` 的 `商品色彩` 措辞保持一致。
2. **`色调倾向` 冗余修复**：`色调倾向` 既在 `BUCKET_ROUTING→COLOR` 又被 COLOR 块
   按项目 `tone` 二次生成，导致同一提示词出现两行 `色调倾向`。改为「用户已显式选择
   则路由已注入、COLOR 块不再重复生成」，消除冗余。
3. **【附加商业元素】渲染验证**：确认 promo 类 `主题定位/版式布局/文案呈现/视觉元素/
   展示渠道` 等均经 `COPY_LABELS` 正确进入 `POSTER` 桶（真实 SeeAny 选项名与配置键一致，
   用户选择不会静默丢失）。
4. **产品图不再出现「肤质/面料」**：`STYLE_VOCAB["高级质感风"]` 原描述含
   `面料纹理高清晰呈现，肤质细腻通透`，在无人像的产品图中造成违和。V12.5 将其改为
   产品通用措辞 `材质纹理清晰呈现，表面光泽与立体感自然`，人物类型再经 `HUMAN_STYLE_VOCAB`
   override 还原人物质感。
5. **45° 俯角与自适应比例强制约束**：原提示词仅在 FOUNDATION 中写「拍摄机位角度：45度俯角」，
   模型容易丢失。V12.5 追加「视角强制约束：画面必须严格呈现「45度俯角」视角...」；
   自适应比例追加「比例强制约束：输出图必须严格保持与参考图完全一致的宽高比例，禁止裁剪、
   拉伸、填充或改变构图比例」。
6. **相机信息未配置时不塞具体型号**：亚马逊主图/白底图等未选择「特写部位/对焦方式/拍摄距离/视角」
   时，不再输出 `索尼 A7M4，50mm 定焦镜头，f/8 光圈` 等未配置信息，改为
   `商业产品摄影，标准棚拍布光，高分辨率无畸变`。
7. **自适应比例推断不再强依赖 Pillow**：新增 `_image_size_from_bytes` 文件头解析，
   在 Pillow 缺失的精简/测试环境仍可读取 PNG/JPEG/GIF/WebP 真实宽高并推断生成尺寸。
8. **生成图乱码尺寸标注修复**：
   - 负面提示词 `NEGATIVE_BASE["画面问题"]` 追加 `数字、字母、尺寸标注、测量线、标注箭头、文字标注、尺码标签、乱码文字`，
     以及英文强约束 `no text, no numbers, no letters, no watermark, no logo, no annotations, no measurement marks, no dimension lines, no size labels`，
     利用英文负面词对多数模型更强的约束力。
   - 零文字约束追加英文括号强调 `(no text, no letters, no numbers, no digits, no watermark, no logo, no typography, no annotations, no measurement marks, no dimension lines, no size labels, no arrows, no callouts, no garbled text, no price tags, no brand names)`。
   - 参考图忽略提示追加 `尺寸标注 / 测量线 / 标注箭头 / 尺码信息 / 技术图纸线条请全部忽略，不要以任何形式复制到生成图`，
     防止模型把参考图上的尺码标注当样本学习。

## 六、用户截图设置示例

见 `ai/agent-output/gallery_prompt_user_setting_sample.txt`：
按截图中「亚马逊主图 + 45度俯角 + 自然柔光 + 使用状态 + 标准色 + 高级质感风 + 自适应尺寸」
生成的完整提示词。可据此核对「选择什么出什么」，无未配置信息混入。

## 七、防乱码尺寸标注示例

见 `ai/agent-output/gallery_prompt_anti_text_sample.txt`：
针对「生成图出现乱码数字、尺寸标注、测量线」问题强化的提示词样例。重点查看：
- 【正向增强与约束】中的 `文字约束`（中英文双重禁止）
- 【正向增强与约束】中的参考图忽略提示（尺寸标注 / 测量线 / 标注箭头 / 尺码信息 / 技术图纸线条）
- 【负面提示词】中的 `画面问题`（含 `数字、字母、尺寸标注、测量线、标注箭头、乱码文字` 及英文 `no text / no numbers / no measurement marks` 等）

## 八、验证结果

- `python -m py_compile app/gallery_prompt.py app/gallery_config.py app/gallery_service.py` ✅
- `python -m pytest tests/test_gallery_prompt.py tests/test_gallery_ratio_prompt.py -q` → **22 passed** ✅
- 文件头解析已用截图中的真实图片验证：`(471, 644)` / `(483, 652)` → 自适应比例会推断为 `竖图 3:4`（768×1024），与原图比例一致 ✅
- 5 类场景采样（`ai/agent-output/gallery_prompt_v12_samples.txt`） + 用户截图设置样例
  （`ai/agent-output/gallery_prompt_user_setting_sample.txt`）+ 防乱码尺寸标注样例
  （`ai/agent-output/gallery_prompt_anti_text_sample.txt`）均呈现完整 8 维度结构且类型侧重正确。

## 九、生效方式

改了后端提示词引擎（`gallery_prompt.py` + `gallery_config.py`）和尺寸推断（`gallery_service.py`）→
**必须重启 `ai-agent-api` + `ai-agent-worker`，前端 Ctrl+F5**。

---

**附：关于「自适应尺寸」与参考图比例**

「自适应尺寸」表示「生成图比例与参考图/商品原图保持一致」。
它正确工作的前提是：该策划项已上传参考图或商品图（系统会读取其真实宽高并映射到最近生成尺寸）。
若未上传任何参考图，系统无法推断比例，会回退到模型默认尺寸（多数模型默认 1:1），
此时请显式选择 `竖图 3:4` 或 `方图 1:1` 等比例。
