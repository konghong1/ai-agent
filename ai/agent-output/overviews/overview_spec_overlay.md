# 规格参数图中文乱码修复 — 方案 A：纯视觉图 + 后端文字叠加

## 问题
用户贴出的规格参数图里，尺码表、测量标注（衣长/裙长/袖长/胸围）全是乱码。

**根因**：扩散模型（Agnes / SD 系列）对汉字字形渲染能力极弱，直接在画面里让模型写中文必然乱码。这不是提示词写得好不好的问题，是模型底层能力限制。

## 选定方案（用户从 5 个方案中择定）
**方案 A**：图像模型只负责生成「干净无文字」的产品视觉，所有中文（尺码表、测量标注、补充说明）由后端用真实 CJK 字体精确绘制叠加，彻底消除乱码。

## 改动清单

### 新增 `app/spec_overlay.py`（核心叠加层）
- `resolve_spec_font()`：优先捆绑 `app/assets/fonts/simhei.ttf`（已从宿主 `C:/Windows/Fonts` 拷入仓库，容器 bind mount 可读），系统字体回退，最终回退 PIL 默认——保证不崩。
- `parse_spec_data(text)`：按 `；/\n` 分行 → 识别尺码（`110码` / `S,M,L` / 数字开头 `110`）→ 正则抽取「名称+数值[单位]」为表格列。返回 `{headers, rows}`。
- `overlay_spec(result_path, spec_text, note, title, category)`：合成「左侧产品(cover 裁剪到 60% 宽) + 右侧浅灰面板(标题/尺码表/补充说明) + 左侧半透明深色尺寸图例」，存为新 `results/xxx.png` 并返回相对名。
- `overlay_spec_image(...)`：纯内存版，供单测/预览复用。

### 提示词改造（让模型不出文字）
- `app/gallery_prompt_ai.py`
  - `_PROMPT_SYSTEM` 第 6 条：spec 改为「画面严禁任何文字，产品居左、右侧预留空白面板、可含极简测量引导线/人体剪影，数据不进图像模型」。
  - `build_user_config_text` 的 spec 分支：告知模型「纯视觉 + 后端叠加、严禁绘制文字」，数据作为叠加层输入（不进图像模型）。
  - `_strip_cjk`：**去掉 spec 例外**——spec 的 `prompt_en` 也必须纯英文，杜绝中文泄漏到图像模型。
- `app/gallery_prompt.py`
  - `_decide_copy_policy`：spec 改 `allow_text=False`（画面零文字）。
  - `_assemble` / `_assemble_en` 的 spec 段改为无文字视觉指令；note 注入对 spec 跳过（补充说明改由叠加层渲染）。

### 生成流程挂载
- `app/gallery_service.py` 的 `run_gallery_task`：spec 类型且 `real` 有 filename 时调用 `overlay_spec`，更新 `rec.result_filename / result_url`。

## 验证
- `py_compile` 全过。
- `pytest` **41 passed**（原 40 + 新增 `test_spec_overlay_parse_and_render`；同步改写 spec 旧断言：数据进 AI 输入、prompt_en 零中文、模板零文字、strip_cjk 去 spec 例外）。
- 容器内实测 `resolve_spec_font`(FreeTypeFont) / `parse_spec_data` / `overlay_spec_image` 均正常。
- 本地生成演示图 `ai/agent-output/verify-shots/spec_overlay_demo.png`（尺码表 + 尺寸图例 + 补充说明，中文清晰、无乱码）。
- `docker restart ai-agent-api` 已生效。

## 你下一步
在「规格参数图」属性设置的 **规格参数原文** 粘贴真实尺码数据，例如：
```
110码 衣长62 胸围72 腰围66；120码 衣长67 胸围76 腰围70
```
重新生成 → 出图自动叠加干净中文尺码表 / 标注，不再乱码。

## 注意 / 坑
- **字体是方案 A 的前提**：容器原本零 CJK 字体，已捆绑 `simhei.ttf`。它是 Windows 专有字体，生产分发建议换成 OFL 许可的 **Noto Sans SC**（代码 `_FONT_CANDIDATES` 已优先尝试 NotoSansCJK 路径，将来容器装了即自动切换）。
- 之前 `_assemble_en` 残留中文测量标签（`衣长/裙长…`）会泄漏进英文提示词，已改为纯英文 `length/chest/sleeve/waist`。
- 前端「规格参数原文」输入框仍建议 Docker build 后变 textarea（上轮已说明），不影响本次修复。
