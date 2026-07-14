"""电商套图模块 · Service 层（业务逻辑，与 HTTP 路由解耦）。

设计要点（低耦合 / 高扩展 / 性能好）：
- 路由仅做参数解析与鉴权，所有业务逻辑在此层。
- 文件统一落盘到 ``uploads/gallery/``，回显经 ``/api/gallery/files/{filename}``。
- 生成服务可插拔：配置了默认 image provider+model 时走真实出图；
  否则离线生成 SVG 占位图，保证端到端流程在无外部依赖时亦可验证。
- 类型/字段/成本等配置全部来自 ``gallery_config``，本层不硬编码业务枚举。
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from app import gallery_prompt

logger = logging.getLogger(__name__)

# uploads/gallery/ 根目录（与 app/services.py 的 UPLOAD_DIR 平级）
from app.http_client import download_bytes_with_fallback
from app.storage import _downscale_image_bytes

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


def _gallery_file_data_url(filename: str) -> str | None:
    """把 gallery 本地文件内联为 base64 ``data:`` URL。

    上游图片模型拉不到本地 ``/api/gallery/files/...`` 地址，参考图/商品图
    必须是 base64。这里读取本地盘文件、按需压缩后返回 ``data:`` URL；
    文件不存在或损坏时返回 ``None``（调用方据此跳过该参考图）。
    """
    p = resolve_file(filename)
    if not p:
        return None
    try:
        raw = p.read_bytes()
    except Exception:
        return None
    if not raw:
        return None
    shrunk = _downscale_image_bytes(raw)
    mime = "image/jpeg" if shrunk is not raw else (mimetypes.guess_type(filename)[0] or "image/png")
    try:
        return f"data:{mime};base64,{base64.b64encode(shrunk).decode()}"
    except Exception:
        return None


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


def save_plan_item_image(project_id: int, data: bytes, original_name: str) -> dict:
    """保存策划项「单独商品图」。

    与 ``save_uploaded_image`` 的区别：不写入 ``GalleryProjectImage`` 行，
    因此不会污染项目产品图列表（项目产品图列表只用于「统一上传」入口）。
    返回 {filename, url}，落盘于 ``projects/{project_id}/items/``。
    """
    _ensure_dirs()
    ext = _safe_ext(original_name)
    fname = f"projects/{project_id}/items/{uuid.uuid4().hex}{ext}"
    path = GALLERY_UPLOAD_ROOT / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"filename": fname, "url": f"/api/gallery/files/{fname}"}


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
    resolved = []
    for it in project.plan_items:
        resolved.append({"type_id": it.type_id, "count": it.output_settings.get("count", 1)})
    est = estimate_cost(resolved)
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
        product_image=payload.get("product_image", "") or "",
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
            product_image=pi.get("product_image", "") or "",
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
# AI 帮写（由 Agnes 多模态大模型，根据产品图 + 类型，帮写更优配置）
# ─────────────────────────────────────────────────────────────

def ai_fill_suggestion(project: models.GalleryProject, type_id: str, current: dict | None = None) -> dict:
    """调用 Agnes 多模态，根据产品图 + 已选类型，帮商家补全/优化配置。

    返回 {common_settings, personal_settings, note}，与旧规则版结构一致，
    便于前端无缝替换。AI 失败时返回空结构（前端保留用户已填内容）。
    """
    from app.gallery_prompt_ai import ai_write_type_config

    return ai_write_type_config(project, type_id, current)


# ─────────────────────────────────────────────────────────────
# 生成（可插拔）
# ─────────────────────────────────────────────────────────────

def _build_prompt(
    project: models.GalleryProject,
    item: models.GalleryPlanItem,
    model_name: str | None = None,
    effective_product_image: str | None = None,
    ratio: str | None = None,
) -> dict:
    """组装图片生成提示词（中英双语）。

    路由规则（对应产品诉求）：
    - 自定义子任务（PLAN_TYPES 中 custom=True）：用户自由填写需求，**不走 AI 改写**，
      直接用原文（personal_settings["自定义需求"] 或 note），prompt_source="custom"。
    - 推荐类型（下拉选择的方向）：优先由 Agnes 2.0 Flash 多模态大模型，根据
      「用户配置 + 卖点 + 参考图」动态生成贴合产品的提示词（prompt_source="ai"）；
      AI 不可达 / 解析失败时自动降级到模板引擎（prompt_source="template"）。

    返回 {prompt: 中文版展示提示词, prompt_en: 英文版生成提示词, prompt_source: str,
          prompt_input: 喂给大模型的输入(溯源), prompt_raw: 大模型原始返回(溯源)}。
    """
    from app.gallery_config import get_plan_type

    t = get_plan_type(item.type_id) if item.type_id else None
    # 自定义子任务：用户原文直出，不调 AI、不改写、不翻译
    if t and t.get("custom"):
        return _build_custom_prompt(item)

    from app.gallery_prompt_ai import generate_prompt_via_ai

    return generate_prompt_via_ai(
        project, item, model_name=model_name,
        effective_product_image=effective_product_image, ratio=ratio,
    )


def _build_custom_prompt(item: models.GalleryPlanItem) -> dict:
    """自定义子任务：直接用用户填写的原始需求文本。

    不调用 AI、不翻译、不改写 —— 用户写什么就用什么（prompt_en 同样用原文，
    因为「不走 AI 改写」是用户的明确意图）。
    """
    ps = dict(item.personal_settings or {})
    custom_text = (ps.get("自定义需求") or "").strip() or (getattr(item, "note", "") or "").strip()
    if not custom_text:
        custom_text = "按用户需求自由生成商品图"
    return {
        "prompt": custom_text,
        "prompt_en": custom_text,  # 用户原文直出，不走 AI 翻译/改写
        "prompt_source": "custom",
        "prompt_input": f"【自定义子任务】用户原始需求（不走 AI 改写）：\n{custom_text}",
        "prompt_raw": "",
    }


# ─────────────────────────────────────────────────────────────
# 批量提示词生成策略（按环境变量 AI_PROMPT_BATCH_MODE 切换）
# ─────────────────────────────────────────────────────────────

def _build_prompts_for_plan(
    project: models.GalleryProject,
    items_meta: list[dict],
    model_name: str | None = None,
) -> dict[int, dict]:
    """按批量策略为整个规划生成所有提示词。

    策略由环境变量 AI_PROMPT_BATCH_MODE 控制：
      - 1（默认）：方案 A，单次 AI 批量调用，把所有非自定义项一次性生成。
      - 2：方案 B，非自定义项并发并行调用（每 item 独立 AI 调用）。
    自定义子任务始终不走 AI 改写，直接透传原文。
    任一策略失败/缺失的项都会兜底到单条 _build_prompt。
    """
    from app.gallery_prompt_ai import _get_batch_mode, generate_prompts_batch_mode_1

    mode = _get_batch_mode()
    results: dict[int, dict] = {}

    non_custom = [m for m in items_meta if not m["is_custom"]]
    for m in items_meta:
        if m["is_custom"]:
            results[m["item"].id] = _build_custom_prompt(m["item"])

    if mode == 1:
        if non_custom:
            batch_results = generate_prompts_batch_mode_1(project, non_custom, model_name=model_name)
            results.update(batch_results)
    elif mode == 2:
        if non_custom:
            parallel_results = _build_prompts_parallel(project, non_custom)
            results.update(parallel_results)
    else:
        # 兜底：串行单条
        for m in non_custom:
            if m["item"].id not in results:
                results[m["item"].id] = _build_prompt(
                    project, m["item"], model_name=m["item_model"],
                    effective_product_image=m["effective_product_image"], ratio=m["ratio"],
                )

    # 兜底：任何缺失的项再走单条 _build_prompt（并发执行，避免串行调用被限流拖慢）
    missing = [
        m for m in items_meta
        if m["item"].id not in results or not results[m["item"].id].get("prompt_en")
    ]
    if missing:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {
                ex.submit(
                    _build_prompt, project, m["item"],
                    model_name=m["item_model"],
                    effective_product_image=m["effective_product_image"], ratio=m["ratio"],
                ): m
                for m in missing
            }
            for f in as_completed(futs):
                m = futs[f]
                try:
                    results[m["item"].id] = f.result()
                except Exception as exc:
                    logger.exception("兜底生成提示词失败 item_id=%s: %s", m["item"].id, exc)
    return results


def _build_prompts_parallel(project: models.GalleryProject, items_meta: list[dict]) -> dict[int, dict]:
    """方案 B：并发并行地为每个非自定义策划项生成提示词。

    使用线程池并行执行 _build_prompt，单个失败不影响其他。
    """
    results: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {}
        for m in items_meta:
            fut = ex.submit(
                _build_prompt,
                project,
                m["item"],
                model_name=m["item_model"],
                effective_product_image=m["effective_product_image"],
                ratio=m["ratio"],
            )
            futures[fut] = m

        for fut in as_completed(futures):
            m = futures[fut]
            try:
                results[m["item"].id] = fut.result()
            except Exception as exc:
                logger.exception("并行生成提示词失败 item_id=%s: %s", m["item"].id, exc)
                # 失败项串行兜底
                results[m["item"].id] = _build_prompt(
                    project,
                    m["item"],
                    model_name=m["item_model"],
                    effective_product_image=m["effective_product_image"],
                    ratio=m["ratio"],
                )
    return results


def list_image_models(db: Session, user: models.User) -> dict:
    """返回当前用户「已启用」的图片生成模型，按提供商分组。

    仅返回当前用户自己配置的图片模型——不跨用户共享。若用户未配置任何
    图片模型，返回空列表，由前端提示去「AI 提供商」中添加，绝不拿其它
    用户的模型来兜底。
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

    只解析当前用户「自己」的模型，绝不跨用户使用他人模型：
    1. 显式指定的 provider_id + model_name（必须属于当前用户）
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


def _save_generated_image(url: str) -> str | None:
    """把 AI 提供商返回的临时图片下载到本地 ``uploads/gallery/results/``。

    返回本地相对文件名（如 ``results/xxx.png``），失败返回 ``None``。
    本地持久化后，下载/预览都走同源 ``/api/gallery/files/``，避免跨域。
    """
    try:
        data, content_type = download_bytes_with_fallback(url, timeout=60)
        if not data:
            return None
    except Exception:
        return None

    ext = ".png"
    ct = (content_type or '').lower()
    low = url.lower()
    if ct.endswith('jpeg') or ct.endswith('jpg') or '.jpg' in low or '.jpeg' in low:
        ext = ".jpg"
    elif ct.endswith('webp') or '.webp' in low:
        ext = ".webp"
    elif ct.endswith('png') or '.png' in low:
        ext = ".png"
    fname = f"results/{uuid.uuid4().hex}{ext}"
    _ensure_dirs()
    path = GALLERY_UPLOAD_ROOT / fname
    try:
        path.write_bytes(data)
    except Exception:
        return None
    return fname


# ── 比例 / 尺寸推断 ──

# 前端可选比例 → 图片生成模型尺寸（短边 1024，长边按 64 整数倍）
_RATIO_SIZE_MAP: dict[str, str] = {
    "方图 1:1": "1024x1024",
    "竖图 3:4": "768x1024",
    "竖图 4:5": "832x1024",
    "竖图 9:16": "576x1024",
    "竖图 2:3": "704x1024",
    "横图 16:9": "1024x576",
    "横图 4:3": "1024x768",
}

# 比例名字 → 浮点比例值，用于自适应时匹配参考图最接近的比例
_RATIO_VALUE_MAP: dict[str, float] = {
    "方图 1:1": 1.0,
    "竖图 3:4": 3 / 4,
    "竖图 4:5": 4 / 5,
    "竖图 9:16": 9 / 16,
    "竖图 2:3": 2 / 3,
    "横图 16:9": 16 / 9,
    "横图 4:3": 4 / 3,
}




def _image_size_from_bytes(data: bytes) -> tuple[int, int] | None:
    """不依赖 Pillow，从常见图片文件头解析宽高。

    作为 ``_infer_size_from_reference`` 的兜底：Docker 环境有 Pillow，
    但精简/测试环境缺失 PIL 时也能根据参考图真实比例推断生成尺寸，
    避免「自适应尺寸」回退成模型默认 1:1 方图而拉伸原图。
    """
    if not data:
        return None
    # PNG: IHDR chunk (w,h are big-endian 4-byte each at offset 16)
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        try:
            w = int.from_bytes(data[16:20], "big")
            h = int.from_bytes(data[20:24], "big")
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass
    # JPEG: SOF0/SOF2/SOF1 markers (0xFFC0/0xFFC2/0xFFC1)
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            marker = data[i]
            if marker != 0xFF:
                i += 1
                continue
            code = data[i + 1]
            if code in (0xC0, 0xC1, 0xC2):
                try:
                    h = int.from_bytes(data[i + 5:i + 7], "big")
                    w = int.from_bytes(data[i + 7:i + 9], "big")
                    if w > 0 and h > 0:
                        return w, h
                except Exception:
                    pass
                break
            if code in (0xD9,):
                break
            seg_len = int.from_bytes(data[i + 2:i + 4], "big")
            i += 2 + seg_len
    # GIF87a / GIF89a
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        if len(data) >= 10:
            try:
                w = int.from_bytes(data[6:8], "little")
                h = int.from_bytes(data[8:10], "little")
                if w > 0 and h > 0:
                    return w, h
            except Exception:
                pass
    # WebP: RIFF....WEBP then VP8/VP8L/VP8X
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8 " and len(data) >= 30:
            try:
                w = int.from_bytes(data[26:28], "little")
                h = int.from_bytes(data[28:30], "little")
                if w > 0 and h > 0:
                    return w, h
            except Exception:
                pass
        elif chunk == b"VP8L" and len(data) >= 25:
            try:
                bits = int.from_bytes(data[21:25], "little")
                w = (bits & 0x3FFF) + 1
                h = ((bits >> 14) & 0x3FFF) + 1
                if w > 0 and h > 0:
                    return w, h
            except Exception:
                pass
        elif chunk == b"VP8X" and len(data) >= 30:
            try:
                w = int.from_bytes(data[24:27], "little") + 1
                h = int.from_bytes(data[27:30], "little") + 1
                if w > 0 and h > 0:
                    return w, h
            except Exception:
                pass
    return None

def _infer_size_from_reference(reference_filename: str | None) -> str | None:
    """根据参考图实际宽高比，推断最接近的生成尺寸。

    用于「自适应尺寸」模式：用户不指定比例时，让生成图比例跟随参考图，
    避免模型默认 1024×1024 方图把竖版连衣裙压成扁胖方图。
    读取失败或无参考图时返回 ``None``，回退到不指定 size（模型默认）。
    """
    if not reference_filename:
        return None
    p = resolve_file(reference_filename)
    if not p:
        return None
    try:
        from PIL import Image

        with Image.open(p) as img:
            w, h = img.size
    except Exception:
        # Pillow 缺失时读取文件头，仍要守住「自适应尺寸」的比例
        try:
            w, h = _image_size_from_bytes(p.read_bytes())
        except Exception:
            return None
    if w <= 0 or h <= 0:
        return None
    image_ratio = w / h

    # 找到 _RATIO_SIZE_MAP 中比例最接近的一项
    best_label, best_diff = None, float("inf")
    for label, ref_ratio in _RATIO_VALUE_MAP.items():
        diff = abs(ref_ratio - image_ratio)
        if diff < best_diff:
            best_diff = diff
            best_label = label
    if best_label:
        return _RATIO_SIZE_MAP[best_label]
    return None


def _ratio_to_size(ratio: str | None, reference_filename: str | None = None) -> str | None:
    """把前端选择的图片比例映射到图片生成模型可接受的尺寸字符串。

    - 显式比例（方图 / 竖图 / 横图）→ 对应尺寸（短边 1024，长边按比例取 64 整数倍，
      兼顾 SD 系列与 Agnes 等 OpenAI-compatible 图片模型的常见输入要求）。
    - 「自适应尺寸」（以及 None / ""）→ 优先根据参考图实际比例推断最接近尺寸；
      无参考图或读取失败时返回 ``None``，交由模型使用其自身默认尺寸。
      这样「自适应」才有实际意义：跟随原图比例，而不是任由模型默认出 1024×1024 方图。
    """
    if ratio and ratio != "自适应尺寸":
        return _RATIO_SIZE_MAP.get(ratio, "1024x1024")
    # 自适应：按参考图比例推断，避免模型默认方图导致扁胖
    if reference_filename:
        inferred = _infer_size_from_reference(reference_filename)
        if inferred:
            return inferred
    return None


def _real_generate(
    db: Session,
    user: models.User,
    prompt: str,
    reference_filenames: list[str],
    provider_id: int | None = None,
    model_name: str | None = None,
    size: str = "1024x1024",
) -> dict:
    """尝试用所选（或默认）AI 提供商的图片模型真实出图。

    返回结构：
    - 成功：{"url"（本地）, "filename", "provider_id", "provider_name", "model_name"}
    - 失败：{"error": "可读原因"}（不再静默返回 None，便于前端展示真实失败原因）

    自动兜底：prompt 超长自动截断；带参考图失败时自动去掉参考图重试一次。
    """
    try:
        from app.media import MediaService

        provider, model = _resolve_image_model(db, user, provider_id, model_name)
        if not provider or not model:
            reason = "未配置可用的图片模型（请在「AI 提供商」中添加并启用一个图片模型，并设为默认图片模型）"
            logger.warning("Real image generation skipped: %s", reason)
            return {"error": reason}
        # 参考图/商品图必须内联为 base64 data URL（上游拉不到本地地址）
        ref_urls: list[str] = []
        for f in reference_filenames:
            if not f:
                continue
            du = _gallery_file_data_url(f)
            if du:
                ref_urls.append(du)
        # prompt 超长截断，避免部分图片模型拒绝或截断输出
        prompt_to_send = (prompt or "").strip()
        if len(prompt_to_send) > 1500:
            prompt_to_send = prompt_to_send[:1500].rstrip() + " ..."
            logger.info("Image prompt truncated to 1500 chars for model %s", model.model_name)

        def _call(refs):
            return MediaService.generate_image(
                provider=provider,
                model_name=model.model_name,
                prompt=prompt_to_send,
                size=size,
                n=1,
                reference_images=refs or None,
                tags=["gallery"],
            )

        # 第一次：带参考图
        result = _call(ref_urls)
        images = result.get("data", [])
        url = images[0].get("url") if images else None
        if not url and ref_urls:
            # 带参考图失败 → 去掉参考图重试一次（参考图格式/大小/不被支持是常见原因）
            logger.warning(
                "Image gen with refs failed (%s); retry without refs",
                result.get("error"),
            )
            result = _call(None)
            images = result.get("data", [])
            url = images[0].get("url") if images else None

        if url:
            filename = _save_generated_image(url)
            if filename:
                return {
                    "url": f"/api/gallery/files/{filename}",
                    "filename": filename,
                    "provider_id": provider.id,
                    "provider_name": provider.name,
                    "model_name": model.model_name,
                }
            # 下载失败但仍保留远程 URL，避免整单失败
            return {
                "url": url,
                "filename": None,
                "provider_id": provider.id,
                "provider_name": provider.name,
                "model_name": model.model_name,
            }
        reason = result.get("error") or "图片模型未返回图片（可能 prompt 过长、参考图不被支持，或被限流）"
        logger.warning("Real image generation failed: %s", reason)
        return {"error": reason}
    except Exception as exc:  # 任意异常都记录原因，不再静默
        reason = f"出图调用异常：{exc}"
        logger.warning("Real image generation failed: %s", reason)
        return {"error": reason}


def generate(db: Session, user: models.User, project_id: int) -> models.GalleryTask:
    """提交一次「立即生成」任务。

    校验前置条件（产品图 / 出图类型）后创建 GalleryTask 并交给后台 worker
    异步执行，立即返回任务对象，前端据此轮询进度。
    """
    from app.gallery_worker import enqueue_task

    proj = get_owned_project(db, user, project_id)
    if not proj:
        raise ValueError("项目不存在")
    if not proj.images:
        raise ValueError("请先上传至少一张产品原图")
    if not proj.plan_items:
        raise ValueError("请先在 AI 智能策划台选择要生成的类型")

    # 计算计划生成的总图数（与 run_gallery_task / recompute_estimate 一致）
    total = 0
    for item in proj.plan_items:
        ios = item.output_settings or {}
        total += max(1, int(ios.get("count", 1) or 1))

    task = models.GalleryTask(
        user_id=user.id,
        project_id=project_id,
        name=None,  # 先留空，flush 取回 id 后再生成默认名
        status="pending",
        total=total,
        done=0,
        failed=0,
    )
    db.add(task)
    db.flush()  # 取回自增主键 id，用于生成默认任务名
    # 默认任务名：项目有自定义名称则沿用，否则用「任务 {id}」序号
    proj_name = (proj.name or "").strip()
    task.name = proj_name if (proj_name and proj_name != "未命名套图") else f"任务 {task.id}"
    db.commit()
    db.refresh(task)

    enqueue_task(task.id)
    return task


def rename_task(db: Session, user: models.User, task_id: int, name: str) -> models.GalleryTask | None:
    """重命名一次创作任务。仅允许修改用户自己的任务。"""
    task = db.get(models.GalleryTask, task_id)
    if not task or task.user_id != user.id:
        return None
    task.name = name.strip() or None
    db.commit()
    db.refresh(task)
    return task


def rename_record(db: Session, user: models.User, record_id: int, title: str) -> models.GalleryRecord | None:
    """重命名单张创作记录（图片）的标题。仅允许修改用户自己的记录。"""
    rec = db.get(models.GalleryRecord, record_id)
    if not rec or rec.user_id != user.id:
        return None
    rec.title = title.strip()
    db.commit()
    db.refresh(rec)
    return rec


def run_gallery_task(task_id: int) -> None:
    """后台 worker 执行的任务体：逐步生成图片并写入 GalleryRecord。

    每张图生成后立刻提交并回写 task.done，因此前端轮询可看到实时进度与
    陆续出现的图片。单张失败不影响整体（计入 failed 并继续）。
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        task = db.get(models.GalleryTask, task_id)
        if not task:
            return
        task.status = "running"
        db.commit()

        proj = db.get(models.GalleryProject, task.project_id)
        user = db.get(models.User, task.user_id)
        if not proj or not user:
            task.status = "failed"
            task.error = "项目或用户不存在"
            db.commit()
            return
        if not proj.images:
            task.status = "failed"
            task.error = "请先上传至少一张产品原图"
            db.commit()
            return
        if not proj.plan_items:
            task.status = "failed"
            task.error = "请先在 AI 智能策划台选择要生成的类型"
            db.commit()
            return

        oc = proj.output_config or {}
        global_provider_id = oc.get("provider_id")
        global_model = oc.get("model_name")

        # 阶段0：收集所有策划项的运行时元数据
        items_meta: list[dict] = []
        for item in proj.plan_items:
            t = get_plan_type(item.type_id)
            title = t["title"] if t else item.type_id
            ios = item.output_settings or {}
            ratio = ios.get("ratio") or "自适应尺寸"
            item_provider_id = ios.get("provider_id") or global_provider_id
            item_model = ios.get("model_name") or global_model
            effective_product_image = item.product_image or (
                proj.images[0].filename if proj.images else None
            )
            size = _ratio_to_size(ratio, reference_filename=effective_product_image)
            ref_files: list[str] = []
            if effective_product_image:
                ref_files.append(effective_product_image)
            ref_files.extend(
                f for f in (item.reference_images or []) if f and f != effective_product_image
            )
            count = max(1, int(ios.get("count", 1) or 1))
            is_custom = bool(t and t.get("custom"))
            items_meta.append({
                "item": item,
                "title": title,
                "ratio": ratio,
                "item_provider_id": item_provider_id,
                "item_model": item_model,
                "effective_product_image": effective_product_image,
                "size": size,
                "ref_files": ref_files,
                "count": count,
                "is_custom": is_custom,
            })

        # 阶段1：按策略批量生成所有提示词（默认方案1：单次批量调用）
        prompts_by_item = _build_prompts_for_plan(proj, items_meta, model_name=global_model)

        # 阶段1.5：预建全部 record（pending），前端轮询即可看到每张图的状态与提示词
        plan: list[dict] = []
        for m in items_meta:
            item = m["item"]
            title = m["title"]
            pd = prompts_by_item.get(item.id)
            if not pd:
                # 极端兜底：任意项没有提示词时回退单条
                pd = _build_prompt(
                    proj, item, model_name=m["item_model"],
                    effective_product_image=m["effective_product_image"], ratio=m["ratio"],
                )
            entries_spec = [{
                "prompt_cn": pd["prompt"],
                "prompt_en": pd["prompt_en"],
                "prompt_source": pd.get("prompt_source", "template"),
                "prompt_input": pd.get("prompt_input", ""),
                "prompt_raw": pd.get("prompt_raw", ""),
            }] * m["count"]

            for idx, spec in enumerate(entries_spec, start=1):
                rec_title = f"{title} #{idx}"
                rec = models.GalleryRecord(
                    project_id=proj.id,
                    plan_item_id=item.id,
                    user_id=user.id,
                    type_id=item.type_id,
                    title=rec_title,
                    status="pending",
                    prompt=spec["prompt_cn"],
                    prompt_en=spec["prompt_en"],
                    prompt_source=spec["prompt_source"],
                    prompt_input=spec.get("prompt_input", ""),
                    prompt_raw=spec.get("prompt_raw", ""),
                    provider_id=m["item_provider_id"],
                    provider_name=None,
                    model_name=m["item_model"],
                    task_id=task.id,
                    plan_item_snapshot={
                        "type_id": item.type_id,
                        "personal_settings": item.personal_settings or {},
                        "common_settings": item.common_settings or {},
                        "output_settings": item.output_settings or {},
                        "note": item.note or "",
                        "reference_images": item.reference_images or [],
                        "product_image": item.product_image or "",
                    },
                )
                db.add(rec)
                db.commit()
                db.refresh(rec)
                plan.append({
                    "rec": rec,
                    "prompt_cn": spec["prompt_cn"],
                    "prompt_en": spec["prompt_en"],
                    "ref_files": m["ref_files"],
                    "size": m["size"],
                    "item_provider_id": m["item_provider_id"],
                    "item_model": m["item_model"],
                    "title": title,
                    "i": idx,
                    "item": item,
                })

        # 阶段2：并发逐张出图（processing → completed / failed），前端实时看到「生成中」
        # 每张图独立调用图片模型，用线程池并发执行，缩短墙钟时间（不再逐张串行等待）。
        for entry in plan:
            entry["rec"].status = "processing"
        db.commit()

        # 预取本线程所需的可序列化字段，避免在线程内访问主会话对象
        jobs = []
        for entry in plan:
            item = entry["item"]
            ps = item.personal_settings or {}
            jobs.append({
                "rec_id": entry["rec"].id,
                "prompt_en": entry["prompt_en"],
                "ref_files": entry["ref_files"],
                "item_provider_id": entry["item_provider_id"],
                "item_model": entry["item_model"],
                "size": entry["size"],
                "type_id": item.type_id,
                "item_id": item.id,
                "i": entry["i"],
                "title": entry["title"],
                "spec_text": ps.get("规格参数原文", "") or "",
                "category": ps.get("产品品类", "") or "",
            })

        def _generate_one(job: dict) -> tuple:
            from app.core.database import SessionLocal
            s = SessionLocal()
            try:
                rec = s.get(models.GalleryRecord, job["rec_id"])
                if not rec:
                    return job["rec_id"], "failed", "记录不存在"
                u = s.get(models.User, user.id)
                real = _real_generate(
                    s, u, job["prompt_en"], job["ref_files"],
                    job["item_provider_id"], job["item_model"],
                    size=job["size"],
                )
                if real and real.get("url"):
                    rec.result_filename = real.get("filename")
                    rec.result_url = real["url"]
                    rec.provider_id = real["provider_id"]
                    rec.provider_name = real["provider_name"]
                    rec.model_name = real["model_name"]
                    # 规格参数图：生成后叠加尺码表/标注（纯视觉图 + 后端文字叠加，消除乱码）
                    if job["type_id"] == "spec" and real.get("filename"):
                        from app.spec_overlay import overlay_spec
                        local = resolve_file(real["filename"])
                        if local:
                            # 注意：note 只进 AI 提示词指导构图，绝不画在图上
                            over_name = overlay_spec(
                                str(local),
                                spec_text=job["spec_text"],
                                note="",
                                title=job["title"],
                                category=job["category"],
                            )
                            if over_name:
                                rec.result_filename = over_name
                                rec.result_url = f"/api/gallery/files/{over_name}"
                    rec.status = "completed"
                    s.commit()
                    return job["rec_id"], "completed", None
                # 真实出图失败：记录可读原因，标记为失败（不再静默给占位图）
                reason = (real or {}).get("error") or "出图失败（未返回图片）"
                rec.status = "failed"
                rec.result_url = None
                rec.error = reason[:500]
                s.commit()
                return job["rec_id"], "failed", reason
            except Exception as exc:
                logger.exception("gallery task %s 单图生成失败 rec=%s: %s", task_id, job["rec_id"], exc)
                try:
                    rec = s.get(models.GalleryRecord, job["rec_id"])
                    if rec:
                        rec.status = "failed"
                        rec.result_url = None
                        rec.error = str(exc)[:500]
                        s.commit()
                except Exception:
                    pass
                return job["rec_id"], "failed", str(exc)
            finally:
                s.close()

        done = 0
        failed = 0
        max_workers = min(4, max(1, len(jobs)))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = [ex.submit(_generate_one, j) for j in jobs]
            for f in as_completed(futs):
                _rid, _st, _err = f.result()
                if _st == "completed":
                    done += 1
                else:
                    failed += 1
        task.done = done
        task.failed = failed
        db.commit()

        if failed == 0:
            task.status = "completed"
        elif done > 0:
            task.status = "partial"
        else:
            task.status = "failed"
        db.commit()
    finally:
        db.close()


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


def publish_showcase(db: Session, user: models.User, *, name: str, category: str, record_ids: list[int]) -> models.GalleryShowcase:
    """把创作结果里优秀的成图发布到「创作案例」对外展示。

    - 仅允许发布当前用户自己的 GalleryRecord；
    - 跳过 SVG 占位图（生成失败/示例），只收真实成图；
    - 原图优先取项目首张产品图，缺则回退到第一张成图。
    """
    if not record_ids:
        raise ValueError("请至少选择一张要发布的作品")
    recs = list(db.scalars(
        select(models.GalleryRecord).where(
            models.GalleryRecord.id.in_(record_ids),
            models.GalleryRecord.user_id == user.id,
        )
    ))
    by_id = {r.id: r for r in recs}
    recs = [by_id[i] for i in record_ids if i in by_id]
    if not recs:
        raise ValueError("没有可发布的作品（仅能发布你自己的创作结果）")

    proj = db.get(models.GalleryProject, recs[0].project_id)
    original_url = ""
    if proj and proj.images:
        original_url = f"/api/gallery/files/{proj.images[0].filename}"

    image_urls: list[str] = []
    for r in recs:
        if r.result_url and not str(r.result_url).endswith(".svg"):
            image_urls.append(r.result_url)
    if not image_urls:
        raise ValueError("所选作品中没有有效的成图，无法发布")

    if not original_url:
        original_url = image_urls[0]

    # 携带源任务参数，供日后「生成同款」一键回填：
    # - 每个 record 的 plan_item_snapshot（类型级 personal/common/output/note/参考图）
    # - 项目级 market_config / output_config / selling_points
    plan_item_snapshots: list[dict] = []
    for r in recs:
        if r.plan_item_snapshot and isinstance(r.plan_item_snapshot, dict):
            plan_item_snapshots.append(r.plan_item_snapshot)

    payload: dict = {
        "plan_items": plan_item_snapshots,
        "market_config": (proj.market_config or {}) if proj else {},
        "output_config": (proj.output_config or {}) if proj else {},
        "selling_points": (proj.selling_points or "") if proj else "",
    }

    sc = models.GalleryShowcase(
        category=category or "其他",
        name=name.strip() or "我的电商套图",
        original_url=original_url,
        image_urls=image_urls,
        total_count=len(image_urls) + 1,
        payload=payload,
    )
    db.add(sc)
    db.commit()
    db.refresh(sc)
    return sc


def list_records(db: Session, user: models.User, project_id: int | None = None) -> list[models.GalleryRecord]:
    q = select(models.GalleryRecord).where(models.GalleryRecord.user_id == user.id)
    if project_id is not None:
        q = q.where(models.GalleryRecord.project_id == project_id)
    return list(db.scalars(q.order_by(models.GalleryRecord.created_at.desc())))
