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
import re
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


def make_project(selling_points="", images=None, market_config=None):
    img = SimpleNamespace(filename="projects/1/test.png", url="/api/gallery/files/projects/1/test.png")
    return SimpleNamespace(
        market_config=market_config if market_config is not None else {},
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


def _fake_settings():
    """注入一个带 key 的假 settings，使 AI 路径不被「未配置 OPENAI_API_KEY」提前拦截。"""
    return SimpleNamespace(openai_api_key="test-key", openai_base_url="http://test", openai_model="agnes-2.0-flash")


def _patch_settings():
    return mock.patch("app.gallery_prompt_ai.get_settings", _fake_settings)


# ── 1. 正常路径 ──────────────────────────────────────────────

def test_generate_prompt_happy_path():
    canned = (
        '```json\n{"prompt_cn": "一张高级质感的白色背景产品图，居中展示。", '
        '"prompt_en": "premium product photo, white background, centered, soft lighting, high detail"}\n```'
    )
    with _patch_settings(), _patch(chat_return=canned), \
         mock.patch("app.gallery_service._gallery_file_data_url", lambda *a, **k: None):
        out = generate_prompt_via_ai(make_project("卖点A"), make_item(), effective_product_image="x.png")
    assert out["prompt_source"] == "ai", out
    assert "白色背景" in out["prompt"]
    assert "premium product photo" in out["prompt_en"]
    # 溯源留痕：正常 AI 路径必须带回输入描述与原始输出
    assert out["prompt_input"], "prompt_input 不应为空"
    assert "卖点A" in out["prompt_input"], "输入应含核心卖点"
    assert out["prompt_raw"], "prompt_raw 不应为空"
    assert "premium product photo" in out["prompt_raw"], "原始输出应含英文提示词"
    print("[OK] test_generate_prompt_happy_path")


# ── 1b. 市场配置必须进入 AI 输入（全局配置核心项） ──────────────

def test_market_config_in_ai_input():
    proj = make_project(
        selling_points="轻盈透气",
        market_config={"target_market": "北美", "platform": "Amazon", "audience": "健身人群"},
    )
    from app.gallery_prompt_ai import build_user_config_text

    text = build_user_config_text(proj, make_item("sport"))
    assert "市场配置" in text, "AI 输入应含【市场配置】段"
    assert "北美" in text and "Amazon" in text and "健身人群" in text, "市场配置值应进入输入"
    assert "【生成方向】" in text, "应明确告知模型要产出的类型"
    print("[OK] test_market_config_in_ai_input")


# ── 1c. 降级路径仍保留明确的输入/输出占位说明 ─────────────────

def test_fallback_keeps_trace_placeholder():
    # 注入假 key 走「AI 返回非 JSON → 重试失败 → 降级但保留溯源」路径
    with mock.patch.object(ai, "_get_ai_key", return_value="fake-key"), \
         _patch(chat_return="抱歉，我无法生成提示词。"):
        with mock.patch("app.gallery_prompt.build_prompt_bilingual",
                        lambda *a, **k: {"prompt": "模板中文", "prompt_en": "template en"}):
            out = generate_prompt_via_ai(make_project(), make_item(), effective_product_image="x.png")
    assert out["prompt_source"] == "template"
    assert out["prompt_input"], "降级也应保留喂给 AI 的输入（用户配置意图）"
    assert "生成方向" in out["prompt_input"], "降级输入应含用户配置"
    assert out["prompt_raw"] == "抱歉，我无法生成提示词。", "降级应保留最后一次 AI 原始返回"
    print("[OK] test_fallback_keeps_trace_placeholder")


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
    with _patch_settings(), _patch(chat_return=canned), \
         mock.patch("app.gallery_service._gallery_file_data_url", lambda *a, **k: None):
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
    with _patch_settings(), _patch(chat_return=canned), \
         mock.patch("app.gallery_service._gallery_file_data_url", lambda *a, **k: None):
        out = ai_write_type_config(make_project("卖点B"), "bg", {"personal_settings": {}, "common_settings": {}})
    assert out["common_settings"].get("visual_style") == "高级质感风"
    assert out["personal_settings"].get("背景") == "纯白"
    assert out["note"]
    print("[OK] test_ai_write_type_config")


# ── 4b. 自定义子任务不走 AI 改写（路由验证） ─────────────────

def test_custom_subtask_uses_original_text():
    """出图规划选「自定义子任务」时，应直接用用户原文，不调用 AI、不改写、不翻译。

    对应产品诉求：仅下拉选择的推荐类型才走 AI 改写；用户自由填写的自定义需求
    必须原样透传。"""
    from app.gallery_service import _build_prompt

    proj = make_project(selling_points="", market_config={})
    item = make_item("custom", personal={"自定义需求": "自由创作一张赛博朋克风格的产品海报"})
    out = _build_prompt(proj, item)
    assert out["prompt_source"] == "custom", "自定义子任务必须标记 prompt_source=custom"
    assert out["prompt"] == "自由创作一张赛博朋克风格的产品海报", "必须原样使用用户填写的需求"
    assert out["prompt_en"] == out["prompt"], "自定义子任务 prompt_en 同样用原文（不走 AI 翻译）"
    assert "自定义子任务" in out["prompt_input"], "溯源应标明这是自定义子任务原文"
    assert out["prompt_raw"] == "", "自定义子任务不调用 AI，prompt_raw 应为空"
    print("[OK] test_custom_subtask_uses_original_text")


# ── 5. 英文版零中文 ───────────────────────────────────────────

def test_strip_cjk():
    dirty = "premium product, 中文泄漏 should not appear, soft lighting"
    clean = _strip_cjk(dirty)
    assert "中文泄漏" not in clean
    assert "premium product" in clean
    # 规格参数图也不例外：prompt_en 必须纯英文（中文由后端叠加层渲染，避免乱码）
    assert "中文保留" not in _strip_cjk("premium, 中文保留", type_id="spec")
    print("[OK] test_strip_cjk")


def test_spec_data_in_user_config_text():
    """规格参数图的规格参数原文必须进入 AI 输入（作为后端叠加层数据，不进图像模型）。"""
    from app.gallery_prompt_ai import build_user_config_text

    proj = make_project()
    item = make_item("spec", personal={
        "产品品类": "服饰穿戴产品",
        "规格参数原文": "110码 衣长62 胸围72；120码 衣长67 胸围76",
    })
    text = build_user_config_text(proj, item)
    assert "规格参数图·渲染策略" in text, "应出现规格参数图渲染策略段（纯视觉图+后端叠加）"
    assert "110码 衣长62 胸围72" in text, "规格参数原文应进入 AI 输入（供叠加层）"
    assert "严禁" in text and "文字" in text, "应强调画面严禁文字"
    print("[OK] test_spec_data_in_user_config_text")


def test_spec_prompt_en_is_text_free():
    """规格参数图的 prompt_en 必须纯英文、不含任何中文（中文由后端叠加层渲染，避免乱码）。"""
    canned = (
        '```json\n{"prompt_cn": "规格参数图，纯视觉，右侧预留空白面板。", '
        '"prompt_en": "spec chart infographic, text-free visual, product on left, '
        'empty light-gray panel on right for back-end overlay, minimal guide lines, no text or numbers"}\n```'
    )
    with _patch_settings(), _patch(chat_return=canned), \
         mock.patch("app.gallery_service._gallery_file_data_url", lambda *a, **k: None):
        out = generate_prompt_via_ai(
            make_project(),
            make_item("spec", personal={
                "产品品类": "服饰穿戴产品",
                "规格参数原文": "110码 衣长62 胸围72",
            }),
            effective_product_image="x.png",
        )
    assert out["prompt_source"] == "ai", out
    # prompt_en 经 _strip_cjk 后必须完全无中文
    leaks = re.findall(r"[\u4e00-\u9fff]", out["prompt_en"])
    assert not leaks, f"spec 的 prompt_en 不应含中文（乱码风险）：{set(leaks)} | {out['prompt_en']}"
    print("[OK] test_spec_prompt_en_is_text_free")


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


# ── 1d. 出图规划项的「补充说明」必须传入 AI 输入（含溯源 prompt_input） ──

def test_note_flows_into_ai_input():
    note_text = "领口加宽更显脸小，主图突出刺绣工艺"
    # 直接校验喂给模型的用户意图文本包含补充说明
    from app.gallery_prompt_ai import build_user_config_text

    cfg_text = build_user_config_text(make_project("轻盈透气"), make_item("bg", note=note_text))
    assert "【补充说明】" in cfg_text, "AI 输入应含【补充说明】段"
    assert note_text in cfg_text, "补充说明原文应进入 AI 输入"
    # 端到端：generate_prompt_via_ai 的溯源 prompt_input 也必须含补充说明
    with _patch_settings(), _patch(chat_return='```json\n{"prompt_cn": "x", "prompt_en": "x"}\n```'), \
         mock.patch("app.gallery_service._gallery_file_data_url", lambda *a, **k: None):
        out = generate_prompt_via_ai(make_project("轻盈透气"), make_item("bg", note=note_text), effective_product_image="x.png")
    assert out["prompt_source"] == "ai"
    assert note_text in out["prompt_input"], "溯源 prompt_input 应含补充说明"
    print("[OK] test_note_flows_into_ai_input")


# ── 1e. 模板兜底路径同样把补充说明注入中文提示词（规格图英文版也注入） ──

def test_note_in_template_prompt():
    from app.gallery_prompt import build_prompt_bilingual

    note_text = "主图突出刺绣工艺与拼色设计"
    item = SimpleNamespace(
        type_id="bg", personal_settings={}, common_settings={},
        output_settings={}, note=note_text, reference_images=[], product_image="",
    )
    pd = build_prompt_bilingual(make_project(""), item)
    assert f"补充说明：{note_text}" in pd["prompt"], "模板中文提示词应含补充说明"

    # 规格参数图：英文生成版允许中文，补充说明也应注入
    spec_note = "尺码表用暖色调强调"
    spec_item = SimpleNamespace(
        type_id="spec", personal_settings={"产品品类": "服饰穿戴产品"},
        common_settings={}, output_settings={}, note=spec_note,
        reference_images=[], product_image="",
    )
    pd_spec = build_prompt_bilingual(make_project(""), spec_item)
    # 规格参数图的补充说明改由后端叠加层渲染，不进图像提示词（避免画面出现中文乱码）
    assert spec_note not in pd_spec["prompt_en"], "规格图英文版不应含补充说明（交由后端叠加层）"
    print("[OK] test_note_in_template_prompt")


# ── 1g. 单图多视角/多场景版式检测（拼贴/分屏/宫格命中） ──

def test_detect_multi_cell():
    """多视角/多场景版式检测：angle 类型与拼贴/分屏关键词应命中，普通类型返回 None。"""
    # angle 类型 → 多视角拼贴指令
    ang = make_item("angle", personal={"展示角度": "多角度拼接", "角度数量": "四个及以上角度（完整呈现）"})
    res = ai._detect_multi_cell(ang)
    assert res and "多视角拼贴" in res, "angle 类型应返回多视角拼贴指令"
    assert "四宫格" in res and "九宫格" in res, "应给出具体网格示例"

    # scene 类型选 四宫格场景拼接 → 多场景拼接指令
    sc = make_item("scene", personal={"排版呈现": "四宫格场景拼接"})
    res2 = ai._detect_multi_cell(sc)
    assert res2 and "多场景拼接" in res2, "四宫格场景拼接应返回多场景指令"

    # 左右分屏 → 命中多场景
    cmp_item = make_item("cmp", personal={"视觉呈现形式": "分屏左右对比"})
    res3 = ai._detect_multi_cell(cmp_item)
    assert res3 and "多场景" in res3, "分屏左右对比应命中多场景版式"

    # 产品主体+多场景
    sc2 = make_item("scene", personal={"排版呈现": "产品主体+多场景"})
    assert ai._detect_multi_cell(sc2) and "多场景" in ai._detect_multi_cell(sc2), "产品主体+多场景应命中"

    # 普通单场景主图 → None
    normal = make_item("bg", personal={"背景场景": "纯白色"})
    assert ai._detect_multi_cell(normal) is None, "普通单场景不应命中多格版式"
    print("[OK] test_detect_multi_cell")


def test_build_user_config_text_multi_cell():
    """单图多格版式指令必须进入 AI 输入（build_user_config_text）。"""
    from app.gallery_prompt_ai import build_user_config_text

    item = make_item("angle", personal={"展示角度": "多角度拼接", "角度数量": "三个角度（全面覆盖）"})
    text = build_user_config_text(make_project("轻盈透气"), item)
    assert "版式指令" in text, "AI 输入应含多格版式指令"
    assert "多视角拼贴" in text, "应注入多视角拼贴指令"
    assert "每一个格子" in text, "应要求逐格描述"
    print("[OK] test_build_user_config_text_multi_cell")


# ── 1f. 规格参数图后端文字叠加层：解析 + 合成（消除中文乱码） ──

def test_spec_overlay_parse_and_render():
    from PIL import Image
    from app.spec_overlay import parse_spec_data, overlay_spec_image, resolve_spec_font

    # 字体解析必须返回可用对象（simhei.ttf 已捆绑）
    font = resolve_spec_font(24)
    assert font is not None

    # 解析：多行尺码数据
    data = parse_spec_data("110码 衣长62 胸围72 腰围66；120码 衣长67 胸围76 腰围70")
    assert data["headers"][0] == "尺码"
    assert "衣长" in data["headers"] and "胸围" in data["headers"]
    assert len(data["rows"]) == 2
    assert data["rows"][0]["尺码"] == "110码"
    assert data["rows"][0]["衣长"] == "62"

    # 解析：无「码」字、纯数字开头也能识别尺码
    d2 = parse_spec_data("120 衣长67 胸围76")
    assert d2["rows"][0]["尺码"] == "120码"

    # 合成：纯内存渲染，输出 RGB 且尺寸不变
    base = Image.new("RGB", (1024, 1024), (200, 200, 200))
    out = overlay_spec_image(base, spec_text="110码 衣长62 胸围72", note="领口加宽", category="服饰穿戴产品")
    assert out.mode == "RGB"
    assert out.size == (1024, 1024)
    print("[OK] test_spec_overlay_parse_and_render")


def make_plan_item(item_id, type_id, personal=None, common=None, note="", output=None, reference_images=None, product_image=""):
    return SimpleNamespace(
        id=item_id,
        type_id=type_id,
        personal_settings=personal or {},
        common_settings=common or {},
        output_settings=output or {},
        note=note,
        reference_images=reference_images or [],
        product_image=product_image,
    )


# ── 2. 批量提示词生成（策略 A/B） ─────────────────────────────

def test_extract_json_array():
    raw = '```json\n[{"item_index": 0, "prompt_cn": "中文", "prompt_en": "english"}]\n```'
    out = ai._extract_json_array(raw)
    assert isinstance(out, list) and len(out) == 1
    assert out[0]["item_index"] == 0
    assert out[0]["prompt_en"] == "english"
    print("[OK] test_extract_json_array")


def test_batch_prompt_mode_1():
    """方案 A：单次 AI 调用为多个策划项返回 JSON 数组提示词。"""
    canned = (
        '```json\n'
        '[{"item_index": 0, "prompt_cn": "主图中文提示", "prompt_en": "main image english prompt"},'
        ' {"item_index": 1, "prompt_cn": "细节图中文提示", "prompt_en": "detail image english prompt"}]'
        '\n```'
    )
    item1 = make_plan_item(101, "bg")
    item2 = make_plan_item(102, "detail")
    meta = [
        {"item": item1, "title": "主图", "ratio": "1:1", "item_provider_id": 1, "item_model": "m1", "effective_product_image": "x.png", "size": "1024x1024", "ref_files": ["x.png"], "count": 1, "is_custom": False},
        {"item": item2, "title": "细节图", "ratio": "1:1", "item_provider_id": 1, "item_model": "m1", "effective_product_image": "x.png", "size": "1024x1024", "ref_files": ["x.png"], "count": 1, "is_custom": False},
    ]
    with _patch_settings(), _patch(chat_return=canned), \
         mock.patch("app.gallery_service._gallery_file_data_url", lambda *a, **k: None):
        out = ai.generate_prompts_batch_mode_1(make_project("轻盈透气"), meta)
    assert len(out) == 2
    assert out[101]["prompt_source"] == "ai"
    assert out[101]["prompt"] == "主图中文提示"
    assert out[101]["prompt_en"] == "main image english prompt"
    assert out[102]["prompt"] == "细节图中文提示"
    assert out[102]["prompt_en"] == "detail image english prompt"
    print("[OK] test_batch_prompt_mode_1")


def test_build_prompts_for_plan_custom():
    """自定义子任务在批量策略中仍走原样透传，不调用 AI。"""
    from app.gallery_service import _build_prompts_for_plan

    custom_item = make_plan_item(201, "bg", personal={"自定义需求": "我要红底图"})
    meta = [
        {"item": custom_item, "title": "自定义", "ratio": "1:1", "item_provider_id": 1, "item_model": "m1", "effective_product_image": "x.png", "size": "1024x1024", "ref_files": ["x.png"], "count": 1, "is_custom": True},
    ]
    out = _build_prompts_for_plan(make_project(""), meta)
    assert out[201]["prompt_source"] == "custom"
    assert out[201]["prompt"] == "我要红底图"
    assert out[201]["prompt_en"] == "我要红底图"
    print("[OK] test_build_prompts_for_plan_custom")


def test_build_prompts_for_plan_mode_2():
    """方案 B：并发并行调用，每 item 独立 AI 调用。"""
    from app.gallery_service import _build_prompts_for_plan

    prev = os.environ.get("AI_PROMPT_BATCH_MODE")
    os.environ["AI_PROMPT_BATCH_MODE"] = "2"
    try:
        canned = '```json\n{"prompt_cn": "中文提示", "prompt_en": "english prompt"}\n```'
        item1 = make_plan_item(301, "bg")
        item2 = make_plan_item(302, "detail")
        meta = [
            {"item": item1, "title": "主图", "ratio": "1:1", "item_provider_id": 1, "item_model": "m1", "effective_product_image": "x.png", "size": "1024x1024", "ref_files": ["x.png"], "count": 1, "is_custom": False},
            {"item": item2, "title": "细节图", "ratio": "1:1", "item_provider_id": 1, "item_model": "m1", "effective_product_image": "x.png", "size": "1024x1024", "ref_files": ["x.png"], "count": 1, "is_custom": False},
        ]
        with _patch_settings(), _patch(chat_return=canned), \
             mock.patch("app.gallery_service._gallery_file_data_url", lambda *a, **k: None):
            out = _build_prompts_for_plan(make_project("卖点"), meta)
        assert len(out) == 2
        assert out[301]["prompt_source"] == "ai"
        assert out[301]["prompt_en"] == "english prompt"
        assert out[302]["prompt_en"] == "english prompt"
    finally:
        if prev is None:
            os.environ.pop("AI_PROMPT_BATCH_MODE", None)
        else:
            os.environ["AI_PROMPT_BATCH_MODE"] = prev
    print("[OK] test_build_prompts_for_plan_mode_2")


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
