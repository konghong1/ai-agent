"""电商套图模块 · 数据驱动配置中心。

设计原则（高扩展 / 低耦合）：
- 所有「策划类型」「个性化字段」「下拉选项」「示例套图种子」都集中在此文件中，
  以纯数据形式声明。前端通过 ``GET /api/gallery/types`` 拉取后动态渲染。
- 新增一种策划类型 = 在 ``PLAN_TYPES`` / ``TYPE_PERSONAL`` 中加一条数据，
  无需改动任何路由、Service 或前端组件。
- 类型成本（积分 / 时长）也在此声明，生成卡据此动态估算。
"""

from __future__ import annotations

import copy
import os

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
    "ratio": ["自适应尺寸", "方图 1:1", "竖图 3:4", "竖图 4:5", "竖图 9:16", "竖图 2:3", "横图 16:9", "横图 4:3"],
    # 活动海报专属：分辨率选择替代比例下拉
    "promo_ratio": ["自适应尺寸", "方图 1:1", "竖图 3:4", "竖图 4:5", "竖图 9:16", "竖图 2:3", "横图 16:9", "横图 4:3"],
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
        {"label": "服装品类", "placeholder": "连衣裙/套装/上衣…"},
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
        {"label": "服装品类", "placeholder": "连衣裙/套装/上衣…"},
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
        {"label": "设计理念", "placeholder": "请选择，或直接输入", "options": [
            "用户需求导向", "功能创新理念", "极简实用主义", "情感共鸣设计",
            "可持续环保理念", "场景适配理念", "美学与功能平衡", "人性化交互设计"
        ]},
        {"label": "灵感溯源", "placeholder": "请选择，或直接输入", "options": [
            "用户痛点洞察", "自然形态借鉴", "传统文化提取", "生活场景观察",
            "科技趋势启发", "艺术作品熏陶", "材质特性挖掘", "地域文化特色"
        ]},
        {"label": "设计过程", "placeholder": "请选择，或直接输入", "options": [
            "概念草图呈现", "原型迭代过程", "细节打磨环节", "材质选型逻辑",
            "色彩搭配思考", "结构优化历程", "功能测试验证", "用户反馈迭代"
        ]},
        {"label": "价值导向", "placeholder": "请选择，或直接输入", "options": [
            "核心功能价值", "使用体验升级", "解决痛点价值", "情感连接价值",
            "品质保障价值", "场景适配价值", "审美提升价值", "便捷高效价值"
        ]},
        {"label": "视觉表达", "placeholder": "请选择，或直接输入", "options": [
            "设计草图 + 成品对比", "灵感元素 + 设计转化示意", "过程节点时间轴", "细节拆解示意图",
            "材质纹理放大呈现", "结构原理可视化", "用户场景关联图示", "色彩理念解读图"
        ]},
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

# 推荐类型「个性化设置」字段的通用下拉选项。
# 当 TYPE_PERSONAL 中未显式声明 options 时，按 label 从此映射自动填充推荐项，
# 保证每个字段都能以下拉形式选择，同时保留允许用户直接输入的 tags 能力。
PERSONAL_OPTIONS: dict[str, list[str]] = {
    "背景处理": ["纯白", "浅灰", "透明", "渐变", "场景化", "保留原背景"],
    "光影效果": ["柔和自然光", "顶光", "侧光", "逆光", "硬光", "无阴影", "暖光", "冷光"],
    "产品角度": ["正视角", "45°", "俯视", "仰视", "侧面", "背面", "悬浮展示"],
    "平台规范": ["亚马逊", "淘宝 / 天猫", "京东", "抖音电商", "拼多多", "小红书", "速卖通"],
    "尺寸比例": ["1:1", "3:4", "4:5", "9:16", "16:9", "4:3", "2:3", "自适应尺寸"],
    "背景要求": ["纯白背景", "浅色背景", "透明背景", "场景背景", "渐变背景"],
    "细节区域": ["整体", "材质纹理", "接口/按钮", "LOGO", "缝线/走线", "局部特写"],
    "放大倍率": ["2x", "3x", "5x", "10x", "微距"],
    "标注方式": ["无标注", "箭头", "文字", "数字编号", "圆框", "图标"],
    "视角数量": ["3视角", "6视角", "8视角", "12视角", "360°"],
    "旋转方向": ["360°", "180°", "90°", "水平旋转", "垂直旋转"],
    "展示重点": ["外观", "结构", "接口", "功能", "LOGO", "材质", "工艺"],
    "价值聚焦": ["品质", "功能", "价格", "情感", "场景", "设计", "服务"],
    "视觉强化": ["质感放大", "色彩冲击", "动态模糊", "光影对比", "虚实结合", "构图张力"],
    "产品呈现": ["整体形态", "局部特写", "悬浮展示", "场景嵌入", "手持/佩戴", "开箱状态"],
    "氛围浓度": ["轻度氛围", "中度氛围", "强氛围", "无氛围"],
    "价值暗示": ["品质细节", "稀有材料", "工艺精度", "设计奖项", "用户好评", "品牌背书"],
    "核心卖点": ["耐用", "轻便", "便携", "智能", "性价比", "高品质", "多功能", "易安装"],
    "图形风格": ["图标", "插图", "数据图", "实拍", "合成", "3D渲染"],
    "文案位置": ["上方", "下方", "侧边", "居中", "环绕产品"],
    "痛点类型": ["使用麻烦", "效果差", "价格高", "质量不稳", "不耐用", "不美观"],
    "解决方案": ["省时", "省钱", "省心", "升级体验", "提升品质", "解决痛点"],
    "对比方式": ["前后对比", "并列对比", "数据对比", "用户证言", "竞品对比"],
    "使用场景": ["居家", "办公", "户外", "旅行", "运动", "商务", "节日", "送礼"],
    "氛围基调": ["温馨", "商务", "活力", "高级", "自然", "科技感", "复古"],
    "道具搭配": ["简约", "丰富", "生活化", "专业", "节日", "自然元素", "无道具"],
    "用户状态": ["专注", "放松", "愉悦", "自信", "兴奋", "舒适", "满足"],
    "细节方向": ["材质", "工艺", "结构", "接口", "LOGO", "纹理", "功能点"],
    "文字密度": ["无文字", "少量", "中等", "大量"],
    "人种肤色": ["亚洲", "白种人", "黑种人", "拉美", "混血", "不限"],
    "性别物种": ["男性", "女性", "中性", "儿童", "宠物", "不限"],
    "年龄维度": ["青年", "中年", "青少年", "中老年", "婴幼儿", "不限"],
    "身型身材": ["标准", "偏瘦", "健壮", "丰满", "高挑", "娇小"],
    "穿着风格": ["休闲", "商务", "街头", "运动", "优雅", "复古", "简约"],
    "动作姿态": ["站立", "坐姿", "行走", "展示", "互动", "使用产品", "指向产品"],
    "表情神态": ["微笑", "自信", "专注", "放松", "惊讶", "满足", "自然"],
    "场景环境": ["室内", "户外", "居家", "工作室", "自然", "城市", "影棚"],
    "代言人设": ["专业模特", "KOL", "真实用户", "AI人物", "名人风格", "专家"],
    "互动形式": ["手持", "佩戴", "演示", "组合", "生活化", "指向", "展示"],
    "情感传递": ["信任感", "向往感", "亲和力", "专业感", "活力感", "高级感"],
    "构图方式": ["中景", "近景", "特写", "全身", "半身", "大头照", "环境人像"],
    "对比维度": ["使用前vs后", "我方vs竞品", "升级前后", "有无产品", "参数对比"],
    "图表形式": ["并列", "分屏", "箭头连接", "数据条", "环形图", "表格", "时间轴"],
    "强调重点": ["优势差异", "升级点", "性价比", "核心功能", "品质背书", "使用场景"],
    "包装状态": ["开箱", "封箱", "运输中", "堆叠", "平铺", "组合展示"],
    "安装步骤": ["简易", "详细", "视频引导", "分步骤", "图文结合", "无需安装"],
    "配件清单": ["完整列出", "突出重点", "图标化", "组合展示", "详细标注"],
    "参数类型": ["材质工艺", "尺寸规格", "功能参数", "认证标准", "包装清单"],
    "呈现形式": ["一图看懂", "表格", "信息图", "场景图", "对比图", "分点图"],
    "产品品类": ["服饰穿戴", "3C数码", "美妆个护", "家居日用", "食品", "母婴"],
    "服装品类": ["连衣裙", "半身裙", "套装", "上衣", "衬衫", "外套", "裤装", "大衣", "旗袍", "礼服"],
    "价值传递": ["专业可信", "品质感", "场景代入", "数据佐证", "用户证言", "品牌故事"],
    "场景适配": ["详情页", "主图", "海报", "视频封面", "社交媒体", "Banner"],
    "包装角度": ["正面", "侧面", "展开", "堆叠", "特写", "组合"],
    "环境氛围": ["简约", "节日", "礼品感", "商务", "自然", "高级", "温馨"],
    "材质表现": ["质感", "环保", "高级", "透明", "柔软", "坚硬", "金属感"],
    "买家氛围": ["生活化", "专业测评", "开箱", "晒单", "真实场景"],
    "拍摄风格": ["自然光", "室内", "户外", "影棚", "街拍", "纪实"],
    "人物数量": ["单人", "双人", "多人", "亲子", "无人物"],
    "促销主题": ["限时折扣", "新品上市", "节日", "清仓", "会员", "满减", "买赠"],
    "设计风格": ["简约", "热闹", "奢华", "复古", "科技", "可爱", "高端"],
    "信息层级": ["主标题+副标题", "价格+CTA", "卖点+促销", "主标题+卖点+价格"],
    "CTA按钮": ["立即购买", "了解更多", "抢购", "加入购物车", "马上预约", "立即领取"],
    # 兜底：万一新增字段未命中，也给一个通用候选集
    "个性化项1": ["选项A", "选项B", "选项C"],
    "个性化项2": ["选项A", "选项B", "选项C"],
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


def _apply_personal_options(source: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """为 type_personal 中「未显式声明 options」的字段按 label 自动填充推荐下拉选项。

    已声明 options 的字段原样保留（如 design 类型自带 8 个选项）。
    该函数同时作用于「库里落库的 type_personal」与「本模块常量 TYPE_PERSONAL」，
    确保前端拿到的每个类型每个字段都带下拉选项。
    """
    out: dict[str, list[dict]] = {}
    for tid, fields in source.items():
        enriched: list[dict] = []
        for f in fields:
            row = copy.deepcopy(f)
            if not row.get("options"):
                row["options"] = PERSONAL_OPTIONS.get(row["label"], ["请选择，或直接输入"])
            enriched.append(row)
        out[tid] = enriched
    return out


def get_personal_fields(type_id: str) -> list[dict]:
    """返回某类型的个性化设置字段（已按 label 自动补齐推荐下拉选项）。"""
    source = {type_id: TYPE_PERSONAL.get(type_id, [
        {"label": "个性化项1", "placeholder": "请选择，或直接输入"},
        {"label": "个性化项2", "placeholder": "请选择，或直接输入"},
    ])}
    return _apply_personal_options(source).get(type_id, [])


def _load_store(db) -> dict | None:
    """从 ``gallery_configs`` 表读取全部固定配置。

    若表为空或关键键缺失则返回 ``None``，调用方据此回退到本模块代码常量。
    """
    from app.models import GalleryConfig

    rows = db.query(GalleryConfig).all()
    if not rows:
        return None
    store = {r.config_key: r.config_value for r in rows}
    needed = {
        "plan_types", "type_personal", "common_options",
        "market_options", "output_options", "showcase_categories", "showcase_seed",
    }
    if not needed.issubset(store.keys()):
        return None
    return store


def seed_gallery_config(db) -> int:
    """把本模块的固定配置幂等落库到 ``gallery_configs`` 表。

    - 仅当某个 ``config_key`` 不存在时才写入，绝不覆盖（便于日后运营直接在库里改配置）。
    - 返回本次新写入的条数。
    """
    from app.models import GalleryConfig

    data: dict[str, object] = {
        "plan_types": PLAN_TYPES,
        "type_personal": TYPE_PERSONAL,
        "common_options": COMMON_OPTIONS,
        "market_options": MARKET_OPTIONS,
        "output_options": OUTPUT_OPTIONS,
        "showcase_categories": SHOWCASE_CATEGORIES,
        "showcase_seed": SHOWCASE_SEED,
    }
    descs = {
        "plan_types": "18 种策划类型（含成本/时长/极速标记）",
        "type_personal": "逐类型个性化字段（部分带下拉选项）",
        "common_options": "通用设置下拉选项",
        "market_options": "市场配置下拉选项",
        "output_options": "输出配置下拉选项",
        "showcase_categories": "套图示例分类",
        "showcase_seed": "套图示例种子",
    }
    added = 0
    for key, val in data.items():
        if db.query(GalleryConfig).filter_by(config_key=key).first() is None:
            db.add(GalleryConfig(config_key=key, config_value=val, description=descs.get(key, "")))
            added += 1
    if added:
        db.flush()
    return added


def serialize_types(db=None) -> list[dict]:
    """返回前端所需的结构化类型定义。

    ``db`` 传入时优先从 ``gallery_configs`` 表读取（落库配置），否则回退到本模块常量。
    """
    store = _load_store(db) if db is not None else None
    plan_types = store["plan_types"] if store else PLAN_TYPES
    # 关键：无论来源是库里落库的 type_personal 还是本模块常量，都按 label 自动补齐下拉选项，
    # 保证前端每个推荐类型的每个个性化字段都以下拉形式呈现（已显式声明 options 的类型保留原值）。
    type_personal = _apply_personal_options(store["type_personal"] if store else TYPE_PERSONAL)
    output_options = store["output_options"] if store else OUTPUT_OPTIONS

    fallback_personal = [
        {"label": "个性化项1", "placeholder": "请选择，或直接输入",
         "options": PERSONAL_OPTIONS.get("个性化项1", ["选项A", "选项B", "选项C"])},
        {"label": "个性化项2", "placeholder": "请选择，或直接输入",
         "options": PERSONAL_OPTIONS.get("个性化项2", ["选项A", "选项B", "选项C"])},
    ]

    out = []
    for t in plan_types:
        out.append({
            "id": t["id"],
            "title": t["title"],
            "desc": t["desc"],
            "fast": t.get("fast", False),
            "hasResolution": t.get("hasResolution", False),
            "points": t.get("points", 5),
            "minutes": t.get("minutes", 0.5),
            "ratioOptions": output_options["promo_ratio"] if t.get("hasResolution") else None,
            "personal": type_personal.get(t["id"], fallback_personal),
        })
    return out


def serialize_options(db=None) -> dict:
    """返回所有下拉选项，供前端初始化表单。``db`` 传入时优先读库。"""
    store = _load_store(db) if db is not None else None
    if store:
        return {
            "common": store["common_options"],
            "market": store["market_options"],
            "output": store["output_options"],
            "showcase_categories": store["showcase_categories"],
        }
    return {
        "common": COMMON_OPTIONS,
        "market": MARKET_OPTIONS,
        "output": OUTPUT_OPTIONS,
        "showcase_categories": SHOWCASE_CATEGORIES,
    }


def estimate_cost(plan_items: list[dict], db=None) -> dict:
    """根据策划项估算总积分与总时长。

    plan_items: [{type_id, count}]
    ``db`` 传入时从落库配置读取类型成本，否则回退到本模块常量。
    """
    store = _load_store(db) if db is not None else None
    plan_types = store["plan_types"] if store else PLAN_TYPES

    total_points = 0
    total_minutes = 0.0
    for item in plan_items:
        t = next((x for x in plan_types if x["id"] == item.get("type_id", "")), None)
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


# ─────────────────────────────────────────────────────────────
# 提示词生成引擎 · 视觉档案库（数据驱动，纯数据，可落库覆盖）
#   由 app.gallery_prompt 的 Resolver / Assembler 消费，把抽象配置
#   转译为可识别的视觉指令。新增市场 / 平台只需在此加一条数据。
# ─────────────────────────────────────────────────────────────

# 目标市场 → 视觉档案
#   subject    : 主体人物硬性要求（人种/肤色/身形/姿态/妆容/发型）
#   palette    : 高饱和等色调倾向对应的具体色系
#   background : 背景方向（贴合该市场审美）
#   avoid      : 该市场审美下应避免的元素
MARKET_PROFILES: dict[str, dict] = {
    "中东": {
        "subject": "适配中东审美的年轻女性模特，暖调健康肤色，柔和立体五官；纤细手臂、"
                   "标准直角肩、匀称修长身形；全身完整入镜无裁切；简约淡系中东妆容、"
                   "柔顺长发或低盘发；端庄舒展站姿，柔和大气；服装完整遮盖肩颈，"
                   "拒绝暴露剪裁，符合中东大众审美",
        "palette": "高饱和中东轻奢色系：暖金、焦糖橙、宝石蓝、酒红（任选其一作为服装主色，"
                   "高饱和低灰度，不刺眼）",
        "background": "浅金 / 米杏纯色轻奢渐变背景，禁止杂乱道具、花草、建筑干扰",
        "avoid": "纯欧美冷白皮、夸张浓妆、西式极简冷白背景、过度性感动作、暴露剪裁",
    },
    "北美": {
        "subject": "多元包容的年轻模特，自然健康肤色，干净立体五官；匀称身形，"
                   "全身完整入镜无裁切；自然淡妆、简约发型；自信舒展站姿",
        "palette": "明亮清晰的高饱和或自然色系，色彩干净不浑浊",
        "background": "纯白或浅灰极简纯色背景，无杂乱道具",
        "avoid": "过重阴影、暗沉低饱和、夸张浓妆",
    },
    "欧洲": {
        "subject": "气质高级的年轻模特，自然肤色，柔和立体五官；修长身形，"
                   "全身完整入镜；淡雅妆容、利落发型；从容站姿",
        "palette": "低饱和高级灰或莫兰迪色系为主，可点缀低灰度高饱和强调色",
        "background": "浅灰 / 米白纯色背景，极简干净",
        "avoid": "高饱和刺眼撞色、杂乱道具",
    },
    "日韩": {
        "subject": "清透年轻的模特，自然偏白肤色，柔和五官；纤细匀称身形，"
                   "全身完整入镜；清透裸妆、柔顺发型；轻盈自然站姿",
        "palette": "明亮清新色系，低饱和度柔和撞色",
        "background": "浅色干净纯色或微弱渐变背景",
        "avoid": "过重阴影、暗沉色调、夸张浓妆",
    },
    "东南亚": {
        "subject": "健康活力的年轻模特，自然暖调肤色，柔和五官；匀称身形，"
                   "全身完整入镜；自然淡妆、柔顺发型；舒展站姿",
        "palette": "明亮热带高饱和色系，色彩鲜活不刺眼",
        "background": "浅色纯色或自然微渐变背景",
        "avoid": "暗沉低饱和、过重阴影",
    },
    "拉美": {
        "subject": "热情活力的年轻模特，健康小麦肤色，立体五官；匀称身形，"
                   "全身完整入镜；自然妆容、柔顺发型；自信舒展站姿",
        "palette": "高饱和暖色调（橙红、金棕、宝石色），鲜活明快",
        "background": "浅暖色纯色或微渐变背景",
        "avoid": "冷灰暗沉、过重阴影",
    },
    "全球": {
        "subject": "多元包容的年轻模特，自然健康肤色，柔和立体五官；匀称身形，"
                   "全身完整入镜无裁切；自然淡妆、简约发型；自信舒展站姿",
        "palette": "均衡清晰的高饱和或自然色系，色彩干净",
        "background": "纯白或浅灰极简纯色背景",
        "avoid": "过重阴影、暗沉低饱和、杂乱道具",
    },
}

# 电商平台 → 主图规范
#   composition : 构图方式
#   subject_ratio: 主体占比与留白
#   resolution  : 画质参数
#   forbidden   : 平台隐性禁忌（汇总）
PLATFORM_PROFILES: dict[str, dict] = {
    "淘宝 / 天猫": {
        "composition": "居中全身构图，正面微侧约30°站姿，完整展示服装版型",
        "subject_ratio": "人物主体占画面约 65%，四周均匀留白，适配首屏主图规范",
        "resolution": "8K 超高清，商业精修，高锐度，无镜头畸变",
        "forbidden": "肢体畸形、模特局部裁切、杂乱背景杂物、过重阴影、反光光斑、多余装饰摆件",
    },
    "亚马逊": {
        "composition": "纯白背景居中构图，产品 / 人物完整入镜无裁切",
        "subject_ratio": "主体占画面约 80%-85%，四周留白，符合亚马逊主图规范",
        "resolution": "高清商业精修，高锐度，无镜头畸变",
        "forbidden": "文字水印、道具场景、边框、多余留白装饰",
    },
    "京东": {
        "composition": "居中构图，主体清晰突出，完整展示",
        "subject_ratio": "主体占画面约 70%，四周均匀留白",
        "resolution": "高清商业精修，高锐度，无镜头畸变",
        "forbidden": "杂乱背景、过重阴影、文字水印",
    },
    "抖音电商": {
        "composition": "适合竖图 3:4 / 9:16 构图，主体突出有视觉冲击",
        "subject_ratio": "主体占画面约 60%-70%，留白适配短视频封面",
        "resolution": "高清商业精修，清晰锐利",
        "forbidden": "杂乱背景、文字水印、畸变",
    },
    "拼多多": {
        "composition": "居中清晰构图，信息直观，主体突出",
        "subject_ratio": "主体占画面约 75%，四周留白",
        "resolution": "高清清晰，无畸变",
        "forbidden": "杂乱背景、文字水印、过重阴影",
    },
    "小红书": {
        "composition": "适合竖图 3:4 构图，氛围清新，主体自然突出",
        "subject_ratio": "主体占画面约 60%，留白适配笔记封面",
        "resolution": "高清清晰，柔和锐利",
        "forbidden": "杂乱背景、文字水印、过重阴影",
    },
}

# 逐类型版式 / 构图差异化指令（让「类型」配置明显改变画面版式）。
# 与 MARKET_PROFILES / PLATFORM_PROFILES 同级，纯数据可维护。
TYPE_LAYOUT: dict[str, str] = {
    "bg": "纯白背景，产品居中正面展示，无场景无道具，极简干净",
    "amz": "纯白背景，产品正面单图，符合亚马逊主图规范，无文字",
    "detail": "超大特写镜头，聚焦局部材质与工艺细节，背景虚化突出纹理",
    "detail2": "局部细节分点特写，关键工艺 / 功能点清晰放大",
    "angle": "多视角旋转展示（如 3/6/8 视角拼贴或环绕），呈现外观结构",
    "hero": "首屏吸睛大图，强视觉冲击构图，主体突出有记忆点",
    "usp": "卖点图形化版式，核心卖点以图标 / 图形 + 少量文案组合呈现",
    "pain": "痛点 → 解决方案对比版式，左痛点右方案，直观对比",
    "scene": "真实使用场景融入，产品在生活化环境中自然呈现",
    "cmp": "使用前 / 后 或 我方 / 竞品 左右分屏对比，差异一目了然",
    "design": "设计草图与成品对比或结构示意，讲解设计亮点",
    "ship": "包装状态 / 安装步骤图示，步骤清晰可读",
    "spec": "尺寸参数标注示意图，关键参数环绕产品呈现",
    "pkg": "包装展示效果，包装本体与开箱质感呈现",
    "tryon": "人物上身 / 上手效果展示，产品真实穿戴状态",
    "model": "人物代言互动，手持 / 佩戴 / 演示产品引导购买",
    "buyer": "真实买家亲善氛围，人物自然使用产品的生活化画面",
    "promo": "促销海报版式，活动信息突出，适合投放",
    "custom": "按补充说明自由呈现画面",
}

# 抽象风格词 → 量化视觉指令
#   键为配置项下拉值（visual_style / tone_tendency / 个性化风格词），
#   值为可直接进入提示词的具象视觉描述。
STYLE_VOCAB: dict[str, str] = {
    # 整体视觉风格
    "高级质感风": "影棚柔光从侧上方打光，面料纹理高清晰呈现，肤质细腻通透，轻微立体轮廓光勾勒体积，整体无廉价过曝，商业高级感",
    "清新自然风": "明亮自然窗光，通透干净的画面，柔和低饱和清新配色，轻松生活化氛围，留白透气不刻意",
    "科技未来感": "冷调硬光与霓虹边缘光，金属 / 玻璃冷质感，几何化构图与锐利高对比，未来科技氛围",
    "复古怀旧风": "暖调柔光，胶片颗粒质感，低对比柔和过渡，复古暖棕色调，怀旧氛围",
    "简约极简风": "均匀柔光，极简纯色背景，大量留白，主体绝对清晰，无多余元素，克制高级",
    "活泼可爱风": "明亮糖果色温，圆润柔和的造型光，轻松欢快的明快氛围，点缀可爱元素",
    # 色调倾向
    "低饱和高级灰": "低饱和度高级灰调，柔和统一，质感沉稳",
    "莫兰迪色系": "莫兰迪低饱和灰调，温柔高级，色彩相互协调",
    "明亮清新": "明亮通透配色，清新自然，轻快干净",
    "暗黑酷感": "暗调背景，强对比光影，冷峻酷感",
    # 氛围浓度（个性化）
    "轻度氛围": "极简纯色背景，仅微弱渐变光影，氛围占比≤10%，视觉重心100%在人物服装",
    "中度氛围": "适度环境光影与场景暗示，氛围占比约 30%，不抢主体",
    "强氛围": "明显场景氛围与光影，氛围占比约 50%，主体仍清晰",
    # 视觉强化（个性化）
    "质感放大": "大比例呈现材质肌理与反光细节，强化触感联想",
    "色彩冲击": "服装主色与背景低对比撞色，突出主体不杂乱",
    "动态模糊": "局部动态模糊营造速度感与活力",
    "光影对比": "强光影反差塑造立体体积与戏剧感",
    "虚实结合": "主体清晰、背景虚化的层次分离",
    "构图张力": "动态构图与非常规角度，增强视觉冲击",
}

# 价值聚焦（个性化「聚焦什么」）→ 视觉重心指令，与 M3 品质质感描述互补不重复
VALUE_FOCUS_VOCAB: dict[str, str] = {
    "品质": "视觉重心聚焦面料质感与精细做工，凸显高品质",
    "功能": "视觉重心聚焦产品功能与使用场景，凸显实用性",
    "价格": "视觉重心聚焦高性价比的直观呈现",
    "情感": "视觉重心聚焦情感联结与使用愉悦感",
    "场景": "视觉重心聚焦真实使用场景的代入感",
    "设计": "视觉重心聚焦设计美学与结构巧思",
    "服务": "视觉重心聚焦安心服务保障感",
}

# 价值暗示（个性化「怎么暗示价值」）→ 视觉暗示指令；
# 注意：「品质细节」故意不在此映射——它由 M3 的「面料垂坠肌理…」统一负责，避免重复
VALUE_HINT_VOCAB: dict[str, str] = {
    "稀有材料": "以稀有 / 特殊材质的独有质感暗示价值，不靠文字",
    "工艺精度": "以毫米级工艺精度细节暗示价值，不靠文字",
    "设计奖项": "以获奖级设计语言暗示价值，不靠文字",
    "用户好评": "以真实使用好评氛围暗示价值，不靠文字",
    "品牌背书": "以高端品牌调性暗示价值，不靠文字",
}

# 修图规范（全局统一追加，解决「过度美颜/色彩失真」隐性短板）
GLOBAL_RETROUCH: str = "自然肤质精修，不夸张瘦脸塑形，面料色彩1:1真实还原，无过度美颜失真"

# 允许在画面放置文字的策划类型（其余类型一律零文字）
#   promo : 活动海报（价格 / CTA 等信息层级需要文字）
#   usp   : 核心卖点图（一句话卖点 + 图形强化）
COPY_ALLOWED_TYPES: set[str] = {"promo", "usp"}

# ─────────────────────────────────────────────────────────────
# 特性开关（上线可统一关闭；本地调试按需开启）
#   查看每张图的提示词：环境变量 GALLERY_PROMPT_VIEW=1 开启，默认关闭
# ─────────────────────────────────────────────────────────────
GALLERY_FEATURES: dict[str, bool] = {
    "show_prompt": os.getenv("GALLERY_PROMPT_VIEW", "0") == "1",
}
