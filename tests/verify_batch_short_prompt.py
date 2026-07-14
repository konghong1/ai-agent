"""验证批量提示词引擎的两处改动（不依赖真实大模型 / 数据库）：

1) build_batch_user_config_text 不再对每个出图方向重复「要求：...」笼统指令，
   改为结尾一次性【综合提示词要求】，并要求模型额外产出最简短场景提示词
   (prompt_cn_short / prompt_en_short)。
2) generate_prompts_batch_mode_1 能正确解析并回传 short 字段。

运行：python tests/verify_batch_short_prompt.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.gallery_prompt_ai as gpa


class FakeItem:
    def __init__(self, type_id, item_id=None, personal=None, common=None, note=""):
        self.type_id = type_id
        self.id = item_id
        self.personal_settings = personal or {}
        self.common_settings = common or {}
        self.note = note


class FakeProject:
    selling_points = ""
    market_config = {}
    images = []


def test_build_text_refactor():
    meta = [
        {
            "item": FakeItem("bg", personal={"场景环境": "客厅"}, common={"visual_style": "简约"}),
            "ratio": "1:1",
            "effective_product_image": None,
        },
        {
            "item": FakeItem("detail", personal={"细节特写": "缝线"}, common={}),
            "ratio": "1:1",
            "effective_product_image": None,
        },
    ]
    text = gpa.build_batch_user_config_text(FakeProject(), meta)

    # 1) 每个方向后不再重复「要求：基于该类型和上述配置...」
    assert "要求：基于该类型和上述配置，写出贴合该方向的差异化提示词" not in text, (
        "仍存在逐方向重复的笼统指令（应移除，改为结尾统一说明）"
    )
    # 2) 结尾存在【综合提示词要求】综合指令
    assert "【综合提示词要求】" in text, "缺少结尾【综合提示词要求】综合指令"
    # 3) 综合指令要求产出最简短场景提示词
    assert "prompt_cn_short" in text and "prompt_en_short" in text, (
        "综合指令未要求产出最简短场景提示词 (prompt_cn_short / prompt_en_short)"
    )
    # 4) 综合指令明确「不再对每个方向重复」——确认只出现一次综合段
    assert text.count("【综合提示词要求】") == 1, "综合提示词要求段应仅出现一次"
    print("PASS: build_batch_user_config_text 已重构（去逐方向重复 + 综合指令 + 最短提示词）")


def test_parse_short_fields():
    canned = (
        "["
        '{"item_index":0,"prompt_cn":"完整中文0","prompt_en":"full english 0",'
        '"prompt_cn_short":"短中文0","prompt_en_short":"short en 0"},'
        '{"item_index":1,"prompt_cn":"完整中文1","prompt_en":"full english 1",'
        '"prompt_cn_short":"短中文1","prompt_en_short":"short en 1"}'
        "]"
    )
    # 用 monkeypatch 替代真实大模型调用与密钥检查，避免触碰网络 / openai 依赖
    original_key = gpa._get_ai_key
    original_run = gpa._run_async

    def _fake_run(coro):
        # 关闭被传入但未执行的协程，避免 RuntimeWarning
        if coro is not None and hasattr(coro, "close"):
            coro.close()
        return canned

    gpa._get_ai_key = lambda: "test-key"
    gpa._run_async = _fake_run
    try:
        meta = [
            {"item": FakeItem("bg", item_id=101), "effective_product_image": None, "ratio": "1:1"},
            {"item": FakeItem("detail", item_id=102), "effective_product_image": None, "ratio": "1:1"},
        ]
        results = gpa.generate_prompts_batch_mode_1(FakeProject(), meta)
    finally:
        gpa._get_ai_key = original_key
        gpa._run_async = original_run

    assert 101 in results and 102 in results, f"解析结果缺失 item：{list(results.keys())}"
    assert results[101]["prompt_short"] == "短中文0", results[101]
    assert results[101]["prompt_en_short"] == "short en 0", results[101]
    assert results[102]["prompt_short"] == "短中文1", results[102]
    assert results[102]["prompt_en_short"] == "short en 1", results[102]
    # short 字段应作为独立键随结果返回，供生成阶段优先使用
    assert "prompt_en_short" in results[101], "结果缺少 prompt_en_short 键"
    print("PASS: generate_prompts_batch_mode_1 正确解析并回传 short 字段")


def test_parse_short_fallback_when_model_omits():
    """真实场景下模型可能不返回 short 字段（已观测到 prompt_raw 无 short）。
    验证解析层兜底：从完整版提炼，保证 prompt_en_short 非空，出图降本逻辑生效。
    """
    canned = (
        "["
        '{"item_index":0,"prompt_cn":"主体为浅蓝针织上衣，搭配条纹披肩，纯白褶裙；场景为浅米色背景；'
        '光影为顶部柔光；画质为8K；风格为日韩甜美。","prompt_en":"light blue knit top, striped shawl, '
        'white ruffle skirt, soft top light, 8K, korean sweet style"}'
        "]"
    )
    original_key = gpa._get_ai_key
    original_run = gpa._run_async

    def _fake_run(coro):
        if coro is not None and hasattr(coro, "close"):
            coro.close()
        return canned

    gpa._get_ai_key = lambda: "test-key"
    gpa._run_async = _fake_run
    try:
        meta = [{"item": FakeItem("bg", item_id=201), "effective_product_image": None, "ratio": "1:1"}]
        results = gpa.generate_prompts_batch_mode_1(FakeProject(), meta)
    finally:
        gpa._get_ai_key = original_key
        gpa._run_async = original_run

    assert 201 in results, f"解析结果缺失 item：{list(results.keys())}"
    # 模型未返回 short → 兜底提炼，必须非空且为 prompt_en 的前几个短语
    short_en = results[201]["prompt_en_short"]
    assert short_en, "模型未返回 short 时，兜底应产出非空 prompt_en_short"
    assert "light blue knit top" in short_en, f"兜底 short 应保留主体短语：{short_en}"
    print("PASS: 模型省略 short 字段时，后端兜底提炼生效 (prompt_en_short=%r)" % short_en)


if __name__ == "__main__":
    test_build_text_refactor()
    test_parse_short_fields()
    test_parse_short_fallback_when_model_omits()
    print("\nRESULT: PASS")
