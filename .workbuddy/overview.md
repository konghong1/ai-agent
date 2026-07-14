# 电商套图 · 提示词生成质量强化（8 维强制 + 单图多视角/多场景逐格）

## 用户诉求
AI 生成的提示词仍不满意，要求按 8 维结构
`[主体]+[细节修饰]+[场景环境]+[构图视角]+[光影质感]+[画质技术参数]+[风格参考]+[负面约束]`
生成；特别是多视角/多场景图，要让 AI 在**单张图内**根据描述生成不同场景与细节（含九宫格、左右分屏等构图），且整体更细节。

## 已完成

### 1. AI 系统提示词重写（单图 + 批量）
- `app/gallery_prompt_ai.py` 的 `_PROMPT_SYSTEM` / `_PROMPT_BATCH_SYSTEM` 改为**强制 8 维全部覆盖且写细**，不再"省略无关维度"。
- 新增「单图多视角/多场景」版式硬规则：
  - 先定整图网格：`2×2 四宫格` / `3×3 九宫格` / `左右分屏` / `上下分屏` / `田字格` / `主图+辅图环绕`；
  - 对**每一格逐一写**【主体(该视角/状态) + 场景环境 + 光影质感 + 构图视角 + 细节修饰】，每格有独立具体的场景/角度/细节，不空泛重复；
  - 跨格产品外观(颜色/版型/材质/logo)严格一致，仅改变视角/场景/光影；
  - 格间细线/留白分隔，整图光影统一。

### 2. 多格版式自动判定与注入
- 新增 `_detect_multi_cell(item)`：扫描 `type_id==angle` 及配置值中的 拼接/拼贴/宫格/分屏/多场景/多视角/多角度/九宫格/四宫格/左右对比/上下对比/产品主体+多场景 等关键词，
  返回「多视角拼贴」或「多场景拼接」中文指令。
- 注入 `build_user_config_text`（单图）与 `build_batch_user_config_text`（批量每项），让 AI 看到明确版式要求。

### 3. 模板兜底引擎同步
- `app/gallery_prompt.py` 新增 `_detect_multi_cell_type(cfg)`（与 AI 口径一致）。
- `_assemble`(中) / `_assemble_en`(英) 检测单图多格时追加逐格场景/角度/光影描述指令，降级路径与 AI 路径一致。

### 4. 预算上调
- `AI_PROMPT_MAX_TOKENS` 4096 → 6144，给更细逐格提示词留足额度（推理模型思维链占额，重试仍升 8192）。

## 交付文件
- `app/gallery_prompt_ai.py`（系统提示词 + 多格判定 + 注入 + 预算）
- `app/gallery_prompt.py`（模板兜底多格指令）
- `tests/test_gallery_prompt_ai.py`、`tests/test_gallery_prompt.py`（新增 4 个用例）

## 验证
- `pytest tests/test_gallery_prompt.py + tests/test_gallery_prompt_ai.py` **49 passed**（45 + 4 新增）
- 4 文件 `py_compile` 全部通过

## 下一步
- `docker restart ai-agent-api` 使后端改动生效（bind mount 免 rebuild）。
- 实测一次多视角/多场景生成，确认逐格描述符合预期；若仍偏模板腔，可再收紧系统提示词或调高温度（当前 0.75）。
