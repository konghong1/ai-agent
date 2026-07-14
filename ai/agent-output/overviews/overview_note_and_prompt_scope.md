# 出图规划「补充说明」传入 AI + 提示词展示范围收窄

## 问题一：出图规划的「补充说明」没传给 AI

**根因**：`app/gallery_prompt_ai.py` 的 `build_user_config_text`（喂给 AI 的用户意图文本）读取了核心卖点 / 市场配置 / 个性化配置 / 通用设置 / 规格数据，但**完全漏掉了 `item.note`（补充说明）**。所以你在规划项里填的补充说明，AI 根本收不到。

**修复**（两条生成路径都覆盖，语义一致）：

| 文件 | 位置 | 改动 |
|------|------|------|
| `app/gallery_prompt_ai.py` | `build_user_config_text` 行 214-217 | 在【核心卖点】后新增 `【补充说明】{note}`，从 `item.note` 取值 |
| `app/gallery_prompt.py` | `_assemble` 中文 行 534-537 | `note` 非空时注入 `补充说明：{note}` |
| `app/gallery_prompt.py` | `_assemble_en` 英文 行 890-893 | **仅规格参数图(spec)** 注入 `supplementary note: {note}`（英文生成版对非规格类型执行零中文硬约束，避免泄漏中文；spec 类型允许中文故注入） |

> 说明：`generate_prompt_via_ai` 返回的 `prompt_input` 就是 `build_user_config_text` 的文本，因此前端「提示词溯源」面板的「喂给 AI 的输入」会自然包含补充说明。

## 问题二：提示词只在「任务列表」显示，详情/发布不显示

**现状核查**：`PromptBadge` 此前在两处渲染——任务列表（`index.tsx:1162`）、作品详情弹窗（原 1355-1359）；发布弹窗（1369+）本就没有提示词。

**修复**：移除详情弹窗的 `PromptBadge`（原 1355-1359 段），**只保留任务列表**。
- 任务列表：`index.tsx:1162` —— 保留 ✅
- 作品详情弹窗：已移除 ✅
- 发布弹窗：本就无 ✅

## 验证结果

- `py_compile` 四个文件全部通过（gallery_prompt_ai.py / gallery_prompt.py / 两个测试文件）。
- `pytest` **40 passed**（原 38 + 新增 2 个）：
  - `test_note_flows_into_ai_input` —— 校验补充说明进入 AI 输入文本 + 溯源 `prompt_input`
  - `test_note_in_template_prompt` —— 校验模板中文提示词含补充说明 + 规格图英文版含补充说明
- `docker restart ai-agent-api` 已生效（8010，startup complete）。

## 你这边需注意

1. **后端已即时生效**：在出图规划项填写「补充说明」并重新生成，AI 路径与模板兜底都会带上该内容。
2. **前端改动需构建才可见**：移除详情弹窗提示词徽标这一改动，要在 Docker 里执行 `cd web && npm install && npm run build` 后才能看到界面变化（本项目 web 目录无 vite 工具链，本机跑不了）。是否需要我帮你排一下前端构建？

## 改动文件清单

- `app/gallery_prompt_ai.py` — 补充说明注入 AI 输入
- `app/gallery_prompt.py` — 模板中/英兜底注入补充说明
- `web/src/pages/EcommerceGallery/index.tsx` — 移除详情弹窗 PromptBadge
- `tests/test_gallery_prompt_ai.py` — 2 个新测试
