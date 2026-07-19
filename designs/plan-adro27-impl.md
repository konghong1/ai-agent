# ADR-027：团队空间（Team Space）详细实现方案

> 状态：**Accepted · 进入实现**（原 ADR-027 为 Proposed，本文件为落地细化方案）
> 关联：ADR-026（产品定位：扩展面是管理员域）/ ADR-028（系统级超管 `is_superuser` 已落地，菜单按 `is_superuser` 过滤）
> 铁律：本方案所有模型/迁移改动**必须兼容容器部署的 MySQL(`ai_agent`)**，新增 NOT NULL 列必须带 `server_default`；TEXT 列禁带默认值。

---

## 1. 背景与问题（Context）

用户 `konghong`（`kh1763751448@gmail.com`，`role=admin`、`is_superuser=0`）反馈两件事：
1. **"我是团队管理员了，在哪里可以添加我的团队成员"** —— 当前系统**没有任何团队功能**（后端 `app/` 搜 `team/Team/TeamMember` 零匹配），ADR-027 此前停留在 Proposed，从未落地。
2. **"为啥看不到 skill 等配置"** —— `BasicLayout.tsx` 把 `/mcp-servers /skills /hooks /users` 锁在 `is_superuser` 后；`konghong` 是 `role=admin` 但非超管，故全隐藏。

**根因**：产品定位(ADR-026)说扩展面是"管理员域"，但 ADR-028 落地时为简单把门槛抬到了系统超管；而真正该管扩展面+成员的"团队管理员"层级(ADR-027)压根没建。于是 `role=admin` 对界面毫无作用，团队能力完全缺失。

**本方案目标**：落地团队空间，使"团队管理员"成为真实存在的角色，能建团队、加成员、管扩展面配置；同时保留系统超管(`is_superuser`)作为平台级最高权限。

---

## 2. 领域模型（Domain）

### 2.1 有界上下文
- **认证上下文**（已存在）：User、凭证、系统超管。
- **团队上下文（新建）**：Team、TeamMember、TeamInvite、TeamJoinRequest。
- **资源上下文**（已存在，需加 `team_id` 做空间归属）：Gallery / KB / Chat / Agents / 扩展面(MCP/Skill/Hook)。

### 2.2 聚合与不变式
- **Team 聚合根**：`owner_id` 固定为首创人；删除团队级联删 `team_members`、置空资源 `team_id`（或随团队删，按资源定）。
- **TeamMember 不变式**：同一 `(team_id, user_id)` 唯一；`role ∈ {owner, admin, member}`；`owner` 至少保留 1 人。
- **TeamInvite 不变式**：`token` 唯一、可过期；接受后生成 `TeamMember` 并置 `accepted_at`。
- **TeamJoinRequest**：用户主动申请，owner/admin 审批。

---

## 3. 数据模型

### 3.1 新增 4 张表（Phase 1，新建表，低风险）

```python
class Team(TimestampMixin, Base):
    __tablename__ = "teams"
    id          = mapped_column(Integer, primary_key=True)
    name        = mapped_column(String(120), unique=True, index=True)
    slug        = mapped_column(String(120), unique=True, index=True)
    description = mapped_column(Text, default="")                 # TEXT 禁带默认值
    owner_id    = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    settings    = mapped_column(SA_JSON, default=dict)
    enabled     = mapped_column(Boolean, default=True, server_default=text("1"), nullable=False)

class TeamMember(TimestampMixin, Base):
    __tablename__ = "team_members"
    id          = mapped_column(Integer, primary_key=True)
    team_id     = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id     = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role        = mapped_column(String(40), default="member", server_default=text("'member'"), nullable=False)
    permissions = mapped_column(SA_JSON, default=list)            # 成员级覆盖(perm 字符串列表)
    invited_by  = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status      = mapped_column(String(20), default="active", server_default=text("'active'"), nullable=False)
    __table_args__ = (UniqueConstraint("team_id","user_id", name="uq_team_user"),)

class TeamInvite(TimestampMixin, Base):
    __tablename__ = "team_invites"
    id          = mapped_column(Integer, primary_key=True)
    team_id     = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    email       = mapped_column(String(255), index=True)
    token       = mapped_column(String(64), unique=True, index=True)
    role        = mapped_column(String(40), default="member", server_default=text("'member'"), nullable=False)
    invited_by  = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at  = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at = mapped_column(DateTime(timezone=True), nullable=True)
    status      = mapped_column(String(20), default="pending", server_default=text("'pending'"), nullable=False)

class TeamJoinRequest(TimestampMixin, Base):
    __tablename__ = "team_join_requests"
    id          = mapped_column(Integer, primary_key=True)
    team_id     = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    user_id     = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message     = mapped_column(Text, default="")
    status      = mapped_column(String(20), default="pending", server_default=text("'pending'"), nullable=False)
    reviewed_by = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
```

### 3.2 资源表加可空 `team_id`（Phase 2，扩展现有表）
对核心资源表加 `team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)`：
`gallery_tasks / gallery_records / gallery_projects / knowledge_bases / threads / agents / mcp_servers / skills / hooks`。
- `NULL` = 个人空间；有值 = 团队空间。
- 全部**可空**，迁移用 `sync_model_columns` 自动 `ADD COLUMN ... NULL`，对 MySQL 非空表安全。
- `user_id` 语义改为"创建者"，权限判定改用 `can()`。

---

## 4. 角色与权限目录

### 4.1 三层角色
| 层级 | 标识 | 来源 | 能力 |
|---|---|---|---|
| 系统管理员 | `is_superuser=1` | seed/提拔(ADR-028) | 平台运维，**放行一切** `can()`；含用户管理 |
| 团队 owner | `TeamMember.role='owner'` | 创建团队自动获得 | 团队全权 + `team.members.manage` + 扩展面 manage |
| 团队 admin | `TeamMember.role='admin'` | owner 指派 | 成员管理 + 扩展面 manage（不能删团队/转移 owner） |
| 团队 member | `TeamMember.role='member'` | 被加/接受邀请 | 按基线用消费类能力 |

### 4.2 功能权限目录（代码常量，非 DB）
```
chat.use
kb.read / kb.write
gallery.use
media
memory
mcp.use / mcp.manage
skill.use / skill.manage
hook.manage
team.members.manage
```
- **角色基线 `ROLE_BASELINE`**：owner/admin 含全部 `*.manage` + 消费类；member 仅 `*.use` + 消费类。
- **个人空间 `PERSONAL_DEFAULT`**：自注册用户默认拥有全部 `*.use` + 消费类（保持现状体验）。

### 4.3 集中判定 `can(user, perm, team_id)`
```python
def can(user, perm, team_id=None) -> bool:
    if user.is_superuser: return True                      # 系统超管放行
    if team_id is None:    return perm in PERSONAL_DEFAULT  # 个人空间
    member = get_member(user.id, team_id)
    if not member or member.status != "active": return False
    baseline = ROLE_BASELINE[member.role]
    overrides = set(member.permissions or [])
    if perm in overrides: return True
    return perm in baseline
```
- 散落的 `role=="admin"` / `is_superuser` 检查统一收敛到 `can()`。

---

## 5. 入伙 4 路径
1. 自注册 → 个人空间（现状）。
2. 创建团队 → 成 owner（`POST /api/teams` 自动建 `TeamMember(role=owner)`）。
3. owner/admin 邀请 → 收件人用 token 接受成 member（`POST /api/teams/{id}/invites` + `POST /api/teams/invites/accept?token=...`）。
4. 用户申请加入 → owner/admin 审批（`POST /api/teams/{id}/join` + `POST /api/teams/{id}/requests/{rid}/approve`）。

---

## 6. 迁移策略（遵守容器 SQL 兼容铁律）
- **机制**：api 容器 CMD `python -m app.db.init_db` → `sync_model_columns` 按 ORM 元数据自动建表/加列（**非** SQLite 专用 `_migrate_sqlite_columns`）。
- **NOT NULL 新列必带 `server_default`**（本方案已用 `text("1")` / `text("'member'")` 等），避开 ADR-028 踩过的 MySQL `ALTER ... NOT NULL` 失败坑。
- **TEXT 列禁带默认值**（`description/message` 用 `default=""` 应用层兜底，无 `server_default`）。
- **激活**：`docker restart ai-agent-api`（bind 挂载，无需 rebuild）；重启即跑迁移。
- **验证**：每次模型改动后必须在**真实 MySQL** 验证 4 表创建/列补齐、API 健康。

---

## 7. 后端路由（Phase 2）
| 方法 | 路径 | 权限 |
|---|---|---|
| POST | `/api/teams` | 登录用户 | 建团队(成 owner) |
| GET | `/api/teams/mine` | 登录用户 | 我的团队列表 |
| GET/PATCH/DELETE | `/api/teams/{id}` | owner | 详情/改/删 |
| GET | `/api/teams/{id}/members` | 团队成员 | 成员列表 |
| POST | `/api/teams/{id}/members` | owner/admin(`team.members.manage`) | 添加成员 |
| DELETE | `/api/teams/{id}/members/{uid}` | owner/admin | 移除 |
| PATCH | `/api/teams/{id}/members/{uid}` | owner/admin | 改角色 |
| POST | `/api/teams/{id}/invites` | owner/admin | 发邀请 |
| POST | `/api/teams/invites/accept` | 登录用户(token) | 接受 |
| POST | `/api/teams/{id}/join` | 登录用户 | 申请加入 |
| POST | `/api/teams/{id}/requests/{rid}/approve` | owner/admin | 审批 |

---

## 8. 前端（Phase 3）
- **工作空间切换器**：右上角下拉「个人空间 / 我的团队A / 我的团队B」，切换后写入全局 `currentSpace`（个人=`{type:'personal'}` / 团队=`{type:'team', team_id}`）。
- **团队管理页**（`/teams` 或 `/team/:id`）：成员表格(添加/邀请/改角色/移除)、团队信息编辑、邀请链接。
- **菜单动态化**：扩展面(MCP/Skill/Hook)菜单项改由 `can(user,'mcp.manage', currentTeamId)` 等判定显隐，而非仅 `is_superuser`。
- **konghong 预期效果**：被加入/自建团队并赋 admin 后，能在团队管理页加成员、看到扩展面配置。

---

## 9. 分阶段落地（可逆、易验证）
- **Phase 1（本批）**：4 张团队表 + MySQL 迁移验证 + `app/permissions.py`(`can()`/常量)。无破坏，仅新建表。
- **Phase 2**：资源表 `team_id` + `TeamService` + 上述路由 + `can()` 接入。
- **Phase 3**：前端切换器 + 团队管理页 + 菜单动态化 + Playwright 真机回归。

---

## 10. 取舍（Trade-offs）
- **放弃简单性（接受双层空间）**：换来"团队共享/隔离"真能力，是产品核心卖点。
- **放弃纯 RBAC 极简（角色基线+成员级覆盖）**：换来细粒度授权，复杂度可控。
- **team_id 同表可空（放弃物理隔离）**：迁移/查询简单，靠 `can()` 逻辑隔离；若未来要强隔离可再拆。
- **个人空间不含扩展面管理（放弃自由度）**：扩展面归团队/平台管，符合 ADR-026"管理员域"。
- **权限目录代码常量（放弃运行时动态）**：部署简单、无额外表；新增权限改代码+迁移。

## 11. 验证计划
- 后端：隔离 import + 真实 MySQL `docker restart` 迁移，确认 4 表存在、API 200。
- 权限：`can()` 单测（超管放行/个人默认/团队角色基线/成员覆盖/owner 至少1人）。
- 前端：Playwright 真机——konghong 建队→加成员→见扩展面菜单；普通成员看不到管理项。
- 全程零破坏真实用户数据；临时脚本用完即清。
