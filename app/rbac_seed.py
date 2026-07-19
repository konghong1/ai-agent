"""RBAC v2 种子：资源(菜单+权限) / 角色 / 用户-角色回填。

幂等、可重复执行；仅 INSERT 缺失行，绝不删除或改动既有数据。
挂接于 ``app.db.init_db.seed_database``。
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.models import (
    Resource,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.permissions import (
    CATALOG,
    PERM_ADMIN_PERMISSIONS_MANAGE,
    PERM_ADMIN_SYSTEM_MANAGE,
    PERM_ADMIN_USERS_MANAGE,
    PERM_GALLERY_USE,
    PERM_HOOK_VIEW,
    PERM_KB_READ,
    PERM_MCP_VIEW,
    PERM_MEDIA_USE,
    PERM_MEMORY_USE,
    PERM_PROVIDERS_VIEW,
    PERM_PROMPT_VIEW,
    PERM_SKILL_VIEW,
    PERM_TEAM_VIEW,
    PERSONAL_DEFAULT,
)

logger = logging.getLogger(__name__)

# 菜单资源种子（镜像 web/src/layouts/BasicLayout.tsx 的 menuItems + MENU_PERM）
# 2026-07-19 Phase 3：新增「系统管理」父菜单（admin.system.manage 门控），
# 把 用户管理 / 团队管理员权限 移入其下，并新增 资源管理 / 角色管理 两项子菜单。
# (code, name, parent_code, path, icon, permission_code, sort_order, is_system)
MENU_SEED: list[tuple] = [
    ("menu.dashboard", "仪表盘", None, "/dashboard", "DashboardOutlined", None, 10, True),
    ("menu.agent", "Agent", None, None, "RobotOutlined", None, 20, True),
    ("menu.agent.chat", "聊天", "menu.agent", "/agents/chat", "", None, 10, True),
    ("menu.agent.providers", "AI 提供商", "menu.agent", "/providers", "", PERM_PROVIDERS_VIEW, 20, True),
    ("menu.agent.mcpservers", "MCP Server", "menu.agent", "/mcp-servers", "", PERM_MCP_VIEW, 30, True),
    ("menu.agent.skills", "Skills", "menu.agent", "/skills", "", PERM_SKILL_VIEW, 40, True),
    ("menu.agent.hooks", "Hooks", "menu.agent", "/hooks", "", PERM_HOOK_VIEW, 50, True),
    ("menu.agent.prompts", "提示词模板", "menu.agent", "/prompt-templates", "", PERM_PROMPT_VIEW, 60, True),
    ("menu.resources", "资源中心", None, None, "CloudServerOutlined", None, 30, True),
    ("menu.resources.kb", "知识库", "menu.resources", "/knowledge-bases", "", PERM_KB_READ, 10, True),
    ("menu.resources.media", "媒体库", "menu.resources", "/media-library", "", PERM_MEDIA_USE, 20, True),
    # ── 系统管理（父菜单，仅超管可见）──
    # 注意：用户管理 / 团队管理员权限 沿用原稳定 code（menu.users / menu.team-admins），
    # 仅把 parent_code 改为 menu.system（upsert 原地更新，避免产生重复顶层项）。
    ("menu.system", "系统管理", None, None, "SettingOutlined", PERM_ADMIN_SYSTEM_MANAGE, 70, True),
    ("menu.users", "用户管理", "menu.system", "/users", "TeamOutlined", PERM_ADMIN_USERS_MANAGE, 10, True),
    ("menu.team-admins", "团队管理员权限", "menu.system", "/admin/team-admins", "SettingOutlined", PERM_ADMIN_PERMISSIONS_MANAGE, 20, True),
    ("menu.system.resources", "资源管理", "menu.system", "/admin/resources", "AppstoreOutlined", PERM_ADMIN_PERMISSIONS_MANAGE, 30, True),
    ("menu.system.roles", "角色管理", "menu.system", "/admin/roles", "SafetyOutlined", PERM_ADMIN_PERMISSIONS_MANAGE, 40, True),
    ("menu.teams", "团队", None, "/teams", "TeamOutlined", PERM_TEAM_VIEW, 90, True),
    ("menu.workbench", "工作台", None, None, "AppstoreOutlined", None, 95, True),
    ("menu.workbench.gallery", "电商套图", "menu.workbench", "/ecommerce-gallery", "", PERM_GALLERY_USE, 10, True),
    ("menu.memory", "长期记忆", None, "/memory", "DatabaseOutlined", PERM_MEMORY_USE, 100, True),
    ("menu.settings", "系统设置", None, "/settings", "SettingOutlined", None, 110, True),
]


def _admin_id(db) -> int:
    su = db.query(User).filter_by(is_superuser=True).order_by(User.id).first()
    return su.id if su else 1


def _upsert_resource(
    db,
    code: str,
    name: str,
    rtype: str,
    category: str = "general",
    parent_code: str | None = None,
    path: str | None = None,
    component: str | None = None,
    icon: str | None = None,
    sort_order: int = 0,
    permission_code: str | None = None,
    is_visible: bool = True,
    is_system: bool = False,
    description: str | None = None,
) -> None:
    """资源幂等 upsert：缺失则 INSERT，存在则按最新定义 UPDATE（含 parent_code 等结构字段）。

    这样菜单结构调整（如把 用户管理 移入 系统管理）在重启 seed 后即可同步到真实库，
    无需手工改库。系统资源(is_system)同样会被刷新为其权威定义。
    """
    existing = db.query(Resource).filter_by(code=code).first()
    if existing is None:
        db.add(
            Resource(
                code=code, name=name, type=rtype, category=category,
                parent_code=parent_code, path=path, component=component, icon=icon,
                sort_order=sort_order, permission_code=permission_code,
                is_visible=is_visible, is_system=is_system, description=description,
            )
        )
        return
    existing.name = name
    existing.type = rtype
    existing.category = category
    existing.parent_code = parent_code
    existing.path = path
    existing.component = component
    existing.icon = icon
    existing.sort_order = sort_order
    existing.permission_code = permission_code
    existing.is_visible = is_visible
    existing.is_system = is_system
    existing.description = description


def seed_rbac_resources(db) -> None:
    """CATALOG 常量 → resources(type=permission) + 静态菜单 → resources(type=menu)。

    权限码统一真源为 resources(type='permission')（ADR-031）；CATALOG 常量仅作种子定义。
    """
    # 1) 权限资源：来自 CATALOG 常量（幂等 upsert，带 description/category/is_system）
    for c in CATALOG:
        _upsert_resource(
            db, code=c["code"], name=c["name"], rtype="permission",
            category=c.get("category", "general"), sort_order=c.get("sort_order", 0),
            description=c.get("description", ""),
            permission_code=c["code"], is_system=c.get("is_system", False),
        )
    # 2) 菜单资源：来自 MENU_SEED（幂等 upsert，结构变更可同步）
    for code, name, parent, path, icon, perm, sort, issys in MENU_SEED:
        _upsert_resource(
            db, code=code, name=name, rtype="menu",
            category="menu", parent_code=parent, path=path,
            icon=(icon or None), sort_order=sort,
            permission_code=perm, is_system=issys,
        )
    logger.info("Seeded RBAC resources (permissions + menus)")


def seed_rbac_roles(db) -> None:
    """base / superuser 角色 + 各自权限。"""
    actor = _admin_id(db)

    base = db.query(Role).filter_by(code="base").first()
    if base is None:
        base = Role(code="base", name="基础角色", description="自注册用户默认获得的最基础权限", is_system=True, is_default=True, sort_order=10)
        db.add(base)
        db.flush()
    for code in PERSONAL_DEFAULT:
        if db.query(RolePermission).filter_by(role_id=base.id, permission_code=code).first() is None:
            db.add(RolePermission(role_id=base.id, permission_code=code, granted_by_user_id=actor))

    su = db.query(Role).filter_by(code="superuser").first()
    if su is None:
        su = Role(code="superuser", name="超级管理员", description="拥有全部权限", is_system=True, is_default=False, sort_order=0)
        db.add(su)
        db.flush()
    all_codes = [c["code"] for c in CATALOG]
    for code in all_codes:
        if db.query(RolePermission).filter_by(role_id=su.id, permission_code=code).first() is None:
            db.add(RolePermission(role_id=su.id, permission_code=code, granted_by_user_id=actor))
    logger.info("Seeded RBAC roles (base + superuser)")


def assign_default_roles_to_user(db, user_id: int) -> int:
    """把当前所有 is_default 角色授予指定用户（幂等）。返回新授予条数。"""
    actor = user_id
    count = 0
    for r in db.scalars(select(Role).where(Role.is_default == True)).all():  # noqa: E712
        if db.query(UserRole).filter_by(user_id=user_id, role_id=r.id, team_id=None).first() is None:
            db.add(UserRole(user_id=user_id, role_id=r.id, team_id=None, granted_by_user_id=actor))
            count += 1
    return count


def backfill_user_roles(db) -> None:
    """为所有用户回填全部 is_default 角色（幂等）；保留现有 user_permissions 作 override。

    2026-07-19 Phase 3：从「仅 base」扩展为「所有默认角色」，使新增的默认角色也能自动覆盖既有用户。
    """
    default_roles = db.scalars(select(Role).where(Role.is_default == True)).all()  # noqa: E712
    if not default_roles:
        return
    actor = _admin_id(db)
    count = 0
    for u in db.query(User).all():
        for r in default_roles:
            if db.query(UserRole).filter_by(user_id=u.id, role_id=r.id, team_id=None).first() is None:
                db.add(UserRole(user_id=u.id, role_id=r.id, team_id=None, granted_by_user_id=actor))
                count += 1
    if count:
        logger.info("Backfilled %d default-role assignments", count)
