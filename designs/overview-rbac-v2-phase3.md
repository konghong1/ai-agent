# 概览：RBAC v2 系统管理模块（Phase 0-3 落地 + 真机验证）

## 完成内容
按用户拍板「按动态菜单实现、团队不细化角色」，完成显式 RBAC 系统管理模块的 Phase 0-3，并通过真实浏览器回归 **11/11 PASS**。

### 实现
- **4 张新表**：`Resource`(菜单/权限码/API 统一注册, 树形 `parent_code`, `is_system` 受保护) / `Role`(全局角色) / `RolePermission` / `UserRole`(`team_id` 恒 NULL)。
- **`can()` 加性并集**：角色权限 ∪ 个人授权 ∪ 团队 scope，超管恒真，无负权限。
- **动态菜单**：`GET /api/system/menus` 由 Resource 驱动，`BasicLayout` 拉接口渲染（保留静态 fallback 防白屏）。
- **系统管理父菜单**（`admin.system.manage` 门控）收纳：用户管理(移入+角色分配抽屉)、资源管理、角色管理、团队管理员权限。
- **后端 CRUD**：`/system/resources`、`/system/roles`、`/system/roles/{id}/permissions`、`/users/{id}/roles`。
- **前端**：`ResourceManage` / `RoleManage`(权限分配 Drawer) / `UserManagement`(角色分配抽屉)；新注册用户自动获默认角色。

### 验证（真实 Docker+MySQL + Playwright 真机）
动态菜单端点、侧边栏渲染、资源 CRUD、**新增菜单整页重载后动态出现**、角色 CRUD、权限分配持久化(`permission_count=2`)、用户角色分配、API 清理、DB 末态无残留、无运行时错误。
- **复盘**：自动化脚本不可用 UI Popconfirm 静默吞错导致测试数据残留；改为 API DELETE 清理 + 末态 DB 复核。

## 关键决策（ADR-030）
- 全量动态菜单（替换硬编码）。
- 全局角色，不按团队细分。
- 「创作案例发布给多团队」属内容分发，推迟到 Phase 5。
- Phase 4（合并 permission_catalog 与 resources）可选，未做。

## 交付物
- `designs/ADR-030-rbac-v2-system-module.md`（新增）
- `designs/plan-permission-rbac-v2-system-module.md`（状态→Accepted）
- 代码：`app/models.py` `app/rbac_seed.py` `app/api.py` `app/services.py` + 前端 `ResourceManage`/`RoleManage`/`UserManagement`
- 记忆：MEMORY.md + 2026-07-19.md 已归档

## 后续
- Phase 4（可选）权限源合并；Phase 5 内容多团队分发。
