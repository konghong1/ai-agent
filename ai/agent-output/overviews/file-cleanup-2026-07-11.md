# 根目录产物整理（2026-07-11）

## 背景
项目根目录被 Agent 生成的各种产物堆满（overview 文档、验证截图、构建日志），与项目源码/文档混在一起，难以辨认。

## 处理方案
新建 `ai/agent-output/`（Agent 产出专属命名空间），按性质分子目录，把"我生成的文件"全部归入：

```
ai/agent-output/
├── overviews/      # 24 个 overview*.md 任务总结
├── verify-shots/   # 18 张验证截图（原 root/verify_shots 11 张 + 根目录 verify_*.png 7 张，已合并）
└── logs/           # 4 个 web_build*.log 构建日志
```

## 移动明细
- `overview*.md`（24 个）→ `ai/agent-output/overviews/`
- 根目录 `verify_*.png`（7 个）+ 原 `verify_shots/*`（11 个）→ `ai/agent-output/verify-shots/`，并删除根目录原 `verify_shots/`
- `web_build*.log`（4 个）→ `ai/agent-output/logs/`

## 链接修正
`overview_ecommerce_gallery_style_fix.md` 内两处相对图片链接由 `verify_shots/` 改为 `../verify-shots/`（目录改名 + 深一层），其余 overview 引用的为裸文件名，不受影响。

## 明确未动（勿动）的文件
- 运行时数据：`agent.db`（被 `.env` 引用，运行中 SQLite，移动会破坏服务）、`ai_agent.db` 等
- 项目文档：`PRD.md` / `FDD.md` / `README.md` / `AGENTS.md` / `TASKS.md` / `MEDIA_MINIO_FIX.md`
- 既有目录与工具：`designs/`、`疑问/`、根目录 Python 工具脚本（`_build_*.py` 等）

## 后续约定
- overview 文档 → 写 `ai/agent-output/overviews/`
- 验证截图 → 写 `ai/agent-output/verify-shots/`
- 构建/运行日志 → 写 `ai/agent-output/logs/`
- 其它性质产物 → 在 `ai/agent-output/` 下按需增设子目录，不再散落根目录
