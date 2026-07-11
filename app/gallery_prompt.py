"""电商套图 · 提示词生成引擎（数据驱动 / 分层组装 / 单一事实源）。

把「配置 → 自然语言提示词」从 ``gallery_service._build_prompt`` 的字符串拼接，
升级为职责单一的工程化流水线：

    Resolver  ──►  CopyPolicy  ──►  Assembler  ──►  Linter
   配置归一化      文案策略决策      分层量化组装      矛盾/要素自检

设计要点：
- 配置与指令分离：市场 / 平台 / 风格的「视觉档案」沉淀在 ``gallery_config``，纯数据可落库。
- 优先级单一：market_config → common_settings → personal_settings（后者覆盖前者）。
- 文案策略唯一事实源：只有 ``CopyPolicy`` 决定「允许文字 / 零文字」，彻底消灭
  「允许文字」与「禁止文字」同时出现的历史矛盾。
- 抽象词量化：visual_style / tone / 个性化风格词经 ``STYLE_VOCAB`` 映射为可识别的视觉指令。
- 可测试：``Linter`` 在生成期拦截自相矛盾与缺要素的提示词。
"""
from __future__ import annotations

from app.gallery_config import (
    MARKET_PROFILES,
    PLATFORM_PROFILES,
    STYLE_VOCAB,
    COPY_ALLOWED_TYPES,
    VALUE_FOCUS_VOCAB,
    VALUE_HINT_VOCAB,
    GLOBAL_RETROUCH,
    get_plan_type,
    TYPE_LAYOUT,
)

# 兜底档案（配置缺失时回退，避免 KeyError）
_DEFAULT_MARKET = "全球"
_DEFAULT_PLATFORM: dict = {
    "composition": "居中清晰构图，主体突出，完整展示",
    "subject_ratio": "主体占画面约 65%，四周均匀留白",
    "resolution": "8K 超高清，商业精修，高锐度，无镜头畸变",
    "forbidden": "肢体畸形、局部裁切、杂乱背景、过重阴影、反光光斑",
}

# 个性化字段分类：归属到哪一段组装
_PRODUCT_LABELS = {"产品呈现", "价值聚焦", "服装品类"}
_STYLE_LABELS = {"视觉强化", "氛围浓度"}
# 人物判定：哪些类型本质关于人（强制人物），以及哪些个性化字段一旦填写即代表需要人物
_HUMAN_FORCED_TYPES = {"tryon", "model", "buyer"}
_HUMAN_SIGNAL_LABELS = {
    "人种肤色", "性别物种", "年龄维度", "身型身材",
    "穿着风格", "动作姿态", "表情神态",
}
# 有无人物都可使用的中性字段（场景/光影/角度），不触发人物注入
_SUBJECT_NEUTRAL_LABELS = {
    "场景环境", "背景处理", "光影效果", "产品角度",
}

# Linter 矛盾检测锚点
#   零文字约束锚点：提示词明确声明「画面中不得有任何文字」
#   允许文字锚点：提示词明确声明「仅允许按类型需求放置少量文案」
# 两者同时出现即自相矛盾；本引擎每个类型只输出其一，M6 的「禁止把配置写成图上文字」
# 属于窄约束（不与上述任一冲突），不计入。
_ZERO_TEXT_MARKERS = ("整张画面不出现任何文字", "不出现任何文字")
_ALLOW_COPY_MARKERS = ("仅允许按类型需求放置",)


# ─────────────────────────────────────────────────────────────
# 档案解析
# ─────────────────────────────────────────────────────────────

def _resolve_market(target_market: str | None) -> dict:
    return MARKET_PROFILES.get(target_market or "", MARKET_PROFILES.get(_DEFAULT_MARKET, {}))


def _resolve_platform(platform: str | None) -> dict:
    return PLATFORM_PROFILES.get(platform or "", _DEFAULT_PLATFORM)


# ─────────────────────────────────────────────────────────────
# ① Resolver：配置归一化
# ─────────────────────────────────────────────────────────────

def _resolve_config(project, item) -> dict:
    """优先级合并：market_config → common_settings（后者覆盖前者）。"""
    market = dict(project.market_config or {})
    cs = dict(item.common_settings or {})
    ps = dict(item.personal_settings or {})

    def pick(*keys: str):
        for k in keys:
            v = cs.get(k) or market.get(k)
            if v:
                return v
        return None

    target_market = pick("target_market")
    platform = pick("ecommerce_platform")
    visual_style = pick("visual_style")
    tone = pick("tone_tendency")
    copy_language = pick("copy_language")

    t = get_plan_type(item.type_id) or {}
    return {
        "type_id": item.type_id,
        "title": t.get("title", item.type_id),
        "target_market": target_market,
        "platform": platform,
        "visual_style": visual_style,
        "tone": tone,
        "copy_language": copy_language,
        "personal": ps,
        "selling_points": (project.selling_points or "").strip(),
        "note": (item.note or "").strip(),
        "has_reference": bool(item.product_image or item.reference_images),
    }


# ─────────────────────────────────────────────────────────────
# ② CopyPolicy：文案策略（单一事实源）
# ─────────────────────────────────────────────────────────────

def _decide_copy_policy(type_id: str, copy_language: str | None) -> dict:
    """全工程只有这一处决定「允许文字 / 零文字」。

    允许文字的类型（海报 / 卖点图）按类型需求放置少量版面文案；
    其余类型一律零文字，卖点仅以视觉元素体现。
    """
    return {
        "allow_text": type_id in COPY_ALLOWED_TYPES,
        "copy_language": copy_language or "英语",
    }


# ─────────────────────────────────────────────────────────────
# ③ Assembler：分层组装（M1-M6，优先级自上而下）
# ─────────────────────────────────────────────────────────────

def _wants_human(type_id: str, personal: dict) -> bool:
    """根据「类型 + 填写的个性化字段」决定是否在画面呈现人物。

    - 试穿/代言/买家秀 本质关于人 → 强制人物；
    - 其余类型默认无人物，仅当填写了人物信号字段（人种/性别/年龄/身型/穿着/
      动作/表情）时才出现人物。
    这样纯产品图（白底图/细节图/多角度…）不会再被市场档案强行塞入模特，
    根治「产品图也带人物构图」的问题。
    """
    if type_id in _HUMAN_FORCED_TYPES:
        return True
    return any(personal.get(l) for l in _HUMAN_SIGNAL_LABELS)


def _to_product_composition(text: str) -> str:
    """非人物场景：把构图/占比描述里的「人物」措辞改为「产品」，去掉站姿暗示。"""
    return (
        text.replace("产品 / 人物", "产品")
        .replace(" / 人物", "")
        .replace("人物主体", "产品主体")
        .replace("正面微侧约30°站姿，", "")
        .replace("居中全身构图", "居中产品构图")
        .replace("全身构图", "产品居中构图")
        .replace("人物", "")
    )


def _subject_fidelity_block(cfg: dict) -> str:
    """有参考图时的「主体一致性锚定」——解决「生成图与产品图不一致」的核心约束。

    参考图商品即画面唯一主体，外观须逐处一致；允许在角度 / 视距 / 背景 / 构图 /
    光影上做变化（用户要的多样性），但商品本身的身份（版型 / 颜色 / 图案 / logo）
    绝不可改变、替换或重新设计。
    人物类型（试穿 / 代言 / 买家秀）：所展示的商品须与参考图一致，人物仅作载体。
    """
    wants_human = _wants_human(cfg["type_id"], cfg["personal"])
    if wants_human:
        return (
            "参考图即本图要展示的商品：模特所穿着 / 手持 / 展示的商品必须与参考图"
            "该商品逐处一致——版型、轮廓、颜色、材质、图案纹理、logo 与标识、"
            "结构比例均不可改变；人物仅作展示载体，可变化姿态 / 人种 / 场景，但"
            "绝不得改变所展示的商品本身，也不得用其他近似款替代。"
            "注：本提示词中「色调倾向 / 配色参考 / 视觉强化」等关于配色的描述"
            "仅作用于背景与场景氛围，所展示商品的颜色、图案、logo 须严格以"
            "参考图该商品为准，不得套用上述配色改变商品颜色。"
        )
    return (
        "参考图即本图要展示的商品本体：画面主体必须严格以参考图商品为准，"
        "外观、版型、轮廓、颜色、材质、图案纹理、logo 与标识、结构比例"
        "逐处一致，不得改变、重新设计或用其他款替换。允许变化的仅限"
        "拍摄角度、视距（特写 / 全景）、背景与场景、构图方式、光影氛围与"
        "道具搭配——商品本身的外观身份必须保持不变。"
        "注：本提示词中「色调倾向 / 配色参考 / 视觉强化」等关于配色的描述"
        "仅作用于背景与场景氛围，商品本身的颜色、图案、logo 须严格以参考图"
        "为准，不得套用上述配色改变商品本体颜色。"
    )


def _dedupe(lines: list[str]) -> list[str]:
    """去除连续/非连续的完全重复行，避免同一句指令出现两次。"""
    seen: set[str] = set()
    out: list[str] = []
    for l in lines:
        s = l.strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(l)
    return out


def _assemble(cfg: dict, copy: dict, market: dict, platform: dict) -> str:
    lines: list[str] = []
    title = cfg["title"]
    wants_human = _wants_human(cfg["type_id"], cfg["personal"])

    # M1 基础商用规范（平台 / 市场 / 分辨率 / 修图）
    lines.append(f"为电商商品生成一张高质量的【{title}】主视觉图。")
    if cfg["has_reference"]:
        # 最强约束：参考图商品即主体，外观须逐处一致（紧接标题，权重最高）
        lines.append(_subject_fidelity_block(cfg))
    if cfg["platform"]:
        lines.append(f"适用电商平台：{cfg['platform']}。")
    if cfg["target_market"]:
        lines.append(f"目标市场与受众地域：{cfg['target_market']}。")
    lines.append(f"画质要求：{platform['resolution']}；{GLOBAL_RETROUCH}。")
    if cfg["platform"] and platform.get("composition"):
        comp = platform["composition"]
        ratio = platform.get("subject_ratio", "")
        if not wants_human:
            # 纯产品场景：净化构图/占比里的「人物」措辞，明确只展示产品
            comp = _to_product_composition(comp)
            ratio = _to_product_composition(ratio)
        lines.append(f"构图规范：{comp}；{ratio}。")
    # 逐类型版式差异化：让「类型」这个配置明显改变画面版式
    layout = TYPE_LAYOUT.get(cfg["type_id"])
    if layout:
        lines.append(f"版式要求：{layout}。")

    # M2 主体：人物 or 纯产品（由类型 + 填写字段决定）
    if wants_human and market.get("subject"):
        lines.append(f"主体人物要求：{market['subject']}。")
        for lbl, val in cfg["personal"].items():
            if lbl in _HUMAN_SIGNAL_LABELS and val:
                lines.append(f"{lbl}：{val}。")
    elif not wants_human:
        lines.append(
            "无人物：画面仅展示产品/主体本身，不出现任何真人、模特、代言人、"
            "人物剪影或手部出镜；主体完整清晰占画面主体。"
        )
    # 中性场景/光影字段：有无人物都可生效
    for lbl, val in cfg["personal"].items():
        if lbl in _SUBJECT_NEUTRAL_LABELS and val:
            lines.append(f"{lbl}：{val}。")
    if market.get("background"):
        lines.append(f"背景：{market['background']}。")
    if market.get("avoid"):
        lines.append(f"避免：{market['avoid']}。")

    # M3 服装 / 产品视觉表达（单一事实源：面料质感传递品质，绝不文字）
    cat = cfg["personal"].get("服装品类")
    if cat:
        lines.append(f"服装品类：{cat}（精准匹配类目版型，完整展示不遮挡核心剪裁）。")
    product_present = cfg["personal"].get("产品呈现")
    if product_present:
        lines.append(f"产品呈现：{product_present}（完整展示，不遮挡核心剪裁与版型）。")
    # 价值聚焦：视觉重心指令（与下方品质质感描述互补，不重复）
    vf = cfg["personal"].get("价值聚焦")
    if vf:
        mapped = VALUE_FOCUS_VOCAB.get(vf)
        lines.append(f"价值聚焦：{mapped}。" if mapped else f"价值聚焦：{vf}。")
    # 卖点：仅以视觉元素体现（允许文字的类型才放少量版面文案）
    sp = cfg["selling_points"]
    if sp and copy["allow_text"]:
        lines.append(
            f"核心卖点「{sp}」可将少量以精致版面文案呈现；其余卖点仍通过"
            f"构图、光影、色彩、材质、姿态等视觉元素体现，不堆砌文字。"
        )
    elif sp:
        lines.append(
            f"核心卖点「{sp}」仅用光、面料、人物姿态等视觉元素体现，"
            f"绝不转为图上文字。"
        )
    # 品质质感统一描述（整段 prompt 只出现一次，避免与价值暗示重复）
    if wants_human or cfg["personal"].get("服装品类"):
        craft = "服装面料垂坠肌理、立体缝线、柔和面料反光、细腻剪裁光影"
    else:
        craft = "产品材质肌理、工艺细节、柔和反光与精致光影"
    lines.append(
        f"产品价值仅通过{craft}等视觉细节传递高品质做工，"
        f"全程不使用任何文字标注卖点。"
    )
    # 价值暗示：除「品质细节」外（已由上句覆盖）才单独输出
    vh = cfg["personal"].get("价值暗示")
    if vh and vh != "品质细节":
        mapped = VALUE_HINT_VOCAB.get(vh)
        lines.append(f"价值暗示：{mapped}。" if mapped else f"价值暗示：{vh}。")

    # M4 视觉风格系统（抽象词量化映射）
    if cfg["visual_style"]:
        vs = STYLE_VOCAB.get(cfg["visual_style"], cfg["visual_style"])
        lines.append(f"整体视觉风格：{vs}。")
    if cfg["tone"]:
        tone_txt = STYLE_VOCAB.get(cfg["tone"], cfg["tone"])
        if market.get("palette"):
            if cfg["has_reference"]:
                # 有参考图：配色仅作用于背景，并摘掉“任选其一作为服装主色”
                # 之类的诱导从句，防止模型把商品重新染色（与主体一致性锚定冲突）
                pal_bg = market["palette"].split("（任选其一作为服装主色")[0].strip("，, ")
                lines.append(
                    f"背景配色倾向：{tone_txt}；背景配色参考{pal_bg}"
                    f"（此配色仅用于背景与场景氛围，商品颜色须严格以参考图为准，"
                    f"不得套用）。"
                )
            else:
                # 市场调色板无条件注入，换市场即换配色（不再卡「高饱和」）
                lines.append(f"色调倾向：{tone_txt}；配色参考{market['palette']}。")
        else:
            lines.append(f"色调倾向：{tone_txt}。")
    for lbl, val in cfg["personal"].items():
        if lbl in _STYLE_LABELS and val:
            vocab = STYLE_VOCAB.get(val)
            lines.append(f"{lbl}：{vocab}。" if vocab else f"{lbl}：{val}。")

    # M5 文字 / 水印约束（统一唯一，绝不出现「允许」与「禁止」并存）
    if copy["allow_text"]:
        lines.append(
            f"画面文案：仅允许按类型需求放置少量精心设计的版面文案"
            f"（语种：{copy['copy_language']}）；除此之外严禁任何其他文字、"
            f"字母、数字、LOGO、水印或标签。"
        )
    else:
        lines.append(
            "文字约束：整张画面不出现任何文字、字母、数字、LOGO、水印、"
            "品牌名、价格、促销标语或标签；不将本提示词的需求、卖点、参数"
            "以文字形式呈现在画面中。"
        )

    # M6 绝对禁止清单（汇总一处，不重复）
    forbid = platform.get("forbidden", "")
    tail = "绝对禁止：" + (forbid + "；" if forbid else "")
    tail += (
        "以及把本提示词配置项 / 卖点 / 个性化要求写成图上文字、"
        "将参考图文字复制到生成图。"
    )
    if cfg["has_reference"]:
        tail += (
            "参考图上的水印 / 价格签 / 背景文字 / 无关标签请忽略，不要复制到生成图；"
            "但参考图中的商品本体须严格还原，不得因忽略其上文字而改变商品外观。"
            "绝对禁止改变商品外观 / 版型 / 颜色 / 图案 / logo，禁止用其他近似产品"
            "替代参考图商品。"
        )
    lines.append(tail)

    # 补充说明（如有）
    if cfg["note"]:
        lines.append(f"补充说明：{cfg['note']}。")

    # 通用收尾
    lines.append(
        "构图完整、主体突出、细节清晰、商业级质感，符合电商平台规范与大众审美。"
    )
    return " ".join(_dedupe(lines))


# ─────────────────────────────────────────────────────────────
# ④ Linter：矛盾检测 + 策略一致性断言
# ─────────────────────────────────────────────────────────────

def _lint(prompt: str, allow_text: bool) -> None:
    has_zero = any(m in prompt for m in _ZERO_TEXT_MARKERS)
    has_allow = any(m in prompt for m in _ALLOW_COPY_MARKERS)
    if has_zero and has_allow:
        raise ValueError(
            "提示词自相矛盾：同时出现零文字约束与允许文字约束。"
            "请检查 CopyPolicy 决策逻辑。"
        )
    if allow_text and not has_allow:
        raise ValueError("提示词校验失败：允许文字的类型未输出文案许可约束。")
    if (not allow_text) and not has_zero:
        raise ValueError("提示词校验失败：零文字类型缺少绝对禁止文字约束。")


# ─────────────────────────────────────────────────────────────
# 对外入口
# ─────────────────────────────────────────────────────────────

def build_prompt(project, item, model_name: str | None = None) -> str:
    """根据项目 / 条目配置组装分层、量化、无矛盾的图片生成提示词。

    ``model_name`` 保留仅为向后兼容签名，引擎内部不再使用。
    """
    cfg = _resolve_config(project, item)
    copy = _decide_copy_policy(cfg["type_id"], cfg["copy_language"])
    market = _resolve_market(cfg["target_market"])
    platform = _resolve_platform(cfg["platform"])
    prompt = _assemble(cfg, copy, market, platform)
    _lint(prompt, copy["allow_text"])
    return prompt
