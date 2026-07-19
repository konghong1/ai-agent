# ADR-029: 权限划分调整与团队入团审批流（Phase A + Phase B 落地）

## Status
Accepted

## Context

在 `plan-permission-rbac.md`（取代 ADR-027 简化角色基线）的两级委派 RBAC 骨架之上，用户要求两件事：

1. **调整 Phase A 的权限划分**：让超管能给团队管理员分配"菜单/功能权限"，自动注册用户拿到基础角色权限，团队管理员能看到超管授予的权限 + 基础权限。具体诉求：仅超管可授范围、细化权限粒度、理顺分类与菜单结构（把 AI 提供商 / 提示词模板纳入权限门控）。
2. **实现 Phase B：团队入团审批流**：用户可发现团队并自申请，团队管理员审批（写审批记录）；团队管理员可邀请，被邀请用户本人同意后才入团。

验证过程中还暴露一个**阻断性缺陷**：`/auth/me` 的响应模型 `UserRead` 没有 `is_team_admin` 字段，导致团队管理员的标志永远到不了前端，`Teams.tsx` 的 `canManage`（`is_superuser || is_team_admin`）对真实团队管理员恒为 false——Phase B 的"待审申请/邀请管理"标签根本无法出现。

## Decision

### 1. Phase A 权限划分调整（数据驱动 + 菜单门控）

- **新增 4 个权限码**（目录 `permission_catalog` 种子，均 `is_system=False`）：
  - `providers.view` / `providers.manage`（分类 `providers`，排序 66/67）
  - `prompt.view` / `prompt.manage`（分类 `prompt`，排序 68/69）
- **修复 `PERSONAL_DEFAULT` 遗漏**：补齐 `hook.view`（原漏）、`providers.view`、`prompt.view`、`team.view`。这是所有用户（含自动注册）的"基础角色"权限，超管通过 `backfill_base_permissions()` 给现有用户补齐。
- **菜单门控**：`BasicLayout.MENU_PERM` 新增 `"/providers": "providers.view"`、`"/prompt-templates": "prompt.view"`；`/users`→`admin.users.manage`、`/teams`→`team.view` 维持。菜单按 `user.permissions` 过滤，超管（`is_superuser`）看全部。
- **`is_system` 维持仅 3 项**：`admin.users.manage` / `admin.system.manage` / `admin.permissions.manage`。团队管理员 scope 永不含 `admin.*`，越权授予以 400 拒绝。
- **委派链**：超管 → `team_admin_scopes`（scope）→ `user_permissions`（成员实际持有，单一真源）；`can()` 为唯一判定入口。

### 2. Phase B 团队入团审批流

**自申请路径**（成员主动）：
- `POST /api/teams/{tid}/join-requests`（pending）→ 管理员在「待审申请」标签 `review`：
  - `approve` → 幂等建/恢复活跃成员 + 授予 `PERSONAL_DEFAULT` 团队权限 + 写 `approval_logs`
  - `reject` → 仅写 `approval_logs`
- `GET /api/teams/discover`（排除已加入团队）、`GET /api/me/join-requests`、`GET /api/teams/{tid}/join-requests`（`require_team_admin`）

**邀请路径**（管理员主动）：
- `POST /api/teams/{tid}/invites`（pending，`message` 为 TEXT 可空列）→ `GET /api/me/invites`
- 被邀请用户 `POST /api/invites/{iid}/respond`：
  - `accept` → 建成员 + 授团队权限 + 写 `approval_logs`（本人同意才入团，满足"拉人需本人同意"）
  - `decline` → 写日志

**前端 `Teams.tsx`**：选项卡式——主 Tabs（团队空间 / 发现团队 / 我的申请 / 我的邀请），团队空间内嵌 Tabs（成员 / 待审申请[`canManage`] / 邀请管理[`canManage`]）。`canManage = !!(user?.is_superuser || user?.is_team_admin)`。

### 3. 修复 `UserRead.is_team_admin` 缺失（阻断性缺陷）

`app/schemas.py` 的 `UserRead` 原仅有 `is_superuser`，**漏掉 `is_team_admin`**。修复：新增 `is_team_admin: bool = False`。此后 `/auth/me` 正确返回团队管理员标志，前端 `canManage` 对真实团队管理员生效，`Teams.tsx` 的团队管理员专属标签/审批/邀请功能才可用。

> 该字段为纯序列化层新增，无 DB 迁移；`docker restart ai-agent-api` 即生效。

## Consequences

**更容易**：
- 超管可精细分配菜单/功能权限给团队管理员，团队管理员在 scope 内再下放到成员，完全数据驱动、可扩展。
- 自动注册用户即获合理基础权限（含 `team.view` 能看到"团队"入口），无需手工补权。
- 入团双向确认（申请需管理员批 / 邀请需本人同意）+ 审批留痕，满足治理诉求。
- `is_team_admin` 修复后，团队管理员在 UI 上真正成为"管理员"，Phase B 功能闭环。

**更难 / 需注意**：
- 权限码持续膨胀，依赖 `permission_catalog` 种子与 `MENU_PERM` 手动同步；新增菜单项须同步登记权限码，否则要么全开（漏登记）要么不可见（错登记）。
- `can()` 是全局唯一判定入口，任何新增校验点都须走它，不能在路由里散落 `role==`/`is_superuser` 判断。
- 前端 Playwright 验证发现 antd v5 按钮标签带字间空格（`通 过`），文本选择器须用 `.ant-modal-content .ant-btn-primary` 或正则 `\s*`，不能硬匹配"通过"。

## 验证记录（生产真实 MySQL + Docker + Playwright 真机）

- **后端全链路**：自申请→审批→建成员(24 团队权限)+写日志 ✓；邀请→本人同意→建成员 ✓；discover 排除已加入 ✓；approval_logs 各 1 条 ✓。
- **前端 Playwright 真机**：admin 4 主标签 + 待审/邀请管理标签 + 邀请上架 ✓；普通用户发现团队+申请 ✓；admin 待审列表见申请人 → 点「审批」→ 点「通过」(`.ant-btn-primary`) → 成员建立 ✓；konghong 菜单隐藏 `用户管理`、显示 `AI 提供商`/`提示词模板`/`团队` ✓；修复后 konghong 在所属团队见 `待审申请`/`邀请管理` 标签 ✓。
- **临时数据与文件已清理**：测试团队/用户(pw%)经 FK 级联删除；所有 `_pw_*`/`_verify_phaseB.py`/`seed_tmp.py` 临时脚本删除。
