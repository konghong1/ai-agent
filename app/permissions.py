"""权限系统（两级委派 · 最细粒度）。

设计要点（见 designs/plan-permission-rbac.md）：
- 权限以 permission_code 为原子单位；CATALOG 常量作为种子定义，重启幂等 upsert 进 resources(type='permission')（统一权限源，见 ADR-031）。
- 两级委派：系统超管 → team_admin_scopes（团队管理员可授予范围）→ user_permissions（用户实际持有）。
- can() 为唯一判定入口，禁止散落 role=="admin"/is_superuser 检查。
- 所有权限判定收敛到 can()，团队空间需 db。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Role, RolePermission, TeamAdminScope, User, UserPermission, UserRole

# ── 权限码常量（种子定义：重启 upsert 进 resources(type='permission')）──
# 菜单可见性绑定各 category 的视图/使用码（前端据此过滤）。
PERM_DASHBOARD_VIEW = "dashboard.view"

PERM_CHAT_USE = "chat.use"
PERM_CHAT_SESSION_CREATE = "chat.session.create"
PERM_CHAT_SESSION_DELETE = "chat.session.delete"
PERM_CHAT_EXPORT = "chat.export"

PERM_KB_READ = "kb.read"
PERM_KB_WRITE = "kb.write"
PERM_KB_DELETE = "kb.delete"
PERM_KB_SHARE = "kb.share"

PERM_GALLERY_USE = "gallery.use"
PERM_GALLERY_TASK_CREATE = "gallery.task.create"
PERM_GALLERY_TASK_REMIX = "gallery.task.remix"
PERM_GALLERY_TASK_DELETE = "gallery.task.delete"
PERM_GALLERY_PUBLISH = "gallery.publish"

PERM_MEDIA_USE = "media.use"
PERM_MEDIA_UPLOAD = "media.upload"
PERM_MEDIA_DELETE = "media.delete"

PERM_MEMORY_USE = "memory.use"
PERM_MEMORY_EDIT = "memory.edit"

PERM_MCP_VIEW = "mcp.view"
PERM_MCP_MANAGE = "mcp.manage"
PERM_SKILL_VIEW = "skill.view"
PERM_SKILL_MANAGE = "skill.manage"
PERM_HOOK_VIEW = "hook.view"
PERM_HOOK_MANAGE = "hook.manage"

# AI 提供商 / 提示词模板：此前菜单完全无权限门控，任何登录用户可见，属安全缺口。
# 现补足 view/manage 两级，与个人空间的「自己的配置」语义一致（view 进基础默认集）。
PERM_PROVIDERS_VIEW = "providers.view"
PERM_PROVIDERS_MANAGE = "providers.manage"
PERM_PROMPT_VIEW = "prompt.view"
PERM_PROMPT_MANAGE = "prompt.manage"

PERM_TEAM_VIEW = "team.view"
PERM_TEAM_MEMBERS_MANAGE = "team.members.manage"
PERM_TEAM_PERMISSIONS_MANAGE = "team.permissions.manage"
PERM_TEAM_SETTINGS_MANAGE = "team.settings.manage"

PERM_ADMIN_USERS_MANAGE = "admin.users.manage"
PERM_ADMIN_SYSTEM_MANAGE = "admin.system.manage"
PERM_ADMIN_PERMISSIONS_MANAGE = "admin.permissions.manage"

# 个人空间默认权限（自注册/迁移补齐，保持现状体验）
PERSONAL_DEFAULT: frozenset[str] = frozenset({
    PERM_DASHBOARD_VIEW,
    PERM_CHAT_USE, PERM_CHAT_SESSION_CREATE, PERM_CHAT_SESSION_DELETE, PERM_CHAT_EXPORT,
    PERM_KB_READ, PERM_KB_WRITE, PERM_KB_DELETE, PERM_KB_SHARE,
    PERM_GALLERY_USE, PERM_GALLERY_TASK_CREATE, PERM_GALLERY_TASK_REMIX, PERM_GALLERY_TASK_DELETE, PERM_GALLERY_PUBLISH,
    PERM_MEDIA_USE, PERM_MEDIA_UPLOAD, PERM_MEDIA_DELETE,
    PERM_MEMORY_USE, PERM_MEMORY_EDIT,
    PERM_MCP_VIEW, PERM_SKILL_VIEW, PERM_HOOK_VIEW,
    PERM_PROVIDERS_VIEW, PERM_PROMPT_VIEW,
    PERM_TEAM_VIEW,
})

# 权限目录（种子化）。category 对应菜单分组；is_system=True 仅超管可授。
CATALOG: list[dict] = [
    {"code": PERM_DASHBOARD_VIEW, "name": "工作台", "category": "dashboard", "description": "查看工作台首页", "sort_order": 0, "is_system": False},

    {"code": PERM_CHAT_USE, "name": "聊天", "category": "chat", "description": "进入并使用聊天", "sort_order": 10, "is_system": False},
    {"code": PERM_CHAT_SESSION_CREATE, "name": "新建会话", "category": "chat", "description": "创建聊天会话", "sort_order": 11, "is_system": False},
    {"code": PERM_CHAT_SESSION_DELETE, "name": "删除会话", "category": "chat", "description": "删除聊天会话", "sort_order": 12, "is_system": False},
    {"code": PERM_CHAT_EXPORT, "name": "导出对话", "category": "chat", "description": "导出对话内容", "sort_order": 13, "is_system": False},

    {"code": PERM_KB_READ, "name": "查看知识库", "category": "knowledge-base", "description": "查看知识库", "sort_order": 20, "is_system": False},
    {"code": PERM_KB_WRITE, "name": "编辑知识库", "category": "knowledge-base", "description": "编辑知识库内容", "sort_order": 21, "is_system": False},
    {"code": PERM_KB_DELETE, "name": "删除知识库", "category": "knowledge-base", "description": "删除知识库", "sort_order": 22, "is_system": False},
    {"code": PERM_KB_SHARE, "name": "共享知识库", "category": "knowledge-base", "description": "共享知识库给其他成员", "sort_order": 23, "is_system": False},

    {"code": PERM_GALLERY_USE, "name": "电商套图", "category": "gallery", "description": "进入电商套图工作台", "sort_order": 30, "is_system": False},
    {"code": PERM_GALLERY_TASK_CREATE, "name": "创建套图任务", "category": "gallery", "description": "创建套图生成任务", "sort_order": 31, "is_system": False},
    {"code": PERM_GALLERY_TASK_REMIX, "name": "一键 remix", "category": "gallery", "description": "对结果一键 remix", "sort_order": 32, "is_system": False},
    {"code": PERM_GALLERY_TASK_DELETE, "name": "删除套图任务", "category": "gallery", "description": "删除套图任务", "sort_order": 33, "is_system": False},
    {"code": PERM_GALLERY_PUBLISH, "name": "发布创作案例", "category": "gallery", "description": "发布为创作案例", "sort_order": 34, "is_system": False},

    {"code": PERM_MEDIA_USE, "name": "素材库", "category": "media", "description": "进入素材库", "sort_order": 40, "is_system": False},
    {"code": PERM_MEDIA_UPLOAD, "name": "上传素材", "category": "media", "description": "上传素材文件", "sort_order": 41, "is_system": False},
    {"code": PERM_MEDIA_DELETE, "name": "删除素材", "category": "media", "description": "删除素材文件", "sort_order": 42, "is_system": False},

    {"code": PERM_MEMORY_USE, "name": "长期记忆", "category": "memory", "description": "查看长期记忆", "sort_order": 50, "is_system": False},
    {"code": PERM_MEMORY_EDIT, "name": "编辑记忆", "category": "memory", "description": "编辑长期记忆", "sort_order": 51, "is_system": False},

    {"code": PERM_MCP_VIEW, "name": "查看 MCP", "category": "mcp", "description": "查看 MCP Server", "sort_order": 60, "is_system": False},
    {"code": PERM_MCP_MANAGE, "name": "管理 MCP", "category": "mcp", "description": "增删改 MCP Server", "sort_order": 61, "is_system": False},
    {"code": PERM_SKILL_VIEW, "name": "查看 Skill", "category": "skill", "description": "查看 Skill", "sort_order": 62, "is_system": False},
    {"code": PERM_SKILL_MANAGE, "name": "管理 Skill", "category": "skill", "description": "增删改 Skill", "sort_order": 63, "is_system": False},
    {"code": PERM_HOOK_VIEW, "name": "查看 Hook", "category": "hook", "description": "查看 Hook", "sort_order": 64, "is_system": False},
    {"code": PERM_HOOK_MANAGE, "name": "管理 Hook", "category": "hook", "description": "增删改 Hook", "sort_order": 65, "is_system": False},

    # AI 提供商 / 提示词模板：此前菜单完全无门控（任何登录用户可见），此处补全 view/manage 两级。
    {"code": PERM_PROVIDERS_VIEW, "name": "查看 AI 提供商", "category": "providers", "description": "查看 AI 提供商配置", "sort_order": 66, "is_system": False},
    {"code": PERM_PROVIDERS_MANAGE, "name": "管理 AI 提供商", "category": "providers", "description": "增删改 AI 提供商", "sort_order": 67, "is_system": False},
    {"code": PERM_PROMPT_VIEW, "name": "查看提示词模板", "category": "prompt", "description": "查看提示词模板", "sort_order": 68, "is_system": False},
    {"code": PERM_PROMPT_MANAGE, "name": "管理提示词模板", "category": "prompt", "description": "增删改提示词模板", "sort_order": 69, "is_system": False},

    {"code": PERM_TEAM_VIEW, "name": "团队空间", "category": "team", "description": "进入团队空间", "sort_order": 70, "is_system": False},
    {"code": PERM_TEAM_MEMBERS_MANAGE, "name": "成员管理", "category": "team", "description": "添加/移除团队成员", "sort_order": 71, "is_system": False},
    {"code": PERM_TEAM_PERMISSIONS_MANAGE, "name": "成员权限分配", "category": "team", "description": "为成员分配功能权限", "sort_order": 72, "is_system": False},
    {"code": PERM_TEAM_SETTINGS_MANAGE, "name": "团队设置", "category": "team", "description": "修改团队设置", "sort_order": 73, "is_system": False},

    {"code": PERM_ADMIN_USERS_MANAGE, "name": "用户管理", "category": "admin", "description": "平台用户管理", "sort_order": 80, "is_system": True},
    {"code": PERM_ADMIN_SYSTEM_MANAGE, "name": "系统管理", "category": "admin", "description": "系统/Provider 等配置", "sort_order": 81, "is_system": True},
    {"code": PERM_ADMIN_PERMISSIONS_MANAGE, "name": "团队管理员权限", "category": "admin", "description": "分配团队管理员的授予范围", "sort_order": 82, "is_system": True},
]


def ensure_personal_defaults(user_id: int, db: Session) -> None:
    """为用户补齐个人空间默认权限（幂等）。无个人空间权限行时才补，避免覆盖显式分配。"""
    cnt = db.scalar(
        select(func.count()).select_from(UserPermission).where(
            UserPermission.user_id == user_id,
            UserPermission.team_id.is_(None),
        )
    )
    if cnt and cnt > 0:
        return
    for code in PERSONAL_DEFAULT:
        db.add(UserPermission(
            user_id=user_id, team_id=None, permission_code=code, granted_by_user_id=user_id,
        ))
    db.flush()


def backfill_base_permissions(user_id: int, db: Session) -> None:
    """确保用户个人空间权限包含全部 PERSONAL_DEFAULT 基础码（缺失则补，不删不改现有）。

    用于目录扩展 / 默认集变更后给既有用户补齐新增的基础权限（如 hook.view / providers.view）。
    与 ensure_personal_defaults 的区别：后者在「已有个人权限时直接返回」以避免覆盖显式分配，
    本函数则保证基础码始终存在（基础角色权限 = 自动注册用户应得），幂等。
    """
    existing = set(db.scalars(
        select(UserPermission.permission_code).where(
            UserPermission.user_id == user_id,
            UserPermission.team_id.is_(None),
        )
    ).all())
    for code in PERSONAL_DEFAULT:
        if code not in existing:
            db.add(UserPermission(
                user_id=user_id, team_id=None, permission_code=code, granted_by_user_id=user_id,
            ))
    db.flush()


def get_user_permissions(user_id: int, team_id: int | None, db: Session) -> set[str]:
    """取用户在指定空间的有效权限码集合。team_id=None 仅个人空间；否则含 NULL(个人)与该团队。"""
    q = select(UserPermission.permission_code).where(UserPermission.user_id == user_id)
    if team_id is None:
        q = q.where(UserPermission.team_id.is_(None))
    else:
        q = q.where((UserPermission.team_id == team_id) | (UserPermission.team_id.is_(None)))
    return set(db.scalars(q).all())


def get_role_permissions(user_id: int, db: Session) -> set[str]:
    """取用户全局角色(team_id IS NULL)所授予的权限码集合。

    角色一律 global（不按团队细分），因此这些权限在任何上下文(个人/任意团队)都生效。
    """
    return set(db.scalars(
        select(RolePermission.permission_code)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id, UserRole.team_id.is_(None))
    ).all())


def get_effective_permissions(user: User, team_id: int | None, db: Session) -> set[str]:
    """加性并集：全局角色权限 ∪ 个人/团队显式授权。

    预测性：纯加性、无负权限 → 判定可枚举、可审计。团队管理员 scope 不在此合并
    （scope 用于"可授予范围"，其等效权限已同步写入 user_permissions，故走 user_permissions 路径）。
    """
    perms = get_user_permissions(user.id, team_id, db)
    perms |= get_role_permissions(user.id, db)
    return perms


def get_team_admin_scope(user_id: int, db: Session) -> set[str]:
    """取团队管理员被允许授予的权限码集合。"""
    return set(db.scalars(
        select(TeamAdminScope.permission_code).where(TeamAdminScope.team_admin_user_id == user_id)
    ).all())


def is_team_admin(user: User, db: Session) -> bool:
    """是否团队管理员（超管不算团队管理员，避免角色混淆）。"""
    if getattr(user, "is_team_admin", False):
        return True
    return db.scalar(
        select(TeamAdminScope.id).where(TeamAdminScope.team_admin_user_id == user.id)
    ) is not None


def can(user: User, perm: str, team_id: int | None = None, db: Session | None = None) -> bool:
    """集中权限判定。

    - 系统超管：放行一切。
    - 无 db：保守拒绝（团队权限必须查库）。
    - 全局角色权限：角色不按团队细分，任何上下文都生效（加性并集）。
    - 个人空间(team_id=None)：仅匹配 team_id IS NULL 的权限行。
    - 团队空间：匹配该团队行或 NULL(个人)行。
    """
    if getattr(user, "is_superuser", False):
        return True
    if db is None:
        return False
    # 1) 全局角色权限（任何上下文生效）
    if perm in get_role_permissions(user.id, db):
        return True
    # 2) 个人/团队显式授权
    q = select(UserPermission.id).where(
        UserPermission.user_id == user.id,
        UserPermission.permission_code == perm,
    )
    if team_id is None:
        q = q.where(UserPermission.team_id.is_(None))
    else:
        q = q.where((UserPermission.team_id == team_id) | (UserPermission.team_id.is_(None)))
    return db.scalar(q) is not None
