"""电商套图 · 后端端到端验证脚本（可重复运行，打印完整响应体）。

运行： .venv/Scripts/python.exe tests/test_gallery_e2e.py
"""
from __future__ import annotations

import base64
import json
import random
import string
import sys

import requests

BASE = "http://127.0.0.1:8010"

# 一张 1x1 的合法 PNG（避免依赖外部文件）
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  -> {detail}")


def jprint(label: str, resp: requests.Response) -> None:
    print(f"--- {label} | HTTP {resp.status_code}")
    try:
        body = resp.json()
        print("    " + json.dumps(body, ensure_ascii=False)[:600])
    except Exception:
        print("    (non-json) " + resp.text[:300])


def main() -> int:
    s = requests.Session()

    # 1) 注册新用户（随机邮箱避免冲突）
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"gallery_{suffix}@test.com"
    pw = "gallery123"
    r = s.post(f"{BASE}/api/auth/register", json={"email": email, "username": "guser", "password": pw})
    jprint("register", r)
    if r.status_code != 200:
        print("注册失败，终止")
        return 2
    token = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {token}"})

    # 2) 类型
    r = s.get(f"{BASE}/api/gallery/types")
    jprint("types", r)
    types = (r.json() or {}).get("types", [])
    check("types=18", len(types) == 18, f"len={len(types)}")
    type_ids = [t["id"] for t in types]
    check("首类型=bg", type_ids and type_ids[0] == "bg", f"first={type_ids[:1]}")

    # 3) 草稿
    r = s.get(f"{BASE}/api/gallery/projects/draft")
    jprint("draft", r)
    pid = (r.json() or {}).get("id")
    check("draft有id", bool(pid), f"pid={pid}")

    # 4) 上传图片
    png = base64.b64decode(PNG_B64)
    files = {"files": ("product.png", png, "image/png")}
    r = s.post(f"{BASE}/api/gallery/projects/{pid}/images", files=files)
    jprint("upload_images", r)
    imgs = ((r.json() or [{}])[0].get("images") if isinstance(r.json(), list) else []) or []
    check("上传后有图片", len(imgs) >= 1, f"imgs={len(imgs)}")

    # 5) 创建策划项
    payload = {
        "type_id": "bg",
        "personal_settings": {"主体名称": "测试商品"},
        "common_settings": {"visual_style": "白底"},
        "output_settings": {"count": 2},
        "note": "测试说明",
    }
    r = s.post(f"{BASE}/api/gallery/projects/{pid}/plan-items", json=payload)
    jprint("create_plan_item", r)
    item_id = (r.json() or {}).get("id")
    check("策划项创建有id", bool(item_id), f"item_id={item_id}")
    check("策划项有status", (r.json() or {}).get("status") is not None, f"status={(r.json() or {}).get('status')}")

    # 6) AI 帮填
    r = s.post(f"{BASE}/api/gallery/projects/{pid}/ai-fill",
               json={"type_id": "bg", "current": {"personal_settings": {"主体名称": "测试商品"}}})
    jprint("ai-fill", r)
    af = r.json() or {}
    check("ai-fill三键", set(af.keys()) >= {"common_settings", "personal_settings", "note"}, f"keys={list(af.keys())}")

    # 7) 生成
    r = s.post(f"{BASE}/api/gallery/projects/{pid}/generate")
    jprint("generate", r)
    gen = r.json() or {}
    check("生成成功", r.status_code == 200, f"code={r.status_code}")
    check("生成有records", len(gen.get("records", [])) >= 1, f"recs={len(gen.get('records', []))}")
    check("生成total_images", gen.get("total_images", 0) >= 1, f"t={gen.get('total_images')}")

    # 8) 项目记录
    r = s.get(f"{BASE}/api/gallery/projects/{pid}/records")
    jprint("project_records", r)
    check("项目记录有数据", len(r.json() or []) >= 1, f"n={len(r.json() or [])}")

    # 9) 我的记录
    r = s.get(f"{BASE}/api/gallery/records")
    jprint("my_records", r)
    check("我的记录有数据", len(r.json() or []) >= 1, f"n={len(r.json() or [])}")

    # 10) 创建模板
    tpl_payload = {
        "name": "测试模板",
        "payload": {
            "plan_items": [{"type_id": "bg", "output_settings": {"count": 1}, "personal_settings": {"主体名称": "模板商品"}}],
            "selling_points": "模板卖点",
        },
    }
    r = s.post(f"{BASE}/api/gallery/templates", json=tpl_payload)
    jprint("create_template", r)
    tpl_id = (r.json() or {}).get("id")
    check("模板创建有id", bool(tpl_id), f"tpl_id={tpl_id}")

    # 11) 应用模板到新草稿
    r2 = s.get(f"{BASE}/api/gallery/projects/draft")
    pid2 = (r2.json() or {}).get("id")
    if tpl_id and pid2:
        r = s.post(f"{BASE}/api/gallery/templates/{tpl_id}/apply", params={"project_id": pid2})
        jprint("apply_template", r)
        check("应用模板成功", r.status_code == 200, f"code={r.status_code}")
    else:
        check("应用模板成功", False, "tpl_id/pid2 missing")

    # 12) 示例展示
    r = s.get(f"{BASE}/api/gallery/showcases")
    jprint("showcases", r)
    check("示例展示有数据", len(r.json() or []) >= 1, f"n={len(r.json() or [])}")

    # 13) 更新策划项
    if item_id:
        r = s.patch(f"{BASE}/api/gallery/projects/{pid}/plan-items/{item_id}",
                    json={"note": "更新后的说明", "output_settings": {"count": 3}})
        jprint("patch_plan_item", r)
        check("更新策划项成功", r.status_code == 200 and (r.json() or {}).get("note") == "更新后的说明", f"code={r.status_code}")

    # 14) 删除（回收）
    if item_id:
        r = s.delete(f"{BASE}/api/gallery/projects/{pid}/plan-items/{item_id}")
        check("删除策划项", r.status_code in (204, 200), f"code={r.status_code}")
    if imgs:
        r = s.delete(f"{BASE}/api/gallery/projects/{pid}/images/{imgs[0]['id']}")
        check("删除图片", r.status_code in (204, 200), f"code={r.status_code}")
    if tpl_id:
        r = s.delete(f"{BASE}/api/gallery/templates/{tpl_id}")
        check("删除模板", r.status_code in (204, 200), f"code={r.status_code}")

    print(f"\n==== 结果: PASS={passed} FAIL={failed} ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
