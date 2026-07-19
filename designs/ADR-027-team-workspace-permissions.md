# ADR-027: 团队工作空间与功能级权限模型

## Status
Proposed

## Context

ADR-026 将产品定位为「自托管小团队 AI 工作台」。当前权限模型无法支撑该定位:

1. **纯个人所有制**:19 个资源表全部 `user_id` 直挂,无团队/组织概念。
2. **权限粒度粗**:User 仅有全局 `role` 字符串(admin/user),无法做到"功能级"控制。
3. **无 C 端入口**:无自助注册流程,无个人空间与团队空间的区分。
4. **扩展面无处安放**:MCP/Skill/Hook 当前是全局资源,无法按团队隔离,也无法对成员做"谁能用、谁能管"的分配。

用户明确诉求:
- C 端用户可自注册,有个人空间与基本功能。
- 可创建团队(创建者即 owner),可申请加入其他团队。
- 团队管理员可邀请成员,可对成员做**功能级权限分配**。
- 资源收敛到团队空间,个人空间保留基本消费能力。

## Decision

采用**双层空间模型(个人 + 团队)+ RBAC 基线 + 功能权限覆盖**。

### 1. 三层角色体系(明确区分,不可混淆)

| 层级 | 角色 | 谁是 | 权限范围 |
|------|------|------|---------|
| 系统层 | 系统管理员 | 部署运营者(`is_superuser=true`) | 全局:用户、系统设置、所有团队可见只读 |
| 团队层 | owner | 团队创建者 | 团队内全权限 + 转让/解散 |
| 团队层 | admin | 团队管理员(owner 任命) | 邀请/审批成员、分配权限、管团队资源 |
| 团队层 | member | 普通成员 | 按被授予的功能权限使用 |

**关键区分**:系统管理员是"自托管运维",管平台本身;团队管理员是"普通用户管自己的团队"。两者不重叠——系统管理员不自动是任何团队的 owner。

### 2. 数据模型(新增 4 表,改造现有表)

```python
class Team(TimestampMixin, Base):
    id, name, slug(unique), owner_user_id(FK users.id),
    description, settings(JSON), enabled

class TeamMember(TimestampMixin, Base):
    id, team_id(FK), user_id(FK),
    role(Enum: owner/admin/member, default member),
    status(Enum: invited/active/disabled/left, default invited),
    permissions(JSON, default={}   # 功能权限覆盖,空=用角色基线
    joined_at, invited_by(FK users.id, nullable)

class TeamInvite(Base):
    id, team_id(FK), invite_code(unique),
    invitee_email(nullable, 定向邀请), invitee_user_id(nullable, 已注册用户),
    status(Enum: pending/accepted/rejected/expired),
    expires_at, created_by(FK users.id)

class TeamJoinRequest(Base):
    id, team_id(FK), user_id(FK), message,
    status(Enum: pending/approved/rejected), reviewed_by, reviewed_at
```

现有资源表改造(**向后兼容**,最小迁移):
- 所有资源表新增 `team_id: Mapped[int | None]`(NULL = 个人空间,有值 = 团队空间)
- 保留 `user_id`(语义变为"创建者",不是"唯一所有者")
- 查询时:`WHERE team_id IS NULL AND user_id = :me`(个人)或 `WHERE team_id = :team`(团队)

### 3. 功能权限目录(代码常量,非数据库硬编码)

```python
PERMISSION_CATALOG = {
    # 消费类(个人空间默认开)
    "chat.use": "使用聊天",
    "kb.read": "读知识库", "kb.write": "写知识库",
    "gallery.use": "使用电商套图", "gallery.manage": "管理套图模板",
    "media.read": "读媒体库", "media.write": "写媒体库",
    "memory.read": "读长期记忆", "memory.manage": "管长期记忆",

    # 扩展面(个人空间默认关,团队管理员分配)
    "mcp.use": "使用 MCP 工具",
    "mcp.manage": "管理 MCP Server 配置",
    "skill.use": "使用 Skill", "skill.manage": "管理 Skill",
    "hook.manage": "管理 Hook",

    # 团队管理(仅 owner/admin)
    "team.members.manage": "管理成员与权限",
    "team.resources.share": "共享资源给团队",
    "team.settings": "团队设置",
}

ROLE_BASELINE = {
    "owner":  dict.fromkeys(PERMISSION_CATALOG, True),           # 全开
    "admin":  {**dict.fromkeys(PERMISSION_CATALOG, True)},     # 全开(可被 owner 收窄)
    "member": {"chat.use":True,"kb.read":True,"kb.write":True,
               "gallery.use":True,"media.read":True,"memory.read":True,
               "mcp.use":False,"skill.use":False,...},          # 默认收敛
}

PERSONAL_DEFAULT = {  # 个人空间(C 端自注册)默认能力
    "chat.use":True,"kb.read":True,"kb.write":True,
    "gallery.use":True,"media.read":True,"memory.read":True,
}
```

**权限判定函数**(集中一处,禁止散落检查):
```python
def can(user, perm: str, team_id: int | None = None) -> bool:
    if user.is_superuser: return True                    # 系统管理员放行
    if team_id is None:                                  # 个人空间
        return PERSONAL_DEFAULT.get(perm, False)
    member = get_team_member(team_id, user.id)
    if not member or member.status != "active": return False
    baseline = ROLE_BASELINE[member.role]
    # 成员级覆盖优先于角色基线
    return member.permissions.get(perm, baseline.get(perm, False))
```

### 4. 入伙流程(4 条路径)

| 路径 | 触发 | 结果 |
|------|------|------|
| 自注册 | C 端用户填邮箱密码 | 个人空间 + PERSONAL_DEFAULT |
| 创建团队 | 任何已注册用户 | 自动成该团队 owner |
| 邀请加入 | admin 生成邀请码/定向邮箱 | 被邀请者接受后成 member(默认基线) |
| 申请加入 | 用户搜索团队 + 提申请 | admin 审批后成 member |

### 5. 权限执行点(FastAPI 依赖)

```python
def require(perm: str, team_id_arg: str = "team_id"):
    def dep(team_id: int = Path(..., alias=team_id_arg),
            user: User = Depends(get_current_user), db = Depends(get_db)):
        if not can(user, perm, team_id): raise HTTPException(403, "无权限")
        return user
    return dep

# 路由用法
@router.post("/teams/{team_id}/mcp-servers", dependencies=[Depends(require("mcp.manage"))])
```

## 权衡(每个选择放弃了什么)

### 选择 A:多工作空间(用户可同时在多个团队) vs 单团队
- **选**:多工作空间(Notion/Slack 模式)
- **放弃**:简单性——前端需要工作空间切换器,用户可能困惑"我现在在哪个空间"
- **理由**:C 端用户预期已是多工作空间,且数据模型成本不大(team_id 外键)

### 选择 B:RBAC 基线 + 成员级覆盖 vs 纯角色 vs 全 ACL
- **选**:基线 + 覆盖
- **放弃**:纯 RBAC 的极简性(3 角色固定);全 ACL 的逐资源粒度
- **理由**:用户明确要"功能级";覆盖机制满足"管理员可对个别成员收放",又不至于 ACL 那般复杂

### 选择 C:team_id 可空(个人/团队同表) vs 个人团队分库
- **选**:同表 + 可空 team_id
- **放弃**:数据隔离的物理性(个人与团队数据混在一张表)
- **理由**:向后兼容(现有 user_id 不动),迁移最小;数据量级不大,逻辑隔离足够

### 选择 D:C 端个人空间默认不含扩展面管理
- **选**:个人空间只给消费类能力(chat/kb/gallery/memory 读)
- **放弃**:个人用户自由配 MCP/Skill/Hook 的灵活性
- **理由**:ADR-026 已定——扩展面是团队管理员域;个人若想试,可创建单人团队获得 owner 权限

### 选择 E:权限目录用代码常量 vs 数据库表
- **选**:代码常量(PERMISSION_CATALOG dict)
- **放弃**:运行时动态增删权限类型的灵活性
- **理由**:权限类型与代码强耦合(每个 perm 对应路由检查),动态化反而割裂;版本控制更可靠

## Consequences

**变容易的**:
- 资源收敛有明确归属(team_id),不再全局混乱。
- "谁能用什么"有单一判定入口(`can()`),不散落。
- C 端入口清晰:自注册 → 个人空间,要更多就建/加入团队。
- 扩展面(MCP/Skill/Hook)自然落到团队空间,个人空间不暴露。

**变困难的**:
- 现有 19 个资源表都要加 team_id 列(MySQL ALTER,需逐步迁移)。
- 前端需引入"工作空间切换器"(个人/团队上下文切换)。
- 所有现有 API 要补权限检查依赖(技术债清点)。
- 已有全局资源(admin 建的 MCP/Skill/Hook)需决策归属:建议迁移到"系统默认团队"或标记 team_id=NULL 作公共池。

**待后续决策**:
- 个人空间是否有配额限制(防滥用)?
- 团队是否限制成员数?
- 跨团队资源能否共享(只读)?
- 计费/套餐(若走向 SaaS)?——当前自托管场景暂不考虑。

## 迁移路径(分批,可回退)

1. **Phase 1(底座)**:新增 Team/TeamMember/TeamInvite/TeamJoinRequest 4 表;User 加 is_superuser 字段。不改现有资源表。可独立测试。
2. **Phase 2(归属)**:现有资源表批量加 team_id(NULL)。存量数据 team_id=NULL(个人空间)。查询逐步改为带 team_id 过滤。
3. **Phase 3(权限)**:实现 `can()` + FastAPI require 依赖;现有路由逐一接入权限检查。
4. **Phase 4(前端)**:工作空间切换器;团队管理页(成员/权限/邀请);C 端注册页。
5. **Phase 5(收敛)**:把全局 MCP/Skill/Hook 迁移到默认团队或保留公共池(team_id=NULL + 标记)。
