# 提示词引擎 V11 · 比例跟随 + 正/负分离 说明

> 改动文件：`app/gallery_config.py`、`app/gallery_prompt.py`
> 配置版本号：`GALLERY_CONFIG_VERSION` 10 → 11

## 一、这些桶到底是怎么构造出来的（构造机制）

提示词由 **数据驱动流水线** 生成，每条指令都能追溯到「配置项 → 模板 → 桶」：

| 你看到的片段 | 来源 |
|---|---|
| 【主体】…【亚马逊主图】 | `PLAN_TYPES` 的 `title` + 有参考图时 `TYPE_SEMANTICS` 主体一致性锚定 |
| 【动作神态】产品状态呈现：使用状态。 | `amz` 类型「产品状态」字段 = `使用状态` → `SETTING_TEMPLATE["产品状态"]` 模板 → 路由 `ACTION` 桶 |
| 【穿搭配饰细节】配件组合呈现：仅产品主体。 | `amz`「配件关联」字段 → `SETTING_TEMPLATE["配件关联"]` → 路由 `OUTFIT` 桶 |
| 【背景环境细节】纯白背景（RGB 255,255,255） | `TYPE_SEMANTICS[amz].bg_mode="white"` → `WHITE_TECH["bg"]` |
| 【光影类型】产品光影处理：自然柔光。 | `amz`「产品光影」字段 → `SETTING_TEMPLATE` → 路由 `LIGHT` 桶 |
| 【色调色彩】纯色背景不额外施加任何彩色色调 | `bg_mode="white"` 分支固定文案 |
| 【镜头构图+相机参数】…45度俯角。 | `amz`「拍摄角度」字段 → `SETTING_TEMPLATE` → 路由 `CAMERA` 桶 + 白底硬性规范 + `TYPE_LAYOUT` |

**三个核心数据表**（都在 `gallery_config.py`，纯数据、可落库覆盖）：
- `TYPE_PERSONAL`：18 种类型的「个性化设置」字段（与 SeeAny 线上 UI 1:1）
- `SETTING_TEMPLATE`：每个字段 label → 一句含 `{v}` 的引导句式（"产品状态呈现：{v}。"）
- `BUCKET_ROUTING`：86 个 label → 10 个语义桶（SUBJECT/ACTION/OUTFIT/SCENE/BG/LIGHT/COLOR/CAMERA/QUALITY/MEDIUM）
- `TYPE_SEMANTICS`：每类型的权威约束（`bg_mode` 背景模式 / `person` 人物 / `platform_override` 平台 / `tech` 硬参数 / `medium` 渲染媒介）

## 二、本次修的两个问题

### 问题 1：比例写死 1:1（与用户选择矛盾）
旧逻辑：`WHITE_TECH` 写死 `"format": "1:1 正方形构图"`，所有白底类（bg/amz/detail/angle/detail2/design）一律注入 1:1。
→ 你选「自适应尺寸」却出现「1:1 正方形构图」，且选「竖图 3:4」时会出现「1:1」与「画面比例：严格按竖图 3:4」两行自相矛盾。

修复：
- 删除 `WHITE_TECH["format"]`，新增 `RATIO_FORMAT` 映射表（方图/竖图/横图 → 比例短语；**自适应尺寸 → None**）。
- 白底分支改为 `fmt = RATIO_FORMAT.get(cfg["ratio"])`：显式比例如实表述，自适应则不写死比例。
- 与 `gallery_service._ratio_to_size` 对齐：自适应在**后端**仍映射为 `1024x1024`（正方形），但**提示词层面尊重你的选择**，不再把 1:1 当成你主动指定的硬参数。
- 非白底类型的「画面比例：严格按 X 构图」逻辑本就比例感知，保持不变。

### 问题 2：正向词 / 负面词混在一起
旧逻辑：结尾是一个 `【品质增强与禁忌】` 块，把品质增强词、负面词、文字约束、参考图约束全堆在一起。

修复：拆成两块，界限清晰、便于模型解析——
- `【正向增强与约束】`：品质增强词 + 文字约束 + 参考图约束 + 收尾要求（**全部正向**）
- `【负面提示词】`：负面清单（独立成块，**全部负向**；无人物类型自动追加 人物/模特/人物剪影/手部出镜）

## 三、验证结果

- `py_compile` 通过
- `tests/test_gallery_prompt.py`：19 项全部 PASS
- `tests/test_gallery_ratio_prompt.py`：全部 PASS
- 复现场景 A（亚马逊主图 + 自适应尺寸）：含 `1:1 正方形构图` = **False**，含 `【负面提示词】` = **True**
- 复现场景 B（同类型 + 竖图 3:4）：含 `3:4 竖版构图` = **True**，含 `1:1` = **False**

## 四、生效须知
修改了后端提示词引擎，**需重启 `ai-agent-api` + `ai-agent-worker`**，前端刷新（Ctrl+F5）后重新生成才会用上新逻辑。
