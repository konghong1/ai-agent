# ADR-031: 合并双权限源（permission_catalog → resources）

## Status
Accepted

## Context
RBAC v2 落地后，系统里存在**两套「权限码」来源**，会随时间漂移：

1. `permission_catalog` 表 —— 由 `permissions.py` 的 `CATALOG` 常量种子化，是 `can()` 之外的权威清单；服务于目录 API、角色授权码校验、团队管理员 scope 校验、超管全集。
2. `resources` 表 `type='permission'` —— 设计上要让「菜单 + 权限码」统一在一张注册表里，但此前该槽位由 `seed_rbac_resources` 从 `permission_catalog` 表**复制**而来，代码注释自承「镜像 permission_catalog，后续合并」。

漂移风险：`ResourceManage` 后台页面能直接建 `type='permission'` 资源，但它只进 `resources`、不进 `permission_catalog` → 角色权限抽屉选不到、`can()` 不认、目录看不到 —— 两套账对不上。

同时 `Resource` 模型缺 `description` 列，而前端权限目录「描述」列依赖它（当前由 `CATALOG` 的 description 字段提供）。

## Decision
**以 `Resource(type='permission')` 为权限码唯一真源，删除 `permission_catalog` 表/模型/种子。**

- `permissions.py` 的 `CATALOG` 常量**保留**，但语义降级为「种子定义」：开发者新增权限只改这一处，重启即幂等 upsert 进 `resources(type='permission')`。
- `rbac_seed.seed_rbac_resources` 的权限部分改为直接遍历 `CATALOG`（不再读 `permission_catalog` 表）；`seed_rbac_roles` 的超管角色全量权限也取自 `CATALOG`。
- 运行时（目录 API、角色授权校验、团队管理员 scope 校验、超管全集、`/api/system/menus`）全部改查 `resources(type='permission')`，不再引用 `CATALOG` 或 `permission_catalog`。
- `Resource` 模型新增可空 `description` 列（`sync_model_columns` 启动自动补列），种子与 `ResourceCreate/Update` 均携带 description，使目录「描述」列对 36 个内置权限有值，自定义权限码也可描述。
- `permission_catalog` 表在 MySQL 中**保留为空置孤儿表**（不动 DROP，保证可逆；后续可手工清理）。

## Consequences
- **更易**：权限码只有一处定义（`CATALOG` 常量）与一处实例化（`resources`）；管理员在后台建的 `type='permission'` 资源即时进入目录/校验/菜单门控，不再漂移。
- **更易**：新增功能权限的开发动作收敛为「改 `CATALOG` 一处 + 重启」，无需同步两张表。
- **更难 / 代价**：
  - 动用了「地基」——`can()` 虽不查 catalog（仅成员判定，无回归），但 6 处 API 校验/目录逻辑改读 DB，需真机验证（已做）。
  - 新增 `Resource.description` 列需经 `sync_model_columns` 在真实 MySQL 上自动加列验证（已做，可空无 server_default）。
  - `permission_catalog` 表成为孤儿表，直至后续手工 DROP；期间它空置、无代码引用，无功能影响。
- **可逆性**：若需回滚，`CATALOG` 常量与 `Resource` 模型均在；重新引入 `permission_catalog` 模型 + `seed_permission_catalog` 即可，数据不丢（`resources(type='permission)` 仍含全部权限码）。

## 验证（2026-07-19）
- api 容器重启后 `sync_model_columns` 成功为 `resources` 加 `description` 列；`seed_rbac_resources` 从 `CATALOG` 种出 36 条 `type='permission'` 资源（带 description）。
- `GET /api/permissions/catalog` 返回 36 项，含 description/category/is_system/held/grantable；超管 held 全 true，konghong（团队管理员）admin.* 为 false。
- 角色授权校验：合法码 200、非法码 400；`/api/system/menus` 超管全集正常。
- 前端 Playwright 真机：角色「分配权限」抽屉按 category 分组、显示 description、勾选保存后 `permission_count>0` 持久化。
