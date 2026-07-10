"""电商套图模块 · HTTP 路由层。

仅做：参数解析、鉴权、调用 Service。业务逻辑全部在 ``gallery_service``。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user
from app import models
from app.gallery_config import serialize_options, serialize_types
from app.gallery_service import (
    add_image,
    add_plan_item,
    ai_fill_suggestion,
    apply_template_to_project,
    create_project,
    delete_image,
    delete_plan_item,
    delete_project,
    delete_template,
    generate,
    get_or_create_draft,
    get_owned_project,
    list_image_models,
    list_projects,
    list_records,
    list_showcases,
    list_templates,
    recompute_estimate,
    reorder_plan_items,
    resolve_file,
    save_template,
    seed_showcases,
    update_plan_item,
    update_project,
    update_template,
)
from app.schemas import (
    GalleryEstimateResponse,
    GalleryGenerateResponse,
    GalleryPlanItemCreate,
    GalleryPlanItemRead,
    GalleryPlanItemUpdate,
    GalleryPlanReorder,
    GalleryProjectCreate,
    GalleryProjectRead,
    GalleryProjectUpdate,
    GalleryTemplateCreate,
    GalleryTemplateRead,
    GalleryTemplateUpdate,
    GalleryTypesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


# ─────────────────────────────────────────────────────────────
# 配置 / 示例
# ─────────────────────────────────────────────────────────────

@router.get("/types", response_model=GalleryTypesResponse)
def get_types(current_user: models.User = Depends(get_current_user)) -> GalleryTypesResponse:
    return GalleryTypesResponse(types=serialize_types(), options=serialize_options())


@router.get("/image-models")
def get_image_models(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    """返回当前用户可用的图片生成模型（来自 AI 提供商配置）。"""
    return list_image_models(db, current_user)


@router.get("/showcases", response_model=list[dict])
def get_showcases(
    category: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list:
    seed_showcases(db)
    items = list_showcases(db, category)
    return [
        {
            "id": s.id,
            "category": s.category,
            "name": s.name,
            "original_url": s.original_url,
            "image_urls": s.image_urls,
            "total_count": s.total_count,
        }
        for s in items
    ]


# ─────────────────────────────────────────────────────────────
# 项目
# ─────────────────────────────────────────────────────────────

@router.get("/projects", response_model=list[GalleryProjectRead])
def list_my_projects(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[models.GalleryProject]:
    return list_projects(db, current_user, status_filter)


@router.get("/projects/draft", response_model=GalleryProjectRead)
def get_draft(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryProject:
    return get_or_create_draft(db, current_user)


@router.post("/projects", response_model=GalleryProjectRead, status_code=status.HTTP_201_CREATED)
def create_new_project(
    payload: GalleryProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryProject:
    return create_project(db, current_user, payload.name)


@router.get("/projects/{project_id}", response_model=GalleryProjectRead)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryProject:
    proj = get_owned_project(db, current_user, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return proj


@router.patch("/projects/{project_id}", response_model=GalleryProjectRead)
def patch_project(
    project_id: int,
    payload: GalleryProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryProject:
    data = payload.model_dump(exclude_unset=True)
    proj = update_project(db, current_user, project_id, data)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return proj


@router.delete("/projects/{project_id}", status_code=204)
def remove_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> None:
    if not delete_project(db, current_user, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")


# ─────────────────────────────────────────────────────────────
# 产品图
# ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/images", response_model=list[GalleryProjectRead])
def upload_images(
    project_id: int,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[models.GalleryProject]:
    proj = get_owned_project(db, current_user, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    for f in files:
        data = f.file.read()
        if not data:
            continue
        img = add_image(db, current_user, project_id, data, f.filename or "image.png")
        if not img:
            raise HTTPException(status_code=404, detail="项目不存在")
    proj = get_owned_project(db, current_user, project_id)
    return [proj]


@router.delete("/projects/{project_id}/images/{image_id}", status_code=204)
def remove_image(
    project_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> None:
    if not delete_image(db, current_user, project_id, image_id):
        raise HTTPException(status_code=404, detail="图片不存在")


# ─────────────────────────────────────────────────────────────
# 策划项
# ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/plan-items", response_model=GalleryPlanItemRead, status_code=status.HTTP_201_CREATED)
def create_plan_item(
    project_id: int,
    payload: GalleryPlanItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = add_plan_item(db, current_user, project_id, payload.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="项目不存在或类型无效")
    return item


@router.patch("/projects/{project_id}/plan-items/{item_id}", response_model=GalleryPlanItemRead)
def patch_plan_item(
    project_id: int,
    item_id: int,
    payload: GalleryPlanItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = update_plan_item(db, current_user, project_id, item_id, payload.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="策划项不存在")
    return item


@router.delete("/projects/{project_id}/plan-items/{item_id}", status_code=204)
def remove_plan_item(
    project_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> None:
    if not delete_plan_item(db, current_user, project_id, item_id):
        raise HTTPException(status_code=404, detail="策划项不存在")


@router.post("/projects/{project_id}/plan-items/reorder", response_model=GalleryProjectRead)
def reorder_items(
    project_id: int,
    payload: GalleryPlanReorder,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryProject:
    if not reorder_plan_items(db, current_user, project_id, payload.ordered_ids):
        raise HTTPException(status_code=404, detail="项目不存在")
    proj = get_owned_project(db, current_user, project_id)
    return proj


# ─────────────────────────────────────────────────────────────
# AI 帮填（规则化建议）
# ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/ai-fill")
def ai_fill(
    project_id: int,
    body: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    proj = get_owned_project(db, current_user, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    type_id = body.get("type_id", "")
    current = body.get("current", {})
    return ai_fill_suggestion(proj, type_id, current)


# ─────────────────────────────────────────────────────────────
# 生成
# ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/generate", response_model=GalleryGenerateResponse)
def run_generate(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GalleryGenerateResponse:
    try:
        result = generate(db, current_user, project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="项目不存在")
    return result


@router.get("/projects/{project_id}/records", response_model=list)
def project_records(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list:
    proj = get_owned_project(db, current_user, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    recs = list_records(db, current_user, project_id)
    return [_rec_to_dict(r) for r in recs]


@router.get("/records", response_model=list)
def my_records(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list:
    recs = list_records(db, current_user)
    return [_rec_to_dict(r) for r in recs]


def _rec_to_dict(r: models.GalleryRecord) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "plan_item_id": r.plan_item_id,
        "type_id": r.type_id,
        "title": r.title,
        "result_filename": r.result_filename,
        "result_url": r.result_url,
        "status": r.status,
        "prompt": r.prompt,
        "provider_id": r.provider_id,
        "provider_name": r.provider_name,
        "model_name": r.model_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# ─────────────────────────────────────────────────────────────
# 模板
# ─────────────────────────────────────────────────────────────

@router.post("/templates", response_model=GalleryTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(
    payload: GalleryTemplateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryTemplate:
    return save_template(db, current_user, payload.name, payload.payload, payload.cover_url)


@router.get("/templates", response_model=list[GalleryTemplateRead])
def get_templates(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[models.GalleryTemplate]:
    return list_templates(db, current_user)


@router.patch("/templates/{template_id}", response_model=GalleryTemplateRead)
def patch_template(
    template_id: int,
    payload: GalleryTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryTemplate:
    data = payload.model_dump(exclude_unset=True)
    tpl = update_template(db, current_user, template_id, data.get("name"), data.get("cover_url"))
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    return tpl


@router.delete("/templates/{template_id}", status_code=204)
def remove_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> None:
    if not delete_template(db, current_user, template_id):
        raise HTTPException(status_code=404, detail="模板不存在")


@router.post("/templates/{template_id}/apply", response_model=GalleryProjectRead)
def apply_template(
    template_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryProject:
    proj = apply_template_to_project(db, current_user, project_id, template_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目或模板不存在")
    return proj


# ─────────────────────────────────────────────────────────────
# 文件回显（图片经此端点返回；路径穿越防护在 service.resolve_file）
# ─────────────────────────────────────────────────────────────

@router.get("/files/{filename:path}")
def serve_file(filename: str):
    path = resolve_file(filename)
    if not path:
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path)
