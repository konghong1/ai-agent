# 权限系统设计方案（两级委派 · 最细粒度 · 入团审批）

> 状态：Proposed → 实现中（Phase A 先落地，Phase B 随后）
> 演进自：ADR-027（团队空间）的权限模型。本方案**取代** ADR-027 中"角色基线自动给权"的简化做法，改为**数据驱动的可分配权限**。
> 约束：所有表结构改动必须兼容 **Docker + MySQL(`ai_agent`)** 部署（NOT NULL 列带 `server_default`，TEXT 列无默认值；生产加列靠 api 容器 `python -m app.db.init_db` 的 `sync_model_columns`）。

---

## 1. 核心诉求（来自用户）

1. 既然做就做**完整且可扩展**的方案。
2. **超级管理员(admin)** 可以给**团队管理员**分配菜单/功能权限。
3. **团队管理员** 可以给**普通用户**分配菜单/功能权限。
4. 权限要到达**最细粒度的功能**（不只是顶层菜单）。
5. 顺序：**先把菜单权限系统做完整** → **再做用户加入团队**（自申请需管理员审批+审批记录；团队管理员拉人需用户本人同意）。

---

## 2. 领域模型

### 2.1 三层主体（沿用 ADR-027）
- **系统超级管理员** `is_superuser=true`：平台级，拥有全部权限，可把任意权限指派给团队管理员。
- **团队管理员** `is_team_admin=true` + 持有 `team_admin_scopes`：被超管授予"可授予的权限范围"，可在该范围内给团队成员分配权限，并管理其团队。
- **普通用户** `team_members` 中的 `member`：仅持有被团队管理员分配的 `user_permissions`。

### 2.2 两级委派（Delegation Chain）
```
系统超管 ──(分配 scope)──▶ 团队管理员  ──(在 scope 内分配)──▶ 普通用户
   (team_admin_scopes)              (user_permissions)
```
- **scope** = 团队管理员"被允许授予"的权限码集合（超管定义上限）。
- 团队管理员给用户分配的权限码 **必须 ⊆ 自己的 scope**，否则拒绝（防越权）。
- 团队管理员自身的可用权限 = 超管在分配 scope 时**同时**写入其 `user_permissions` 的那部分（即"能管就能用"）。

### 2.3 最细粒度：权限目录（数据驱动、可扩展）
权限以 **`permission_code`** 为原子单位，按 `category`（对应菜单分组）组织。新增功能只需：
1. 在代码常量里加一行（`PERM_*`）；
2. 种子函数 upsert 进 `permission_catalog` 表；
3. 前端菜单/按钮引用该 code → **UI 自动出现，无需改表结构**。

**建议目录（首版，可继续细化）**

| category(菜单) | permission_code | 说明 | 系统级(仅超管可授) |
|---|---|---|---|
| dashboard | `dashboard.view` | 工作台首页 | 否 |
| chat | `chat.use` | 进入聊天 | 否 |
| chat | `chat.session.create` | 新建会话 | 否 |
| chat | `chat.session.delete` | 删除会话 | 否 |
| chat | `chat.export` | 导出对话 | 否 |
| knowledge-base | `kb.read` | 查看知识库 | 否 |
| knowledge-base | `kb.write` | 编辑知识库 | 否 |
| knowledge-base | `kb.delete` | 删除知识库 | 否 |
| knowledge-base | `kb.share` | 共享知识库 | 否 |
| gallery | `gallery.use` | 进入电商套图 | 否 |
| gallery | `gallery.task.create` | 创建套图任务 | 否 |
| gallery | `gallery.task.remix` | 一键 remix | 否 |
| gallery | `gallery.task.delete` | 删除套图任务 | 否 |
| gallery | `gallery.publish` | 发布为创作案例 | 否 |
| media | `media.use` | 素材库 | 否 |
| media | `media.upload` | 上传素材 | 否 |
| media | `media.delete` | 删除素材 | 否 |
| memory | `memory.use` | 长期记忆 | 否 |
| memory | `memory.edit` | 编辑记忆 | 否 |
| mcp | `mcp.view` | 查看 MCP | 否 |
| mcp | `mcp.manage` | 管理 MCP Server | 否 |
| skill | `skill.view` | 查看 Skill | 否 |
| skill | `skill.manage` | 管理 Skill | 否 |
| hook | `hook.view` | 查看 Hook | 否 |
| hook | `hook.manage` | 管理 Hook | 否 |
| team | `team.view` | 团队空间入口 | 否 |
| team | `team.members.manage` | 成员管理 | 否 |
| team | `team.permissions.manage` | 成员权限分配 | 否 |
| team | `team.settings.manage` | 团队设置 | 否 |
| admin | `admin.users.manage` | 用户管理(平台) | **是** |
| admin | `admin.system.manage` | 系统/Provider 等 | **是** |
| admin | `admin.permissions.manage` | 团队管理员权限分配 | **是** |

> 菜单可见性规则：菜单项绑定一个"视图权限码"（多为 `*.view` / `*.use`），`can(user, code, team_id)` 为真才渲染。超管恒真。

---

## 3. 数据模型（新增/变更）

### 3.1 新增 `permission_catalog`（目录注册表，种子化）
```
code          VARCHAR(80) PK        # 如 "gallery.task.delete"
name          VARCHAR(120) NOT NULL
category      VARCHAR(40) NOT NULL  # 菜单分组 key
description   TEXT  (无默认值)
sort_order    INT  DEFAULT 0
is_system     BOOLEAN NOT NULL DEFAULT 0  # 仅超管可授予
created_at    DateTime server_default now
```

### 3.2 新增 `team_admin_scopes`（超管给团队管理员的"可授予范围"）
```
id                 INT PK
team_admin_user_id INT FK(users.id) INDEX
team_id            INT NULL  # 预留：NULL=对该管理员所有团队生效
permission_code    VARCHAR(80) NOT NULL  # FK 逻辑关联到 catalog.code
granted_by_user_id INT FK(users.id)
created_at         DateTime
UNIQUE(team_admin_user_id, team_id, permission_code)
```
> 该表存在即代表此用户是"团队管理员"（同时其自身 `user_permissions` 会被写入等效权限以便使用）。

### 3.3 新增 `user_permissions`（用户实际持有权限，单一真源）
```
id             INT PK
user_id        INT FK(users.id) INDEX
team_id        INT NULL  # NULL=个人空间权限；非NULL=该团队内权限
permission_code VARCHAR(80) NOT NULL
granted_by_user_id INT FK(users.id)
created_at     DateTime
UNIQUE(user_id, team_id, permission_code)
```
> **取代** `TeamMember.permissions`(JSON) 作为权限真源；`TeamMember.role` 仅保留为组织角色标签。

### 3.4 变更 `users`
- 新增 `is_team_admin BOOLEAN NOT NULL DEFAULT 0`（`server_default "0"`）——超管分配 scope 时置 1，便于快速判定/UI。

### 3.5 变更 `team_join_requests`（审批记录，Phase B 用）
- 现有 `reviewed_by` 保留；新增 `reviewed_at DATETIME`、`review_comment TEXT`。

### 3.6 变更 `team_invites`（用户同意，Phase B 用）
- 现有字段保留；新增 `reviewed_at`/`responded_at DATETIME`、`comment TEXT`（记录响应备注）。

### 3.7 新增 `approval_logs`（审批审计轨迹，Phase B 用）
```
id           INT PK
team_id      INT FK(teams.id)
target_type  VARCHAR(20) NOT NULL  # join_request | invite
target_id    INT NOT NULL
action       VARCHAR(20) NOT NULL # approve|reject|accept|decline
actor_id     INT FK(users.id)     # 操作人(审批者/响应者)
comment      TEXT
created_at   DateTime
```
> "包括审批记录" → 用专用审计表，而非只在请求行上留字段，便于追溯与扩展。

---

## 4. 权限判定（集中收敛）

`app/permissions.py` 重写为：
```python
def can(user, perm, team_id=None, db=None) -> bool:
    if user.is_superuser: return True
    if db is None: return False
    # 查 user_permissions：个人空间(team_id=None)只匹配 NULL 行；团队空间匹配该团队或 NULL 行
    ...
def get_user_permissions(user_id, team_id, db) -> set[str]: ...
def get_team_admin_scope(user_id, db) -> set[str]: ...
def is_team_admin(user, db) -> bool: ...   # 查 team_admin_scopes 或 user.is_team_admin
def ensure_personal_defaults(user_id, db):  # 个人空间默认权限(首次/迁移补齐)
```
**禁止散落 `role=="admin"` / `is_superuser` 检查**，全部走 `can()`。

---

## 5. API 设计（Phase A）

| 方法 | 路径 | 守卫 | 说明 |
|---|---|---|---|
| GET | `/api/permissions/catalog` | 登录即可 | 返回目录；超管见全部，团队管理员仅见自己 scope 内可授项 |
| GET | `/api/me/permissions?team_id=` | 登录 | 返回当前用户在该空间的有效权限码（前端菜单过滤用） |
| GET/POST | `/api/admin/team-admins` | `require_superuser` | 列出/设置团队管理员（设置=写 `team_admin_scopes` + 自身 `user_permissions` + `is_team_admin=1`） |
| GET/POST/DELETE | `/api/admin/team-admins/{uid}/scope` | `require_superuser` | 读/改某团队管理员的授予范围 |
| GET/POST/DELETE | `/api/teams/{tid}/members/{uid}/permissions` | 团队管理员(scope 内) | 读/改某成员在团队内的权限（码必须 ⊆ 管理员 scope） |

Phase B（用户加入团队）：
| 方法 | 路径 | 守卫 | 说明 |
|---|---|---|---|
| POST | `/api/teams/{tid}/join-requests` | 登录 | 用户自申请，status=pending |
| GET | `/api/teams/{tid}/join-requests` | 团队管理员 | 待审列表 |
| POST | `/api/teams/{tid}/join-requests/{rid}/review` | 团队管理员 | approve/reject + comment → 写 approval_logs；approve 建成员+授默认权限 |
| POST | `/api/teams/{tid}/invites` | 团队管理员 | 拉人，status=pending |
| POST | `/api/invites/{iid}/respond` | 被邀请用户 | accept/decline（用户本人同意）→ 写 approval_logs；accept 建成员 |

---

## 6. 前端（Phase A.3）

- **菜单**：`BasicLayout` 启动时拉 `/api/me/permissions`，菜单项带 `permission` 字段，`can` 为假则不渲染（**替换 `ADMIN_ONLY_KEYS` 硬编码**）。
- **超管控制台** `/admin/team-admins`：勾选目录分配团队管理员 scope。
- **团队管理员控制台** `/teams/:id/permissions`：勾选（仅限自己 scope）分配给成员。
- 菜单/按钮级：后续把 `gallery.task.delete` 等挂到对应按钮 `disabled` 上，做到"最细粒度"。

---

## 7. 实现顺序与取舍

1. **Phase A.1** 数据模型 + 目录种子（MySQL 验证）→ 地基。
2. **Phase A.2** `can()` 重写 + 分配 API（MySQL/接口验证）。
3. **Phase A.3** 前端菜单权限化 + 两个控制台（Playwright 真机验证）。
4. **Phase B** 入团审批流（自申请+审批记录 / 邀请+同意）+ 前端 UI。

**关键取舍（Trade-offs）**
- *用独立 `user_permissions` 表而非 JSON 列*：换来可查询、可审计、可做跨层委派；代价是多表关联（已用索引缓解）。
- *scope 上限由超管设定*：防止团队管理员越权授出 `admin.*`；代价是超管需先配一次。
- *目录种子化*：换来扩展性与 UI 自动渲染；代价是代码常量与表需保持同步（种子 upsert 兜底）。
- *审批用专用 `approval_logs`*：换来完整审计轨迹；代价是多写一张表（值得）。

---

## 8. 验证计划（铁律：动代码须验证）
- 后端：隔离副本 + 真实 MySQL `sync_model_columns` 建表/加列预验证；`docker restart ai-agent-api` 启动链路无 traceback；接口用超管/团队管理员/普通用户三角色实测。
- 前端：Playwright 真机——超管见全部、konghong 经超管分配 scope 后见扩展面、普通用户仅见被授权项、无权限菜单不渲染。
- 真实数据：零破坏性；个人空间默认权限为现有用户补齐（幂等）。
