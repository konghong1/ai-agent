# 规格参数图升级：测量标注 + 尺码表 + 人体剪影

## 目标
让「规格参数图」类型不再只出衣服主体，而是生成带测量箭头、中文尺码标签、尺码表、人体剪影的电商信息图。

## 改动

### 1. 后端配置 (`app/gallery_config.py`)
- `TYPE_PERSONAL["spec"]` 新增字段 `规格参数原文`（用户粘贴真实尺码/参数数据）。
- `COPY_ALLOWED_TYPES` 加入 `"spec"`，允许规格参数图在画面呈现文字。

### 2. AI 提示词引擎 (`app/gallery_prompt_ai.py`)
- `_PROMPT_SYSTEM` 新增「规格参数图」特殊规则：
  - 服饰类必须含测量箭头、中文标注（衣长/裙长/袖长/胸围）、尺码表、人体剪影。
  - 用户提供了 `规格参数原文` 则必须严格填入表格，不得编造。
  - 明确 `prompt_en` 允许保留中文标签/表头/数据（规格参数图例外）。
- `_strip_cjk` 增加 `type_id` 参数，对 `spec` 类型保留中文，其余仍零中文。
- `build_user_config_text` 对 `spec` 单独输出「规格参数图·数据强制」段，把用户数据强调查给模型。

### 3. 模板兜底 (`app/gallery_prompt.py`)
- `_decide_copy_policy` 对 `spec` 强制 `copy_language=中文`。
- `_assemble`（中文）新增 `spec` 专用块：左侧产品主体 + 测量箭头 + 尺码表 + 人体剪影 + 真实数据回填。
- `_assemble_en`（英文）同样新增 `spec` 块，并保留中文标签/表头/数据。

### 4. 前端输入 (`web/src/pages/EcommerceGallery/TypeSettingsModal.tsx`)
- `规格参数原文` 字段渲染为 `Input.TextArea`（3 行），方便粘贴多行尺码数据。
- 需要 Docker 里 `cd web && npm install && npm run build` 才生效。

## 验证
- `py_compile` 五文件全过。
- `pytest tests/test_gallery_prompt.py + tests/test_gallery_prompt_ai.py`：**38 passed**（新增 3 模板 + 2 AI 测试）。
- 模板兜底输出示例：
  - 中文：含「尺码表」「衣长/裙长/袖长/胸围」「身高/年龄段」「人体剪影」、真实数据落地。
  - 英文：含对应中文标签/表头/数据，便于中文图像模型正确渲染。
- `docker restart ai-agent-api` 生效，服务正常启动。

## 用户下一步
1. 在「规格参数图」属性设置里填写 `规格参数原文`，例如：
   ```
   110码 衣长62 胸围72 腰围66
   120码 衣长67 胸围76 腰围70
   130码 衣长72 胸围80 腰围74
   ```
2. 重新生成图片，即可得到带测量标注 + 尺码表 + 人体剪影的规格参数图。
3. 前端 textarea 输入框需 Docker build 后才可见；当前可用单行输入框先粘贴数据。
