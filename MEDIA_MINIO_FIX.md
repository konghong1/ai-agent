# 媒体资源入桶（ai-agent-minio）诊断与修复 + MinIO 目录设计方案

> 高级开发工程师（Senior Developer）· 2026-07-07

## 一、为什么图片/视频没进 `ai-agent-minio` 桶？

根因有 **两层致命问题**，导致生成流程每次都"假装成功"但文件实际停留在供应商外部 CDN 或本地 `./media`，从未写入 MinIO：

### 1. 导入目标写错（最致命）
- 聊天生成走的主路径是 `app/api.py` → `app/media.py` 的 `MediaService`。
- `app/media.py` 里写的是 `from app.storage import get_storage_backend`，但 **`app/storage/__init__.py` 里根本没有这个函数**（它只存在于 `app/media_new.py`）。
- 结果：`_download_and_store` 每次执行到 `get_storage_backend()` 都抛 `ImportError` → 被外层 `except` 吞掉 → 回退成原始外部 CDN 直链。**文件从未进桶。**
- 之前只修了 `media_routes` 的导入，漏掉了真正干活的生成主路径 `app/media`。

### 2. `boto3` 没装（次致命）
- `MinIOStorageBackend` 懒加载 `boto3`，上传时 `put()` 在没装 boto3 的环境直接 `ImportError`。`requirements.txt` 漏了 `boto3`。即使上面修好，没有 boto3 仍然存不进去。

### 3. 配置/命名混乱（加剧 confusion）
- `get_storage_backend()` 默认后端是 `"local"`（写本地 `./media`）。
- `docker-compose.yml` 的 `minio-init` 创建的是 **`media-assets`** 桶，而应用配置用的是 **`ai-agent-minio`** 桶（worker 默认也是 `media-assets`）——三方命名不一致，你看到的 `media-assets` 其实是个"空桶"，谁也没往里写。

---

## 二、已做的修复

| 改动 | 说明 |
|------|------|
| `app/storage/__init__.py` | **真正落地** `get_storage_backend()`（单一真相源），默认 `minio` + 桶 `ai-agent-minio`，修正 `MINIO_PUBLIC_URL` 默认桶名；并加 `reset_storage_backend()`。 |
| `app/media.py` / `app/media_new.py` / `app/media_routes.py` | 三者统一从 `app.storage` 导入 `get_storage_backend`，消除重复与错配。 |
| `requirements.txt` + 受管 venv | 增加 `boto3>=1.34.0` 并安装（Docker 镜像经 requirements 自动带入）。 |
| `app/media.py._download_and_store` | 对象键改为 `images|videos/{user_id}/{yyyy}/{mm}/{dd}/{uuid}.{ext}`；返回**后端代理路径** `/api/media/assets/by-key/{key}`（浏览器可达）；MIME/扩展名推断更稳健。 |
| `app/api.py` | 图片：`_handle_image_generation` 传入 `user_id` 并落库 `MediaAsset`；视频：`get_video_status` 端点完成时写入 `MediaAsset`（object_key / user_id / status=completed），便于管理与清理。 |
| `docker-compose.yml` | `minio-init` 改为创建并公开 **`ai-agent-minio`**；api/worker 的 `MINIO_BUCKET` 默认回退统一为 `ai-agent-minio`。 |
| `.env`（本地） | 显式补 `STORAGE_BACKEND=minio` + `MINIO_*` 配置，本地直跑也指向 MinIO。 |
| `app/worker/media_worker.py` | 默认桶改为 `ai-agent-minio`；`NOW()` → `CURRENT_TIMESTAMP`（SQLite 安全）；键前缀对齐。 |

**验证**：全部改动文件 `py_compile` 通过；`get_storage_backend()` 解析为 `MinIOStorageBackend`，桶 `ai-agent-minio`；`media_new.get_storage_backend is storage.get_storage_backend == True`（已统一）。

> ⚠️ 已运行的容器需 `pip install boto3` 或 `docker compose build` 重建镜像后才会真正上传。

---

## 三、MinIO 管理目录设计方案（桶：`ai-agent-minio`）

```
ai-agent-minio/
├── images/                         # 文生图 / 聊天框生成的图片
│   └── {user_id}/
│       └── {yyyy}/{mm}/{dd}/
│           └── {uuid}.{ext}        # e.g. images/7/2026/07/07/9f3c1a…png
├── videos/                         # 文生视频 / 聊天框生成的视频
│   └── {user_id}/
│       └── {yyyy}/{mm}/{dd}/
│           └── {uuid}.{ext}        # e.g. videos/7/2026/07/07/9f3c1a…mp4
├── avatars/                        # 用户头像（预留）
│   └── {user_id}/{uuid}.{ext}
├── thumbnails/                     # 缩略图（预留）
│   └── {yyyy}/{mm}/{dd}/{uuid}.jpg
└── temp/                           # 生成中转 / 临时文件（预留）
    └── {uuid}.{ext}
```

### 设计理由
- **一级按媒体类型**（`images` / `videos`）：便于差异化的生命周期策略（视频更短 TTL、图片更长）。
- **二级按 `user_id` 隔离**：配额、按用户清理、检索都方便，也避免越权遍历。
- **三级按日期 `yyyy/mm/dd` 分片**：避免单目录对象爆炸，便于冷热分层与定时归档。
- **文件名用 uuid**：防冲突、防信息泄露。
- **预留 `avatars/thumbnails/temp`**：让后续功能（头像、缩略图、临时中转）有统一归处。

### 管理建议
- 每个对象对应一条 `media_assets` 表记录（`user_id, object_key, mime_type, file_size, status`）→ 可做后台管理页、按用户/日期统计、清理孤儿对象。
- MinIO **ILM 生命周期规则**：`videos` 30 天转低频/过期，`images` 180 天，`temp` 7 天自动删。
- 前端统一走 `/api/media/assets/by-key/{object_key}`（后端代理，支持 `Range` 视频拖动），**不直接暴露** MinIO 地址。

---

## 四、如何确认生效
1. `docker compose build api worker && docker compose up -d`（确保镜像含 boto3、桶为 `ai-agent-minio`）。
2. 在聊天框用图片/视频模型各生成一次。
3. MinIO 控制台（:9001）→ `ai-agent-minio` 桶下应出现 `images/<你的user_id>/...` 与 `videos/<你的user_id>/...`；`media_assets` 表同步新增对应记录。
4. 刷新聊天页，视频/图片仍可从我们的代理路径正常加载（不再依赖外部 CDN 临时链接）。
