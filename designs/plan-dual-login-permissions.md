# 技术方案:双登录入口 + 三层权限控制落地

> 状态:Proposed(等用户确认后转 Accepted 进入实现)
> 关联:ADR-026(产品定位)/ ADR-027(团队工作空间权限模型)
> 本文档是 ADR-027 权限模型在**登录层 + 路由守卫层**的具体落地实现

## 一、决策:逻辑分流,不拆服务

| 方案 | 做法 | 放弃了 | 选择? |
|------|------|--------|-------|
| A 物理双入口 | 拆 admin-service + user-service 两个进程,各自 User 表/JWT | 一倍代码重复、双身份数据同步、过度工程 | ✗ |
| **B 逻辑分流** | **一套后端 + 双前端路由 + 依赖守卫** | 管理后台 URL 对 C 端可见(靠守卫拦) | **✓** |

**为什么选 B:**
1. 你后端是单体,`User` 表只有一个,拆服务是"假隔离"——后端 `/auth/login` 还得是同一个
2. Notion/Slack/Linear 都是"一套登录 + 按角色分流 Shell",被验证过
3. 复用现有 90% 代码,迁移成本最小
4. **可逆**:后续真要硬隔离,把 `AdminLayout` 对应路由独立成服务即可,不用推倒重来

---

## 二、后端改动

### 2.1 模型层 (`app/models.py`)

**User 表加字段:**
```python
class User(TimestampMixin, Base):
    # 现有字段不动
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    # role 字段保留做向后兼容,但新逻辑一律走 is_superuser + TeamMembership.role
```

> 迁移:现有 `role='admin'` 的用户,迁移脚本设 `is_superuser=True`。`role` 字段不删,只读不用。

**ADR-027 定义的 4 张新表(本方案落地):**
```python
class Team(TimestampMixin, Base):
    id, name, slug(unique), owner_id(FK users), created_at

class TeamMembership(TimestampMixin, Base):
    id, team_id(FK), user_id(FK), role(String: owner|admin|member)
    # UNIQUE(team_id, user_id)

class TeamInvite(TimestampMixin, Base):
    id, team_id(FK), invited_email, token(unique), role(default member),
    status(pending|accepted|rejected|revoked), invited_by(FK users), expires_at

class PermissionOverride(TimestampMixin, Base):
    id, team_id(FK), user_id(FK), permission(String, 见目录),
    granted(bool)  # True=开, False=关(收窄)
    # UNIQUE(team_id, user_id, permission)
```

### 2.2 依赖层 (`app/deps.py`) — 核心,三个守卫

```python
def get_current_user(token, db) -> User:
    # 现有不动,只验 JWT → 返回 User

def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    """系统管理员守卫:保护管理后台 API"""
    if not current_user.is_superuser:
        raise HTTPException(403, "系统管理员权限 required")
    return current_user

def require_team_role(*allowed: str):
    """团队角色守卫工厂:保护团队资源 API
    用法: @router.get("/teams/{team_id}/members", dependencies=[Depends(require_team_role("owner","admin"))])
    注意:需从路径参数取 team_id,用 request.path_params 或显式传参"""
    def _guard(team_id: int, current_user: User = Depends(get_current_user), db = Depends(get_db)):
        m = db.scalar(select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.user_id == current_user.id
        ))
        if not m or m.role not in allowed:
            raise HTTPException(403, "团队权限不足")
        return m
    return _guard

def can(user: User, team_id: int, permission: str, db) -> bool:
    """功能级权限检查:基线 + 覆盖
    1. owner → 全开
    2. 查 TeamMembership.role 的 ROLE_BASELINE[role][permission]
    3. 查 PermissionOverride 是否覆盖(优先级最高)
    返回 bool。用于"能不能用这个功能",不是路由守卫。"""
```

**权限目录(代码常量,不放 DB):**
```python
PERMISSION_CATALOG = [
    "chat.use", "kb.read", "kb.write",           # C 端基础
    "gallery.use", "memory.read",                 # 垂直应用
    "mcp.use", "skill.use",                       # 扩展面使用
    "mcp.manage", "skill.manage", "hook.manage",  # 扩展面管理(团队管理员)
    "team.manage_members", "team.invite",         # 团队管理
    "team.billing", "team.audit",                 # 团队高级
]

ROLE_BASELINE = {
    "owner":  {p: True for p in PERMISSION_CATALOG},
    "admin":  {p: True for p in PERMISSION_CATALOG},   # 可被 owner 收窄
    "member": {"chat.use": True, "kb.read": True, "kb.write": True,
               "gallery.use": True, "memory.read": True,
               "mcp.use": True, "skill.use": True},    # 不含 manage
}
```

### 2.3 路由层 (`app/api.py`) — 按保护级别分三类

| 级别 | 守卫 | 路由示例 | 谁能访问 |
|------|------|---------|---------|
| C 端基础 | `get_current_user` | `/chat`, `/kb`, `/gallery`, `/auth/me` | 任何登录用户 |
| 团队资源 | `require_team_role(...)` | `/teams/{id}/members`, `/teams/{id}/mcp` | 团队成员 |
| 系统管理 | `require_superuser` | `/admin/users`, `/admin/system`, 全局 MCP/Skill/Hook | 仅 `is_superuser` |

**关键改动:现有 MCP/Skill/Hook 管理路由**
- 当前:任何登录用户都能在自己名下建 MCP/Skill/Hook(`user_id` 直挂)
- 改后:
  - `is_superuser` → 系统级管理(全局默认团队/公共池)
  - `team admin/owner` 且有 `mcp.manage` → 团队级管理
  - 普通 member 只能 `mcp.use`(用,不能配)

**注册路由收紧:**
```python
@router.post("/auth/register")
def register(payload, db):
    # 保持开放(C 端自注册),但新建用户 is_superuser=False, role="user"
    # 自动创建"个人空间"(team_id=NULL 的资源),不自动加入任何团队
```

**新增管理 API 前缀 `/admin/*`(全挂 require_superuser):**
```python
@router.get("/admin/users", dependencies=[Depends(require_superuser)])
@router.post("/admin/users/{id}/toggle-superuser", dependencies=[Depends(require_superuser)])
@router.get("/admin/system/settings", dependencies=[Depends(require_superuser)])
```

**新增团队 API 前缀 `/teams/*`:**
```python
@router.post("/teams", dependencies=[Depends(get_current_user)])  # 任何登录用户可建团队
@router.post("/teams/{id}/invite", dependencies=[Depends(require_team_role("owner","admin"))])
@router.post("/teams/invites/{token}/accept", dependencies=[Depends(get_current_user)])
@router.get("/teams/{id}/members", dependencies=[Depends(require_team_role("owner","admin","member"))])
```

---

## 三、前端改动

### 3.1 路由结构 (`web/src/App.tsx`)

```tsx
// 两个登录入口
<Route path="/login" element={<Login mode="user" />} />
<Route path="/admin/login" element={<Login mode="admin" />} />

// C 端工作台(任何登录用户)
<Route element={<RequireAuth><CLayout /></RequireAuth>}>
  <Route path="/dashboard" element={<Dashboard />} />
  <Route path="/chat" element={<Chat />} />
  <Route path="/gallery" element={<Gallery />} />
  <Route path="/kb" element={<KnowledgeBase />} />
</Route>

// 管理后台(仅 is_superuser)
<Route element={<RequireAuth><RequireSuperuser><AdminLayout /></RequireSuperuser></RequireAuth>}>
  <Route path="/admin/users" element={<UserManagement />} />
  <Route path="/admin/system" element={<SystemSettings />} />
  <Route path="/admin/mcp" element={<MCPManagement />} />     {/* 全局 MCP */}
  <Route path="/admin/skills" element={<SkillManagement />} />
  <Route path="/admin/hooks" element={<HookManagement />} />
</Route>

// 团队空间(团队成员)
<Route element={<RequireAuth><TeamLayout /></RequireAuth>}>
  <Route path="/teams/:id/members" element={<TeamMembers />} />
  <Route path="/teams/:id/mcp" element={<TeamMCP />} />
</Route>
```

### 3.2 双守卫组件

```tsx
function RequireAuth({ children }) {
  const { isAuthenticated } = useAuthStore()
  return isAuthenticated ? children : <Navigate to="/login" />
}

function RequireSuperuser({ children }) {
  const { user } = useAuthStore()
  return user?.is_superuser ? children : <Navigate to="/dashboard" replace />
  // C 端用户误访问 /admin/* → 踢回工作台
}
```

### 3.3 登录页分流 (`web/src/pages/Login/index.tsx`)

```tsx
export default function Login({ mode }: { mode: "user" | "admin" }) {
  // 同一个表单,同一个 /auth/login 端点
  // 区别仅在登录成功后跳转:
  const handleSubmit = async (values) => {
    const { user } = await login(values.email, values.password)
    if (mode === "admin") {
      if (user.is_superuser) navigate("/admin/users")
      else message.error("该账号无管理权限")  // 非 superuser 走 /admin/login 直接拒
    } else {
      navigate("/dashboard")
    }
  }
  // UI: admin 模式标题"管理后台",user 模式标题"AI 工作台"
}
```

### 3.4 菜单分离
- **CLayout**(C 端):聊天 / 知识库 / 套图 / 记忆 — **不含** MCP/Skill/Hook
- **AdminLayout**(管理后台):用户管理 / 系统设置 / 全局 MCP/Skill/Hook — **只有** is_superuser 能进
- **TeamLayout**(团队空间):成员 / 团队级 MCP/Skill / 权限分配 — 团队 owner/admin 可见管理项

---

## 四、JWT 与会话

**关键决策:JWT 里只放 user_id,不放角色。**

为什么?角色会变(今天升 admin,明天降 member)。如果 JWT 里带 role,改完角色旧 token 还是旧权限,得等过期才生效。只放 user_id,每次请求查 DB,实时准确。代价是每个请求多一次 DB 查询——对你这个规模可忽略。

`/auth/me` 返回的 `UserRead` schema 加 `is_superuser` 和 `teams: [{id,name,role}]`,前端据此渲染菜单和守卫。

---

## 五、迁移路径(5 批,可回退)

| 批次 | 改动 | 风险 | 可回退? |
|------|------|------|--------|
| 1 | User 加 `is_superuser`;现有 admin 迁移;`require_superuser` 依赖 | 低(加字段,旧逻辑不破坏) | ✓ 删字段 |
| 2 | 新增 Team/TeamMembership/TeamInvite/PermissionOverride 4 表 | 低(新表,不影响现有) | ✓ 删表 |
| 3 | 现有资源表加 `team_id`(NULL,存量变个人空间);`can()` 函数 | 中(改表结构,需测迁移) | ✓ team_id 留 NULL |
| 4 | 管理路由加 `require_superuser`;团队路由加 `require_team_role` | 中(权限收紧,可能误拒) | ✓ 去掉依赖 |
| 5 | 前端双入口 + 双 Layout + 路由守卫;MCP/Skill/Hook 页移入 /admin | 低(纯前端) | ✓ 恢复旧路由 |

**每批都能独立测试和回退。** 批次 1-2 完全不影响现有功能;批次 3 开始才动资源归属;批次 4-5 是权限收紧和前端分流。

---

## 六、需要你拍板的 3 个问题

1. **现有那个 `role='admin'` 的用户,迁移后 `is_superuser=True` 对吗?**
   (建议:是。他就是部署这个系统的人,理应是系统管理员)

2. **C 端注册要不要加开关控制?**
   - 完全开放:任何人能注册(现状)
   - 关闭注册:只能被邀请加入(适合纯内部团队)
   - 开放但需审核:注册后等 superuser 审批

3. **管理后台要不要独立域名/端口?(增强隔离)**
   - 不独立:`localhost/admin/*`(推荐,省事)
   - 独立子域:`admin.localhost`(nginx 加一个 server block,前端仍一套代码)

---

## 七、不做什么(防止过度工程)

- ❌ 不拆后端服务(方案 A 已否)
- ❌ 不做 OAuth/SSO(自托管小团队,邮箱密码够)
- ❌ 不做 RBAC 框架(Casbin 之类)——`can()` 函数够用,引入框架是杀鸡用牛刀
- ❌ 不做权限的运行时动态增删(权限目录是代码常量,跟版本走)
- ❌ 不做审计日志表(先用现有 Hook 机制,真需要再加)
