"""电商套图：后台生成任务 worker。

设计要点：
- 单进程内一个守护线程，从队列取 task_id 执行，避免阻塞 HTTP 请求。
- worker 内的生成逻辑在 ``app.gallery_service.run_gallery_task`` 中，
  使用独立 DB 会话（不复用请求会话），逐张提交以便前端轮询看到实时进度。
- 多次「立即生成」会入队多个任务，依次执行（图片生成本身串行，避免打爆上游）。
"""

from __future__ import annotations

import datetime as _dt
import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# 进程启动时刻，用于孤儿恢复时排除“本进程刚创建”的活跃任务，避免重复生成
PROCESS_START = _dt.datetime.now()

_task_queue: "queue.Queue[int]" = queue.Queue()
_worker_thread: threading.Thread | None = None
_worker_pool: "ThreadPoolExecutor | None" = None
_worker_started = False
_recovery_done = False
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
    # 并发消费队列：用线程池并行处理多个任务，单任务卡顿（如上游 chat 接口超时）
    # 不会再阻塞全局——其他任务 / 孤儿恢复仍能独立推进。
    while True:
        task_id = _task_queue.get()
        try:
            _worker_pool.submit(_process, task_id)
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
        global _worker_pool
        _worker_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gallery-worker")
        _worker_thread = threading.Thread(target=_worker_loop, name="gallery-worker", daemon=True)
        _worker_thread.start()
        _worker_started = True
        logger.info("gallery background worker started")
        # api 容器重启会清空进程内存队列，重启前处于 running 的任务成为孤儿。
        # worker 启动后扫描并重新入队这些孤儿，避免任务永久卡在“创作中”。
        threading.Thread(target=_recover_orphans, name="gallery-recover", daemon=True).start()


def _recover_orphans() -> None:
    """恢复 api 重启后遗留的 running 孤儿任务：重新入队让 worker 接管。

    判定改用「最后进度时间」(updated_at)：只恢复 running 且 updated_at 明显早于
    本进程启动时刻（PROCESS_START 之前 120s 以上）的任务。这样能同时覆盖两类孤儿：
    （1）上次进程重启前已创建、因内存队列丢失而从未被处理的任务；
    （2）运行中因进程重启而中断、其出图线程已消失的任务。
    而本进程刚创建、正在正常处理的活跃任务会持续刷新 updated_at，不会被误接管，
    避免重复生成。`run_gallery_task` 内部已实现 resume（复用已有 record、跳过已完成项），
    因此即使极端情况下重复入队也安全幂等。
    """
    global _recovery_done
    with _worker_lock:
        if _recovery_done:
            return
        _recovery_done = True
    try:
        from app.core.database import SessionLocal
        from app import models
        cutoff = PROCESS_START - _dt.timedelta(seconds=120)
        db = SessionLocal()
        try:
            orphans = (
                db.query(models.GalleryTask)
                .filter(models.GalleryTask.status == "running")
                .filter(models.GalleryTask.updated_at < cutoff)
                .all()
            )
            for o in orphans:
                logger.info("恢复孤儿生成任务 task=%s（因 api 重启丢失内存队列）", o.id)
                _task_queue.put(o.id)
        finally:
            db.close()
    except Exception:
        logger.exception("恢复 gallery 孤儿任务失败")


def enqueue_task(task_id: int) -> None:
    """把任务放入队列（确保 worker 已启动）。"""
    start_worker()
    _task_queue.put(task_id)
