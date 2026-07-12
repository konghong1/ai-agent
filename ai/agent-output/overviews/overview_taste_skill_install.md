# 安装 Taste Skill 并确认项目适用性

## 来源
GitHub 开源项目 [`Leonxlnx/taste-skill`](https://github.com/Leonxlnx/taste-skill)（MIT 协议，*The Anti-Slop Frontend Framework for AI Agents*）——给 AI Agent 注入前端审美的 `SKILL.md` 规则矩阵。

> 注：WorkBuddy 推荐市场（BuiltinMarket）中**没有**名为「Taste」的 Skill（已用 Taste/taste/品味/审美/UI/design 多个关键字交叉搜索，0 命中）。用户指定从 git 获取，故走 GitHub 导入流程。

## 安全审计（结论：P2 / 安全，可安装）
- `skill.sh`：仅一个路径注册表（echo 路径），不执行命令、不联网、不删文件
- `scripts/*.mjs`：仓库维护用的 README 图片转换工具，不属于 skill 运行时，不安装
- 全部 13 个 `SKILL.md`：仅设计规则文本，扫描确认**无任何** `bash`/`terminal`/`npm`/`npx`/`git`/删除/联网/curl 等危险指令
- 无数据外泄、无特权操作、无混淆代码

## 安装结果
- 安装位置：**用户级** `~/.workbuddy/skills/`（团队任意项目可用，符合「提升团队技术水平」目标）
- 已装入 13 个子技能：
  - `taste-skill`（design-taste-frontend，v2 默认）
  - `taste-skill-v1`（遗留兼容）
  - `gpt-tasteskill`（GPT/Codex 强化）
  - `image-to-code-skill`（参考图→代码）
  - `imagegen-frontend-web` / `imagegen-frontend-mobile`（仅出参考图）
  - `brandkit`（品牌套件）
  - `redesign-skill`（改进已有 UI）
  - `soft-skill` / `minimalist-skill` / `brutalist-skill`（风格变体）
  - `output-skill`（强制完整输出）
  - `stitch-skill`（Stitch 集成）

## 项目适用性确认（已用 redesign-skill 清单实测）
项目是 **React/Vite 前端**（`web/src`），taste-skill 直接对口。对刚重构的 `EcommerceGallery` 组件做迷你审计，清单**确实产生具体发现**：

| redesign-skill 规则 | 项目现状 | 结论 |
|---|---|---|
| 禁止「AI 紫蓝 glow」 | `gallery.css:20` `--gb-ai-purple:#7C3AED` 作主品牌色 | ⚠️ 命中反模式，建议换中性底 + 单一克制强调色 |
| 禁止「均匀 AI 渐变」 | `gallery.css:135` `linear-gradient(135deg,#2A2A33,#46464F)` | ⚠️ 命中，建议径向/网格渐变或噪声叠层 |
| hover / active 态 | 多处 `:hover` + `transform:translateY` | ✅ 已符合 |
| tinted shadow | `box-shadow: var(--gb-sh-1)` 用 token | ✅ 已符合 |
| 字体有性格 | `--gb-font-body/--gb-font-display` 待确认是否 Inter/系统字体 | ❓ 若是则建议换 Geist/Outfit/Satoshi |

→ **确认：该 Skill 可在本项目中落地**，且已能输出可执行的改进项。

## 最相关子技能映射
- **`redesign-skill`** → 改进刚重做的电商套图 UI（属性设置弹窗 / AI 智能策划台）
- **`design-taste-frontend`** → 后续新建页面/落地页
- **`minimalist-skill` / `soft-skill`** → 若要把套图 UI 往 Linear/克制精致方向调
- **`output-skill`** → 确保我生成的 UI 代码完整、不省略

## 使用方式
在 WorkBuddy 的【技能管理】面板可见已安装的 taste-skill 系列。需要我对电商套图 UI 跑一轮正式 `redesign-skill` 审查并出改进方案时，直接说一声即可。
