# ADR-028 细化实现方案：单登录 + 权限驱动菜单 + 超管配置

> 状态：Accepted（已与用户确认方向）
> 关联：ADR-026（产品定位：自托管小团队 AI 工作台）、ADR-027（团队权限模型，本版**不实现**，留后续轮次）
> 设计修正：本方案替代此前 `designs/plan-dual-login-permissions.md` 的物理双登录思路（用户已否决双登录）。

---

## 0. 决策回顾（已批准）

1. **单登录**：管理员与普通用户走同一个 `/login`，不搞物理双登录页。
2. **菜单叠加**：登录后根据 `user.is_superuser`（未来再加 `teams[].role`）动态渲染菜单。超管自动比普通用户多出管理后台相关入口，无需切换身份或重新登录。
3. **超管配置**：`.env` 配置初始超管 + `require_superuser` 守卫集中化 + 运行时界面提拔/降级。

---

## 1. 范围

### 本版实现
1. `User` 模型新增 `is_superuser` 字段（Boolean，默认 False），`role` 字段保留兼容。
2. 数据库加列迁移（复用现有 `_migrate_sqlite_columns`，MySQL 兼容）。
3. `UserRead` / `UserUpdate` 暴露 `is_superuser`（顺带补 `enabled`，UserManagement 已用）。
4. seed 创建初始超管时 `is_superuser=True`；支持从 `.env` 读 `INIT_SUPERUSER_EMAIL` / `INIT_SUPERUSER_PASSWORD`。
5. `app/deps.py` 新增 `require_superuser` 守卫；替换散落 4 处 `role != "admin"` 字符串检查。
6. 新增 `POST /api/admin/users/{id}/promote` 与 `/demote` 接口（受 `require_superuser` 保护）。
7. 前端 `BasicLayout` 菜单按 `is_superuser` 动态过滤（MCP / Skills / Hooks / 用户管理 仅超管可见）。
8. 前端 `UserManagement` 增加"超级管理员"列与提拔/降级操作。

### 明确不做（留给后续轮次，不阻塞本版）
- ADR-027 团队空间：Team / TeamMember / TeamInvite / PermissionOverride 四表、`can()` 函数、前端工作空间切换器、团队角色（owner/admin）权限分配。
- 团队 owner/admin 的权限分层（属 ADR-027）。
- 注册开关 / 审批流（现有 `/api/auth/register` 保持现状）。

---

## 2. 现状基线（关键发现，避免改错）

| 关注点 | 现状 | 位置 |
|--------|------|------|
| User 模型 | `role: str default="user"`，**无 `is_superuser`** | `app/models.py:30` |
| UserRead | 仅 `id/email/username/role`，前端拿不到超管标识 | `app/schemas.py:35` |
| 权限检查（散落 4 处） | 均为 `role != "admin"` 字符串比较 | `app/api.py:186`、`app/services.py:417/425/437` |
| 迁移机制 | `create_all` + `_migrate_sqlite_columns`（inspect 判列存在再 ALTER，MySQL 同步生效；**TEXT 列禁带默认值，BOOLEAN 不受影响**） | `app/core/database.py:46-52、55` |
| seed | 硬编码创建 `admin@example.com`/`admin123`，`role="admin"` | `app/db/__init__.py:91-102` |
| 前端菜单 | `menuItems` 为**静态写死数组**，MCP/Skills/Hooks/用户管理对所有人可见，与"管理员功能"定位冲突 | `web/src/layouts/BasicLayout.tsx:35` |
| 前端用户管理 | 已有完整 CRUD（role 下拉、enabled 开关、删除），无 `is_superuser` 概念 | `web/src/pages/UserManagement/index.tsx` |

---

## 3. 数据模型改动

```python
# app/models.py — User 类内新增
is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

`role` 字段保留（UserManagement 仍展示 `admin/editor/user`），**超管判定统一改用 `is_superuser`**，不再用 `role == "admin"`。

### 迁移（在 `_migrate_sqlite_columns` 增加一段）

```python
# users.is_superuser（超级管理员标识）
if insp.has_table("users"):
    u_cols = {c["name"] for c in insp.get_columns("users")}
    if "is_superuser" not in u_cols:
        with engine.connect() as conn:
            # BOOLEAN 非 TEXT，MySQL 可带默认值，SQLite 同样兼容，避开 1101 坑
            conn.execute(text("ALTER TABLE users ADD COLUMN is_superuser BOOLEAN DEFAULT 0"))
            conn.commit()
            logger.info("Added is_superuser column to users")
```

兼容性：SQLite `BOOLEAN`→INTEGER DEFAULT 0 安全；MySQL `BOOLEAN`→tinyint(1) DEFAULT 0 安全（非 TEXT 列，不触发 1101）。

---

## 4. 后端改动

### 4.1 schemas（app/schemas.py）

```python
class UserRead(BaseModel):
    id: int
    email: EmailStr
    username: str
    role: str
    is_superuser: bool = False       # 新增
    enabled: bool = True             # 新增（UserManagement 已用）
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    role: str | None = Field(default=None, min_length=1, max_length=40)
    enabled: bool | None = None
    is_superuser: bool | None = None     # 新增
```

> 注：`login` 返回 `TokenResponse(user=UserRead)`，加字段后前端 `authStore.user` 直接带 `is_superuser`，菜单过滤即可用。

### 4.2 seed（app/db/__init__.py）

```python
init_email = os.getenv("INIT_SUPERUSER_EMAIL", "admin@example.com")
init_pw = os.getenv("INIT_SUPERUSER_PASSWORD", "admin123")
admin = db.query(User).filter_by(username="admin").first()
if admin is None:
    admin = User(
        username="admin",
        email=init_email,
        password_hash=hash_password(init_pw),
        role="admin",
        is_superuser=True,          # 新增
        enabled=True,
    )
```

`.env`（根 `.env` 与 `docker/.env` 同步增加）：

```env
INIT_SUPERUSER_EMAIL=admin@example.com
INIT_SUPERUSER_PASSWORD=改成你的强密码
```

### 4.3 守卫 + 替换检查

`app/deps.py` 新增：

```python
def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser access required.")
    return current_user
```

替换 4 处散落检查：

| 位置 | 原判断 | 改后 |
|------|--------|------|
| `app/api.py:186` | `if current_user.role != "admin": raise 403` | 路由签名改为 `current_user: User = Depends(require_superuser)`，删除内置判断 |
| `app/services.py:417` | `if admin_user.role == "admin":` | `if admin_user.is_superuser:` |
| `app/services.py:425` | `if current.role != "admin" and current.id != target_user.id:` | `if not current.is_superuser and current.id != target_user.id:` |
| `app/services.py:437` | `if current.role != "admin":` | `if not current.is_superuser:` |

### 4.4 promote / demote 接口（app/api.py）

```python
@router.post("/admin/users/{user_id}/promote")
def promote_user(
    user_id: int,
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    u.is_superuser = True
    db.commit()
    return {"ok": True, "user": UserRead.model_validate(u)}

@router.post("/admin/users/{user_id}/demote")
def demote_user(
    user_id: int,
    current_user: User = Depends(require_superuser),
    db: Session = Depends(get_db),
) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    # 防自降级导致系统无超管
    if u.id == current_user.id:
        raise HTTPException(400, "不能降级自己")
    if not db.scalars(select(User).where(User.is_superuser, User.id != u.id)).first():
        raise HTTPException(400, "至少保留一位超级管理员")
    u.is_superuser = False
    db.commit()
    return {"ok": True, "user": UserRead.model_validate(u)}
```

`/api/users`（list）与 `PATCH/DELETE /api/users/{id}` 保持现有判定（已在 services 改为 `is_superuser`），路由层无需额外守卫。

---

## 5. 前端改动

### 5.1 菜单动态过滤（BasicLayout.tsx）

将模块级静态 `menuItems` 改为 `buildMenuItems(isSuperuser)` 函数，组件内 `useMemo` 生成：

```tsx
const ADMIN_ONLY = ["/mcp-servers", "/skills", "/hooks", "/users"]

function filterMenu(items: MenuItem[], isSuper: boolean): MenuItem[] {
  if (isSuper) return items
  return items
    .filter((it) => !ADMIN_ONLY.includes(it.key as string))
    .map((it) => (it.children ? { ...it, children: filterMenu(it.children, isSuper) } : it))
}

const menuItems = useMemo(() => filterMenu(MENU_ALL, !!user?.is_superuser), [user])
```

分组规则：

- **超管专属（非超管移除）**：MCP Server、Skills、Hooks、用户管理
- **所有人保留**：仪表盘、聊天、AI 提供商、提示词模板、知识库、媒体库、电商套图、长期记忆、系统设置
- 暂保留"AI 提供商"对所有人生效（聊天需选提供商）；提供商配置权限细化留待后续（不阻塞本版）

### 5.2 用户管理提拔（UserManagement/index.tsx）

- `User` interface 加 `is_superuser: boolean`
- 表格加"超级管理员"列：`render: (v) => <Tag color={v ? 'gold' : 'default'}>{v ? '超级管理员' : '否'}</Tag>`
- 编辑弹窗加 `is_superuser` 开关：`Form.Item name="is_superuser" valuePropName="checked" label="超级管理员"`
- `handleSave` 已 `PATCH` 全部 values，`UserUpdate` 加了 `is_superuser` 即生效
- 非超管访问 `/users` 应由路由守卫拦截（见 §7 验证）

---

## 6. 迁移批次（每批可独立回退）

| 批次 | 内容 | 回退方式 |
|------|------|----------|
| A | 模型 + 迁移 + seed（加字段、加列、seed 设 True） | 删列 + 还原 seed |
| B | schemas + 守卫 + promote/demote 接口 | 还原代码 |
| C | 前端菜单过滤 + 用户管理提拔 UI | 还原前端 |

---

## 7. 验证（铁律：改动须通过测试/浏览器回归才宣布完成）

### 后端（脚本 / curl）
- 迁移后 `users.is_superuser` 列存在、默认 0
- `admin@example.com` 的 `is_superuser = 1`
- 普通用户调 `POST /api/admin/users/{id}/promote` → 403
- 超管调 promote → 成功；demote 自己 → 400；demote 最后一位超管 → 400
- 普通用户调 `PATCH /api/users/{other_id}`（改 role）→ 被拒；改自己 → 成功

### 前端（Playwright 真实浏览器，遵守铁律）
- 超管登录 → 菜单含 MCP / Skills / Hooks / 用户管理
- 普通用户登录 → 上述四项不可见
- 超管在用户管理把普通用户提拔 → 该用户重新登录后菜单出现管理项；降级后消失

---

## 8. 待确认项（已给推荐，不阻塞本版）

1. **"AI 提供商"菜单本版对所有人可见**（推荐）；提供商配置权限细化留后续。
2. **demote 防自降级 + 防降级最后一位超管**（推荐：已实现于 §4.4）。
3. **`role` 字段保留展示，超管判定统一用 `is_superuser`**，不再以 `role == "admin"` 判管理员（推荐）。

---

## 9. 实际验证结果（2026-07-19，隔离环境，未触碰真实 agent.db）

### 9.1 验证方式
- 后端：两套脚本，均对 **agent.db 的副本** 操作（真实库零写入）。
  - `verify_seed`：全新库 → `init_db()` + `seed_database()` → 确认产出 `is_superuser=True` 的 admin，登录 + `/auth/me` 校验通过。
  - `verify_adro28`：真实库副本 → 确认迁移加列、`require_superuser` 拦截（promote/reset-password → 403）、admin promote→200、demote 自己→400、demote 他人→200、清理 OK。
- 前端：Playwright 真实浏览器，起**隔离** uvicorn(8011) + vite dev(5173)，两个隔离浏览器上下文（超管 / 普通用户）。13 项断言全过：
  - 超管菜单含 MCP Server / Skills / Hooks / 用户管理；
  - 普通用户四项全不可见（其余正常项保留）；
  - 普通用户直达 `/users` 被重定向到 `/dashboard`。
- 服务起停：验证结束后已停掉隔离的 8011/5173 进程，真实 8010/80（Docker）保持运行。

### 9.2 验证中发现并修复的预存缺陷（超出本 ADR 范围，但阻塞核心功能）
1. **`gallery_tasks.name` 缺失 → 新建套图任务崩溃**
   运行时 `init_db()` 路径（`_migrate_sqlite_columns`）此前未补齐 `GalleryTask.name`（仅 CLI `sync_model_columns` 覆盖），旧库新建套图任务报 `no such column: gallery_tasks.name`。
   **修复**：`app/core/database.py` 的 `_migrate_sqlite_columns` 追加可空 `name VARCHAR(200)` 迁移；隔离库回归：列存在 + 新建 GalleryTask 成功。
2. **历史库 `username=admin` 残留记录永不被提拔为超管**
   真实 agent.db 存在历史残留 `username=admin`（email=`admin@admin.com`、`is_superuser=False`）。原 seed 在记录已存在时跳过创建，导致重启后管理员永不为超管、ADR-028 菜单不可见。
   **修复**：`app/db/__init__.py` 的 `seed_database` 改为——若 `username=admin` 已存在且非超管，则仅补 `is_superuser=True`（**不动 password/email**，避免覆盖用户凭据）。隔离副本验证：残留被提拔、22 个普通用户无一是误提。

### 9.3 用户侧上线须知（重要）
- 真实 agent.db 中的 `username=admin` 为历史残留（email `admin@admin.com`，非文档惯例的 `admin@example.com`）。**下次重启真实 API 时该账号会被自动提拔为超级管理员**（密码/邮箱保持不变）。
- 若你惯用 `admin@example.com` / `admin123` 登录（见工作记忆约定），该邮箱在真实库中尚不存在 → 需你确认是否要我做一次**非破坏性**对齐（把残留 admin 的 email 改为 `admin@example.com`、密码重置为 `admin123`，仅影响这一条 admin 记录），或你直接用现有 `admin@admin.com` 凭据登录。
- 上线动作：重启 API 容器（Docker）即触发迁移 + seed 提拔；前端需重新 `build` 使 `dist` 含本版改动（当前运行的是旧 `dist`）。
