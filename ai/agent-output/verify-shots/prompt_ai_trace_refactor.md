# 提示词重构 · AI 路径真实调用溯源（优化后 8 维结构）

## 路由规则（本次重构落地）
- 下拉选择的推荐类型（如 亚马逊主图 amz）→ 走 AI 改写（generate_prompt_via_ai）
- 出图规划选「自定义子任务」→ 原样透传用户需求，prompt_source=custom，不调 AI
- 用户核心卖点 → 仅作为 AI 理解的参考，不可修改/杜撰

## 真实调用（Docker 容器内，agnes-2.0-flash）
- 类型：amz（亚马逊主图，推荐类型）
- 配置：45度俯角 / 居中产品构图四周留白 / 纯白背景棚拍 / 全球市场 / 亚马逊平台
- 核心卖点：高品质女童汉服套装，精致刺绣，复古风格
- **prompt_source = ai** （确认走大模型，非模板）

## 喂给 AI 的输入 prompt_input（362 字，即你的配置，无任何手写提示词）
【生成方向】亚马逊主图：符合平台规定的主图

【核心卖点】高品质女童汉服套装，精致刺绣，复古风格

【市场配置】
- 目标市场：全球
- 销售平台：亚马逊
- 目标人群：儿童
- 品类：童装

【出图规划·个性化配置】
- 拍摄角度：45度俯角
- 构图方式：居中产品构图，四周均匀留白

【通用设置】
- 电商平台：亚马逊
- 目标市场：全球
- 视觉风格：纯白背景棚拍

【出图比例】1:1

【参考图】已提供产品参考图，请据此理解产品的真实外观（颜色 / 版型 / 材质 / logo / 结构），并在提示词中保持产品一致，不得改变产品本身。

【你的任务】不要套用通用模板，请基于以上「用户配置 + 参考图」理解这个真实产品，写出一份贴合该产品、符合上述生成方向的差异化高质量提示词（中文展示版 + 纯英文生成版）。

## AI 原始返回 prompt_raw（646 字，模型真实输出 JSON）


{
  "prompt_cn": "亚马逊合规主图规格，主体为女童复古汉服套装居中呈现，45度俯角拍摄，纯白背景棚布光。精准还原高品质面料肌理与精致刺绣工艺，四周均匀留白符合平台裁剪规范。均匀柔光搭配真实接地阴影，色彩准确，边缘锐利，杜绝杂乱背景、文字水印与透视变形，1:1高清电商级画质。",
  "prompt_en": "Amazon compliant main image, centered girls' retro Hanfu set viewed from a 45-degree overhead angle, pure white background studio lighting. Accurately renders high-quality fabric texture and exquisite embroidery craftsmanship, even white margins around for platform cropping standards. Even soft lighting with realistic grounding shadow, precise color reproduction, sharp edges, no clutter, no text watermarks, no perspective distortion, 1:1 high-definition e-commerce quality."
}

## 最终提示词（中文 127 字，短小精炼，8 维流动体）
亚马逊合规主图规格，主体为女童复古汉服套装居中呈现，45度俯角拍摄，纯白背景棚布光。精准还原高品质面料肌理与精致刺绣工艺，四周均匀留白符合平台裁剪规范。均匀柔光搭配真实接地阴影，色彩准确，边缘锐利，杜绝杂乱背景、文字水印与透视变形，1:1高清电商级画质。

## 英文生成版 prompt_en（477 字）
Amazon compliant main image, centered girls' retro Hanfu set viewed from a 45-degree overhead angle, pure white background studio lighting. Accurately renders high-quality fabric texture and exquisite embroidery craftsmanship, even white margins around for platform cropping standards. Even soft lighting with realistic grounding shadow, precise color reproduction, sharp edges, no clutter, no text watermarks, no perspective distortion, 1:1 high-definition e-commerce quality.

## 模板兜底（AI 不可用时）也已精简
amz 类型中文提示词降至约 1328 字，去掉 8 个分桶标题、连续流动、保留全部硬约束。
