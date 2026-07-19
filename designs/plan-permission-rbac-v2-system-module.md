# 技术方案：系统管理模块 + 显式 RBAC（资源 / 角色 / 用户-角色）

> 状态：Accepted（已落地并真机验证 2026-07-19，Playwright 11/11 PASS）
> 演进自：`plan-permission-rbac.md`（两级委派）与 `ADR-029`（权限划分 + 入团审批落地）
> 约束：所有表结构改动须兼容 **Docker + MySQL(`ai_agent`)**——新表由 `Base.metadata.create_all` 自动建表；新增列/改列须带 `server_default`，TEXT 列禁默认值；生产迁移靠 api 容器启动 `python -m app.db.init_db`。

---

## 0. 决策摘要（TL;DR）

| 项目 | 本次方案 |
|---|---|
| 新增模块 | **系统管理**（父菜单，`admin.system.manage` 门控），收纳：用户管理、资源管理、角色管理、团队管理员权限 |
| 显式 RBAC | 新增 `Resource`(资源) / `Role`(角色) / `RolePermission`(角色-权限) / `UserRole`(用户-角色) 四张表 |
| 基础角色 | 新增 `base` 角色（`is_default=true`），等价于当前 `PERSONAL_DEFAULT`，自注册用户自动获得 |
| 动态菜单 | 菜单由 `Resource` 表（`type='menu'`，带 `parent_code` 树）驱动，替换 `BasicLayout` 硬编码 `menuItems` |
| 团队约束 | **保留**两级委派：`team_admin_scopes`(超管限定团队管理员可授上限) + `user_permissions`(团队内成员实际持有) 作为"团队/个人 override 层" |
| 权限判定 | `can()` 改为 **加性并集**：角色权限 ∪ 个人 user_permissions ∪ (团队内)团队授权；超管恒真 |
| 团队语义 | **权限壳 + 内容共享**：角色一律 global（不按团队细分）；"创作案例发布给多团队使用"走**发布/共享**模型（数据归创建者，显式发布到多团队可见），不引入 team_id 数据归属 |

---

## 1. 目标与边界

### 1.1 目标
1. 提供一个**可视化管理入口**（系统管理模块）来配置权限，而非只在代码里改常量。
2. **资源可新增**：管理员能在后台新增"菜单项 + 权限码"（如新上线一个功能模块，登记资源后即出现在菜单与分配列表）。
3. **角色可新增**：除内置角色外，可自定义角色并勾选其权限集合；设某角色为"默认角色"后，新注册用户自动获得。
4. **基础角色**：所有自注册用户天然持有最基础菜单权限（无需手动配）。
5. 与现有**团队两级委派并存**——超管限定团队管理员 scope、团队管理员在 scope 内给成员授权的逻辑不动。

### 1.2 明确不做（边界）
- 不改动已落地的入团审批流（自申请审批 / 邀请同意）。
- 不引入外部 IdP / OAuth；只做平台内部 RBAC。
- 首版角色仅 **global**（不按团队细分角色）；团队内细粒度授权仍走 `user_permissions` + `team_admin_scopes`。
- **团队不细化角色（用户已确认）**：不在 `user_roles` 中按 `team_id` 细分角色；多团队差异化授权继续走现有成员级 `user_permissions` override。
- **"创作案例发布给多团队使用"不在本次权限改造范围内**，但本次奠基的「团队 + 权限体系」正是为它服务：案例数据归创建者(`user_id`)，通过其"发布/共享到团队"的关联表让多个团队可见/可用（解法② 共享模型，不引入 `team_id` 数据归属）。该能力单列后续 **Phase 5**。
- 不做"负权限"（deny）——权限模型纯加性，收回=删关联行。

---

## 2. 领域模型

### 2.1 实体关系

```
                 ┌──────────────┐
                 │  Resource    │  菜单/权限/API 的统一定义
                 │  (资源)       │  type: menu|permission|api
                 └──────┬───────┘  parent_code → 树形菜单
                        │ 1       │ N
            ┌───────────┴───────────┐
            ▼                       ▼
     ┌──────────────┐      ┌────────────────┐
     │ Role         │      │ RolePermission │  角色-权限关联
     │ (角色)        │◀────│ (角色⇢权限)     │
     │ code: base…  │ 1   N│ role_id, code  │
     └──────┬───────┘      └────────────────┘
            │ 1       │ N
            ▼
     ┌──────────────┐
     │ UserRole     │  用户-角色关联（global: team_id=NULL）
     │ (用户⇢角色)   │
     └──────────────┘

  ── 保留的 override 层（团队/个人显式授权，优先级叠加）──
     user_permissions (个人/团队实际持有)  +  team_admin_scopes (超管限定团队管理员上限)
```

### 2.2 新表结构（DDL 要点，MySQL 兼容）

**`resources`（资源表 —— 菜单与权限的统一注册）**
```
id            INT PK AUTO_INCREMENT
code          VARCHAR(80) NOT NULL UNIQUE   # 菜单码如 "menu.chat" 或 权限码如 "chat.use"
name          VARCHAR(120) NOT NULL
type          VARCHAR(16) NOT NULL          # 'menu' | 'permission' | 'api'
category      VARCHAR(40) NOT NULL INDEX
parent_code   VARCHAR(80) NULL INDEX        # 菜单树：指向父资源 code（NULL=顶层）
path          VARCHAR(160) NULL             # 菜单路由，如 "/providers"
component     VARCHAR(120) NULL             # 前端组件名（可选，路由已在 App.tsx 静态注册）
icon          VARCHAR(60) NULL              # antd 图标名
sort_order    INT NOT NULL DEFAULT 0         # server_default "0"
permission_code VARCHAR(80) NULL            # 该菜单可见性绑定的权限码（多从 code 本身取）
is_visible    BOOLEAN NOT NULL DEFAULT 1     # server_default "1"
is_system     BOOLEAN NOT NULL DEFAULT 0     # server_default "0" —— 系统资源禁删/禁改 code
created_at / updated_at  DateTime (server_default now / onupdate)
```
> `parent_code` 是本次关键新增——现有 `permission_catalog` 没有层级，菜单树只能靠前端硬编码。

**`roles`（角色表）**
```
id            INT PK AUTO_INCREMENT
code          VARCHAR(60) NOT NULL UNIQUE    # 'base' | 'superuser' | 自定义
name          VARCHAR(80) NOT NULL
description   VARCHAR(255) DEFAULT ''
is_system     BOOLEAN NOT NULL DEFAULT 0     # server_default "0" —— base/superuser 受保护
is_default    BOOLEAN NOT NULL DEFAULT 0     # server_default "0" —— True=新用户自动获得
sort_order    INT NOT NULL DEFAULT 0
created_at / updated_at
```

**`role_permissions`（角色-权限关联）**
```
id            INT PK
role_id       INT FK(roles.id) ON DELETE CASCADE INDEX
permission_code VARCHAR(80) NOT NULL INDEX
created_at    DateTime
UNIQUE(role_id, permission_code)
```

**`user_roles`（用户-角色关联）**
```
id            INT PK
user_id       INT FK(users.id) ON DELETE CASCADE INDEX
role_id       INT FK(roles.id) ON DELETE CASCADE INDEX
team_id       INT NULL INDEX                 # 首版恒 NULL（global 角色）；预留团队级
granted_by_user_id INT FK(users.id)
created_at    DateTime
UNIQUE(user_id, role_id, team_id)
```

### 2.3 种子数据（迁移映射，零破坏）

1. **`permission_catalog` → `resources`（type='permission'）**：把现有 36 个权限码 upsert 进 `resources`，`code` 沿用原 `code`，`permission_code` 同 `code`。`is_system` 沿用（admin.* 三项为系统级）。
2. **`BasicLayout` 静态菜单 → `resources`（type='menu'）**：把当前 `menuItems` 树逐节点迁为 menu 资源，`parent_code` 还原层级（如 `/providers` 的 parent 是 menu 资源 `menu.agent`）。`permission_code` 取自现有 `MENU_PERM` 字典。
3. **角色种子**：
   - `base`（基础角色，`is_default=true`）：`role_permissions` 写入现有 `PERSONAL_DEFAULT` 全部码（24 项）。**这就是"自注册用户看到最基础菜单"的落点**。
   - `superuser`（系统角色，`is_system=true`）：含全部权限（含 admin.*）。
4. **历史用户回填**：对库中每个用户 `INSERT user_roles(user_id, role_id=base, team_id=NULL)`（幂等，已存在则跳过）。**不删现有 `user_permissions`**——旧个人权限作为 override 保留。

---

## 3. 权限判定（重构 `can()`）

```python
def get_effective_permissions(user, team_id, db) -> set[str]:
    perms: set[str] = set()
    # 1) 全局角色权限（UserRole where team_id IS NULL → Role → RolePermission）
    role_codes = db.scalars(select(RolePermission.permission_code)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user.id, UserRole.team_id.is_(None)))
    perms |= set(role_codes)
    # 2) 个人/团队显式授权（user_permissions，保留为 override）
    perms |= get_user_permissions(user.id, team_id, db)
    # 3) 若 user 是团队管理员，其 scope 内权限亦可用（团队上下文）
    if team_id is not None and is_team_admin(user, db):
        perms |= get_team_admin_scope(user.id, db)
    return perms

def can(user, perm, team_id=None, db=None) -> bool:
    if getattr(user, "is_superuser", False): return True   # 超管恒真
    if db is None: return False
    return perm in get_effective_permissions(user, team_id, db)
```

**关键取舍**：采用 **加性并集（additive union）** 而非"角色覆盖个人"。
- 好处：团队管理员给成员加权限、超管给团队管理员加 scope，语义完全不变；角色变动不会误收回用户的显式授权。
- 代价：存在"两个真相"（角色 + 个人表），需在文档中明确优先级的**叠加**语义（不是覆盖）。
- 预测性：纯加性、无负权限 → 判定结果可枚举、可审计。

---

## 4. 动态菜单（核心前端变更）

### 4.1 新增接口 `GET /api/system/menus`
- 取所有 `type='menu'` 且 `is_visible=true` 的 Resource，按 `parent_code` 组装成树。
- 逐节点用 `permission_code` 过滤：`can(user, node.permission_code)` 为假则不返回该节点（超管全返回）。
- 返回结构：`[{ key, label, icon, path, children: [...] }]`，供 antd `Menu` 直接消费。

### 4.2 `BasicLayout` 改造
- 移除硬编码 `menuItems` + `MENU_PERM` + `filterMenuByPerm`。
- 改为挂载时 `fetch('/api/system/menus')` 渲染菜单（仍受 `user?.is_superuser` 短路）。
- **保留静态菜单快照作 fallback**：接口失败/超时则回退当前硬编码菜单，保证布局不白屏。
- 路由（`App.tsx`）不变——菜单只是"开关"，无权限用户直接敲 URL 时由 `RequireAuth` + 后端接口 `can()` 双重兜底。

---

## 5. 前端页面（系统管理模块）

父菜单 **系统管理**（`SystemOutlined`，`admin.system.manage` 门控），子项：

| 页面 | 路由 | 守卫 | 功能 |
|---|---|---|---|
| 用户管理 | `/users` | `admin.users.manage` | 从顶层移入；用户详情抽屉内**分配角色**（勾选角色） |
| 资源管理 | `/admin/resources` | `admin.permissions.manage` | Resource CRUD：新增菜单项（父级下拉 + 路由 + 图标 + 绑定权限码）/ 权限码；`is_system` 禁止删除 |
| 角色管理 | `/admin/roles` | `admin.permissions.manage` | Role CRUD：新建角色、勾选权限分配（Transfer/Tree）、切换"默认角色" |
| 团队管理员权限 | `/admin/team-admins` | `admin.permissions.manage` | 已有，保留（超管给团队管理员定 scope） |

组件建议落位：`web/src/pages/System/{ResourceManage,RoleManage}.tsx`，`UserManagement.tsx` 增加角色分配抽屉。

---

## 6. 后端 API（新增）

| 方法 | 路径 | 守卫 | 说明 |
|---|---|---|---|
| GET | `/api/system/menus` | 登录 | 当前用户可见菜单树（§4.1） |
| GET | `/api/system/resources` | `admin.permissions.manage` | 资源列表（树/扁平，支持筛选 type） |
| POST/PUT/DELETE | `/api/system/resources` | `admin.permissions.manage` | 新增/改/删资源；删 `is_system` 拒绝 |
| GET | `/api/system/roles` | `admin.permissions.manage` | 角色列表 |
| POST/PUT/DELETE | `/api/system/roles` | `admin.permissions.manage` | 新建/改/删角色（删 `is_system` 拒绝） |
| GET/POST/DELETE | `/api/system/roles/{id}/permissions` | `admin.permissions.manage` | 角色-权限分配 |
| GET/POST/DELETE | `/api/users/{id}/roles` | `admin.users.manage` | 用户-角色分配（设默认角色时新用户自动获得） |

> 团队两级委派接口（`/api/admin/team-admins/*`、`/api/teams/{id}/members/{uid}/permissions`）**原样保留**。

---

## 7. 落地顺序（每步可独立验证、可逆）

- **Phase 0 — 地基（纯新增表，零破坏）**
  1. 加 4 张表（`resources`/`roles`/`role_permissions`/`user_roles`）。
  2. 种子：catalog→resources(permission)、静态菜单→resources(menu, parent_code 树)、base/superuser 角色、历史用户回填 base 角色。
  3. `docker restart ai-agent-api` 经 `create_all` 自动建表 + `sync_model_columns` 兜底。
  4. 验证：新表存在、base 角色含 24 码、历史用户 `user_roles` 有 base 行。

- **Phase 1 — 角色生效（与旧逻辑并行）**
  1. `can()` / `get_user_permissions()` 纳入角色（加性并集）。
  2. `/api/me/permissions` 返回 角色 ∪ 个人权限 并集。
  3. 旧 `PERSONAL_DEFAULT` 隐式授予**保留作兜底**，待确认无误再移除。
  4. 验证：三角色（超管/团队管理员/普通）权限行为不变。

- **Phase 2 — 动态菜单**
  1. `/api/system/menus` 上线；`BasicLayout` 切换到动态菜单 + 静态 fallback。
  2. 验证：超管见全部菜单；普通用户菜单随 `base` 角色收缩；无权限菜单不渲染。

- **Phase 3 — 管理 UI**
  1. 「系统管理」父菜单 + 资源管理/角色管理页面 + 用户管理角色分配抽屉。
  2. 验证（Playwright 真机）：超管进系统管理 → 新增一个 menu 资源 → 超管菜单出现新项 → 无权限用户不显示；新建角色并分配给测试用户 → 其菜单随之变化。

- **Phase 4（可选清理）**
  - `permission_catalog` 与 `resources(type='permission')` 合并（catalog 可作为权限子集视图）；移除 `PERSONAL_DEFAULT` 隐式授予，统一走 base 角色。

---

## 8. 关键取舍（Trade-offs）

| 决策 | 得到 | 放弃 / 代价 |
|---|---|---|
| 动态菜单（资源驱动） | 新增功能菜单无需发版；运营可自助 | 布局加载多一次接口（缓存 + fallback 缓解）；菜单结构从代码迁到 DB，需种子脚本兜底一致性 |
| 角色层 + `user_permissions` 双源 | 灵活：默认来自角色，特例来自显式授权 | "两个真相"，需在文档固化**叠加**语义（非覆盖） |
| 全量角色化（base 角色） | 迁移平滑，等价于现状 `PERSONAL_DEFAULT` | 旧 `user_permissions` 仍并存（短期内角色与个人表都算数） |
| `resources` 与 `permission_catalog` 首版并存 | 降低风险，权限分配 UI 暂不动 | 长期应合并，否则两套"权限清单"易分裂 |
| 纯加性、无负权限 | 判定可预测、可审计 | 无法表达"授予角色 A 但收回其中某权限"——需建子角色或显式删 RolePermission |

---

## 9. 风险与回滚

- **菜单接口故障** → `BasicLayout` 回退静态菜单快照，布局不白屏。
- **新表无外键指向旧表**（除 `user_roles`/`role_permissions` 指向 users/roles），若方案废弃可单独 `DROP` 四张新表，不影响现有权限体系。
- **真实数据零破坏**：base 角色只"新增关联"；`user_permissions` 保留；种子 upsert 幂等。
- **`is_system` 保护**：admin.* 三项、内置 base/superuser 角色禁止删除/改 code，防误操作锁死平台。

---

## 10. 验证计划（铁律：动代码须验证）

- 后端：真实 MySQL `create_all` 建表预验证；`docker restart ai-agent-api` 启动无 traceback；接口三角色实测（超管/团队管理员/普通用户）。
- 前端：Playwright 真机——超管见「系统管理」+ 资源管理/角色管理；新增 menu 资源→超管菜单出现→无权限用户不显示；新建角色→分配给测试用户→其菜单变化；konghong（团队管理员）仍看不到「系统管理」（门控生效）。
- 真实数据：零破坏；历史用户 base 角色补全（幂等）。

---

## 11. 内容共享（创作案例发布给多团队使用）— 后续 Phase 5（本次不实现）

### 11.1 动机
用户核心诉求：自己创作的"案例"发布后，可**被多个团队使用**。这定义了"团队"在产品里的真实价值——团队是**内容的分发/可见性单元**，而非数据的拥有者。

### 11.2 模型选择：解法②（出生归个人 + 显式共享）
- 案例数据**始终 `user_id` 归属创建者**，不挂 `team_id`，从根上回避"多团队下数据归谁"的悖论。
- 新增关联表 `case_team_shares(case_id, team_id, visibility, shared_by)`，一条案例可发布到 N 个团队。
- 可见性判定：`can_use_case(user, case)` = 案例创建者本人 OR 用户所属某团队 ∈ case 的共享团队集合。
- 与本次 RBAC v2 的关系：RBAC 管"谁能进案例模块/谁能发布"，`case_team_shares` 管"发布到哪些团队"。两者正交，本期只把权限/团队地基打好。

### 11.3 与团队玩法矩阵对齐
对应图2「协作空间」语义：团队是共享池，成员通过发布/订阅看到彼此内容，而非各自的数据孤岛。
