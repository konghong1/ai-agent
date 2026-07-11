"""电商套图：后台生成任务 worker。

设计要点：
- 单进程内一个守护线程，从队列取 task_id 执行，避免阻塞 HTTP 请求。
- worker 内的生成逻辑在 ``app.gallery_service.run_gallery_task`` 中，
  使用独立 DB 会话（不复用请求会话），逐张提交以便前端轮询看到实时进度。
- 多次「立即生成」会入队多个任务，依次执行（图片生成本身串行，避免打爆上游）。
"""

from __future__ import annotations

import logging
import queue
import threading

logger = logging.getLogger(__name__)

_task_queue: "queue.Queue[int]" = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_started = False
_worker_lock = threading.Lock()


def _process(task_id: int) -> None:
    from app import gallery_service
    from app.core.database import SessionLocal
    from app import models

    try:
        gallery_service.run_gallery_task(task_id)
    except Exception as exc:  # 硬失败兜底：把任务标记为 failed，避免永久 pending
        logger.exception("gallery task %s hard failure: %s", task_id, exc)
        try:
            db = SessionLocal()
            task = db.get(models.GalleryTask, task_id)
            if task and task.status not in ("completed", "partial"):
                task.status = "failed"
                task.error = f"worker error: {exc}"
                db.commit()
            db.close()
        except Exception:
            pass


def _worker_loop() -> None:
    while True:
        task_id = _task_queue.get()
        try:
            _process(task_id)
        finally:
            _task_queue.task_done()


def start_worker() -> None:
    """启动后台 worker（幂等，进程内只启动一次）。"""
    global _worker_thread, _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        _worker_thread = threading.Thread(target=_worker_loop, name="gallery-worker", daemon=True)
        _worker_thread.start()
        _worker_started = True
        logger.info("gallery background worker started")


def enqueue_task(task_id: int) -> None:
    """把任务放入队列（确保 worker 已启动）。"""
    start_worker()
    _task_queue.put(task_id)
