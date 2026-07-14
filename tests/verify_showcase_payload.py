"""后端验证：发布到创作案例时是否带上源任务参数，且能被读取。

不依赖运行中的服务、也不需要真实图片模型：
- 用独立临时 SQLite 库建表，避免污染 agent.db；
- 直接调用 publish_showcase，断言返回的 GalleryShowcase.payload 含
  plan_items / market_config / output_config / selling_points；
- 模拟 GET /showcases 的字典拼装，确认 payload 能被返回。

运行： .venv/Scripts/python.exe tests/verify_showcase_payload.py
"""
from __future__ import annotations

import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.gallery_service import list_showcases, publish_showcase


def main() -> int:
    tmp = tempfile.mktemp(suffix=".db", prefix="verify_showcase_")
    engine = create_engine(f"sqlite:///{tmp}", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = Session()
    try:
        # 用户 + 项目（带市场/输出/卖点配置）
        user = models.User(email="verify@example.com", username="verify", password_hash="x", role="user")
        db.add(user)
        db.commit()

        proj = models.GalleryProject(
            user_id=user.id,
            name="验证套图",
            status="draft",
            market_config={"ecommerce_platform": "淘宝", "target_market": "中国"},
            output_config={"resolution": "1K", "ratio": "竖图 3:4", "count": 2, "provider_id": 1, "model_name": "m"},
            selling_points="产品名称：测试连衣裙\n核心卖点：显瘦",
        )
        db.add(proj)
        db.commit()

        plan = models.GalleryPlanItem(
            project_id=proj.id,
            type_id="detail",
            order=0,
            personal_settings={"风格": "复古"},
            common_settings={"场景": "街拍"},
            output_settings={"ratio": "竖图 3:4", "count": 1},
            note="强调质感",
            reference_images=["projects/1/ref.png"],
            product_image="projects/1/p.png",
        )
        db.add(plan)
        db.commit()

        # 一条真实成图（非 .svg），带 plan_item 配置快照
        rec = models.GalleryRecord(
            project_id=proj.id,
            plan_item_id=plan.id,
            user_id=user.id,
            type_id="detail",
            title="细节图 #1",
            status="completed",
            result_url="/api/gallery/files/results/real1.png",
            prompt="中文提示词",
            prompt_en="english prompt",
            plan_item_snapshot={
                "type_id": "detail",
                "personal_settings": {"风格": "复古"},
                "common_settings": {"场景": "街拍"},
                "output_settings": {"ratio": "竖图 3:4", "count": 1},
                "note": "强调质感",
                "reference_images": ["projects/1/ref.png"],
                "product_image": "projects/1/p.png",
            },
        )
        db.add(rec)
        db.commit()

        # —— 执行发布 ——
        sc = publish_showcase(
            db, user, name="验证案例", category="服装鞋帽", record_ids=[rec.id],
        )
        payload = sc.payload or {}
        print("payload =", payload)

        ok = True
        if not payload.get("plan_items"):
            print("[FAIL] payload.plan_items 缺失")
            ok = False
        else:
            pi = payload["plan_items"][0]
            if pi.get("type_id") != "detail" or pi.get("personal_settings", {}).get("风格") != "复古":
                print("[FAIL] plan_items 内容不正确:", pi)
                ok = False
        if payload.get("market_config", {}).get("ecommerce_platform") != "淘宝":
            print("[FAIL] market_config 未携带")
            ok = False
        if payload.get("output_config", {}).get("ratio") != "竖图 3:4":
            print("[FAIL] output_config 未携带")
            ok = False
        if payload.get("selling_points", "") != proj.selling_points:
            print("[FAIL] selling_points 未携带")
            ok = False

        # —— 模拟 GET /showcases 的字典拼装 ——
        items = list_showcases(db)
        d = [
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
        if not d or not d[0].get("payload", {}).get("plan_items"):
            print("[FAIL] GET /showcases 未返回 payload")
            ok = False
        else:
            print("[PASS] GET /showcases 返回 payload，plan_items 数 =", len(d[0]["payload"]["plan_items"]))

        print("RESULT:", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        db.close()
        try:
            os.remove(tmp)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
