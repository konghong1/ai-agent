"""电商套图模块 · HTTP 路由层。

仅做：参数解析、鉴权、调用 Service。业务逻辑全部在 ``gallery_service``。
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.deps import get_current_user, get_current_user_sse
from app import models
from app.gallery_config import GALLERY_FEATURES, serialize_options, serialize_types
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
    publish_showcase,
    list_templates,
    recompute_estimate,
    reorder_plan_items,
    rename_record,
    rename_task,
    resolve_file,
    save_plan_item_image,
    save_template,
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
    GalleryRecordRead,
    GalleryRecordUpdate,
    GalleryShowcaseCreate,
    GalleryShowcaseRead,
    GalleryTaskRead,
    GalleryTaskUpdate,
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
def get_types(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GalleryTypesResponse:
    # 保证固定配置已落库（若被清空可自动恢复），运行时优先读库
    from app.gallery_config import seed_gallery_config

    if db.query(models.GalleryConfig).count() == 0:
        seed_gallery_config(db)
        db.commit()
    return GalleryTypesResponse(types=serialize_types(db), options=serialize_options(db), features=GALLERY_FEATURES)


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
    # 不再自动注入 SVG 示例图：创作案例只展示用户真实发布的优秀成图
    items = list_showcases(db, category)
    return [
        {
            "id": s.id,
            "category": s.category,
            "name": s.name,
            "original_url": s.original_url,
            "image_urls": s.image_urls,
            "total_count": s.total_count,
            "payload": s.payload or {},
        }
        for s in items
    ]


@router.post("/showcases", response_model=GalleryShowcaseRead, status_code=status.HTTP_201_CREATED)
def create_showcase(
    payload: GalleryShowcaseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryShowcase:
    """把创作结果里优秀的成图发布到「创作案例」。"""
    try:
        sc = publish_showcase(
            db, current_user,
            name=payload.name, category=payload.category, record_ids=payload.record_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sc


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


@router.post("/projects/{project_id}/plan-items/upload-image")
def upload_plan_item_image(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> dict:
    """上传策划项「单独商品图」。

    与项目产品图接口不同：本接口不写入 ``GalleryProjectImage`` 表，
    仅落盘并返回 {filename, url}，由前端存入对应策划项的 ``product_image`` 字段。
    """
    proj = get_owned_project(db, current_user, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")
    return save_plan_item_image(project_id, data, file.filename or "image.png")


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
# 卖点 AI 帮写（根据产品图，AI 输出结构化卖点）
# ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/ai-write-selling-points")
def ai_write_selling_points_endpoint(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    proj = get_owned_project(db, current_user, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not proj.images:
        raise HTTPException(status_code=400, detail="请先上传至少一张产品图，AI 才能理解产品")
    from app.gallery_prompt_ai import ai_write_selling_points

    return ai_write_selling_points(proj, db)


# ─────────────────────────────────────────────────────────────
# 生成
# ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/generate", response_model=GalleryTaskRead)
def run_generate(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GalleryTaskRead:
    try:
        task = generate(db, current_user, project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return GalleryTaskRead.model_validate(task)


@router.get("/tasks", response_model=list[GalleryTaskRead])
def list_tasks(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> list[GalleryTaskRead]:
    from sqlalchemy import select

    tasks = db.scalars(
        select(models.GalleryTask)
        .where(models.GalleryTask.user_id == current_user.id)
        .order_by(models.GalleryTask.created_at.desc())
    ).all()
    return [GalleryTaskRead.model_validate(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=GalleryTaskRead)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GalleryTaskRead:
    from sqlalchemy import select

    task = db.scalar(
        select(models.GalleryTask).where(
            models.GalleryTask.id == task_id,
            models.GalleryTask.user_id == current_user.id,
        )
    )
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return GalleryTaskRead.model_validate(task)


@router.get("/tasks/stream")
def stream_tasks(
    current_user: models.User = Depends(get_current_user_sse),
) -> StreamingResponse:
    """SSE 任务进度推送：替代前端轮询。

    单次连接内持续推送当前用户「进行中」任务的实时进度（done/total/status），
    并在任务终态（completed/partial/failed）时各推送一次最终快照，随后结束流。
    每轮用独立 ``SessionLocal`` 查询，不在长连接期间持有数据库事务/连接。

    鉴权：复用 ``get_current_user_sse``（Authorization 头或 ``?token=`` 查询参数），
    以兼容浏览器 EventSource 无法自定义请求头的限制。
    """
    uid = current_user.id

    def event_gen():
        announced_terminal: set[int] = set()
        streaming_ids: set[int] = set()
        # 最多推送 ~15 分钟（900 * 1s），超过则强制结束，避免僵尸连接
        for _ in range(900):
            with SessionLocal() as db:
                active = db.scalars(
                    select(models.GalleryTask).where(
                        models.GalleryTask.user_id == uid,
                        models.GalleryTask.status.in_(["pending", "running"]),
                    )
                ).all()
                for t in active:
                    streaming_ids.add(t.id)
                # 推送进行中任务（每轮都推，前端据此刷新进度）
                for t in active:
                    snap = GalleryTaskRead.model_validate(t).model_dump_json()
                    yield f"data: {snap}\n\n"
                # 推送刚结束的任务（每任务仅一次）
                if streaming_ids:
                    term = db.scalars(
                        select(models.GalleryTask).where(
                            models.GalleryTask.id.in_(list(streaming_ids)),
                            models.GalleryTask.status.in_(
                                ["completed", "partial", "failed"]
                            ),
                        )
                    ).all()
                    for t in term:
                        if t.id not in announced_terminal:
                            announced_terminal.add(t.id)
                            snap = GalleryTaskRead.model_validate(t).model_dump_json()
                            yield f"data: {snap}\n\n"
                    streaming_ids -= announced_terminal
            # keep-alive 注释，避免代理/浏览器空闲断开
            yield ": keep-alive\n\n"
            if not streaming_ids:
                # 所有任务已结束，推送完毕，正常结束流
                break
            time.sleep(1)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 关闭 nginx 缓冲，确保实时推送
        },
    )


@router.patch("/tasks/{task_id}", response_model=GalleryTaskRead)
def patch_task(
    task_id: int,
    payload: GalleryTaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> GalleryTaskRead:
    """重命名创作任务。"""
    task = rename_task(db, current_user, task_id, payload.name or "")
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return GalleryTaskRead.model_validate(task)


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


@router.patch("/records/{record_id}", response_model=GalleryRecordRead)
def patch_record(
    record_id: int,
    payload: GalleryRecordUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
) -> models.GalleryRecord:
    """重命名单张创作记录（图片）的标题。仅允许用户修改自己的记录。"""
    rec = rename_record(db, current_user, record_id, payload.title or "")
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")
    return rec


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
        "plan_item_snapshot": r.plan_item_snapshot,
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
