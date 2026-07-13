"""电商套图 · AI 提示词生成引擎重构验证。

运行（无需 pytest）：
    python tests/test_gallery_prompt_ai.py

覆盖：
1. generate_prompt_via_ai 正常路径：解析 AI 返回的 JSON → prompt_cn/prompt_en，source=ai
2. generate_prompt_via_ai 降级路径：AI 返回非 JSON / 抛异常 → 降级模板引擎，source=template
3. ai_write_selling_points：返回结构化卖点字段
4. ai_write_type_config：返回 {common_settings, personal_settings, note}
5. 英文版零中文硬约束：中文泄漏被 _strip_cjk 清除
6. 真实 Agnes 多模态调用（联网）：确认 data URL 图片可被理解且返回合法 JSON
"""

import asyncio
import os
import sys
import json
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.gallery_prompt_ai as ai
from app.gallery_prompt_ai import (
    _extract_json,
    _strip_cjk,
    generate_prompt_via_ai,
    ai_write_selling_points,
    ai_write_type_config,
)

PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLv"
    "AAAAAElFTkSuQmCC"
)


def make_project(selling_points="", images=None):
    img = SimpleNamespace(filename="projects/1/test.png", url="/api/gallery/files/projects/1/test.png")
    return SimpleNamespace(
        market_config={},
        selling_points=selling_points,
        images=images if images is not None else [img],
    )


def make_item(type_id="bg", personal=None, common=None, note=""):
    return SimpleNamespace(
        type_id=type_id,
        personal_settings=personal or {},
        common_settings=common or {},
        output_settings={},
        note=note,
        reference_images=[],
        product_image="",
    )


def _patch(chat_return=None, chat_side_effect=None):
    """返回一个 mock.patch 上下文管理器，替换 _chat_multimodal。"""

    async def _fake(*a, **k):
        return chat_return

    target = _fake if chat_return is not None else chat_side_effect
    return mock.patch.object(ai, "_chat_multimodal", target)


# ── 1. 正常路径 ──────────────────────────────────────────────

def test_generate_prompt_happy_path():
    canned = (
        '```json\n{"prompt_cn": "一张高级质感的白色背景产品图，居中展示。", '
        '"prompt_en": "premium product photo, white background, centered, soft lighting, high detail"}\n```'
    )
    with _patch(chat_return=canned):
        out = generate_prompt_via_ai(make_project("卖点A"), make_item(), effective_product_image="x.png")
    assert out["prompt_source"] == "ai", out
    assert "白色背景" in out["prompt"]
    assert "premium product photo" in out["prompt_en"]
    print("[OK] test_generate_prompt_happy_path")


# ── 2. 降级路径（AI 返回非 JSON） ──────────────────────────────

def test_generate_prompt_fallback_on_bad_json():
    with _patch(chat_return="抱歉，我无法生成提示词。"):
        with mock.patch("app.gallery_prompt.build_prompt_bilingual",
                        lambda *a, **k: {"prompt": "模板中文", "prompt_en": "template en"}):
            out = generate_prompt_via_ai(make_project(), make_item(), effective_product_image="x.png")
    assert out["prompt_source"] == "template", out
    assert out["prompt"] == "模板中文"
    print("[OK] test_generate_prompt_fallback_on_bad_json")


# ── 2b. 降级路径（AI 抛异常） ──────────────────────────────────

def test_generate_prompt_fallback_on_exception():
    async def _boom(*a, **k):
        raise RuntimeError("Agnes 不可达")

    with _patch(chat_side_effect=_boom):
        with mock.patch("app.gallery_prompt.build_prompt_bilingual",
                        lambda *a, **k: {"prompt": "模板中文", "prompt_en": "template en"}):
            out = generate_prompt_via_ai(make_project(), make_item(), effective_product_image="x.png")
    assert out["prompt_source"] == "template"
    print("[OK] test_generate_prompt_fallback_on_exception")


# ── 3. 卖点 AI 帮写 ───────────────────────────────────────────

def test_ai_write_selling_points():
    canned = (
        '{"product_name": "无线降噪耳机", "selling_points": "主动降噪，续航30小时", '
        '"audience": "通勤人群", "scene": "地铁/办公室", "params": "蓝牙5.3"}'
    )
    with _patch(chat_return=canned):
        out = ai_write_selling_points(make_project())
    assert out["product_name"] == "无线降噪耳机"
    assert out["audience"] == "通勤人群"
    print("[OK] test_ai_write_selling_points")


# ── 4. 类型配置 AI 帮写 ───────────────────────────────────────

def test_ai_write_type_config():
    canned = (
        '{"common_settings": {"visual_style": "高级质感风"}, '
        '"personal_settings": {"背景": "纯白"}, "note": "突出产品金属质感"}'
    )
    with _patch(chat_return=canned):
        out = ai_write_type_config(make_project("卖点B"), "bg", {"personal_settings": {}, "common_settings": {}})
    assert out["common_settings"].get("visual_style") == "高级质感风"
    assert out["personal_settings"].get("背景") == "纯白"
    assert out["note"]
    print("[OK] test_ai_write_type_config")


# ── 5. 英文版零中文 ───────────────────────────────────────────

def test_strip_cjk():
    dirty = "premium product, 中文泄漏 should not appear, soft lighting"
    clean = _strip_cjk(dirty)
    assert "中文泄漏" not in clean
    assert "premium product" in clean
    print("[OK] test_strip_cjk")


def test_extract_json_fenced():
    raw = '说明文字\n```json\n{"a": 1}\n```\n结束'
    assert _extract_json(raw) == {"a": 1}
    print("[OK] test_extract_json_fenced")


# ── 6. 真实 Agnes 多模态调用（联网，失败不阻塞其它用例） ────────

def test_real_agnes_multimodal():
    try:
        from app.settings import get_settings

        if not get_settings().openai_api_key:
            print("[SKIP] test_real_agnes_multimodal: 未配置 OPENAI_API_KEY")
            return
        data_url = f"data:image/png;base64,{PNG_B64}"
        raw = asyncio.run(
            ai._chat_multimodal(
                ai._PROMPT_SYSTEM,
                "【生成方向】产品白底图\n【核心卖点】测试产品\n请生成提示词",
                data_url,
                ai.AI_PROMPT_TEMPERATURE,
            )
        )
        print(f"[DEBUG] raw from Agnes: {raw[:500]!r}")
        data = _extract_json(raw)
        assert data and data.get("prompt_en"), f"AI 未返回有效 JSON: {raw[:300]}"
        assert _strip_cjk(data["prompt_en"]) == data["prompt_en"], "英文版含中文"
        print(f"[OK] test_real_agnes_multimodal: cn={len(data.get('prompt_cn',''))}字 en={len(data['prompt_en'])}字")
    except Exception as e:
        print(f"[FAIL] test_real_agnes_multimodal: {e!r}")


if __name__ == "__main__":
    results = []
    names = [n for n in dir() if n.startswith("test_")]
    for name in names:
        fn = globals()[name]
        if name == "test_real_agnes_multimodal":
            fn()
            continue
        try:
            fn()
            results.append((name, True, ""))
        except Exception as e:
            results.append((name, False, repr(e)))
    print("\n==== 结果汇总 ====")
    for name, ok, err in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -> {err}" if err else ""))
    failed = [n for n, ok, _ in results if not ok]
    sys.exit(1 if failed else 0)
