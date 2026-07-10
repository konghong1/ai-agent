"""电商套图模块 · 数据驱动配置中心。

设计原则（高扩展 / 低耦合）：
- 所有「策划类型」「个性化字段」「下拉选项」「示例套图种子」都集中在此文件中，
  以纯数据形式声明。前端通过 ``GET /api/gallery/types`` 拉取后动态渲染。
- 新增一种策划类型 = 在 ``PLAN_TYPES`` / ``TYPE_PERSONAL`` 中加一条数据，
  无需改动任何路由、Service 或前端组件。
- 类型成本（积分 / 时长）也在此声明，生成卡据此动态估算。
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────
# 通用设置 / 市场配置 的下拉选项（所有类型共享）
# ─────────────────────────────────────────────────────────────

COMMON_OPTIONS: dict[str, list[str]] = {
    "copy_language": ["英语", "中文", "日语", "德语", "法语", "西班牙语", "葡萄牙语", "阿拉伯语"],
    "target_market": ["北美", "欧洲", "东南亚", "拉美", "中东", "日韩", "全球"],
    "ecommerce_platform": ["亚马逊", "淘宝 / 天猫", "京东", "抖音电商", "拼多多", "小红书"],
    "visual_style": ["高级质感风", "清新自然风", "科技未来感", "复古怀旧风", "简约极简风", "活泼可爱风"],
    "copy_need": ["核心卖点文案", "场景化文案", "功能参数文案", "情感故事文案", "促销转化文案"],
    "tone_tendency": ["高饱和色调", "低饱和高级灰", "莫兰迪色系", "明亮清新", "暗黑酷感"],
}

MARKET_OPTIONS: dict[str, list[str]] = {
    "ecommerce_platform": COMMON_OPTIONS["ecommerce_platform"],
    "target_market": COMMON_OPTIONS["target_market"],
    "copy_language": COMMON_OPTIONS["copy_language"],
    "visual_style": COMMON_OPTIONS["visual_style"],
}

# ─────────────────────────────────────────────────────────────
# 全局输出配置 的下拉选项
# ─────────────────────────────────────────────────────────────

OUTPUT_OPTIONS: dict[str, object] = {
    "model": ["Banana-pro", "Banana-lite", "Gpt-image-2", "通用"],
    "resolution": ["1K", "2K", "4K"],
    "count_min": 1,
    "count_default": 1,
    "ratio": ["自适应尺寸", "竖图 3:4", "横图 16:9", "方形 1:1", "横图 4:3"],
    # 活动海报专属：分辨率选择替代比例下拉
    "promo_ratio": ["自动", "竖图 3:4", "横图 16:9", "方形 1:1", "横图 4:3"],
    "promo_resolution": ["1K", "2K", "4K"],
}

# ─────────────────────────────────────────────────────────────
# 18 种策划类型（数据驱动）
#   fast=True  → 极速出图（设计稿中荧光绿标记）
#   hasResolution=True → 出图设置用「分辨率 1K/2K/4K」替代比例下拉
#   points / minutes → 单次出图成本，用于生成卡估算
# ─────────────────────────────────────────────────────────────

PLAN_TYPES: list[dict] = [
    {"id": "bg", "title": "产品白底图", "desc": "纯白背景，突出商品本体", "points": 4, "minutes": 0.4},
    {"id": "amz", "title": "亚马逊主图", "desc": "符合平台规定的主图", "points": 4, "minutes": 0.4},
    {"id": "detail", "title": "细节特写", "desc": "放大细节，展示质感工艺", "points": 5, "minutes": 0.5},
    {"id": "angle", "title": "产品多角度", "desc": "多视角展示外观结构", "points": 6, "minutes": 0.6},
    {"id": "hero", "title": "首屏视觉图", "desc": "首屏吸睛，提升点击转化", "points": 7, "minutes": 0.7},
    {"id": "usp", "title": "核心卖点图", "desc": "一句话卖点＋图形强化", "points": 5, "minutes": 0.5},
    {"id": "pain", "title": "客户痛点展示", "desc": "指出痛点并给出解决方案", "points": 5, "minutes": 0.5},
    {"id": "scene", "title": "场景图（非服饰）", "desc": "真实使用场景带入感", "points": 6, "minutes": 0.6},
    {"id": "detail2", "title": "细节展示图", "desc": "局部细节分点说明", "points": 5, "minutes": 0.5},
    {"id": "tryon", "title": "试穿试戴场景", "desc": "上身/上手效果展示", "points": 8, "minutes": 0.8},
    {"id": "model", "title": "产品代言互动", "desc": "人物代言＋互动引导购买", "points": 8, "minutes": 0.8},
    {"id": "design", "title": "产品设计图", "desc": "结构示意，讲解设计亮点", "points": 6, "minutes": 0.6},
    {"id": "cmp", "title": "使用对比图", "desc": "使用前/后/竞品对比更直观", "points": 6, "minutes": 0.6},
    {"id": "ship", "title": "运输安装", "desc": "运输包装与安装步骤说明", "points": 5, "minutes": 0.5},
    {"id": "spec", "title": "规格参数图", "desc": "尺寸参数一图看懂", "points": 5, "minutes": 0.5},
    {"id": "pkg", "title": "包装展示图", "desc": "包装展示效果呈现", "points": 5, "minutes": 0.5},
    {"id": "buyer", "title": "通用买家秀", "desc": "真实买家亲善氛围图", "points": 6, "minutes": 0.6},
    {"id": "promo", "title": "活动海报", "desc": "促销信息海报，用于投放", "fast": True,
     "hasResolution": True, "points": 3, "minutes": 0.3},
    {"id": "custom", "title": "自定义子任务", "desc": "自由填写需求生成指定画面", "custom": True,
     "points": 5, "minutes": 0.5},
]

# 逐类型「个性化设置」字段。
# 每个字段: {"label":..., "placeholder":..., "options":[...] 可选}
# 有 options → 渲染为下拉；无 → 渲染为文本输入（设计稿中多为「请选择，或直接输入」）。
TYPE_PERSONAL: dict[str, list[dict]] = {
    "bg": [
        {"label": "背景处理", "placeholder": "纯白/渐变/透明"},
        {"label": "光影效果", "placeholder": "请选择，或直接输入"},
        {"label": "产品角度", "placeholder": "正视角/45°/俯视"},
    ],
    "amz": [
        {"label": "平台规范", "placeholder": "符合亚马逊主图要求"},
        {"label": "尺寸比例", "placeholder": "1:1 正方形"},
        {"label": "背景要求", "placeholder": "纯白背景"},
    ],
    "detail": [
        {"label": "细节区域", "placeholder": "请选择，或直接输入"},
        {"label": "放大倍率", "placeholder": "请选择，或直接输入"},
        {"label": "标注方式", "placeholder": "无标注/箭头/文字"},
    ],
    "angle": [
        {"label": "视角数量", "placeholder": "3/6/8/12 视角"},
        {"label": "旋转方向", "placeholder": "360°/180°"},
        {"label": "展示重点", "placeholder": "外观/结构/接口"},
    ],
    "hero": [
        {"label": "价值聚焦", "placeholder": "请选择，或直接输入"},
        {"label": "视觉强化", "placeholder": "质感放大"},
        {"label": "产品呈现", "placeholder": "整体形态"},
        {"label": "氛围浓度", "placeholder": "轻度氛围"},
        {"label": "价值暗示", "placeholder": "品质细节"},
    ],
    "usp": [
        {"label": "核心卖点", "placeholder": "一句话卖点"},
        {"label": "图形风格", "placeholder": "图标/插图/数据图"},
        {"label": "文案位置", "placeholder": "上方/下方/侧边"},
    ],
    "pain": [
        {"label": "痛点类型", "placeholder": "使用前困扰"},
        {"label": "解决方案", "placeholder": "产品如何解决"},
        {"label": "对比方式", "placeholder": "前后对比/并列对比"},
    ],
    "scene": [
        {"label": "使用场景", "placeholder": "请选择，或直接输入"},
        {"label": "氛围基调", "placeholder": "请选择，或直接输入"},
        {"label": "道具搭配", "placeholder": "请选择，或直接输入"},
        {"label": "用户状态", "placeholder": "请选择，或直接输入"},
    ],
    "detail2": [
        {"label": "细节方向", "placeholder": "请选择，或直接输入"},
        {"label": "标注方式", "placeholder": "请选择，或直接输入"},
        {"label": "文字密度", "placeholder": "请选择，或直接输入"},
    ],
    "tryon": [
        {"label": "人种肤色", "placeholder": "请选择，或直接输入"},
        {"label": "性别物种", "placeholder": "请选择，或直接输入"},
        {"label": "年龄维度", "placeholder": "请选择，或直接输入"},
        {"label": "身型身材", "placeholder": "请选择，或直接输入"},
        {"label": "穿着风格", "placeholder": "请选择，或直接输入"},
        {"label": "动作姿态", "placeholder": "请选择，或直接输入"},
        {"label": "表情神态", "placeholder": "请选择，或直接输入"},
        {"label": "场景环境", "placeholder": "请选择，或直接输入"},
    ],
    "model": [
        {"label": "代言人设", "placeholder": "专业模特/KOL/真实用户"},
        {"label": "互动形式", "placeholder": "手持/佩戴/演示"},
        {"label": "情感传递", "placeholder": "信任感/向往感/亲和力"},
        {"label": "构图方式", "placeholder": "中景/近景/特写"},
    ],
    "design": [
        {"label": "展示角度", "placeholder": "爆炸图/剖面图/分层图"},
        {"label": "标注密度", "placeholder": "精简/详细/极简"},
        {"label": "配色方案", "placeholder": "产品原色/单色/品牌色"},
        {"label": "技术感程度", "placeholder": "高/中/低"},
    ],
    "cmp": [
        {"label": "对比维度", "placeholder": "使用前vs后/我方vs竞品"},
        {"label": "图表形式", "placeholder": "并列/分屏/箭头连接"},
        {"label": "强调重点", "placeholder": "优势差异/升级点"},
    ],
    "ship": [
        {"label": "包装状态", "placeholder": "开箱/封箱/运输中"},
        {"label": "安装步骤", "placeholder": "简易/详细/视频引导"},
        {"label": "配件清单", "placeholder": "完整列出/突出重点"},
    ],
    "spec": [
        {"label": "参数类型", "placeholder": "材质工艺参数"},
        {"label": "呈现形式", "placeholder": "请选择，或直接输入"},
        {"label": "产品品类", "placeholder": "服饰穿戴产品"},
        {"label": "价值传递", "placeholder": "请选择，或直接输入"},
        {"label": "场景适配", "placeholder": "详情页参数专区"},
    ],
    "pkg": [
        {"label": "包装角度", "placeholder": "正面/侧面/展开/堆叠"},
        {"label": "环境氛围", "placeholder": "简约/节日/礼品感"},
        {"label": "材质表现", "placeholder": "强调质感/环保/高级"},
    ],
    "buyer": [
        {"label": "买家氛围", "placeholder": "生活化/专业测评/开箱"},
        {"label": "拍摄风格", "placeholder": "自然光/室内/户外"},
        {"label": "人物数量", "placeholder": "单人/多人/亲子"},
    ],
    "promo": [
        {"label": "促销主题", "placeholder": "限时折扣/新品上市/节日"},
        {"label": "设计风格", "placeholder": "简约/热闹/奢华"},
        {"label": "信息层级", "placeholder": "主标题+副标题+价格+CTA"},
        {"label": "CTA按钮", "placeholder": "立即购买/了解更多/抢购"},
    ],
}


# ─────────────────────────────────────────────────────────────
# 示例套图种子（热门套图示例）。图片在 seed 时由 Service 生成为本地 SVG。
#   hue: 渐变主色相（0-360），用于生成占位图
#   count: 该套图包含的图片总数（含原图），用于卡片「+N」角标
# ─────────────────────────────────────────────────────────────

SHOWCASE_SEED: list[dict] = [
    {"category": "服装鞋帽", "name": "黑色蕾丝拼接皮质吊带连衣裙", "hue": 330, "count": 10},
    {"category": "3C 数码", "name": "无线主动降噪蓝牙耳机 Pro", "hue": 210, "count": 13},
    {"category": "箱包配饰", "name": "复古真皮通勤大容量托特包", "hue": 28, "count": 16},
    {"category": "个护美妆", "name": "烟酰胺提亮修护精华液 30ml", "hue": 350, "count": 10},
    {"category": "日用百货", "name": "北欧风极简陶瓷马克杯 400ml", "hue": 160, "count": 19},
    {"category": "其他", "name": "婴儿硅胶安抚牙胶玩具", "hue": 45, "count": 11},
]

SHOWCASE_CATEGORIES: list[str] = ["全部", "服装鞋帽", "3C 数码", "箱包配饰", "个护美妆", "日用百货", "其他"]


# ─────────────────────────────────────────────────────────────
# 序列化辅助：供 /api/gallery/types 返回
# ─────────────────────────────────────────────────────────────

def get_plan_type(type_id: str) -> dict | None:
    for t in PLAN_TYPES:
        if t["id"] == type_id:
            return t
    return None


def get_personal_fields(type_id: str) -> list[dict]:
    return TYPE_PERSONAL.get(type_id, [
        {"label": "个性化项1", "placeholder": "请选择，或直接输入"},
        {"label": "个性化项2", "placeholder": "请选择，或直接输入"},
    ])


def serialize_types() -> list[dict]:
    """返回前端所需的结构化类型定义。"""
    out = []
    for t in PLAN_TYPES:
        out.append({
            "id": t["id"],
            "title": t["title"],
            "desc": t["desc"],
            "fast": t.get("fast", False),
            "hasResolution": t.get("hasResolution", False),
            "points": t.get("points", 5),
            "minutes": t.get("minutes", 0.5),
            "ratioOptions": OUTPUT_OPTIONS["promo_ratio"] if t.get("hasResolution") else None,
            "personal": get_personal_fields(t["id"]),
        })
    return out


def serialize_options() -> dict:
    """返回所有下拉选项，供前端初始化表单。"""
    return {
        "common": COMMON_OPTIONS,
        "market": MARKET_OPTIONS,
        "output": OUTPUT_OPTIONS,
        "showcase_categories": SHOWCASE_CATEGORIES,
    }


def estimate_cost(plan_items: list[dict]) -> dict:
    """根据策划项估算总积分与总时长。

    plan_items: [{type_id, count}]
    """
    total_points = 0
    total_minutes = 0.0
    for item in plan_items:
        t = get_plan_type(item.get("type_id", ""))
        if not t:
            continue
        count = max(1, int(item.get("count", 1) or 1))
        total_points += t.get("points", 5) * count
        total_minutes += t.get("minutes", 0.5) * count
    return {
        "total_points": total_points,
        "total_minutes": round(total_minutes, 1),
        "total_images": sum(max(1, int(i.get("count", 1) or 1)) for i in plan_items),
    }
