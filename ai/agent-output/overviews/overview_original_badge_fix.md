# 修复「原图」角标仅首张显示 + 排序反序

## 问题现象
上传产品图时，只有**第一张**显示「原图」角标，第二张及之后的图不显示；并且列表顺序也有问题（首张反而排到最后）。

## 根因
`app/gallery_service.py` 的 `add_image()`：

```python
is_first = (项目内图片数 == 0)
img = GalleryProjectImage(
    original=is_first,        # 仅首张为 True
    order=int(is_first),      # 首张 order=1，其余 order=0（排序反了）
)
```

- `original=True` 只给了「项目里还没有图时的第一张」，其余都是 `False` → 没有角标。
- `order=int(is_first)` 让首张 `1`、其余 `0`，而前端按 `order` 升序展示，首张反而排末尾。

`original` 字段仅用于前端「原图」角标展示，**未进入出图生成链路**，改它不影响生成逻辑，安全。

## 修复内容
文件：`app/gallery_service.py`

```python
existing_count = db.scalar(select(func.count(...)).where(project_id == project_id)) or 0
img = GalleryProjectImage(
    original=True,            # 所有上传的产品图都是用户原图（多视角）
    order=existing_count,     # 按上传顺序升序
)
```

- `delete_image()` 中已无意义的「删除后重标首张为原图」逻辑一并移除（语义已变为「全部都是原图」）。

## 部署与存量数据
运行的 API 在 Docker 容器 `ai-agent-api` 内，使用 **Docker 的 MySQL**（库 `ai_agent`），且 uvicorn **没有 `--reload`**，因此：

1. **重启容器**加载新代码：`docker compose -f docker/docker-compose.yml restart api`（已执行，容器 Up）。
2. **存量数据回填**（MySQL）：把全部 `gallery_project_images.original` 置 `1`，并用窗口函数按 `id` 重排 `order`。
   - 回填前：`id=2（第二张）original=0, order=0`
   - 回填后：`id=2 original=1, order=1` ✅

## 验证
- `py_compile app/gallery_service.py` 通过，无语法错误。
- MySQL 回填后查询：两张图均为 `original=1`，`order` 为 0、1（上传顺序正确）。
- `docker compose ps api`：容器 `Up`，新代码已加载。

## 给团队的提醒
- 本地 `agent.db`（SQLite）是旧的本地残留数据，**不是**当前运行环境的库；排查线上/运行行为要以 Docker 内的 MySQL 为准。
- 改后端 Python 代码后，Docker 部署下必须 `restart api`（无热重载），否则仍是旧逻辑。
