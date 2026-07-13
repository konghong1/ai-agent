"""提示词生成引擎 · 单元测试 + 可执行校验脚本。

运行方式（无需 pytest 依赖）：
    python tests/test_gallery_prompt.py

若环境已装 pytest，也可：
    python -m pytest tests/test_gallery_prompt.py -q
"""
from __future__ import annotations

import os
import sys
import types

# 让 `from app...` 可被直接执行时发现
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.gallery_prompt import build_prompt, _lint  # noqa: E402


# ── 测试用假对象（仅携带引擎需要的属性） ──────────────────────────

def _make_project(market_config: dict, selling_points: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(market_config=market_config, selling_points=selling_points)


def _make_item(
    type_id: str,
    personal_settings: dict | None = None,
    common_settings: dict | None = None,
    note: str = "",
    product_image: str = "",
    reference_images: list | None = None,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        type_id=type_id,
        personal_settings=personal_settings or {},
        common_settings=common_settings or {},
        note=note,
        product_image=product_image,
        reference_images=reference_images or [],
        output_settings={},
    )


# ── 测试用例 ──────────────────────────────────────────────────────

def test_middle_east_hero_zero_text():
    """中东 + 首屏视觉图：应零文字、含市场 palette、平台构图，且无矛盾。"""
    project = _make_project(
        market_config={
            "target_market": "中东",
            "ecommerce_platform": "淘宝 / 天猫",
            "visual_style": "高级质感风",
            "tone_tendency": "高饱和色调",
        },
        selling_points="年轻女性模特，纤细手臂直角肩，全身，干净背景，不展示产品信息",
    )
    item = _make_item(
        "hero",
        personal_settings={
            "价值聚焦": "品质",
            "视觉强化": "色彩冲击",
            "产品呈现": "整体形态",
            "氛围浓度": "轻度氛围",
            "价值暗示": "品质细节",
            "人种肤色": "中东暖调健康肤色",  # 触发人物（否则 hero 默认无人物）
        },
    )
    prompt = build_prompt(project, item)

    # 市场档案适配
    assert "中东" in prompt, "应含中东市场主体要求"
    assert "暖金" in prompt and "焦糖橙" in prompt and "宝石蓝" in prompt, "高饱和色调应注入中东 palette"
    # 平台规范
    assert "居中全身构图" in prompt, "应含淘宝/天猫构图规范（人物场景）"
    assert "65%" in prompt, "应含主体占比"
    assert "8K" in prompt, "应含画质参数"
    # 零文字策略
    assert "整张画面不出现任何文字" in prompt, "零文字类型必须含绝对禁止文字约束"
    assert "绝不转为图上文字" in prompt, "卖点应仅为视觉体现"
    # 矛盾检查：不允许出现「允许文字」分支
    assert "仅允许按类型需求放置" not in prompt, "零文字类型不得出现允许文字分支"
    assert "画面文案需求" not in prompt, "不得残留 copy_need 式矛盾表述"
    print("[PASS] test_middle_east_hero_zero_text")


def test_promo_allows_copy():
    """活动海报：允许按类型需求放置少量版面文案，且无零文字广约束。"""
    project = _make_project(
        market_config={"target_market": "全球", "ecommerce_platform": "淘宝 / 天猫"},
    )
    item = _make_item("promo")
    prompt = build_prompt(project, item)

    assert "仅允许按类型需求放置" in prompt, "海报应允许少量版面文案"
    assert "整张画面不出现任何文字" not in prompt, "允许文字类型不得含零文字广约束"
    print("[PASS] test_promo_allows_copy")


def test_selling_points_visual_not_on_image():
    """卖点绝不以「画面文案需求」形式出现，仅以视觉指令承载。"""
    sp = "年轻女性，纤细手臂直角肩，全身入镜，干净背景"
    project = _make_project(
        market_config={"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫"},
        selling_points=sp,
    )
    item = _make_item("hero")
    prompt = build_prompt(project, item)

    assert sp in prompt, "卖点文本应出现在提示词中"
    assert "核心卖点" in prompt and "绝不转为图上文字" in prompt, "卖点应包裹为视觉体现指令"
    assert "画面文案需求" not in prompt, "卖点不得作为图上文字需求"
    print("[PASS] test_selling_points_visual_not_on_image")


def test_subject_personal_injected():
    """试穿试戴类型的主体个性化字段应进入提示词（M2）。"""
    project = _make_project(market_config={"target_market": "北美", "ecommerce_platform": "亚马逊"})
    item = _make_item(
        "tryon",
        personal_settings={"人种肤色": "亚洲", "性别物种": "女性", "身型身材": "标准"},
    )
    prompt = build_prompt(project, item)
    assert "亚洲" in prompt and "女性" in prompt and "标准" in prompt, "主体个性化字段应落地"
    print("[PASS] test_subject_personal_injected")


def test_linter_catches_contradiction():
    """Linter 必须拦截「零文字 + 允许文字」并存的自相矛盾提示词。"""
    bad = "整张画面不出现任何文字。仅允许按类型需求放置少量文案。"
    raised = False
    try:
        _lint(bad, allow_text=False)
    except ValueError:
        raised = True
    assert raised, "Linter 应拦截自相矛盾提示词"
    print("[PASS] test_linter_catches_contradiction")


def test_config_change_produces_different_prompt():
    """关键回归：配置选择不同时，生成的提示词必须明显不同。

    直接回应「配置选择不同时基本生成的图基本没啥变化」——
    引擎必须把市场/风格/色调/个性化选项的差异，显著注入提示词。
    """
    base_mk = {"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫",
               "visual_style": "高级质感风", "tone_tendency": "高饱和色调"}
    base_personal = {"服装品类": "连衣裙", "价值聚焦": "品质", "视觉强化": "质感放大",
                     "产品呈现": "整体形态", "氛围浓度": "轻度氛围", "价值暗示": "品质细节"}

    p_a = _make_project(dict(base_mk), selling_points="高质量服装")
    i_a = _make_item("hero", personal_settings=dict(base_personal))
    prompt_a = build_prompt(p_a, i_a)

    # 仅改：视觉风格 + 色调 + 服装品类 + 价值聚焦 + 价值暗示 + 产品呈现 + 氛围浓度
    p_b = _make_project(
        {"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫",
         "visual_style": "科技未来感", "tone_tendency": "暗黑酷感"},
        selling_points="高质量服装",
    )
    i_b = _make_item("hero", personal_settings={
        "服装品类": "套装", "价值聚焦": "设计", "视觉强化": "色彩冲击",
        "产品呈现": "局部特写", "氛围浓度": "强氛围", "价值暗示": "稀有材料"})
    prompt_b = build_prompt(p_b, i_b)

    # 仅改：色调倾向（高饱和→低饱和）+ 服装品类 + 价值聚焦
    p_c = _make_project(
        {"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫",
         "visual_style": "高级质感风", "tone_tendency": "低饱和高级灰"},
        selling_points="高质量服装",
    )
    i_c = _make_item("hero", personal_settings={
        "服装品类": "上衣", "价值聚焦": "功能", "视觉强化": "质感放大",
        "产品呈现": "整体形态", "氛围浓度": "轻度氛围", "价值暗示": "品质细节"})
    prompt_c = build_prompt(p_c, i_c)

    assert prompt_a != prompt_b, "视觉风格/色调/个性化全改后 prompt 必须不同"
    assert prompt_a != prompt_c, "仅改色调倾向+品类+聚焦后 prompt 必须不同"
    # 不同选项必须各自落地到 prompt（证明差异是真实的，不是随机噪声）
    assert "冷调硬光" in prompt_b and "暗调背景" in prompt_b, "科技未来/暗黑酷感应落地"
    assert "低饱和度高级灰调" in prompt_c, "低饱和色调应落地且不同于高饱和"
    assert "视觉重心聚焦设计美学与结构巧思" in prompt_b, "价值聚焦=设计应落地"
    assert "视觉重心聚焦产品功能与使用场景" in prompt_c, "价值聚焦=功能应落地"
    print("[PASS] test_config_change_produces_different_prompt")


def test_no_redundant_quality_line():
    """关键回归：分桶结构下品质维度只出现一次，且 4 个 V8 维度词各落地一次、不重复。"""
    project = _make_project(
        {"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫",
         "visual_style": "高级质感风", "tone_tendency": "高饱和色调"},
        selling_points="高品质服装",
    )
    item = _make_item("hero", personal_settings={
        "价值聚焦": "品质", "视觉强化": "质感放大", "产品呈现": "整体形态",
        "氛围浓度": "轻度氛围", "价值暗示": "品质细节"})
    prompt = build_prompt(project, item)

    # 画质要求（分辨率+修图）只出现一次，不重复
    assert prompt.count("画质要求：") == 1, "画质要求行不应重复出现"
    # 4 个 V8 维度词各落地一次（分桶后互不重复）
    assert prompt.count("价值聚焦：") == 1, "价值聚焦应落地且仅一次"
    assert prompt.count("视觉强化：") == 1, "视觉强化应落地且仅一次"
    assert prompt.count("氛围浓度：") == 1, "氛围浓度应落地且仅一次"
    assert prompt.count("价值暗示：") == 1, "价值暗示应落地且仅一次"
    print("[PASS] test_no_redundant_quality_line")


def test_missing_constraints_present():
    """中东市场 + 人物信号：应补齐中东合规（遮盖肩颈）、平台构图（30°站姿）、
    修图规范（色彩真实还原），且 V9 真实维度（价值聚焦）落地。"""
    project = _make_project(
        {"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫",
         "visual_style": "高级质感风", "tone_tendency": "高饱和色调"})
    item = _make_item("hero", personal_settings={"人种肤色": "中东暖调", "价值聚焦": "品质"})
    prompt = build_prompt(project, item)

    assert "服装完整遮盖肩颈" in prompt, "应补齐中东合规：遮盖肩颈"
    assert "所展示商品色彩1:1真实还原" in prompt, "应补齐修图规范：色彩真实还原"
    assert "正面微侧约30°" in prompt, "应补齐具象站姿"
    assert "画面主体人物：" in prompt, "人物信号应注入人物主体描述"
    assert "中东暖调" in prompt, "中东人种肤色应落地"
    assert "价值聚焦：视觉重心聚焦面料质感与精细做工" in prompt, "价值聚焦=品质 应落地（分桶后语义映射）"
    print("[PASS] test_missing_constraints_present")


def test_v9_real_settings_injected():
    """V9 回归：SeeAny 真实设置项应 1:1 落地到提示词（语义模板驱动，非裸值）。"""
    project = _make_project(market_config={"target_market": "北美", "ecommerce_platform": "亚马逊"})

    # 商品主图：摆放状态 / 拍摄角度 / 有无模特
    p_bg = build_prompt(project, _make_item("bg", personal_settings={
        "摆放状态": "斜放", "拍摄角度": "俯视", "有无模特": "无模特平铺展示"}))
    assert "产品摆放形态：斜放。" in p_bg, "摆放状态 应经语义模板注入"
    assert "拍摄机位角度：俯视。" in p_bg, "拍摄角度 应经语义模板注入"
    assert "无人物" in p_bg, "纯产品类型不得出现人物"

    # 产品多角度：展示角度 / 角度数量 / 背景场景
    p_angle = build_prompt(project, _make_item("angle", personal_settings={
        "展示角度": "45度角", "角度数量": "三个角度（全面覆盖）", "背景场景": "纯白色"}))
    assert "展示视角：45度角。" in p_angle, "展示角度 应落地"
    assert "多视角数量：三个角度（全面覆盖）。" in p_angle, "角度数量 应落地"
    assert "背景与场景：纯白色。" in p_angle, "背景场景 应落地"

    # 场景图：场景类型 / 氛围营造
    p_scene = build_prompt(project, _make_item("scene", personal_settings={
        "场景类型": "居家空间", "氛围营造": "简约高级风"}))
    assert "使用场景：居家空间。" in p_scene, "场景类型 应落地"
    assert "画面氛围营造：简约高级风。" in p_scene, "氛围营造 应落地"

    # 试穿试戴：人物信号 + 展示排版 / 场景类型
    p_tryon = build_prompt(project, _make_item("tryon", personal_settings={
        "人种肤色": "亚洲", "性别物种": "女性", "展示排版": "全身穿搭全景", "场景类型": "日常通勤场景"}))
    assert "画面主体人物：" in p_tryon, "人物信号应注入人物主体描述"
    assert "人物展示排版：全身穿搭全景。" in p_tryon, "展示排版 应落地"
    assert "使用场景：日常通勤场景。" in p_tryon, "场景类型 应落地"

    # 痛点图：痛点方向 / 对比方式
    p_pain = build_prompt(project, _make_item("pain", personal_settings={
        "痛点方向": "功能缺失痛点", "对比方式": "使用前后对比"}))
    assert "营销痛点切入：功能缺失痛点。" in p_pain, "痛点方向 应落地"
    assert "对比手法：使用前后对比。" in p_pain, "对比方式 应落地"

    print("[PASS] test_v9_real_settings_injected")


def test_product_type_has_no_human():
    """关键回归：纯产品类型（白底图）不得被强行塞入人物构图。

    直接回应「生成的图总带人物构图」——未填写人物字段的产品类型应明确无人物，
    且构图措辞净化掉「人物」。
    """
    project = _make_project(
        market_config={"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫"},
    )
    item = _make_item("bg", personal_settings={"产品角度": "正视角"})
    prompt = build_prompt(project, item)

    assert "无人物" in prompt, "纯产品类型必须声明无人物"
    assert "主体人物要求" not in prompt, "纯产品类型不得注入市场人物要求"
    assert "居中产品构图" in prompt, "构图措辞应净化掉「人物」"
    assert "版式要求" in prompt and "纯白背景" in prompt, "应注入逐类型版式"
    print("[PASS] test_product_type_has_no_human")


def test_human_type_with_fields():
    """填写人物字段的 hero 仍应注入人物要求。"""
    project = _make_project(
        market_config={"target_market": "北美", "ecommerce_platform": "淘宝 / 天猫"},
    )
    item = _make_item("hero", personal_settings={"人种肤色": "亚洲", "动作姿态": "自然站立"})
    prompt = build_prompt(project, item)

    assert "画面主体人物：" in prompt, "填写人物字段应注入人物主体描述"
    assert "无人物" not in prompt, "有人物字段时不得声明无人物"
    assert "亚洲" in prompt and "自然站立" in prompt, "人物个性化字段应落地"
    print("[PASS] test_human_type_with_fields")


def test_palette_injected_for_any_tone():
    """关键回归：场景类类型（hero）的市场调色板随色调无条件注入，换市场即换配色。

    注意：纯白底类型（bg 等）背景已锁定纯白，不再注入彩色调色板——这是预期行为，
    因此本测试改用场景类 hero 验证调色板注入逻辑。
    """
    project = _make_project(
        market_config={"target_market": "北美", "ecommerce_platform": "淘宝 / 天猫",
                       "tone_tendency": "低饱和高级灰"},
    )
    item = _make_item("hero")
    prompt = build_prompt(project, item)

    assert "配色参考" in prompt, "场景类市场调色板应随色调无条件注入（出现「配色参考」标记）"
    assert "明亮清晰" in prompt or "自然色系" in prompt, "应注入北美市场调色板文本"
    print("[PASS] test_palette_injected_for_any_tone")


def test_type_layout_differentiation():
    """关键回归：不同「类型」配置应产生明显不同的版式指令。"""
    project = _make_project(market_config={"target_market": "全球", "ecommerce_platform": "淘宝 / 天猫"})
    p_bg = build_prompt(project, _make_item("bg"))
    p_detail = build_prompt(project, _make_item("detail"))
    p_cmp = build_prompt(project, _make_item("cmp"))

    assert p_bg != p_detail != p_cmp, "不同类型版式指令必须不同"
    assert "纯白背景，产品居中正面展示" in p_bg, "白底图版式应落地"
    assert "超大特写镜头" in p_detail, "细节特写版式应落地"
    assert "左右分屏对比" in p_cmp, "对比图版式应落地"
    print("[PASS] test_type_layout_differentiation")


def test_reference_fidelity_product():
    """关键回归：有参考图的产品图必须「主体一致锚定」——参考图商品即主体，
    外观逐处一致，仅允许角度/背景/构图/光影变化，禁止改变商品本身。

    直接回应「首屏视觉图生成结果与产品图完全不一致」。"""
    project = _make_project(
        market_config={"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫",
                       "visual_style": "高级质感风", "tone_tendency": "高饱和色调"},
    )
    item = _make_item("hero", product_image="prod_001.png",
                      personal_settings={"产品角度": "正视角"})
    prompt = build_prompt(project, item)

    # 锚定核心断言
    assert "参考图即本图要展示的商品本体" in prompt, "有参考图必须注入主体一致性锚定"
    assert "逐处一致" in prompt, "必须要求参考图商品外观逐处一致"
    assert "不得改变" in prompt or "不得用其他款替换" in prompt, "必须禁止改变/替换商品"
    # 允许的多样性维度（用户要的变化）
    assert "拍摄角度" in prompt and "背景与场景" in prompt and "构图方式" in prompt, \
        "应明示允许角度/背景/构图变化"
    # 绝对禁止清单里也须含商品保真负向约束
    assert "不得因忽略其上文字而改变商品外观" in prompt, "M6 禁止清单须含商品保真约束"
    print("[PASS] test_reference_fidelity_product")


def test_reference_fidelity_human():
    """有参考图的人物类型（试穿）：所展示商品须与参考图一致，人物仅作载体。"""
    project = _make_project(
        market_config={"target_market": "北美", "ecommerce_platform": "淘宝 / 天猫"},
    )
    item = _make_item("tryon", product_image="prod_002.png",
                      personal_settings={"人种肤色": "亚洲", "动作姿态": "自然站立"})
    prompt = build_prompt(project, item)

    assert "模特所穿着" in prompt, "人物类型须锚定「模特所展示商品」与参考图一致"
    assert "与参考图该商品逐处一致" in prompt, "所展示商品须与参考图逐处一致"
    assert "绝不得改变所展示的商品本身" in prompt, "禁止改变所展示的商品"
    print("[PASS] test_reference_fidelity_human")


def test_reference_color_not_recolored():
    """关键回归：有参考图时，商品颜色必须以参考图为准，绝不被市场配色重新染色。

    直接回应「生成的图形状一样、颜色不一样」——中东 palette 自带
    「（任选其一作为服装主色）」诱导从句，有参考图时必须摘掉并改为「背景配色」，
    否则模型会把商品重新染成色板里的某一色。
    """
    project = _make_project(
        market_config={"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫",
                       "visual_style": "高级质感风", "tone_tendency": "高饱和色调"},
    )
    item = _make_item("hero", product_image="prod_001.png",
                      personal_settings={"服装品类": "上衣", "视觉强化": "色彩冲击"})
    prompt = build_prompt(project, item)

    # 配色被重定向为「背景配色」，且明确商品颜色以参考图为准
    assert "背景配色参考" in prompt, "有参考图时配色应改为仅作用于背景"
    assert "商品颜色严格以参考图为准" in prompt, "必须声明商品颜色以参考图为准"
    assert "不得套用" in prompt, "必须禁止把背景配色套用到商品"
    # 原来诱导重新染色的从句必须被摘掉
    assert "任选其一作为服装主色" not in prompt, "有参考图时必须摘掉「任选其一作为服装主色」诱导"
    # 主体一致性锚定仍在
    assert "参考图即本图要展示的商品本体" in prompt
    print("[PASS] test_reference_color_not_recolored")


def test_no_reference_no_fidelity_block():
    """无参考图时不应注入「参考图即主体」锚定（避免误导模型去找不存在的参考）。"""
    project = _make_project(
        market_config={"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫"},
    )
    item = _make_item("hero", product_image="", reference_images=[])
    prompt = build_prompt(project, item)

    assert "参考图即本图要展示的商品本体" not in prompt, "无参考图不得注入参考锚定"
    assert "绝对禁止改变商品外观" not in prompt, "无参考图不得注入商品保真负向约束"
    print("[PASS] test_no_reference_no_fidelity_block")


def test_all_plan_types_no_contradiction():
    """遍历全部策划类型，引擎产出均不应抛异常（矛盾/缺要素自检通过）。"""
    project = _make_project(
        market_config={"target_market": "中东", "ecommerce_platform": "淘宝 / 天猫",
                        "visual_style": "高级质感风", "tone_tendency": "高饱和色调"},
        selling_points="高品质服装",
    )
    from app.gallery_config import get_plan_type
    for t in ["bg", "amz", "detail", "angle", "hero", "usp", "pain", "scene",
              "detail2", "tryon", "model", "design", "cmp", "ship", "spec",
              "pkg", "buyer", "promo", "custom"]:
        assert get_plan_type(t), f"类型 {t} 应在配置中存在"
        item = _make_item(t, personal_settings={"氛围浓度": "轻度氛围", "视觉强化": "色彩冲击"})
        _ = build_prompt(project, item)  # 若自相矛盾/Linter 失败会抛异常
    print("[PASS] test_all_plan_types_no_contradiction")


# ── 直接运行入口（无需 pytest） ──────────────────────────────────

def _run_all() -> None:
    test_middle_east_hero_zero_text()
    test_promo_allows_copy()
    test_selling_points_visual_not_on_image()
    test_subject_personal_injected()
    test_linter_catches_contradiction()
    test_all_plan_types_no_contradiction()
    test_config_change_produces_different_prompt()
    test_no_redundant_quality_line()
    test_missing_constraints_present()
    test_v9_real_settings_injected()
    test_product_type_has_no_human()
    test_human_type_with_fields()
    test_palette_injected_for_any_tone()
    test_type_layout_differentiation()
    test_reference_fidelity_product()
    test_reference_fidelity_human()
    test_reference_color_not_recolored()
    test_no_reference_no_fidelity_block()
    print("\nALL TESTS PASSED ✅")


if __name__ == "__main__":
    _run_all()
