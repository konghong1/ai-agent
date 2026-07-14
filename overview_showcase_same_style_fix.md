# 修复：一键做同款参数丢失 + 创作案例假数据

## 问题定位
1. **「发布到创作案例」未带上参数**：`GalleryShowcase` 只存图 URL，无参数字段；`publish_showcase` 不存配置；前端创作案例「生成同款」只是 `openDrawer()`，什么参数都不带。
2. **创作案例展示假数据**：`seed_showcases` 向 `gallery_showcases` 注入了 6 条 SVG 占位图（渐变+文案），库里 `agent.db` 实测 6 行全是 `.svg` 假图。

## 改动清单

### 后端
- `app/models.py`：`GalleryShowcase` 新增 `payload`(JSON) 列，存源任务参数
  `{plan_items:[plan_item_snapshot…], market_config, output_config, selling_points}`。
- `app/gallery_service.py`：`publish_showcase` 发布时从源 records 的 `plan_item_snapshot`
  与项目级 `market_config/output_config/selling_points` 组装 `payload` 落库。
- `app/schemas.py`：`GalleryShowcaseRead` 增加 `payload` 字段。
- `app/gallery_routes.py`：`GET /showcases` 返回 `payload`；移除未调用的 `seed_showcases` 导入。
- `app/server.py`：启动时幂等自愈 `gallery_showcases.payload` 列（兼容 SQLite/MySQL，
  不写 server_default，避免 MySQL TEXT/JSON 列默认值约束）。
- `migrations/showcase_payload.py`：迁移脚本——加列 + 删除 `.svg` 假数据（已执行，删 6 行）。

### 前端
- `web/src/services/gallery.ts`：`GalleryShowcase` 接口加 `payload` 类型。
- `web/src/pages/EcommerceGallery/index.tsx`：
  - 抽取共享 `applySnapshotsToProject`（按 type_id 去重回填，携带全局 output/market/selling_points）。
  - 任务结果「一键做同款」复用该helper。
  - 新增 `handleSameStyleFromShowcase(sc)`：把案例携带的 `payload` 回填到左侧配置面板。
  - 创作案例**卡片**与**详情**的「生成同款」按钮由 `openDrawer()` 改为 `handleSameStyleFromShowcase`。

## 验证结果
- 前端 `npm run build`（tsc + vite）通过。
- 后端单测 `tests/verify_showcase_payload.py`：发布后 `payload` 含 `plan_items/market_config/
  output_config/selling_points`；`GET /showcases` 字典正确返回 `payload` → **PASS**。
- 库实测：`gallery_showcases` 已含 `payload` 列；假数据 6 行已清空（展示空态，待真实发布）。

## 用户须注意
- 本地已自动迁移并清理假数据；**Docker(MySQL) 部署请运行 `python migrations/showcase_payload.py`**
  （或重启 api 由启动自愈逻辑加列）。
- 改后端后请重启 FastAPI 服务并刷新浏览器。
