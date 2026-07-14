# V7 全类型配置项重构 — 审查报告与修复总结

## 审查发现

### 致命 BUG：大部分配置字段被静默丢弃

提示词引擎 (`gallery_prompt.py`) 只显式处理了约 20 个标签名，其余所有类型的专属字段从未进入提示词。

**受影响类型**（字段全部被丢弃）：usp、pain、scene、detail2、model、design、cmp、ship、spec、pkg、buyer、promo

**不受影响类型**（字段正常注入）：bg、hero、tryon（因为这些类型的字段恰好命中了引擎的白名单）

### 10 个类型存在字段级问题

| 类型 | 问题 | 修复 |
|------|------|------|
| **bg** | "背景处理"与白底图定义矛盾 | → 展示重点 |
| **amz** | 3个字段全是固定值（平台已选/比例固定/背景固定） | → 产品角度/展示重点/组合方式 |
| **detail** | "放大倍率"(2x/3x) AI 不懂；"标注方式"属 detail2 | → 特写程度/光影效果 |
| **angle** | "旋转方向"对静态图无意义 | → 视角布局 |
| **usp** | 缺视觉氛围维度 | + 视觉氛围 |
| **pain** | "痛点类型"选项太泛；缺情绪基调 | → 痛点场景; + 情绪基调 |
| **scene** | "用户状态"含义模糊 | → 产品融入度 |
| **detail2** | "文字密度"与零文字策略矛盾 | → 信息密度; 加入 COPY_ALLOWED_TYPES |
| **model** | "代言人设"选项(KOL/真实用户)不可渲染 | → 人种肤色/性别物种/年龄维度 |
| **ship** | 安装步骤有"视频引导"(静态图无意义) | → 安装展示(整体示意/分步骤图解/爆炸拆解图) |
| **spec** | "产品品类"冗余; "场景适配"有"视频封面" | 移除产品品类; → 画面用途 |
| **pkg** | "材质表现"选项是形容词非材质名 | → 包装材质(纸盒/天地盒/礼盒…) |

## 修复方案

### 1. 通用兜底机制（核心修复）

在 `_assemble` 的 M3 和 M4 之间新增 M3.5 通用兜底段：

```python
# M3.5 通用兜底：注入所有尚未被 M2/M3 显式处理的个性化字段
for lbl, val in cfg["personal"].items():
    if lbl not in _EXPLICITLY_HANDLED and lbl not in _STYLE_LABELS and val:
        vocab = STYLE_VOCAB.get(val)
        lines.append(f"{lbl}：{vocab}。" if vocab else f"{lbl}：{val}。")
```

**效果**：任何新增字段自动进入提示词，无需修改引擎代码。旧数据中的已废弃字段名也通过兜底正确注入。

### 2. 字段分类更新

```python
_STYLE_LABELS = {"视觉强化", "氛围浓度", "视觉氛围", "情绪基调"}
_SUBJECT_NEUTRAL_LABELS = {
    "场景环境", "光影效果", "产品角度",
    "互动形式", "构图方式", "情感传递", "产品融入度",
}
```

### 3. detail2 加入 COPY_ALLOWED_TYPES

detail2（细节展示图）在电商场景中需要标注文字（如"防水涂层"、"YKK拉链"），原零文字策略导致"标注方式"字段自相矛盾。加入允许文字类型后，M5 自动切换为允许少量版面文案。

### 4. 版本号 6→7

重启服务后 `seed_gallery_config` 自动检测版本变化，强制更新 DB 中的 `type_personal` 和 `common_options`。

## 验证结果

- **18/18 类型全部通过**：每个类型的每个字段都正确出现在生成的提示词中
- **旧数据兼容**：已废弃的字段名（产品品类/场景适配/安装步骤等）通过兜底机制正确注入
- **无矛盾**：Linter 矛盾检测通过，零文字类型与允许文字类型策略一致

## 修改文件

- `app/gallery_config.py` — TYPE_PERSONAL(10类型) / PERSONAL_OPTIONS(新增11个字段) / COPY_ALLOWED_TYPES(+detail2) / GALLERY_CONFIG_VERSION(→7)
- `app/gallery_prompt.py` — _STYLE_LABELS(+) / _SUBJECT_NEUTRAL_LABELS(+) / _EXPLICITLY_HANDLED(新增) / M3.5 通用兜底

## 部署

重启 FastAPI 服务 + Ctrl+F5 刷新浏览器。
