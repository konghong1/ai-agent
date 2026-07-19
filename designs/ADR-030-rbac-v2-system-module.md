# ADR-030: RBAC v2 系统管理模块（动态菜单 + 全局角色）

## Status
Accepted（已落地并真机验证 2026-07-19）

## Context
原权限系统（ADR-029，两级委派）以硬编码 `menuItems` + `MENU_PERM` 渲染菜单，权限只能由超管在代码层增删；用户诉求是新增「系统管理」模块，把「用户管理」移入其下，并提供**资源 / 角色的增删**（即管理员可自己在后台加菜单、加角色），自注册用户自动获得一个「基础角色」能看到最基础菜单。同时要求**保留原有的团队两级委派约束**。

核心张力：菜单到底是「硬编码 + 按角色可见性过滤」还是「全量动态（菜单由资源表驱动）」？前者改动小但管理员无法自助加菜单；后者灵活但替换了现有菜单渲染路径（最大变更点）。

## Decision
1. **全量动态菜单**：菜单完全由 `Resource(type=menu, parent_code 树)` 驱动。新增 `GET /api/system/menus`（按当前用户 `can()` 过滤），前端 `BasicLayout` 改为拉接口渲染，移除硬编码 `menuItems`/`MENU_PERM`，仅保留静态 fallback 防白屏。管理员在「资源管理」页新增菜单资源后，持有对应权限的用户整页重载即可见。
2. **显式 RBAC 四表**：`Resource` / `Role` / `RolePermission` / `UserRole`。`can()` 改为**加性并集**：角色权限 ∪ 个人 `user_permissions` ∪ 团队 `team_admin_scopes`，超管恒真，纯加性、无负权限。
3. **全局角色，不按团队细分**：`UserRole.team_id` 恒为 `NULL`。角色是「用户拥有什么权限集合」的全局抽象，与团队数据归属解耦。
4. **默认角色自动授予**：`Role.is_default=true` 的角色在用户注册/存量回填时自动授予（`assign_default_roles_to_user` / `backfill_user_roles`）。
5. **内容分发推迟到 Phase 5**：「创作案例发布给多团队使用」被判定为**内容可见性/分发**问题（解法②：案例 born-personal + 显式 `case_team_shares` 共享表），**不是**数据归属问题，故不进入角色/团队细分模型，留待后续。

## Consequences
- **易**：管理员可自助配置菜单与角色，无需改代码/重启；新菜单项对有权用户立即生效；权限模型统一为「原子 permission_code + 加性并集」，扩展面清晰。
- **难 / 代价**：
  - 动态菜单使「菜单结构」成为受保护数据——误删系统资源(`is_system`)会破坏 UI，故对系统资源/系统角色做了删除保护。
  - `can()` 加性并集 + 无负权限，意味着「收回某权限」只能从对应角色/个人授权中移除，不能「deny 覆盖」；当前产品不需要 deny，可接受。
  - 全局角色与团队数据隔离正交，未来若要做「按团队的角色」，需新增 `team_id` 维度（本期明确不做）。
  - 菜单渲染依赖运行时接口，BasicLayout 需处理加载态与 fallback（已加静态 fallback）。
- **未做（Phase 4 可选）**：合并 `permission_catalog` 与 `resources(type=permission)`，消除两套权限注册源；本期保留双源以降风险。

## 验证
真实 Docker + MySQL(`ai_agent`) + Playwright 真机回归 11/11 PASS：动态菜单端点、侧边栏渲染、资源 CRUD、新增菜单整页重载后动态出现、角色 CRUD、权限分配持久化(`permission_count=2`)、用户角色分配、API 清理测试数据、DB 末态无残留、无前端运行时错误。
