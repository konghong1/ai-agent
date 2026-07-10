"""电商套图模块 · Service 层（业务逻辑，与 HTTP 路由解耦）。

设计要点（低耦合 / 高扩展 / 性能好）：
- 路由仅做参数解析与鉴权，所有业务逻辑在此层。
- 文件统一落盘到 ``uploads/gallery/``，回显经 ``/api/gallery/files/{filename}``。
- 生成服务可插拔：配置了默认 image provider+model 时走真实出图；
  否则离线生成 SVG 占位图，保证端到端流程在无外部依赖时亦可验证。
- 类型/字段/成本等配置全部来自 ``gallery_config``，本层不硬编码业务枚举。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.gallery_config import (
    SHOWCASE_SEED,
    estimate_cost,
    get_plan_type,
)

logger = logging.getLogger(__name__)

# uploads/gallery/ 根目录（与 app/services.py 的 UPLOAD_DIR 平级）
GALLERY_UPLOAD_ROOT = Path(__file__).resolve().parents[1] / "uploads" / "gallery"

_ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


# ─────────────────────────────────────────────────────────────
# 文件存储
# ─────────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    GALLERY_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    (GALLERY_UPLOAD_ROOT / "projects").mkdir(parents=True, exist_ok=True)
    (GALLERY_UPLOAD_ROOT / "results").mkdir(parents=True, exist_ok=True)
    (GALLERY_UPLOAD_ROOT / "showcase").mkdir(parents=True, exist_ok=True)


def _safe_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return ext if ext in _ALLOWED_IMAGE_EXT else ".png"


def resolve_file(filename: str) -> Path | None:
    """将相对文件名解析为绝对路径，做路径穿越防护。"""
    if not filename or ".." in filename or filename.startswith("/"):
        return None
    candidate = (GALLERY_UPLOAD_ROOT / filename).resolve()
    root = GALLERY_UPLOAD_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.exists() else None


def save_uploaded_image(project_id: int, data: bytes, original_name: str) -> dict:
    """保存上传的产品原图，返回 {filename, url, size}。"""
    _ensure_dirs()
    ext = _safe_ext(original_name)
    fname = f"projects/{project_id}/{uuid.uuid4().hex}{ext}"
    path = GALLERY_UPLOAD_ROOT / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"filename": fname, "url": f"/api/gallery/files/{fname}", "size": len(data)}


def _hue_from_key(key: str) -> int:
    return (hash(key) % 360 + 360) % 360


def _make_svg(hue: int, title: str, subtitle: str, tag: str) -> str:
    """生成一个离线占位 SVG（渐变 + 文案），无需联网。"""
    h2 = (hue + 40) % 360
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600" viewBox="0 0 600 600">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="hsl({hue},70%,62%)"/>'
        f'<stop offset="100%" stop-color="hsl({h2},65%,48%)"/></linearGradient></defs>'
        f'<rect width="600" height="600" fill="url(#g)"/>'
        f'<rect x="24" y="24" width="552" height="552" rx="28" fill="none" stroke="rgba(255,255,255,.5)" stroke-width="2"/>'
        f'<text x="300" y="280" font-family="PingFang SC,Microsoft YaHei,sans-serif" font-size="40" font-weight="700" '
        f'fill="#fff" text-anchor="middle">{_esc(title)}</text>'
        f'<text x="300" y="330" font-family="Inter,sans-serif" font-size="20" fill="rgba(255,255,255,.85)" text-anchor="middle">{_esc(subtitle)}</text>'
        f'<text x="300" y="540" font-family="Inter,sans-serif" font-size="16" fill="rgba(255,255,255,.8)" text-anchor="middle">{_esc(tag)}</text>'
        f"</svg>"
    )


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def write_result_svg(plan_item_id: int, index: int, title: str, key: str) -> str:
    """生成一张「出图结果」占位 SVG，返回相对文件名。"""
    _ensure_dirs()
    hue = _hue_from_key(key)
    svg = _make_svg(hue, title, f"第 {index} 张", "AI 套图 · 生成示例")
    fname = f"results/{uuid.uuid4().hex}.svg"
    path = GALLERY_UPLOAD_ROOT / fname
    path.write_text(svg, encoding="utf-8")
    return fname


def write_showcase_svg(seed: dict, idx: int) -> str:
    _ensure_dirs()
    hue = int(seed.get("hue", 200))
    title = seed["name"][:10]
    svg = _make_svg(hue, title, f"示例 {idx}", "热门套图示例")
    fname = f"showcase/{uuid.uuid4().hex}.svg"
    path = GALLERY_UPLOAD_ROOT / fname
    path.write_text(svg, encoding="utf-8")
    return fname


# ─────────────────────────────────────────────────────────────
# 项目
# ─────────────────────────────────────────────────────────────

def get_or_create_draft(db: Session, user: models.User) -> models.GalleryProject:
    proj = db.scalar(
        select(models.GalleryProject)
        .where(models.GalleryProject.user_id == user.id, models.GalleryProject.status == "draft")
        .order_by(models.GalleryProject.updated_at.desc())
    )
    if proj:
        return proj
    proj = models.GalleryProject(user_id=user.id, name="未命名套图", status="draft")
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def create_project(db: Session, user: models.User, name: str) -> models.GalleryProject:
    proj = models.GalleryProject(user_id=user.id, name=name or "未命名套图", status="draft")
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return proj


def list_projects(db: Session, user: models.User, status: str | None = None) -> list[models.GalleryProject]:
    q = select(models.GalleryProject).where(models.GalleryProject.user_id == user.id)
    if status:
        q = q.where(models.GalleryProject.status == status)
    return list(db.scalars(q.order_by(models.GalleryProject.updated_at.desc())))


def get_owned_project(db: Session, user: models.User, project_id: int) -> models.GalleryProject | None:
    return db.scalar(
        select(models.GalleryProject).where(
            models.GalleryProject.id == project_id, models.GalleryProject.user_id == user.id
        )
    )


def update_project(db: Session, user: models.User, project_id: int, data: dict) -> models.GalleryProject | None:
    proj = get_owned_project(db, user, project_id)
    if not proj:
        return None
    for k, v in data.items():
        if v is not None:
            setattr(proj, k, v)
    db.commit()
    db.refresh(proj)
    return proj


def delete_project(db: Session, user: models.User, project_id: int) -> bool:
    proj = get_owned_project(db, user, project_id)
    if not proj:
        return False
    db.delete(proj)
    db.commit()
    return True


def recompute_estimate(db: Session, project: models.GalleryProject) -> None:
    items = [{"type_id": it.type_id, "count": it.output_settings.get("count", 1)} for it in project.plan_items]
    est = estimate_cost(items)
    project.estimated_points = est["total_points"]
    project.estimated_minutes = est["total_minutes"]


# ─────────────────────────────────────────────────────────────
# 产品图
# ─────────────────────────────────────────────────────────────

def add_image(db: Session, user: models.User, project_id: int, data: bytes, original_name: str) -> models.GalleryProjectImage | None:
    proj = get_owned_project(db, user, project_id)
    if not proj:
        return None
    meta = save_uploaded_image(project_id, data, original_name)
    # 所有上传的产品图均为用户原图（多视角）；order 用已有图数量，保证按上传顺序升序排列
    existing_count = db.scalar(
        select(func.count(models.GalleryProjectImage.id)).where(models.GalleryProjectImage.project_id == project_id)
    ) or 0
    img = models.GalleryProjectImage(
        project_id=project_id,
        filename=meta["filename"],
        url=meta["url"],
        original=True,
        order=existing_count,
    )
    db.add(img)
    db.commit()
    db.refresh(img)
    return img


def delete_image(db: Session, user: models.User, project_id: int, image_id: int) -> bool:
    proj = get_owned_project(db, user, project_id)
    if not proj:
        return False
    img = db.get(models.GalleryProjectImage, image_id)
    if not img or img.project_id != project_id:
        return False
    db.delete(img)
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────
# 策划项
# ─────────────────────────────────────────────────────────────

def add_plan_item(db: Session, user: models.User, project_id: int, payload: dict) -> models.GalleryPlanItem | None:
    proj = get_owned_project(db, user, project_id)
    if not proj:
        return None
    if not get_plan_type(payload.get("type_id", "")):
        return None
    order = db.scalar(
        select(func.count(models.GalleryPlanItem.id)).where(models.GalleryPlanItem.project_id == project_id)
    ) or 0
    item = models.GalleryPlanItem(
        project_id=project_id,
        type_id=payload["type_id"],
        order=int(order),
        personal_settings=payload.get("personal_settings", {}) or {},
        common_settings=payload.get("common_settings", {}) or {},
        output_settings=payload.get("output_settings", {}) or {},
        note=payload.get("note", "") or "",
        reference_images=payload.get("reference_images", []) or [],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    recompute_estimate(db, proj)
    db.commit()
    return item


def get_plan_item(db: Session, user: models.User, project_id: int, item_id: int) -> models.GalleryPlanItem | None:
    proj = get_owned_project(db, user, project_id)
    if not proj:
        return None
    item = db.get(models.GalleryPlanItem, item_id)
    if not item or item.project_id != project_id:
        return None
    return item


def update_plan_item(db: Session, user: models.User, project_id: int, item_id: int, data: dict) -> models.GalleryPlanItem | None:
    item = get_plan_item(db, user, project_id, item_id)
    if not item:
        return None
    for k, v in data.items():
        if v is not None:
            setattr(item, k, v)
    db.commit()
    db.refresh(item)
    recompute_estimate(db, item.project)
    db.commit()
    return item


def delete_plan_item(db: Session, user: models.User, project_id: int, item_id: int) -> bool:
    item = get_plan_item(db, user, project_id, item_id)
    if not item:
        return False
    proj = item.project
    db.delete(item)
    db.commit()
    recompute_estimate(db, proj)
    db.commit()
    return True


def reorder_plan_items(db: Session, user: models.User, project_id: int, ordered_ids: list[int]) -> bool:
    proj = get_owned_project(db, user, project_id)
    if not proj:
        return False
    for idx, item_id in enumerate(ordered_ids):
        item = db.get(models.GalleryPlanItem, item_id)
        if item and item.project_id == project_id:
            item.order = idx
    db.commit()
    return True


# ─────────────────────────────────────────────────────────────
# 模板
# ─────────────────────────────────────────────────────────────

def save_template(db: Session, user: models.User, name: str, payload: dict, cover_url: str | None = None) -> models.GalleryTemplate:
    tpl = models.GalleryTemplate(user_id=user.id, name=name, payload=payload or {})
    if cover_url:
        tpl.payload["cover_url"] = cover_url
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


def update_template(db: Session, user: models.User, template_id: int, name: str | None = None, cover_url: str | None = None) -> models.GalleryTemplate | None:
    tpl = get_owned_template(db, user, template_id)
    if not tpl:
        return None
    if name is not None:
        tpl.name = name
    if cover_url is not None:
        tpl.payload = dict(tpl.payload or {})
        if cover_url:
            tpl.payload["cover_url"] = cover_url
        else:
            tpl.payload.pop("cover_url", None)
    db.commit()
    db.refresh(tpl)
    return tpl


def list_templates(db: Session, user: models.User) -> list[models.GalleryTemplate]:
    return list(db.scalars(
        select(models.GalleryTemplate).where(models.GalleryTemplate.user_id == user.id)
        .order_by(models.GalleryTemplate.created_at.desc())
    ))


def get_owned_template(db: Session, user: models.User, template_id: int) -> models.GalleryTemplate | None:
    return db.scalar(
        select(models.GalleryTemplate).where(
            models.GalleryTemplate.id == template_id, models.GalleryTemplate.user_id == user.id
        )
    )


def delete_template(db: Session, user: models.User, template_id: int) -> bool:
    tpl = get_owned_template(db, user, template_id)
    if not tpl:
        return False
    db.delete(tpl)
    db.commit()
    return True


def apply_template_to_project(db: Session, user: models.User, project_id: int, template_id: int) -> models.GalleryProject | None:
    """将模板中的策划项批量写入当前项目（追加）。"""
    proj = get_owned_project(db, user, project_id)
    tpl = get_owned_template(db, user, template_id)
    if not proj or not tpl:
        return None
    payload = tpl.payload or {}
    base_order = db.scalar(
        select(func.count(models.GalleryPlanItem.id)).where(models.GalleryPlanItem.project_id == project_id)
    ) or 0
    for i, pi in enumerate(payload.get("plan_items", [])):
        if not get_plan_type(pi.get("type_id", "")):
            continue
        db.add(models.GalleryPlanItem(
            project_id=project_id,
            type_id=pi["type_id"],
            order=base_order + i,
            personal_settings=pi.get("personal_settings", {}) or {},
            common_settings=pi.get("common_settings", {}) or {},
            output_settings=pi.get("output_settings", {}) or {},
            note=pi.get("note", "") or "",
            reference_images=pi.get("reference_images", []) or [],
        ))
    if payload.get("market_config"):
        proj.market_config = payload["market_config"]
    if payload.get("output_config"):
        proj.output_config = payload["output_config"]
    if payload.get("selling_points"):
        proj.selling_points = payload["selling_points"]
    db.commit()
    recompute_estimate(db, proj)
    db.commit()
    db.refresh(proj)
    return proj


# ─────────────────────────────────────────────────────────────
# AI 帮填（规则化建议，可后续替换为真实大模型）
# ─────────────────────────────────────────────────────────────

def ai_fill_suggestion(project: models.GalleryProject, type_id: str, current: dict | None = None) -> dict:
    """基于已填字段给出规则化补全建议。"""
    current = current or {}
    t = get_plan_type(type_id)
    title = t["title"] if t else type_id

    # 通用设置建议
    common = dict(current.get("common_settings", {}) or {})
    if project.selling_points and not common.get("copy_need"):
        common["copy_need"] = "核心卖点文案"
    market = project.market_config or {}
    if market.get("ecommerce_platform") and not common.get("ecommerce_platform"):
        common["ecommerce_platform"] = market["ecommerce_platform"]
    if market.get("target_market") and not common.get("target_market"):
        common["target_market"] = market["target_market"]
    if market.get("copy_language") and not common.get("copy_language"):
        common["copy_language"] = market["copy_language"]
    if market.get("visual_style") and not common.get("visual_style"):
        common["visual_style"] = market["visual_style"]
    if not common.get("tone_tendency"):
        common["tone_tendency"] = "高饱和色调"

    # 个性化设置建议：用「卖点」回填首个字段，其余给占位示例
    personal = dict(current.get("personal_settings", {}) or {})
    from app.gallery_config import get_personal_fields
    fields = get_personal_fields(type_id)
    for f in fields:
        if f["label"] not in personal:
            if project.selling_points and f == fields[0]:
                personal[f["label"]] = project.selling_points[:30]
            else:
                personal[f["label"]] = f["placeholder"]

    # 补充说明建议
    note = current.get("note") or ""
    if not note and project.selling_points:
        note = f"围绕核心卖点「{project.selling_points[:20]}」生成{title}，突出差异化优势。"

    return {"common_settings": common, "personal_settings": personal, "note": note}


# ─────────────────────────────────────────────────────────────
# 生成（可插拔）
# ─────────────────────────────────────────────────────────────

def _build_prompt(project: models.GalleryProject, item: models.GalleryPlanItem, model_name: str | None = None) -> str:
    t = get_plan_type(item.type_id)
    title = t["title"] if t else item.type_id
    parts = [f"为电商商品生成【{title}】。"]
    if project.selling_points:
        parts.append(f"核心卖点：{project.selling_points}。")
    ps = item.personal_settings or {}
    if ps:
        kv = "；".join(f"{k}：{v}" for k, v in ps.items() if v)
        if kv:
            parts.append(f"个性化要求：{kv}。")
    cs = item.common_settings or {}
    if cs.get("target_market"):
        parts.append(f"目标市场：{cs['target_market']}。")
    if cs.get("visual_style"):
        parts.append(f"视觉风格：{cs['visual_style']}。")
    if cs.get("tone_tendency"):
        parts.append(f"色调：{cs['tone_tendency']}。")
    if item.note:
        parts.append(f"补充说明：{item.note}。")
    # 记录所选模型，确保「所有配置都有记录」
    if model_name:
        parts.append(f"使用模型：{model_name}。")
    parts.append("输出高质量电商主图，白底或场景化，符合平台规范。")
    return " ".join(parts)


def list_image_models(db: Session, user: models.User) -> dict:
    """返回当前用户「已启用」的图片生成模型，按提供商分组。

    供前端「模型」下拉框动态渲染 —— 取代原先硬编码的模型名列表，
    确保用户在「AI 提供商」中配置的图片模型才是可选范围。
    """
    rows = db.execute(
        select(models.Provider, models.ProviderModel)
        .join(models.ProviderModel, models.ProviderModel.provider_id == models.Provider.id)
        .where(
            models.Provider.user_id == user.id,
            models.Provider.enabled == True,  # noqa: E712
            models.ProviderModel.model_type == "image",
            models.ProviderModel.enabled == True,  # noqa: E712
        )
        .order_by(models.Provider.is_default.desc(), models.Provider.id, models.ProviderModel.id)
    ).all()

    providers: dict[int, dict] = {}
    default = None
    for prov, mdl in rows:
        entry = providers.setdefault(
            prov.id,
            {
                "provider_id": prov.id,
                "provider_name": prov.name,
                "is_default_provider": bool(prov.is_default),
                "models": [],
            },
        )
        entry["models"].append(
            {"model_id": mdl.id, "model_name": mdl.model_name, "is_default": bool(mdl.is_default_image)}
        )
        # 记录默认图片模型（取第一个 is_default_image）
        if mdl.is_default_image and default is None:
            default = {
                "provider_id": prov.id,
                "provider_name": prov.name,
                "model_name": mdl.model_name,
            }

    return {"providers": list(providers.values()), "default_image_model": default}


def _resolve_image_model(
    db: Session, user: models.User, provider_id: int | None, model_name: str | None
) -> tuple[models.Provider | None, models.ProviderModel | None]:
    """解析出图所用的 (Provider, ProviderModel)。

    优先级：
    1. 显式指定的 provider_id + model_name（用户在前端选择的 AI 提供商图片模型）
    2. 用户的默认图片模型（ProviderModel.is_default_image）
    3. 均未找到 → 返回 (None, None)，由调用方降级到离线 SVG 占位图
    """
    if provider_id and model_name:
        prov = db.get(models.Provider, provider_id)
        if prov and prov.user_id == user.id and prov.enabled:
            mdl = db.scalar(
                select(models.ProviderModel).where(
                    models.ProviderModel.provider_id == provider_id,
                    models.ProviderModel.model_name == model_name,
                    models.ProviderModel.model_type == "image",
                    models.ProviderModel.enabled == True,  # noqa: E712
                )
            )
            if mdl:
                return prov, mdl
    # 降级：用户的默认图片模型
    hit = db.execute(
        select(models.Provider, models.ProviderModel)
        .join(models.ProviderModel, models.ProviderModel.provider_id == models.Provider.id)
        .where(
            models.Provider.user_id == user.id,
            models.Provider.enabled == True,  # noqa: E712
            models.ProviderModel.model_type == "image",
            models.ProviderModel.enabled == True,  # noqa: E712
            models.ProviderModel.is_default_image == True,  # noqa: E712
        )
        .limit(1)
    ).first()
    if hit:
        return hit[0], hit[1]
    return None, None


def _real_generate(
    db: Session,
    user: models.User,
    prompt: str,
    reference_filenames: list[str],
    provider_id: int | None = None,
    model_name: str | None = None,
) -> dict | None:
    """尝试用所选（或默认）AI 提供商的图片模型真实出图。

    返回 {"url", "provider_id", "provider_name", "model_name"} 或 None（降级到离线 SVG）。
    """
    try:
        from app.media import MediaService

        provider, model = _resolve_image_model(db, user, provider_id, model_name)
        if not provider or not model:
            return None
        # 参考图转为可访问 url
        ref_urls = [f"/api/gallery/files/{f}" for f in reference_filenames if f]
        result = MediaService.generate_image(
            provider=provider,
            model_name=model.model_name,
            prompt=prompt,
            size="1024x1024",
            n=1,
            reference_images=ref_urls or None,
            tags=["gallery"],
        )
        images = result.get("data", [])
        url = images[0].get("url") if images else None
        if url:
            return {
                "url": url,
                "provider_id": provider.id,
                "provider_name": provider.name,
                "model_name": model.model_name,
            }
    except Exception as exc:  # 任意异常都降级到离线模拟
        logger.warning("Real image generation failed, fallback to simulation: %s", exc)
    return None


def generate(db: Session, user: models.User, project_id: int):
    """执行生成：为每个策划项按其数量生成结果图，写入 GalleryRecord。"""
    from app.schemas import GalleryGenerateResponse, GalleryRecordRead

    proj = get_owned_project(db, user, project_id)
    if not proj:
        return None
    if not proj.images:
        raise ValueError("请先上传至少一张产品原图")
    if not proj.plan_items:
        raise ValueError("请先在 AI 智能策划台选择要生成的类型")

    proj.status = "generating"
    db.commit()

    oc = proj.output_config or {}
    global_provider_id = oc.get("provider_id")
    global_model = oc.get("model_name")

    records: list[models.GalleryRecord] = []
    total_images = 0
    for item in proj.plan_items:
        t = get_plan_type(item.type_id)
        title = t["title"] if t else item.type_id
        ios = item.output_settings or {}
        count = max(1, int(ios.get("count", 1) or 1))
        # 模型选择优先级：条目级 > 全局级
        item_provider_id = ios.get("provider_id") or global_provider_id
        item_model = ios.get("model_name") or global_model
        prompt = _build_prompt(proj, item, model_name=item_model)
        ref_files = item.reference_images or []
        for i in range(1, count + 1):
            total_images += 1
            real = _real_generate(db, user, prompt, ref_files, item_provider_id, item_model)
            if real:
                result_filename = None
                result_url = real["url"]
                rec_provider_id = real["provider_id"]
                rec_provider_name = real["provider_name"]
                rec_model_name = real["model_name"]
            else:
                result_filename = write_result_svg(item.id, i, title, f"{item.type_id}-{i}")
                result_url = f"/api/gallery/files/{result_filename}"
                # 离线降级时仍记录用户所选配置，保证「所有配置都有记录」
                rec_provider_id = item_provider_id
                rec_provider_name = None
                rec_model_name = item_model
            rec = models.GalleryRecord(
                project_id=project_id,
                plan_item_id=item.id,
                user_id=user.id,
                type_id=item.type_id,
                title=f"{title} #{i}",
                result_filename=result_filename,
                result_url=result_url,
                status="completed",
                prompt=prompt,
                provider_id=rec_provider_id,
                provider_name=rec_provider_name,
                model_name=rec_model_name,
            )
            db.add(rec)
            records.append(rec)

    proj.status = "completed"
    db.commit()
    for r in records:
        db.refresh(r)

    est = estimate_cost([{"type_id": it.type_id, "count": it.output_settings.get("count", 1)} for it in proj.plan_items])
    return GalleryGenerateResponse(
        project_id=project_id,
        status="completed",
        total_images=total_images,
        total_points=est["total_points"],
        total_minutes=est["total_minutes"],
        records=[GalleryRecordRead.model_validate(r) for r in records],
    )


# ─────────────────────────────────────────────────────────────
# 示例套图种子
# ─────────────────────────────────────────────────────────────

def seed_showcases(db: Session) -> int:
    existing = db.scalar(select(func.count(models.GalleryShowcase.id)))
    if existing:
        return 0
    count = 0
    for seed in SHOWCASE_SEED:
        orig = write_showcase_svg(seed, 0)
        imgs = [write_showcase_svg(seed, i) for i in range(1, 4)]
        sc = models.GalleryShowcase(
            category=seed["category"],
            name=seed["name"],
            original_url=f"/api/gallery/files/{orig}",
            image_urls=[f"/api/gallery/files/{u}" for u in imgs],
            total_count=seed.get("count", len(imgs) + 1),
        )
        db.add(sc)
        count += 1
    db.commit()
    return count


def list_showcases(db: Session, category: str | None = None) -> list[models.GalleryShowcase]:
    q = select(models.GalleryShowcase)
    if category and category != "全部":
        q = q.where(models.GalleryShowcase.category == category)
    return list(db.scalars(q.order_by(models.GalleryShowcase.id)))


def list_records(db: Session, user: models.User, project_id: int | None = None) -> list[models.GalleryRecord]:
    q = select(models.GalleryRecord).where(models.GalleryRecord.user_id == user.id)
    if project_id is not None:
        q = q.where(models.GalleryRecord.project_id == project_id)
    return list(db.scalars(q.order_by(models.GalleryRecord.created_at.desc())))
