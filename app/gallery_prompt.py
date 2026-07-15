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

import re

from app.gallery_config import (
    MARKET_PROFILES,
    PLATFORM_PROFILES,
    STYLE_VOCAB,
    HUMAN_STYLE_VOCAB,
    COPY_ALLOWED_TYPES,
    VALUE_FOCUS_VOCAB,
    VALUE_HINT_VOCAB,
    PRODUCT_PRESENT_VOCAB,
    GLOBAL_RETROUCH,
    RETOUCH_NO_HUMAN,
    SETTING_TEMPLATE,
    TYPE_PERSONAL,
    TYPE_SEMANTICS,
    TYPE_CAMERA,
    get_plan_type,
    TYPE_LAYOUT,
    BUCKET_ORDER,
    BUCKET_TITLE,
    BUCKET_ROUTING,
    COPY_LABELS,
    QUALITY_BOOSTERS,
    NEGATIVE_BASE,
    RATIO_FORMAT,
    # 英文版提示词资产
    MARKET_PROFILES_EN,
    PLATFORM_PROFILES_EN,
    STYLE_VOCAB_EN,
    HUMAN_STYLE_VOCAB_EN,
    VALUE_FOCUS_VOCAB_EN,
    VALUE_HINT_VOCAB_EN,
    PRODUCT_PRESENT_VOCAB_EN,
    FABRIC_VOCAB_EN,
    CRAFT_VOCAB_EN,
    SETTING_TEMPLATE_EN,
    TYPE_LAYOUT_EN,
    TYPE_CAMERA_EN,
    NEGATIVE_BASE_EN,
    QUALITY_BOOSTERS_EN,
    RATIO_FORMAT_EN,
    GLOBAL_RETROUCH_EN,
    RETOUCH_NO_HUMAN_EN,
    WHITE_TECH_EN,
    OPTIONS_EN,
)

# V8 转化维度词 → 语义 VOCAB 映射（避免裸值输出，保留专业视觉表达）
_DIM_VOCAB = {
    "价值聚焦": VALUE_FOCUS_VOCAB,
    "视觉强化": STYLE_VOCAB,
    "氛围浓度": STYLE_VOCAB,
    "价值暗示": VALUE_HINT_VOCAB,
}

# 兜底档案（配置缺失时回退，避免 KeyError）
_DEFAULT_MARKET = "全球"
_DEFAULT_PLATFORM: dict = {
    "composition": "centered clear composition, subject prominent, complete display",
    "subject_ratio": "subject fills about 65%, even margins around",
    "resolution": "8K ultra HD, commercial retouch, high sharpness, no lens distortion",
    "forbidden": "limb deformity, partial crop, cluttered background, heavy shadows, reflection spots",
}

# 个性化字段分类（V8 电商转化视角）
# 所有类型统一收敛到 5 个转化维度：价值聚焦 / 视觉强化 / 产品呈现 / 氛围浓度 / 价值暗示
# 另保留少量「类型辅助字段」和「旧数据兼容字段」。

# V8 核心转化维度
_CORE_DIMENSIONS = {"价值聚焦", "视觉强化", "产品呈现", "氛围浓度", "价值暗示"}
# M4 视觉风格字段（用于遍历个人设置中的风格词）
_STYLE_LABELS = {"视觉强化", "氛围浓度", "视觉氛围", "情绪基调"}
# 辅助字段（直接输出，不触发人物）
_AUXILIARY_LABELS = {"背景处理", "光影质感", "展示逻辑", "自定义需求"}
# 旧数据兼容字段（仍映射为视觉指令）
_COMPAT_LABELS = {"面料质感", "工艺细节", "展示方式", "场景环境", "互动形式", "构图方式", "情感传递", "产品融入度"}

# 人物判定：试穿/代言/买家秀 本质关于人 → 强制人物；
# V8 不再要求用户填 8 个人物参数，人物基础描述由 target_market 市场档案提供。
_HUMAN_FORCED_TYPES = {"tryon", "model", "buyer"}
# 历史字段兼容：若旧数据仍有人物信号字段，仍触发人物
# V9 扩展：加入 SeeAny 代言类型(tryon/model)的人物描述字段（性别风格/年龄特点）
_HUMAN_SIGNAL_LABELS = {
    "人种肤色", "性别物种", "性别风格", "年龄维度", "年龄特点", "身型身材",
    "穿着风格", "动作姿态", "表情神态",
}
# 有无人物都可使用的中性字段（场景/光影/角度/互动/构图），不触发人物注入
_SUBJECT_NEUTRAL_LABELS = {
    "场景环境", "光影效果", "产品角度",
    "互动形式", "构图方式", "情感传递", "产品融入度",
}
# V8 已显式处理的标签全集（M3 前部分支已消费，M3.5 兜底跳过）
_V8_HANDLED = (
    _CORE_DIMENSIONS | _AUXILIARY_LABELS | _COMPAT_LABELS |
    _SUBJECT_NEUTRAL_LABELS |
    {"服装品类", "面料质感", "工艺细节", "展示方式", "场景环境", "互动形式", "构图方式", "情感传递", "产品融入度"}
)
# M2/M3/M4 已显式处理的标签全集——通用兜底跳过这些，避免重复注入。
# 含 V9 全部 SeeAny 真实设置项（从 TYPE_PERSONAL 动态收集），保证不被兜底重复注入。
_EXPLICITLY_HANDLED = set(_V8_HANDLED | _HUMAN_SIGNAL_LABELS)
for _flds in TYPE_PERSONAL.values():
    for _f in _flds:
        _EXPLICITLY_HANDLED.add(_f["label"])

# Linter 矛盾检测锚点
#   零文字约束锚点：提示词明确声明「画面中不得有任何文字」
#   允许文字锚点：提示词明确声明「仅允许按类型需求放置少量文案」
# 两者同时出现即自相矛盾；本引擎每个类型只输出其一，M6 的「禁止把配置写成图上文字」
# 属于窄约束（不与上述任一冲突），不计入。
_ZERO_TEXT_MARKERS = ("整张画面不出现任何文字", "不出现任何文字")
_ALLOW_COPY_MARKERS = ("仅允许按类型需求放置",)


# ── 单图多视角 / 多场景 / 拼贴 / 分屏 版式检测（与 AI 引擎口径一致） ──
_MULTI_CELL_KEYWORDS = [
    "拼接", "拼贴", "宫格", "分屏", "多场景", "多视角", "多角度", "多细节",
    "组合", "collage", "grid", "九宫格", "四宫格", "田字格", "左右对比", "上下对比",
    "主场景配辅", "产品主体+多场景", "产品不同状态", "不同时间季节",
    "同一人物不同场景", "不同人物同一场景", "多个细节", "局部细节拼接",
    "两个角度", "三个角度", "四个及以上角度", "环绕", "多面旋转",
]
_MULTI_CELL_RE = re.compile("|".join(re.escape(k) for k in _MULTI_CELL_KEYWORDS), re.IGNORECASE)


def _detect_multi_cell_type(cfg: dict) -> str | None:
    """检测配置是否为「单图多格」版式，返回 'angle' / 'scene' / None。

    与 AI 引擎 ``gallery_prompt_ai._detect_multi_cell`` 判定口径一致，
    保证降级路径与 AI 路径对多视角/多场景的指令风格统一。
    """
    type_id = cfg.get("type_id")
    ps = cfg.get("personal") or {}
    haystack = " ".join(str(v) for v in ps.values())
    is_angle = type_id == "angle"
    if not (is_angle or _MULTI_CELL_RE.search(haystack)):
        return None
    if is_angle or ("角度" in haystack or "视角" in haystack or "拼贴" in haystack or "环绕" in haystack):
        return "angle"
    return "scene"


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

def _resolve_config(project, item, effective_product_image: str | None = None) -> dict:
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
    # 参考图判定：以运行时实际使用的参考文件为准（含项目产品图回退），
    # 避免「传了参考图但提示词没写主体一致性约束」导致生成图与产品无关。
    has_reference = bool(
        item.product_image or item.reference_images or effective_product_image
    )
    # 输出比例：仅当用户明确选择非自适应时才注入提示词
    ratio = (item.output_settings or {}).get("ratio") or "自适应尺寸"
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
        "ratio": ratio,
        "has_reference": has_reference,
    }


# ─────────────────────────────────────────────────────────────
# ② CopyPolicy：文案策略（单一事实源）
# ─────────────────────────────────────────────────────────────

def _decide_copy_policy(type_id: str, copy_language: str | None) -> dict:
    """全工程只有这一处决定「允许文字 / 零文字」。

    允许文字的类型（海报 / 卖点图）按类型需求放置少量版面文案；
    其余类型一律零文字，卖点仅以视觉元素体现。
    规格参数图采用「纯视觉图 + 后端文字叠加」，画面严禁任何文字，
    因此强制 allow_text=False（中文尺码表/标注由后端叠加层渲染）。
    """
    if type_id == "spec":
        return {"allow_text": False, "copy_language": copy_language or "英语"}
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


# 产品呈现中「暗示人物」的选项（PRODUCT_PRESENT_VOCAB 的键）。
# 当类型语义禁止人物时，这些选项会被降级为「平铺展示」，避免「无人物 + 真人穿着」冲突。
_PERSON_PRESENT_VALUES = {"穿着效果", "手持/佩戴"}


def _resolve_person(type_id: str, personal: dict, sem: dict) -> bool:
    """由类型语义档案决定画面是否出人物，优先级高于用户误选的个性化字段。

    - forced   : 试穿/代言/买家秀，必然有人物；
    - forbidden: 白底图/纯产品图，绝不出现人物（即便误选「真人穿着」也降级）；
    - optional : 仅在填写了人物信号字段（人种/性别/年龄…）时才出人物。
    """
    mode = (sem or {}).get("person", "optional")
    if mode == "forced":
        return True
    if mode == "forbidden":
        return False
    return _wants_human(type_id, personal)


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
    """有参考图时的「主体一致性锚定 + 颜色锁定」——解决「生成图与产品图不一致」的核心约束。

    V5 重构：把颜色锁定从 M4 的「补救式」前移到 M1 紧接标题处，作为最强优先指令。
    明确告诉模型：商品颜色、图案、logo = 参考图 = 唯一事实源；
    配色 / 色调 = 背景维度 = 不得作用于商品本体。

    人物类型（试穿 / 代言 / 买家秀）：所展示的商品须与参考图一致，人物仅作载体。
    """
    wants_human = _wants_human(cfg["type_id"], cfg["personal"])
    if wants_human:
        return (
            "参考图即本图要展示的商品：模特所穿着 / 手持 / "
            "展示的商品必须与参考图该商品逐处一致——版型、轮廓、颜色、材质、图案纹理、"
            "logo 与标识、结构比例均不可改变。商品颜色严格以参考图为准，本提示词中所有"
            "关于「色调 / 配色 / 色系」的描述仅作用于背景与场景氛围，绝不改变商品本体"
            "的颜色、图案或 logo。人物仅作展示载体，可变化姿态 / 人种 / 场景，但绝不得"
            "改变所展示的商品本身，也不得用其他近似款替代。"
        )
    return (
        "参考图即本图要展示的商品本体：画面主体必须严格以"
        "参考图商品为准，外观、版型、轮廓、颜色、材质、图案纹理、logo 与标识、"
        "结构比例逐处一致，不得改变、重新设计或用其他款替换。商品颜色严格以参考图"
        "为准——本提示词中所有关于「色调 / 配色 / 色系」的描述仅作用于背景与场景"
        "氛围，绝不改变商品本体的颜色、图案或 logo。允许变化的仅限拍摄角度、视距"
        "（特写 / 全景）、背景与场景、构图方式、光影氛围与道具搭配——商品本身的"
        "外观身份与颜色必须保持不变。"
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
    """视觉分桶组装（V13 精简）：按电商 8 大创作维度，输出连续流动、无分桶标题的精炼提示词。

    维度顺序（仅保留与本次配置相关的维度，无关省略）：
      画面基础定位 → 主体（参考图一致性） → 人物（仅人物类型） → 场景环境
      → 色彩调性 → 画风/相机/画质 → 附加商业元素
    末尾补：正向增强约束（零/允许文字锚点，供 Linter 校验） + 负面约束单行。

    - 86 个配置项经 BUCKET_ROUTING 路由进 8 个分桶，提示词随用户选择实时变化。
    - 强约束（颜色锁定 / 文字禁止 / 参考图一致性）只出现一次；矛盾被消解。
    - 不再输出【分桶标题】，破除模板腔，8 维内容直接空格拼接为流动段落。
    - 白底类比例跟随 output_settings.ratio（RATIO_FORMAT），「自适应尺寸」按参考图比例，
      不再写死 1:1，也不任由模型默认出方形图。
    """
    type_id = cfg["type_id"]
    sem = TYPE_SEMANTICS.get(type_id, {"bg_mode": "scene", "person": "optional",
                                       "tech": {}, "medium": "商业产品摄影"})
    bg_mode = sem.get("bg_mode", "scene")
    tech = sem.get("tech", {})
    medium = sem.get("medium", "商业产品摄影")
    plat = sem.get("platform_override") or cfg["platform"]
    wants_human = _resolve_person(type_id, cfg["personal"], sem)
    title = cfg["title"]
    ps = cfg["personal"]
    has_ref = cfg["has_reference"]
    sp = cfg["selling_points"]

    buckets: dict[str, list[str]] = {k: [] for k in BUCKET_ORDER}

    # ── 【画面基础定位】用途/版式 + 比例 + 景别视角 + 构图 ──
    found: list[str] = [f"电商{title}核心展示："]
    if plat:
        found.append(f"适用电商平台：{plat}。")
    if cfg["target_market"]:
        found.append(f"目标市场与受众地域：{cfg['target_market']}。")
    layout = TYPE_LAYOUT.get(type_id)
    if bg_mode == "white":
        found.append("居中产品构图，完整展示商品版型，四周均匀留白。")
        specs = []
        if cfg["ratio"] == "自适应尺寸":
            specs.append("按参考图比例自适应构图：输出图必须保持与参考图完全一致的宽高比例，禁止裁剪、拉伸或填充为其他比例")
        else:
            fmt = RATIO_FORMAT.get(cfg["ratio"], None)
            if fmt:
                specs.append(fmt)
        specs.append(tech.get("product_ratio", "主体占画面≥85%"))
        specs.append(tech.get("min_px", "最小边长≥1000px"))
        found.append("；".join(specs) + "。")
        if layout:
            found.append(f"版式要求：{layout}。")
    elif bg_mode == "neutral":
        found.append("居中产品构图，浅灰纯色背景，四周均匀留白。")
        if layout:
            found.append(f"版式要求：{layout}。")
    else:
        comp = platform.get("composition")
        ratio = platform.get("subject_ratio", "")
        if comp:
            if not wants_human:
                comp = _to_product_composition(comp)
                ratio = _to_product_composition(ratio)
            found.append(f"构图规范：{comp}；{ratio}。")
        if layout:
            found.append(f"版式要求：{layout}。")
        fmt = RATIO_FORMAT.get(cfg.get("ratio"), None)
        if fmt:
            found.append(f"画面比例：{fmt}。")
    buckets["FOUNDATION"] = found + buckets["FOUNDATION"]

    # ── 【核心商品主体】参考图一致性 + 产品呈现 + 核心卖点 + 无人物 ──
    # 品类/材质/颜色/细节等逐 label 字段由下方路由循环注入 SUBJECT 桶
    subj: list[str] = []
    if has_ref:
        subj.append(_subject_fidelity_block(cfg))
    # 产品呈现（禁止人物的类型若误选「真人穿着」降级为平铺展示）
    display = ps.get("产品呈现")
    if display:
        if not wants_human and display in _PERSON_PRESENT_VALUES:
            display = "平铺展示"
        mapped = PRODUCT_PRESENT_VOCAB.get(display)
        subj.append(f"产品呈现：{mapped}。" if mapped else f"产品呈现：{display}。")
    # 核心卖点（视觉化重点，零文字类型绝不以图上文字呈现）
    if sp:
        if copy["allow_text"]:
            subj.append(
                f"核心卖点：「{sp}」以精致版面文案呈现（语种：{copy['copy_language']}），"
                f"位置不喧宾夺主，与视觉主体协调。"
            )
        else:
            subj.append(
                f"核心卖点：「{sp}」须作为画面视觉重点，通过构图重心、材质特写、"
                f"光影强化、使用场景等视觉语言重点突出，绝不转为图上文字、字母、数字或标签。"
            )
    if not wants_human:
        subj.append("无人物：画面仅展示产品/主体本身，不出现任何真人、模特、人物剪影或手部出镜。")
    buckets["SUBJECT"] = subj + buckets["SUBJECT"]

    # ── 【人物/模特】（仅人物类型 / 填写了人物字段）──
    # 人物基础描述由 target_market 市场档案提供；逐 label 人物字段由路由循环注入 PERSON 桶
    person: list[str] = []
    if wants_human and market.get("subject"):
        person.append(f"画面主体人物：{market['subject']}。")
    buckets["PERSON"] = person + buckets["PERSON"]

    # ── 其余配置项按 BUCKET_ROUTING 路由 ──
    skip_labels = set()
    for lbl, val in ps.items():
        if not val:
            continue
        if lbl in skip_labels:
            continue
        # 已在【核心商品主体】合成的部分直接跳过
        if lbl == "产品呈现":
            continue
        # 禁止人物的类型：出镜方式（有无模特）若含人物描述会与「无人物」冲突
        if lbl == "有无模特" and not wants_human:
            continue
        # 禁止人物的类型：人物类 label 一律跳过，避免与「无人物」矛盾
        if not wants_human and BUCKET_ROUTING.get(lbl) == "PERSON":
            continue
        # 纯文案 label 仅允许文字的类型才进入【附加商业元素】，否则跳过（避免文字矛盾）
        if lbl in COPY_LABELS:
            if copy["allow_text"]:
                tpl = SETTING_TEMPLATE.get(lbl)
                buckets["POSTER"].append(tpl.format(v=val) if tpl else f"{lbl}：{val}。")
            continue
        # 转化维度词需经语义 VOCAB 映射（不裸输出）
        if lbl in _DIM_VOCAB:
            vocab = _DIM_VOCAB[lbl].get(val)
            buckets[BUCKET_ROUTING[lbl]].append(f"{lbl}：{vocab}。" if vocab else f"{lbl}：{val}。")
            continue
        bucket_key = BUCKET_ROUTING.get(lbl)
        if not bucket_key:
            continue
        tpl = SETTING_TEMPLATE.get(lbl)
        buckets[bucket_key].append(tpl.format(v=val) if tpl else f"{lbl}：{val}。")

    # 强化用户明确选择的拍摄角度与比例：避免模型在后续渲染中「丢失」这些关键指令
    if ps.get("拍摄角度"):
        buckets["FOUNDATION"].append(
            f"视角强制约束：画面必须严格呈现「{ps['拍摄角度']}」视角，相机机位与透视关系不得擅自改为正面、平视或仰拍。"
        )
    if cfg["ratio"] == "自适应尺寸":
        buckets["FOUNDATION"].append(
            "比例强制约束：输出图必须严格保持与参考图完全一致的宽高比例，禁止裁剪、拉伸、填充或改变构图比例。"
        )

    # ── 【场景环境】白底 / 中性 / 实景 + 道具，按类型语义权威约束消解自相矛盾 ──
    if bg_mode == "white":
        _bg_line = tech.get("bg") or "纯白背景（RGB 255,255,255），无场景、无道具、无额外装饰。"
        buckets["SCENE"] = [_bg_line] + buckets["SCENE"]
    elif bg_mode == "neutral":
        _bg_line = "浅灰 / 纯色极简背景，无杂乱道具与场景。"
        buckets["SCENE"] = [_bg_line] + buckets["SCENE"]
    else:  # scene：允许生活化场景 + 市场调色板
        if market.get("background") and not buckets["SCENE"]:
            buckets["SCENE"].append(f"背景：{market['background']}。")
        if market.get("avoid"):
            buckets["SCENE"].append(f"避免：{market['avoid']}。")

    # ── 【色彩调性】色调倾向 + 市场配色（参考图存在时仅作用于背景）──
    if bg_mode == "white":
        buckets["COLOR"] = ["色调：纯色背景不额外施加任何彩色色调，保持干净通透。"] + buckets["COLOR"]
    elif bg_mode == "neutral":
        buckets["COLOR"] = ["色调：保持中性低饱和，不施加高饱和彩色。"] + buckets["COLOR"]
    else:
        # 用户已显式选择「色调倾向」时，路由循环已注入 COLOR 桶，这里不再重复生成（避免冗余）
        _tone_injected = any("色调倾向" in ln for ln in buckets["COLOR"])
        tone = cfg["tone"]
        if tone and not _tone_injected:
            tone_txt = STYLE_VOCAB.get(tone, tone)
            if market.get("palette"):
                if has_ref:
                    buckets["COLOR"].append(
                        f"背景色调：{tone_txt}；背景配色参考{market['palette']}"
                        f"（此配色仅用于背景与场景氛围，商品颜色严格以参考图为准，不得套用）。"
                    )
                else:
                    buckets["COLOR"].append(f"色调倾向：{tone_txt}；配色参考{market['palette']}。")
            else:
                buckets["COLOR"].append(f"色调倾向：{tone_txt}。")

    # ── 【画风·相机·画质】相机镜头 + 画质参数 + 整体视觉风格 + 渲染媒介 ──
    cam: list[str] = []
    # 未选择相机/特写类字段时，白底/产品图用轻量描述，避免塞入未配置的镜头型号
    camera_selected = any(ps.get(l) for l in ("特写部位", "对焦方式", "拍摄距离", "视角"))
    if wants_human or camera_selected or type_id not in {"amz", "bg"}:
        cam.append(f"拍摄设备与镜头：{TYPE_CAMERA.get(type_id, '商业产品摄影，标准器材布光')}。")
    else:
        cam.append("拍摄设备与镜头：商业产品摄影，标准棚拍布光，高分辨率无畸变。")
    retouch = GLOBAL_RETROUCH if wants_human else RETOUCH_NO_HUMAN
    cam.append(f"画质要求：{platform['resolution']}；{retouch}。")
    if cfg["visual_style"]:
        vs = (HUMAN_STYLE_VOCAB if wants_human else STYLE_VOCAB).get(cfg["visual_style"], cfg["visual_style"])
        cam.append(f"整体视觉风格：{vs}。")
    cam.append(f"渲染媒介：{medium}。")
    # 路由循环已把特写部位/对焦方式/视角等 CAMERA 标签追加入 buckets["CAMERA"]
    buckets["CAMERA"] = cam + buckets["CAMERA"]

    # ── 组装为精炼流动提示词（按 8 维顺序拼接，去分桶标题，破除模板腔）──
    # 维度顺序：画面基础定位 → 主体 → 人物 → 场景 → 色彩 → 画质 → 附加商业元素
    lines: list[str] = []
    for key in BUCKET_ORDER:
        for ln in _dedupe(buckets.get(key, [])):
            if ln and ln.strip():
                lines.append(ln)

    # 规格参数图：产品视觉为主 + 后端文字叠加（画面严禁任何文字）
    # 策略：overlay 会替换右侧约40%为自有面板，所以 AI 必须把产品画大画完整
    if type_id == "spec":
        is_apparel = ps.get("产品品类") == "服饰穿戴产品"
        spec_parts: list[str] = [f"画面类型为「{title}」专业电商信息图（纯视觉，画面不出现任何文字）："]
        spec_parts.append(
            "产品大而清晰、占画面 70-75% 面积，居中或略偏左；完整展示产品全貌（服饰需显示整套），细节清晰可见、不被裁切或挤压到边缘；"
        )
        spec_parts.append(
            "浅灰（#F5F5F7）纯色背景，干净的棚拍光线，柔和自然阴影，高级目录品质；"
        )
        if is_apparel:
            # 允许优雅的测量引导线（无线条上的文字）——像真实规格参数图那样专业
            spec_parts.append(
                "产品周围可带优雅的细测量指示线+箭头（左侧竖向长度箭头、胸部/腰部横向宽度箭头、袖子斜向箭头）——仅干净线条，线上绝对无文字/数字/标签；"
            )
            spec_parts.append(
                "可附带极淡的儿童人体轮廓剪影作为穿着比例参考（同样无文字）；"
            )
        else:
            spec_parts.append(
                "产品周围可带淡淡的双向箭头尺寸标注线（高/宽/深方向）——仅线条、无文字标签；"
            )
        spec_parts.append("整体为高端电商规格参数表风格，排版干净专业；")
        spec_parts.append("再次强调：画面中绝对不要出现任何文字、数字、字母、表格、水印或价格标签。")
        lines.append(" ".join(spec_parts))

    # 对比类（使用对比图 / 客户痛点展示）：左右分屏，两屏均锚定上传参考图商品
    if type_id in {"cmp", "pain"}:
        cmp_parts: list[str] = [
            "左右分屏对比信息图，中间以细分割线分隔；",
            "左、右两个分屏都必须是上传参考图中的同一款商品（颜色、材质、图案、logo、结构完全一致），绝不可用近似或通用产品替代；",
            "两屏仅在场景、使用状态、环境或语境上不同，商品本身始终保持一致；",
        ]
        if type_id == "cmp":
            cmp_parts.append(
                "左屏为「使用前 / 普通款 / 竞品」状态，右屏为「使用后 / 本产品优势」状态，对比直观一目了然；"
            )
        else:  # pain：左痛点右方案
            cmp_parts.append(
                "左屏呈现客户痛点（不便、杂乱、不适、低效）的生活化场景，右屏呈现同一款产品解决问题后的状态；"
            )
        if has_ref:
            cmp_parts.append(
                "两个分屏中的商品都必须与参考图严格一致，不得改变其颜色/图案/logo，也不得替换成其他产品；"
            )
        cmp_parts.append("两屏光影与背景色调统一，干净电商对比风格。")
        lines.append(" ".join(cmp_parts))

    # 用户补充说明（出图规划项里自由填写的额外方向，作为补充约束注入提示词）
    # 规格参数图的补充说明改由后端叠加层渲染，不进图像提示词（避免画面出现中文）
    note = (cfg.get("note") or "").strip()
    if note and type_id != "spec":
        lines.append(f"补充说明：{note}")

    # 单图多视角/多场景：在单图内逐格描述不同场景/角度（拼贴/分屏/宫格版式）
    mc = _detect_multi_cell_type(cfg)
    if mc == "angle":
        lines.append(
            "整图采用产品多角度拼贴版式：在单张画面内按网格或环绕排列产品的多个视角"
            "（如正面/侧面/背面/45°/俯视/细节特写），为每一格写明该视角的主体、细节、"
            "构图与光影，产品外观跨格严格一致、仅视角与光影变化，格间以细线或留白分隔。"
        )
    elif mc == "scene":
        lines.append(
            "整图采用多场景拼接版式：在单张画面内按网格（如四宫格/九宫格/左右分屏/上下分屏）"
            "拼接多个使用场景，为每一格写明该场景的环境、主体状态、构图视角与光影质感，"
            "各格场景明显不同、产品外观跨格一致，格间以细线或留白分隔，整图光影统一。"
        )

    # 正向增强 + 约束（精简，全部为正向词；保留零/允许文字锚点供 Linter 校验）保留零/允许文字锚点供 Linter 校验）
    if copy["allow_text"]:
        lines.append(
            f"仅允许按类型需求放置少量精心设计的版面文案（语种：{copy['copy_language']}），"
            f"其余严禁任何文字、字母、数字、LOGO、水印或标签。"
        )
    else:
        lines.append(
            "整张画面不出现任何文字、字母、数字、LOGO、水印、品牌名、价格或标签；"
            "不将需求、卖点、参数以文字形式呈现（no text, no watermark, no logo）。"
        )
    if has_ref:
        lines.append(
            "参考图上的水印/价格签/背景文字/尺寸标注/测量线/标注箭头请全部忽略不复制，"
            "但商品本体须严格还原，不得因忽略其上文字而改变商品外观；"
            "绝对禁止改变商品颜色/图案/版型/logo，禁止用其他近似产品替代参考图商品，"
            "商品颜色始终以参考图为唯一标准。"
        )
    lines.append("构图完整、主体突出、细节清晰、商业级质感，符合电商平台规范。")

    # 负面约束（压缩为一行，保留三维度关键词：商品瑕疵 / 人像崩坏 / 画面问题）
    neg_items: list[str] = []
    for dim, items in NEGATIVE_BASE.items():
        its = list(items)
        if dim == "人像崩坏" and not wants_human:
            its += ["人物", "模特", "人物剪影", "手部出镜"]
        neg_items += its
    lines.append("避免：" + "、".join(neg_items) + "。")

    return " ".join(lines).strip()

def _join_blocks(blocks: list[tuple[str, list[str]]]) -> str:
    """将分段块拼接为最终提示词：段内去重、段间空行分隔，提升模型解析清晰度。"""
    out: list[str] = []
    for title, lines in blocks:
        body = " ".join(_dedupe(lines)).strip()
        if not body:
            continue
        out.append(f"{title}\n{body}" if title else body)
    return "\n\n".join(out)


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

def build_prompt(project, item, model_name: str | None = None, effective_product_image: str | None = None) -> str:
    """根据项目 / 条目配置组装分层、量化、无矛盾的图片生成提示词。

    ``model_name`` 保留仅为向后兼容签名，引擎内部不再使用。
    ``effective_product_image`` 用于提示词内参考图一致性判定，解决运行时回退到
    项目产品图但提示词未感知的问题。
    """
    cfg = _resolve_config(project, item, effective_product_image=effective_product_image)
    copy = _decide_copy_policy(cfg["type_id"], cfg["copy_language"])
    market = _resolve_market(cfg["target_market"])
    platform = _resolve_platform(cfg["platform"])
    prompt = _assemble(cfg, copy, market, platform)
    _lint(prompt, copy["allow_text"])
    return prompt


# ─────────────────────────────────────────────────────────────
# 英文版紧凑提示词生成器（V13 · 供图片模型直接消费）
# 目标：短小、精准、配置相关性强，优先把「类型 + 用户选择」放在句首。
# ─────────────────────────────────────────────────────────────

def _t(v: str | None) -> str:
    """把中文选项值翻译成英文；无命中时原样返回。"""
    if not v:
        return ""
    return OPTIONS_EN.get(v, v)


def _type_opening_en(cfg: dict, sem: dict, platform_en: dict) -> str:
    """英文提示词最强句首：类型 + 平台/市场，尽可能短。"""
    type_id = cfg["type_id"]
    title = OPTIONS_EN.get(cfg["title"], cfg["title"])
    layout = TYPE_LAYOUT_EN.get(type_id, "")
    ps = cfg["personal"]

    # 角度类：单张图内呈现产品多个视角
    if type_id == "angle":
        return f"Product multi-angle collage for {platform_en.get('name', 'e-commerce')}. {layout}"

    if type_id in {"bg", "amz", "detail", "detail2"}:
        return f"{title} for {platform_en.get('name', 'e-commerce')}. {layout}"

    if type_id in {"tryon", "model", "buyer"}:
        return f"{title} for {platform_en.get('name', 'e-commerce')}. {layout}"

    if type_id == "promo":
        theme = _t(ps.get("主题定位", ""))
        return f"{title} for {platform_en.get('name', 'e-commerce')}{', ' + theme if theme else ''}. {layout}"

    return f"{title} for {platform_en.get('name', 'e-commerce')}. {layout}"


def _subject_fidelity_en(cfg: dict) -> str:
    """有参考图时的紧凑主体一致性约束。"""
    if not cfg["has_reference"]:
        return ""
    wants_human = _wants_human(cfg["type_id"], cfg["personal"])
    if wants_human:
        return (
            "Product worn/held/displayed must exactly match reference in color, material, "
            "pattern, logo and structure. Only pose, angle, lighting and background may change."
        )
    return (
        "Product must exactly match reference in color, material, pattern, logo and structure. "
        "Only angle, distance, background and lighting may change."
    )


def _market_subject_en(cfg: dict, market_en: dict) -> str:
    """人物类型的人物档案（英文）。"""
    if not _wants_human(cfg["type_id"], cfg["personal"]):
        return ""
    return market_en.get("subject", "")


def _person_details_en(cfg: dict) -> str:
    """把人物信号字段合并成简短英文描述。"""
    ps = cfg["personal"]
    fields = ["人种肤色", "性别物种", "年龄维度", "身型身材", "穿着风格", "动作姿态", "表情神态", "性别风格", "年龄特点"]
    vals = [OPTIONS_EN.get(ps.get(l), ps.get(l)) for l in fields if ps.get(l)]
    return ", ".join(vals)


def _resolve_market_en(target_market: str | None) -> dict:
    return MARKET_PROFILES_EN.get(target_market or "", MARKET_PROFILES_EN.get(_DEFAULT_MARKET, {}))


def _resolve_platform_en(platform: str | None) -> dict:
    p = PLATFORM_PROFILES_EN.get(platform or "", dict(_DEFAULT_PLATFORM))
    p["name"] = _t(platform) or "e-commerce"
    return p


def _assemble_en(cfg: dict, copy: dict, market_en: dict, platform_en: dict) -> str:
    """紧凑英文提示词组装器：以类型/配置为核心，去除冗余标题。"""
    type_id = cfg["type_id"]
    sem = TYPE_SEMANTICS.get(type_id, {"bg_mode": "scene", "person": "optional", "tech": {}, "medium": "commercial product photography"})
    bg_mode = sem.get("bg_mode", "scene")
    tech = WHITE_TECH_EN if bg_mode == "white" else {}
    medium = TYPE_CAMERA_EN.get(type_id, "commercial product photography")
    plat = sem.get("platform_override") or cfg["platform"]
    platform_en = _resolve_platform_en(plat)
    wants_human = _resolve_person(type_id, cfg["personal"], sem)
    ps = cfg["personal"]
    has_ref = cfg["has_reference"]
    ratio = cfg["ratio"]

    chunks: list[str] = []

    # 1. 类型最强句首
    chunks.append(_type_opening_en(cfg, sem, platform_en))

    # 2. 构图与比例
    comp_parts: list[str] = []
    if bg_mode == "white":
        comp_parts.append("centered product, complete silhouette")
        comp_parts.append(tech.get("product_ratio", "product fills ≥85%"))
        comp_parts.append(tech.get("min_px", "short edge ≥1000px"))
        if ratio == "自适应尺寸":
            comp_parts.append("match reference aspect ratio, no crop/stretch")
        else:
            fmt = RATIO_FORMAT_EN.get(ratio)
            if fmt:
                comp_parts.append(fmt)
    elif bg_mode == "neutral":
        comp_parts.append("centered product, light gray background, even margins")
    else:
        comp_parts.append(platform_en.get("composition", "centered composition"))
        comp_parts.append(platform_en.get("subject_ratio", "subject prominent"))
        if ratio != "自适应尺寸":
            fmt = RATIO_FORMAT_EN.get(ratio)
            if fmt:
                comp_parts.append(fmt)
        else:
            comp_parts.append("match reference aspect ratio")

    # 配置相关性：用户显式选择的角度/数量/距离等
    if ps.get("角度数量"):
        comp_parts.append(f"{_t(ps['角度数量'])}")
    if ps.get("展示角度"):
        comp_parts.append(f"view: {_t(ps['展示角度'])}")
    if ps.get("拍摄角度"):
        comp_parts.append(f"camera: {_t(ps['拍摄角度'])}")
    if ps.get("拍摄距离"):
        comp_parts.append(f"distance: {_t(ps['拍摄距离'])}")
    if ps.get("摆放状态"):
        comp_parts.append(f"placement: {_t(ps['摆放状态'])}")
    if ps.get("构图方式"):
        comp_parts.append(f"composition: {_t(ps['构图方式'])}")
    if ps.get("排版呈现") or ps.get("表现形式") or ps.get("视觉呈现形式"):
        comp_parts.append(f"layout: {_t(ps.get('排版呈现') or ps.get('表现形式') or ps.get('视觉呈现形式'))}")

    chunks.append(", ".join(comp_parts) + ".")

    # 3. 商品主体与卖点
    subj_parts: list[str] = []
    if has_ref:
        subj_parts.append(_subject_fidelity_en(cfg))
    display = ps.get("产品呈现")
    if display:
        if not wants_human and display in _PERSON_PRESENT_VALUES:
            display = "平铺展示"
        subj_parts.append(PRODUCT_PRESENT_VOCAB_EN.get(display, _t(display)))
    if cfg["selling_points"]:
        if copy["allow_text"]:
            subj_parts.append(f"selling point: {cfg['selling_points']} ({_t(copy['copy_language'])})")
        else:
            subj_parts.append(f"highlight visually: {cfg['selling_points']}")
    # 5 转化维度（仅输出 value，避免冗长）
    for dim in ("价值聚焦", "视觉强化", "产品呈现", "氛围浓度", "价值暗示"):
        v = ps.get(dim)
        if not v:
            continue
        vocab = None
        if dim == "价值聚焦":
            vocab = VALUE_FOCUS_VOCAB_EN.get(v)
        elif dim == "视觉强化":
            vocab = STYLE_VOCAB_EN.get(v)
        elif dim == "产品呈现":
            vocab = PRODUCT_PRESENT_VOCAB_EN.get(v)
        elif dim == "氛围浓度":
            vocab = STYLE_VOCAB_EN.get(v)
        elif dim == "价值暗示":
            vocab = VALUE_HINT_VOCAB_EN.get(v)
        if vocab:
            subj_parts.append(vocab)
    # 面料/工艺
    if ps.get("面料质感"):
        subj_parts.append(FABRIC_VOCAB_EN.get(ps["面料质感"], _t(ps["面料质感"])))
    if ps.get("工艺细节"):
        subj_parts.append(CRAFT_VOCAB_EN.get(ps["工艺细节"], _t(ps["工艺细节"])))
    if not wants_human:
        subj_parts.append("no people, no hands, no model")
    if subj_parts:
        chunks.append(" ".join([s for s in subj_parts if s]) + ".")

    # 4. 人物
    if wants_human:
        person_parts: list[str] = []
        market_subject = _market_subject_en(cfg, market_en)
        if market_subject:
            person_parts.append(market_subject)
        person_details = _person_details_en(cfg)
        if person_details:
            person_parts.append(person_details)
        for lbl in ("互动方式", "展示排版", "场景类型", "场景背景", "展示重点", "氛围营造"):
            if ps.get(lbl):
                tpl = SETTING_TEMPLATE_EN.get(lbl, "{lbl}: {v}. ")
                person_parts.append(tpl.format(v=_t(ps[lbl])).strip())
        if person_parts:
            chunks.append(" ".join(person_parts))

    # 5. 场景 / 背景
    scene_parts: list[str] = []
    if bg_mode == "white":
        scene_parts.append(tech.get("bg", "pure white background (RGB 255,255,255)"))
    elif bg_mode == "neutral":
        scene_parts.append("light gray solid background, no clutter")
    else:
        if ps.get("背景场景"):
            scene_parts.append(f"background: {_t(ps['背景场景'])}")
        if market_en.get("background") and not scene_parts:
            scene_parts.append(f"background: {market_en['background']}")
        if ps.get("场景类型"):
            scene_parts.append(f"scene: {_t(ps['场景类型'])}")
        if market_en.get("avoid"):
            scene_parts.append(f"avoid: {market_en['avoid']}")
    if scene_parts:
        chunks.append(", ".join(scene_parts) + ".")

    # 6. 光影与色彩
    light_parts: list[str] = []
    if ps.get("产品光影") or ps.get("光影质感"):
        light_parts.append(f"lighting: {_t(ps.get('产品光影') or ps.get('光影质感'))}")
    if cfg["visual_style"]:
        vs = (HUMAN_STYLE_VOCAB_EN if wants_human else STYLE_VOCAB_EN).get(cfg["visual_style"], _t(cfg["visual_style"]))
        light_parts.append(vs)
    if bg_mode == "neutral":
        light_parts.append("neutral low saturation, no vivid color")
    elif bg_mode == "white":
        # 纯白底已由场景段给出 "pure white background (RGB 255,255,255)"，此处不再重复，
        # 仅补一句无阴影，避免与场景段白底描述冗余。
        light_parts.append("no cast shadow")
    else:
        if cfg["tone"]:
            tone = STYLE_VOCAB_EN.get(cfg["tone"], _t(cfg["tone"]))
            if market_en.get("palette"):
                if has_ref:
                    light_parts.append(f"background tone: {tone}; palette only for background, product color stays true to reference")
                else:
                    light_parts.append(f"tone: {tone}; palette: {market_en['palette']}")
            else:
                light_parts.append(f"tone: {tone}")
    if light_parts:
        chunks.append(", ".join(light_parts) + ".")

    # 7. 相机/画质/风格
    cam_parts: list[str] = [medium]
    retouch = GLOBAL_RETROUCH_EN if wants_human else RETOUCH_NO_HUMAN_EN
    cam_parts.append(f"{platform_en.get('resolution', '8K ultra HD, sharp, no distortion')}; {retouch}")
    cam_parts.append(QUALITY_BOOSTERS_EN)
    chunks.append(". ".join(cam_parts) + ".")

    # Spec chart: product-focused visual + back-end text overlay (NO text in image)
    # Strategy: overlay replaces the right ~40% with its own panel anyway,
    # so the AI must make the product LARGE, CLEAR, and COMPLETE within the frame.
    if type_id == "spec":
        is_apparel = ps.get("产品品类") == "服饰穿戴产品"
        spec_en: list[str] = [
            "professional e-commerce specification size chart infographic, TEXT-FREE visual only:",
            # Product must be LARGE and PROMINENT — overlay will crop left portion
            "product displayed LARGE and CLEAR, filling 70-75% of the image area, centered or slightly left-of-center;",
            "product shown COMPLETE (full outfit if apparel), all details visible, not cropped or squeezed to edge;",
            "light gray (#F5F5F7) solid background, clean studio lighting, soft natural shadows, premium catalog quality;",
        ]
        if is_apparel:
            # Allow elegant measurement guide LINES (no text) — they look professional like real spec charts
            spec_en.append(
                "elegant thin measurement indicator lines with arrow tips around the product "
                "(vertical length arrows along left side, horizontal width arrows across chest/waist, diagonal sleeve arrows) "
                "— clean lines ONLY, absolutely no text/numbers/labels on the lines;"
            )
            spec_en.append(
                "optional very faint child body silhouette outline as wearing scale reference near the product, text-free;"
            )
        else:
            spec_en.append(
                "subtle dimension indicator lines with double-headed arrows showing height/width/depth "
                "— clean lines ONLY, no text labels;"
            )
        spec_en.append("high-end e-commerce product specification sheet style, clean and professional layout;")
        spec_en.append(
            "CRITICAL: absolutely NO text, numbers, letters, words, tables, watermarks, brand names, or price tags anywhere in the image."
        )
        chunks.append(" ".join(spec_en))

    # 对比类（使用对比图 / 客户痛点展示）：左右分屏，两屏均锚定上传参考图商品
    if type_id in {"cmp", "pain"}:
        cmp_en: list[str] = [
            "split-screen comparison infographic with a thin vertical divider;",
            "BOTH left and right panels feature the SAME product as the uploaded reference image "
            "(identical color, material, pattern, logo and structure) — never substitute a similar or generic product;",
            "the two panels differ ONLY in scene, usage state, environment or context, not in the product itself;",
        ]
        if type_id == "cmp":
            cmp_en.append(
                "left panel = 'before / ordinary / competitor' state, right panel = 'after / our product advantage' state, "
                "clear and intuitive contrast;"
            )
        else:  # pain：左痛点右方案
            cmp_en.append(
                "left panel shows the customer PAIN POINT (inconvenience, mess, discomfort, inefficiency) in a relatable "
                "lifestyle scene, right panel shows the SOLUTION with the same product resolving it;"
            )
        if has_ref:
            cmp_en.append(
                "product in both panels must exactly match the reference image; do NOT alter its color/pattern/logo or swap it;"
            )
        cmp_en.append("consistent lighting and background tone across both panels, clean e-commerce comparison style.")
        chunks.append(" ".join(cmp_en))

    # 用户补充说明（规格参数图的补充说明改由后端叠加层渲染，不进英文图像提示词）
    note = (cfg.get("note") or "").strip()
    if note and type_id != "spec":
        chunks.append(f"supplementary note: {note}")

    # Single-image multi-angle / multi-scene collage: describe each panel distinctly
    mc = _detect_multi_cell_type(cfg)
    if mc == "angle":
        chunks.append(
            "multi-angle collage, each panel a distinct view "
            "(front/side/back/45/top/detail), product identical across panels, thin separators."
        )
    elif mc == "scene":
        chunks.append(
            "multi-scene collage, each panel a distinct usage scenario "
            "(grid/4-grid/9-grid/split), product identical across panels, thin separators, unified lighting."
        )

    # 8. 文字约束
    if copy["allow_text"]:
        chunks.append(f"Text allowed only for layout copy in {_t(copy['copy_language'])}; no other text, logo, watermark or numbers.")
    else:
        chunks.append("No text, letters, numbers, logos, watermarks, brand names, prices, tags or annotations in the image.")

    # 9. 负面提示词（精简为最高频核心词）
    neg_core = [
        "blurry", "out of focus", "heavy noise", "cluttered background", "messy shadows",
        "oversaturated", "cartoon", "3D render feel", "watermark", "text", "logo", "numbers",
        "letters", "people", "model", "hands", "deformed", "plastic feel",
        "wrong size", "out of proportion", "damaged edges", "messy stitching", "flash reflection",
        "crushed shadows"
    ]
    # Spec 类型需要保留测量指示线（无文字），所以排除 dimension/masurement 相关负面词
    if type_id != "spec":
        neg_core += ["dimension marks", "measurement lines", "annotation arrows"]
    if wants_human:
        neg_core += ["deformed hands", "extra fingers", "distorted face", "incomplete limbs", "pale face"]
    seen = set()
    neg_uniq = [x for x in neg_core if not (x in seen or seen.add(x))]
    chunks.append("Negative: " + ", ".join(neg_uniq) + ".")

    # 清理并合并
    text = " ".join(_dedupe([c.strip() for c in chunks if c.strip()]))
    return " ".join(text.split())


def build_prompt_en(project, item, model_name: str | None = None, effective_product_image: str | None = None) -> str:
    """生成紧凑英文提示词，直接用于图片模型生成。"""
    cfg = _resolve_config(project, item, effective_product_image=effective_product_image)
    copy = _decide_copy_policy(cfg["type_id"], cfg["copy_language"])
    market_en = _resolve_market_en(cfg["target_market"])
    platform_en = _resolve_platform_en(cfg["platform"])
    return _assemble_en(cfg, copy, market_en, platform_en)


def build_prompt_bilingual(project, item, model_name: str | None = None, effective_product_image: str | None = None) -> dict:
    """同时返回中文版（展示）与英文版（生成）提示词。"""
    cfg = _resolve_config(project, item, effective_product_image=effective_product_image)
    copy = _decide_copy_policy(cfg["type_id"], cfg["copy_language"])
    market = _resolve_market(cfg["target_market"])
    platform = _resolve_platform(cfg["platform"])
    prompt_cn = _assemble(cfg, copy, market, platform)
    _lint(prompt_cn, copy["allow_text"])

    market_en = _resolve_market_en(cfg["target_market"])
    platform_en = _resolve_platform_en(cfg["platform"])
    prompt_en = _assemble_en(cfg, copy, market_en, platform_en)
    return {"prompt": prompt_cn, "prompt_en": prompt_en}


