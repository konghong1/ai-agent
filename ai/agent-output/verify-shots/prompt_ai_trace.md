# 提示词 AI 溯源报告（真实调用验证）

## 1. 喂给 AI 的输入（prompt_input）—— 即「我们告诉模型用户配了啥、要产出啥」
```
【生成方向】amazon_main

【核心卖点】高品质女童汉服套装，精致刺绣，复古风格

【市场配置】
- 目标市场：全球
- 销售平台：亚马逊
- 品类：童装
- 目标人群：儿童

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
```

## 2. AI 原始返回（prompt_raw）—— 模型实际吐出的内容
```


{
  "prompt_cn": "亚马逊主图标准布局，纯白背景棚拍。采用45度俯视视角，女童汉服套装精准居中，四周保留均匀合规电商留白。严格锁定并还原参考图中服装的真实版型、复古刺绣纹样、面料肌理与原有配色，绝不修改产品本体结构。采用柔和均匀的无影商业布光，细腻呈现精致刺绣的立体浮雕感与材质的高级光泽。整体为极简干净的全球化童装类目主图视觉，超高清画质，无文字水印，无多余装饰，突出产品核心质感。",
  "prompt_en": "Amazon main image composition, pure white background #FFFFFF studio photography, 45-degree overhead angle, girls Hanfu outfit set centered, uniform compliant e-commerce whitespace around, strict preservation of reference product silhouette, vintage embroidery patterns detail, authentic fabric texture, original color scheme, no structural alterations to product, soft even shadowless studio lighting, intricate embroidery relief highlight, premium material sheen, professional commercial e-commerce photography, ultra sharp focus, minimalist clean layout, optimized for global children's clothing category, no text, no watermark, no extra props, no human model, no mannequin --no text, watermark, logo, additional props, dark background, flat lay, distorted embroidery, low resolution, blur, oversaturated, human figures, 3d render, cartoon, illustration"
}
```

## 3. 解析后的提示词
- **prompt_source**: `ai`
- **中文展示版 (prompt_cn)**:
亚马逊主图标准布局，纯白背景棚拍。采用45度俯视视角，女童汉服套装精准居中，四周保留均匀合规电商留白。严格锁定并还原参考图中服装的真实版型、复古刺绣纹样、面料肌理与原有配色，绝不修改产品本体结构。采用柔和均匀的无影商业布光，细腻呈现精致刺绣的立体浮雕感与材质的高级光泽。整体为极简干净的全球化童装类目主图视觉，超高清画质，无文字水印，无多余装饰，突出产品核心质感。
- **英文生成版 (prompt_en)**:
Amazon main image composition, pure white background #FFFFFF studio photography, 45-degree overhead angle, girls Hanfu outfit set centered, uniform compliant e-commerce whitespace around, strict preservation of reference product silhouette, vintage embroidery patterns detail, authentic fabric texture, original color scheme, no structural alterations to product, soft even shadowless studio lighting, intricate embroidery relief highlight, premium material sheen, professional commercial e-commerce photography, ultra sharp focus, minimalist clean layout, optimized for global children's clothing category, no text, no watermark, no extra props, no human model, no mannequin --no text, watermark, logo, additional props, dark background, flat lay, distorted embroidery, low resolution, blur, oversaturated, human figures, 3d render, cartoon, illustration
