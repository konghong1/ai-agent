"""验证：图片生成 0 失败机制（品牌清洗 + 内容拒绝自愈 + 中性兜底）。

纯脚本（无 pytest 依赖）：在 api 容器内 `python tests/verify_zero_failure.py` 运行。
两层验证：
1) 确定性单元测试（mock 图像模型）：_sanitize_brand / _is_content_rejection /
   当图像模型拒绝含品牌提示词时，_real_generate 递进到清洗/深度清洗/中性兜底并返回图片。
2) 实弹（--live）：对真实项目发起生成任务，轮询至终态，断言 failed == 0。
"""
from __future__ import annotations

import sys
import time
import unittest.mock as mock

import app.gallery_service as gs
from app.gallery_service import _sanitize_brand, _is_content_rejection, _real_generate


class _FakeProvider:
    id = 1
    name = "fake"
    base_url = "http://fake"
    api_key = "x"


class _FakeModel:
    model_name = "fake-model"


def _fake_resolve(*a, **k):
    return _FakeProvider(), _FakeModel()


def test_sanitize_brand_strips_terms():
    # 非深度清洗：去掉品牌整词 + 仿冒短语（logo/double c 属「深度清洗」才去）
    p = "a Chanel handbag with double C logo, in the style of 1:1 replica"
    out = _sanitize_brand(p)
    assert "chanel" not in out.lower()
    assert "1:1" not in out.lower()
    assert "replica" not in out.lower()
    # 深度专用词在非深度模式下应保留（确认分级设计）
    assert "logo" in out.lower()
    assert "double c" in out.lower()
    assert "handbag" in out.lower()


def test_sanitize_brand_deep_removes_logo_emblem():
    p = "product with monogram and emblem, brand signature"
    out = _sanitize_brand(p, deep=True)
    assert "monogram" not in out.lower()
    assert "emblem" not in out.lower()
    assert "brand" not in out.lower()


def test_is_content_rejection_detects():
    assert _is_content_rejection("Unable to generate this content. Please modify your prompt and try again.")
    assert _is_content_rejection("内容安全策略拒绝：包含品牌")
    assert not _is_content_rejection("图像服务当前繁忙（队列已满）")
    assert not _is_content_rejection("")


def test_real_generate_self_heals_brand_rejection():
    calls = []

    def fake_gen(**kwargs):
        p = kwargs.get("prompt", "")
        calls.append(p)
        low = p.lower()
        if "chanel" in low or "double c" in low or "logo" in low:
            return {"error": "Unable to generate this content. Please modify your prompt and try again.", "data": []}
        return {"data": [{"url": "http://example.com/img.png"}]}

    with mock.patch.object(gs, "_resolve_image_model", _fake_resolve), \
         mock.patch("app.media.MediaService.generate_image", side_effect=fake_gen), \
         mock.patch.object(gs, "_save_generated_image", return_value="saved.png"):
        res = _real_generate(1, "a Chanel handbag with double C logo, professional photo", [])

    assert res.get("url"), f"应返回图片，实际: {res}"
    assert len(calls) >= 3, f"应递进多次尝试，实际调用次数 {len(calls)}"
    assert "chanel" not in calls[-1].lower()
    assert "logo" not in calls[-1].lower()


def test_real_generate_falls_back_to_neutral():
    calls = []

    def fake_gen(**kwargs):
        p = kwargs.get("prompt", "")
        calls.append(p)
        if "forbiddenword" in p.lower():
            return {"error": "Unable to generate this content. Please modify your prompt and try again.", "data": []}
        return {"data": [{"url": "http://example.com/img.png"}]}

    with mock.patch.object(gs, "_resolve_image_model", _fake_resolve), \
         mock.patch("app.media.MediaService.generate_image", side_effect=fake_gen), \
         mock.patch.object(gs, "_save_generated_image", return_value="saved.png"):
        res = _real_generate(1, "a product shot with forbiddenword, studio light", [])

    assert res.get("url"), f"中性兜底应返回图片，实际: {res}"
    # 原/深度均被拒（无品牌词无法清洗），中性兜底成功（candidates 已被去重为 3 个）
    assert len(calls) >= 3, f"应走到中性兜底，实际调用 {len(calls)}"
    assert "forbiddenword" not in calls[-1].lower()


def _run_unit_tests():
    test_sanitize_brand_strips_terms()
    print("PASS: _sanitize_brand 剥离品牌/IP/仿冒描述")
    test_sanitize_brand_deep_removes_logo_emblem()
    print("PASS: _sanitize_brand(deep) 去掉 logo/emblem/brand")
    test_is_content_rejection_detects()
    print("PASS: _is_content_rejection 识别内容策略拒绝")
    test_real_generate_self_heals_brand_rejection()
    print("PASS: 含品牌提示词被拒 → 递进清洗/深度清洗 → 返回图片（自愈）")
    test_real_generate_falls_back_to_neutral()
    print("PASS: 全候选被拒 → 中性兜底提示词 → 返回图片（0 失败兜底）")


def _run_live():
    """实弹：对真实项目发起一次生成任务，轮询至终态，断言 failed == 0。"""
    from app.core.database import SessionLocal
    from app import models
    from app.gallery_service import generate

    PROJECT_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    with SessionLocal() as db:
        user = db.get(models.User, 2)
        project = db.get(models.GalleryProject, PROJECT_ID)
        assert user and project, "用户/项目不存在"
        assert project.plan_items, "项目无规划项"
        assert project.images, "项目无产品图"
        task = generate(db, user, PROJECT_ID)
        tid = task.id
        print(f"LIVE: 已创建任务 task_id={tid}（{len(project.plan_items)} 张图），等待 worker 执行...")

    terminal = {"completed", "partial", "failed"}
    for _ in range(180):  # 最多 15 分钟
        time.sleep(5)
        with SessionLocal() as db:
            t = db.get(models.GalleryTask, tid)
            if t is None:
                continue
            print(f"  task {tid}: status={t.status} done={t.done} failed={t.failed}")
            if t.status in terminal:
                break

    with SessionLocal() as db:
        t = db.get(models.GalleryTask, tid)
        print(f"LIVE RESULT: task {tid} status={t.status} done={t.done} failed={t.failed}")
        assert t.failed == 0, f"任务存在失败记录 failed={t.failed}（未达 0 失败）"
        assert t.status in ("completed", "partial"), f"任务未成功完成: {t.status}"
    print("PASS: 实弹任务 failed == 0（0 失败）")


if __name__ == "__main__":
    if "--live" in sys.argv:
        _run_live()
    else:
        _run_unit_tests()
    print("\nRESULT: PASS")
