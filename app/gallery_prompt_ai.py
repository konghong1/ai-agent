"""电商套图 · AI 驱动提示词生成引擎（重构核心）。

设计目标（对应产品诉求）：
- 旧引擎 ``gallery_prompt.py`` 用 86 个配置项硬编码拼装，同配置出图千篇一律、
  无法适配任意产品图。本模块改为「把用户的【配置 + 卖点 + 参考图】交给 Agnes
  2.0 Flash 多模态大模型，由 AI 理解产品外观并写出高质量提示词」。
- 我们**只**把「用户配置 + 用户输入」作为 AI 的上下文（不自己拼接提示词），
  创意部分完全交给模型，从而保证不同产品 / 不同配置都能产出差异化、贴合产品
  的提示词。

降级策略：AI 调用不可达 / 超时 / 解析失败时，自动回退到 ``gallery_prompt``
模板引擎（标记 prompt_source="template"），保证系统不挂。

依赖：``app.settings`` 中的 OPENAI_API_KEY（或 AGNES_API_KEY）/
OPENAI_BASE_URL（或 AGNES_BASE_URL）/ OPENAI_MODEL（或 AGNES_MODEL，已配置为 Agnes 2.0 Flash）。
多模态图片以 base64 data URL 内联传入。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from app.settings import get_settings

logger = logging.getLogger(__name__)

# ── 超时与温度 ────────────────────────────────────────────────
# 提示词生成需要「看懂图 + 写文案」，给足 90s；温度略高以放大产品差异，
# 但不过高以免同一产品每次跳变太大。
AI_PROMPT_TIMEOUT = 120
AI_FILL_TIMEOUT = 90
AI_PROMPT_TEMPERATURE = 0.75
AI_FILL_TEMPERATURE = 0.7
# agnes-2.0-flash 是带思维链的推理模型：思考过程会占满 token 额度，
# 导致 content（最终答案）为空。必须给足 max_tokens 让推理完成、答案落进 content。
# 实测 4096 可稳定返回；重试时再上调到 6144 / 8192 兜底超长推理。
AI_PROMPT_MAX_TOKENS = 6144
AI_FILL_MAX_TOKENS = 2048

_PROMPT_SYSTEM = """你是一位顶尖的电商视觉创意总监与图像提示词工程师，精通 Midjourney / DALL·E / Stable Diffusion / 通义万相等主流图像生成模型的中英文提示词写法。

任务：根据商家提供的【产品参考图】+【生成方向】+【核心卖点(参考,不可修改)】+【配置项】，写一份可直接用于图像生成模型的高质量提示词。

一、强制 8 维结构（必须全部覆盖、且写细，不得只写两三个维度就结束）：
   [主体] 明确产品主体、在画面中的位置/占比、姿态朝向，外观严格以参考图为准；
   [细节修饰] 材质纹理、工艺、配色、logo、边缘、结构等关键细节刻画；
   [场景环境] 背景/布景/环境氛围，是纯色还是真实场景，场景元素；
   [构图视角] 景别(全身/半身/特写)、机位角度、构图方式(居中/三分法/对称/留白)；
   [光影质感] 光线类型(自然光/棚拍柔光/硬光/逆光)、光位、阴影、质感；
   [画质技术参数] 镜头/器材暗示、分辨率、锐度、大师级渲染词；
   [风格参考] 视觉风格(简约高级/杂志感/科技感/生活化)与参考流派；
   [负面约束] 明确不要的元素(without/no：水印、文字、变形、多余人物、杂乱背景)。
   在 prompt_cn / prompt_en 中按上述维度组织内容（维度之间自然过渡，不必写死方括号标题），确保每个维度都有具体描述。

二、单图多视角 / 多场景（关键：当用户选择拼贴 / 分屏 / 宫格 / 多场景 / 多角度等版式时）：
   必须把这整张图当作一个"构图版式"来设计，而不是只描述单一场景：
   1) 先说明整图的版式网格：如「2×2 四宫格」「3×3 九宫格」「左右分屏」「上下分屏」「田字格」「主图+辅图环绕」；
   2) 对每一个格子/分屏，逐一写明该格内的【主体(该具体视角/该使用状态) + 场景环境 + 光影质感 + 构图视角 + 细节修饰】，使每个格都有独立且具体的场景/角度/细节，绝不空泛重复；
   3) 保持产品外观(颜色/版型/材质/logo)跨格严格一致，仅改变视角、场景、光影与细节侧重；
   4) 说明格子之间的分隔方式(细线/留白/统一底色)与整体统一的光影基调，让它们看起来是一张协调的整图而非拼凑。

三、差异化与细节：
   - 必须根据"每幅图自身的场景与参数"写出差异化内容，不要套用千篇一律的模板腔；
   - 描述要具体、有画面感（具体到光线方向、材质触感、景别距离、环境元素），避免空泛形容词堆砌；
   - 尊重参考图产品外观，不改产品本身；核心卖点只作理解参考，不杜撰图中没有的特征。

四、输出格式：纯 JSON，不要任何额外解释：
{
  "prompt_cn": "严格按上述 8 维组织的中文提示词（画面感强、细节足；多视角/多场景时按版式逐格描述）",
  "prompt_en": "纯英文提示词（逗号分隔短语，无中文；负面用 without/no；多场景时英文同样逐格描述）"
}
5. prompt_en 必须为纯英文，严禁任何中文字符（硬性约束，规格参数图也不例外）。

六、规格参数图额外规则（画面严禁任何文字/数字/字母/表格，文字与尺码表由后端统一精确叠加）：
   - 纯视觉图 + 后端文字叠加：图像模型生成产品视觉，并用淡淡的测量引导线 / 指示点标出关键尺寸部位（如衣长、胸围、袖长、腰围），引导线可以有、但严禁带任何文字、数字或字母；
   - 产品置左约 60% 宽，右侧预留干净的浅灰空白面板区（供后端叠加尺码表）；
   - 服饰类可附淡淡的人体 / 比例剪影作参照（同样无文字）；
   - 浅灰纯色背景，电商信息图质感；
   - 用户的「规格参数原文」不进入图像模型（由后端叠加渲染），但「补充说明」可指导你突出哪些产品特性与尺寸部位。"""

# ── 批量提示词生成策略 ─────────────────────────────────────────
# 默认方案 1：单次批量调用（最快）。若生成质量不理想，可设置环境变量
# AI_PROMPT_BATCH_MODE=2 切换到并发并行调用（每 item 独立 AI 调用，但并行执行）。
AI_PROMPT_BATCH_TEMPERATURE = 0.7
AI_PROMPT_BATCH_MAX_TOKENS = 8192

_PROMPT_BATCH_SYSTEM = """你是一位顶尖的电商视觉创意总监与图像提示词工程师，精通 Midjourney / DALL·E / Stable Diffusion / 通义万相等主流图像生成模型的中英文提示词写法。

任务：商家已为同一款产品规划了多个出图方向，并提供了【产品参考图】+【公共上下文（核心卖点、市场配置、通用设置）】+【每个方向的类型与侧重点】。请你从整体视角把握这款产品，为每个方向分别写出可直接用于图像生成模型的高质量提示词，确保整套图风格统一、像同一品牌/同一商品的系列套图，同时每个方向又有明确差异。

一、强制 8 维结构（每个方向都必须全部覆盖、且写细，不得只写两三个维度就结束）：
   [主体] + [细节修饰] + [场景环境] + [构图视角] + [光影质感] + [画质技术参数] + [风格参考] + [负面约束]
   在 prompt_cn / prompt_en 中按上述维度组织内容（维度之间自然过渡，不必写死方括号标题），确保每个维度都有具体描述。

二、单图多视角 / 多场景（关键：当某个方向的类型/排版选择拼贴 / 分屏 / 宫格 / 多场景 / 多角度等版式时）：
   该方向的提示词必须把这整张图当作一个"构图版式"设计——先说明版式网格（如 2×2 四宫格 / 3×3 九宫格 / 左右分屏 / 上下分屏 / 田字格 / 主图+辅图环绕），再对每一个格子逐一写明该格的【主体(该视角/该状态) + 场景环境 + 光影质感 + 构图视角 + 细节修饰】，使每格有独立具体的场景/角度/细节、绝不空泛重复；产品外观跨格一致，格间细线/留白分隔，整图光影统一。

三、差异化与细节：
   - 每个方向必须根据"该图自身的场景与参数"写出差异化内容，不要千篇一律；
   - 描述要具体、有画面感（光线方向、材质触感、景别距离、环境元素），避免空泛堆砌；
   - 尊重参考图产品外观，不改产品本身；核心卖点只作理解参考，不杜撰图中没有的特征。

四、输出格式：纯 JSON 数组，不要任何额外解释。每个元素格式严格如下：
[
  {
    "item_index": 0,
    "prompt_cn": "严格按 8 维组织的【完整】中文提示词（多视角/多场景时逐格描述）",
    "prompt_en": "【完整】纯英文提示词（逗号分隔短语，无中文）",
    "prompt_cn_short": "该方向最简短的中文场景提示词（仅保留主体+场景+关键风格/角度，长度约为完整版 1/3）",
    "prompt_en_short": "该方向最简短的纯英文场景提示词（逗号分隔短语，无中文，实际送图像模型生成时使用）"
  },
  ...
]
5. 数组长度必须与输入方向数量一致；item_index 必须按输入顺序从 0 开始，不得错位。
6. 每个 prompt_en / prompt_en_short 必须为纯英文，严禁任何中文字符（规格参数图的画面严禁文字/数字/表格，均由后端叠加；可含淡淡测量引导线，但不得带任何文字）。
7. 整套提示词需保持同一产品的视觉一致性（颜色/版型/材质不变），但每个方向应根据其「类型 + 个性配置 + 补充说明 + 版式要求」突出不同侧重点。
8. prompt_cn_short / prompt_en_short 是「最简短场景提示词」：用最少的词传达该场景最核心的视觉要素，必须让图像模型仍能生成符合该场景的结果，但不得冗长重复完整版内容。"""

_FILL_SP_SYSTEM = """你是一位资深电商选品与文案专家。商家上传了一张【产品图】，请你看图理解这个产品，并输出结构化的卖点信息，帮助后续 AI 生成套图。

输出**纯 JSON**，不要任何额外解释，格式严格如下：
{
  "product_name": "产品名称（简洁准确）",
  "selling_points": "核心卖点（2-4 句，突出差异化优势与用户价值）",
  "audience": "适用人群（谁会买、谁用得上）",
  "scene": "期望场景（产品最适合的使用/展示场景）",
  "params": "具体参数（关键规格、材质、尺寸、容量等可量化信息，没有就留空字符串）"
}
所有字段用中文填写，务必基于图片中真实可见的产品特征，不要编造图片里看不到的规格。"""

_FILL_CFG_SYSTEM = """你是一位电商套图策划专家。商家已经为某一种【套图类型】选了一些配置，并上传了【产品图】。请你看图理解产品，并基于该类型的最佳实践，帮商家把这套配置补全 / 优化得更合理。

你会收到：生成方向（类型）、商家已填的个性化设置与通用设置、核心卖点。
请输出**纯 JSON**，不要任何额外解释，格式严格如下：
{
  "common_settings": { /* 通用设置建议：可含 copy_language / target_market / ecommerce_platform / visual_style / copy_need / tone_tendency，只输出你认为更优的键，未填的给推荐值 */ },
  "personal_settings": { /* 该类型个性化设置建议：键为字段中文标签，值为推荐值；只输出有价值的键 */ },
  "note": "一句话补充说明建议（基于产品与卖点，给 AI 生成时的构图/文案方向；可为空字符串）"
}
务必基于图片中真实产品的特征给出贴合建议，不要套用与产品无关的默认值。"""


def _get_ai_model() -> str:
    """ Agnes 多模态 chat 默认模型：优先 AGNES_MODEL，其次非默认的 OPENAI_MODEL，兜底 agnes-2.0-flash。
    避免 settings.openai_model 默认的 gpt-4o-mini 误用到 Agnes 栈。"""
    s = get_settings()
    if explicit := os.getenv("AGNES_MODEL"):
        return explicit
    if s.openai_model and s.openai_model != "gpt-4o-mini":
        return s.openai_model
    return "agnes-2.0-flash"


# ─────────────────────────────────────────────────────────────
# 底层：Agnes 多模态 chat 调用（OpenAI 兼容，proxy=None 直连）
# ─────────────────────────────────────────────────────────────

def _get_ai_key() -> str | None:
    """兼容 OPENAI_API_KEY 与 AGNES_API_KEY 两种环境变量命名。"""
    s = get_settings()
    return s.openai_api_key or os.getenv("AGNES_API_KEY")


def _get_ai_base_url() -> str | None:
    """兼容 OPENAI_BASE_URL 与 AGNES_BASE_URL 两种环境变量命名。"""
    s = get_settings()
    return s.openai_base_url or os.getenv("AGNES_BASE_URL")


def _build_client():
    from openai import AsyncOpenAI
    import httpx

    return AsyncOpenAI(
        api_key=_get_ai_key() or "",
        base_url=_get_ai_base_url(),
        http_client=httpx.AsyncClient(proxy=None),
        timeout=AI_PROMPT_TIMEOUT,
        # 上游 chat 接口偶发不可达时快速失败，避免默认 2 次重试叠加 timeout 把单任务
        # 卡死过久（配合 gallery worker 并发消费，单任务卡顿也不会冻死全局）。
        max_retries=1,
    )


async def _chat_multimodal(
    system: str, text: str, image_data_url: str | None, temperature: float, max_tokens: int = AI_PROMPT_MAX_TOKENS
) -> str:
    """调用 Agnes 2.0 Flash 多模态接口，返回模型文本。

    agnes-2.0-flash 为带思维链的推理模型：最终答案在 ``content``，思考过程在
    ``reasoning_content``。必须给足 ``max_tokens``，否则推理占满额度后 content 为空。
    """
    client = _build_client()
    model = _get_ai_model()

    user_content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    if image_data_url:
        user_content.append({"type": "image_url", "image_url": {"url": image_data_url}})

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]

    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    msg = resp.choices[0].message
    return msg.content or ""


def _run_async(coro):
    """在同步上下文（worker 守护线程 / 线程池路由）中运行协程。

    当前所有调用方都是同步函数（worker 线程、FastAPI 线程池路由），所在线程
    没有正在运行的事件循环，因此用 ``asyncio.run`` 是安全的。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 极端兜底：若已有运行中的 loop（不应发生），新开线程跑
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(lambda: asyncio.run(coro)).result()


# ─────────────────────────────────────────────────────────────
# 工具：把用户配置组织成「自然语言意图描述」（不是拼接提示词）
# ─────────────────────────────────────────────────────────────

def build_user_config_text(
    project: Any,
    item: Any,
    effective_product_image: str | None = None,
    ratio: str | None = None,
) -> str:
    """把用户的配置 + 卖点 + 类型，转成一段给 AI 看的自然语言意图描述。

    这里**不做任何提示词拼装**——只忠实描述「用户配置了什么、希望产出什么类型」，
    创意（写出贴合产品的提示词）完全交给模型。包含：
      · 核心卖点（用户输入）
      · 市场配置（项目级全局配置：目标市场 / 平台 / 人群 / 品类 / 季节 / 价格带）
      · 出图规划·个性化配置（该类型在策划台填的个性项）
      · 通用设置（文案语种 / 视觉风格 / 色调等）
      · 生成方向（类型）与出图比例
    """
    from app.gallery_config import get_plan_type

    t = get_plan_type(item.type_id) if item else None
    type_title = t["title"] if t else (item.type_id if item else "未指定类型")
    type_desc = t.get("desc", "") if t else ""

    lines: list[str] = []
    lines.append(f"【生成方向】{type_title}" + (f"：{type_desc}" if type_desc else ""))

    sp = (getattr(project, "selling_points", "") or "").strip()
    if sp:
        lines.append(f"【核心卖点】{sp}")

    # 补充说明（用户在出图规划项里自由填写的额外方向，AI 据此调整文案/构图建议）
    note = (getattr(item, "note", None) or "").strip()
    if note:
        lines.append(f"【补充说明】{note}")

    # 市场配置（项目级全局配置：目标市场 / 平台 / 人群等）
    market = getattr(project, "market_config", None) or {}
    if market:
        mlines = []
        market_label_map = {
            "target_market": "目标市场",
            "platform": "销售平台",
            "audience": "目标人群",
            "category": "品类",
            "season": "季节/节点",
            "price_band": "价格带",
        }
        for k, v in market.items():
            if v:
                mlines.append(f"- {market_label_map.get(k, k)}：{v}")
        if mlines:
            lines.append("【市场配置】\n" + "\n".join(mlines))

    # 出图规划·个性化配置（该类型在策划台单独设置的个性项）
    personal = getattr(item, "personal_settings", None) or {}
    if personal:
        plines = []
        for k, v in personal.items():
            if v:
                plines.append(f"- {k}：{v}")
        if plines:
            lines.append("【出图规划·个性化配置】\n" + "\n".join(plines))

    # 规格参数图：数据不进图像模型，仅告知模型「画面无文字、数据交由后端叠加」
    if getattr(item, "type_id", None) == "spec":
        spec_text = (personal.get("规格参数原文") or "").strip()
        if spec_text:
            lines.append(
                "【规格参数图·渲染策略】本类型为规格参数图，采用「纯视觉图 + 后端文字叠加」："
                "图像模型生成产品视觉，并用淡淡的测量引导线/指示点标出关键尺寸部位（衣长、胸围、袖长、腰围等，严禁带任何文字/数字），"
                "产品置左、右侧预留干净的浅灰面板供后端叠加尺码表；"
                "严禁在画面中绘制任何文字、数字、字母或表格——尺码表与标注由后端用真实字体精确叠加，不进入图像模型。"
                f"用户提供的真实规格数据（供叠加层使用，不进图像模型）：\n{spec_text}"
            )
        else:
            lines.append(
                "【规格参数图·渲染策略】本类型为规格参数图，采用「纯视觉图 + 后端文字叠加」："
                "图像模型生成产品视觉，并用淡淡的测量引导线/指示点标出关键尺寸部位（严禁带任何文字/数字），"
                "产品置左、右侧预留干净的浅灰面板供后端叠加尺码表；"
                "严禁在画面中绘制任何文字、数字、字母或表格；用户未提供规格数据，后端叠加层将用示例占位。"
            )

    # 通用设置
    common = getattr(item, "common_settings", None) or {}
    if common:
        clines = []
        label_map = {
            "copy_language": "文案语种",
            "target_market": "目标市场",
            "ecommerce_platform": "电商平台",
            "visual_style": "视觉风格",
            "copy_need": "文案需求",
            "tone_tendency": "色调倾向",
        }
        for k, v in common.items():
            if v:
                clines.append(f"- {label_map.get(k, k)}：{v}")
        if clines:
            lines.append("【通用设置】\n" + "\n".join(clines))

    if ratio:
        lines.append(f"【出图比例】{ratio}")

    # 单图多视角/多场景：命中拼贴/分屏/宫格/多场景/多角度版式时，注入逐格构图指令
    multi = _detect_multi_cell(item)
    if multi:
        lines.append(multi)

    lines.append(
        "【参考图】已提供产品参考图，请据此理解产品的真实外观（颜色 / 版型 / 材质 / logo / 结构），"
        "并在提示词中保持产品一致，不得改变产品本身。"
    )
    lines.append(
        "【你的任务】不要套用通用模板，请基于以上「用户配置 + 参考图」理解这个真实产品，"
        "写出一份贴合该产品、符合上述生成方向的差异化高质量提示词（中文展示版 + 纯英文生成版）。"
    )
    return "\n\n".join(lines)


# ─────────────────────────────────────────────────────────────
# 工具：JSON 解析（模型偶尔会在 JSON 外裹一层 ```json 或解释）
# ─────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    # 去掉 ```json ... ``` 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    # 截取首个 { 到末个 }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _strip_cjk(s: str, type_id: str | None = None) -> str:
    """把英文提示词里残留的中文字符清掉（硬约束兜底）。

    规格参数图也不例外：该类型画面严禁文字（文字由后端叠加层渲染），
    因此 prompt_en 也必须保持纯英文，不能泄漏中文。
    """
    return re.sub(r"[\u4e00-\u9fff]", "", s).strip()


def _derive_short(text: str, max_phrases: int = 8) -> str:
    """模型未返回 prompt_*_short 时的兜底：从完整提示词提炼最短场景版。

    仅做轻量切分（按中/英文逗号、分号取前 N 个短语），保证主体+场景+关键
    风格/角度仍在；不调用大模型，纯规则、零成本。用于让「最简短场景提示词」
    功能始终生效（实际出图优先用 short 降本提速）。
    """
    if not text:
        return ""
    for sep in (",", "，"):
        parts = [p.strip() for p in text.split(sep) if p.strip()]
        if len(parts) > 1:
            return sep.join(parts[:max_phrases]).strip()
    # 无逗号分隔：按长度截断，避免把一整段塞进 short
    return text.strip()[:200].strip()


# ── 单图多视角 / 多场景 / 拼贴 / 分屏 版式检测 ───────────────
# 命中下列关键词即视为「单图多格」版式，需要 AI 在单图内逐格描述不同场景/角度。
_MULTI_CELL_KEYWORDS = [
    "拼接", "拼贴", "宫格", "分屏", "多场景", "多视角", "多角度", "多细节",
    "组合", "collage", "grid", "九宫格", "四宫格", "田字格", "左右对比", "上下对比",
    "主场景配辅", "产品主体+多场景", "产品不同状态", "不同时间季节",
    "同一人物不同场景", "不同人物同一场景", "多个细节", "局部细节拼接",
    "两个角度", "三个角度", "四个及以上角度", "环绕", "多面旋转",
]
_MULTI_CELL_RE = re.compile("|".join(re.escape(k) for k in _MULTI_CELL_KEYWORDS), re.IGNORECASE)


def _detect_multi_cell(item: Any) -> str | None:
    """检测某出图项是否为「单图多视角/多场景/拼贴」版式。

    返回 ``None`` 表示单场景单视角（无需逐格描述）；否则返回一段给 AI 的
    中文版式指令，告诉模型在单图内按网格逐格描述不同视角/场景。
    """
    type_id = getattr(item, "type_id", None)
    personal = getattr(item, "personal_settings", None) or {}
    common = getattr(item, "common_settings", None) or {}
    haystack = " ".join(str(v) for v in list(personal.values()) + list(common.values()))
    is_angle = type_id == "angle"
    if not (is_angle or _MULTI_CELL_RE.search(haystack)):
        return None
    # 多角度 / 多视角：逐格呈现不同角度
    if is_angle or ("角度" in haystack or "视角" in haystack or "拼贴" in haystack or "环绕" in haystack):
        return (
            "【版式指令·多视角拼贴】本图需在单张画面内呈现产品的多个视角/角度"
            "（如正面、侧面、背面、45°、俯视、细节特写等），按网格或环绕布局排列"
            "（如 2×2 四宫格、3×3 九宫格、田字格或环形排布）。"
            "为每一个格子逐一写明该格的【主体(该具体视角) + 细节修饰 + 构图视角 + 光影质感】，"
            "使每格呈现明确不同的角度与细节；产品外观（颜色/版型/材质/logo）跨格严格一致，"
            "仅改变视角、距离与光影侧重；格子之间以细线或留白分隔，整图光影基调统一。"
        )
    # 多场景
    return (
        "【版式指令·多场景拼接】本图需在单张画面内拼接多个使用/展示场景"
        "（如居家、户外、不同季节、不同使用状态等），按版式网格排布"
        "（如 2×2 四宫格、3×3 九宫格、左右分屏、上下分屏、主场景+辅场景环绕等）。"
        "为每一个格子逐一写明该格的【场景环境 + 主体(该场景下的产品状态) + 构图视角 + 光影质感 + 细节修饰】，"
        "使每格呈现明显不同的场景与氛围（而非空泛重复）；产品外观（颜色/版型/材质/logo）跨格严格一致，"
        "仅改变场景、光影与细节侧重；格子之间以细线或留白分隔，整图保持同一品牌/商品调性、光影统一。"
    )


# ─────────────────────────────────────────────────────────────
# 对外 1：根据配置 + 参考图，AI 生成图片提示词
# ─────────────────────────────────────────────────────────────

def generate_prompt_via_ai(
    project: Any,
    item: Any,
    model_name: str | None = None,
    effective_product_image: str | None = None,
    ratio: str | None = None,
) -> dict:
    """调用 Agnes 多模态生成图片提示词。

    返回结构：
      - prompt: 中文展示版
      - prompt_en: 英文生成版（送图像模型）
      - prompt_source: "ai" | "template"
      - prompt_input: 喂给大模型的完整意图描述（用户配置 + 参考图说明，非最终提示词），用于溯源
      - prompt_raw: 大模型原始返回文本（解析前的 JSON 字符串），AI 路径才有，模板降级为空

    AI 路径失败时降级到 ``gallery_prompt.build_prompt_bilingual``（source=template）。
    """
    from app import gallery_prompt

    # 参考图内联为 base64（本地图非公开 URL，必须内联）
    image_url = None
    if effective_product_image:
        from app.gallery_service import _gallery_file_data_url

        image_url = _gallery_file_data_url(effective_product_image)

    # 这一步只「告诉模型用户配了啥、希望产出啥类型」，不自己拼提示词
    user_text = build_user_config_text(
        project, item, effective_product_image=effective_product_image, ratio=ratio
    )

    if not _get_ai_key():
        logger.warning("未配置 OPENAI_API_KEY / AGNES_API_KEY，跳过 AI 提示词，降级模板引擎")
        pd = gallery_prompt.build_prompt_bilingual(
            project, item, model_name=model_name, effective_product_image=effective_product_image
        )
        return {
            "prompt": pd["prompt"],
            "prompt_en": pd["prompt_en"],
            "prompt_source": "template",
            "prompt_input": "（AI 提示词引擎不可用：未配置 OPENAI_API_KEY / AGNES_API_KEY，未调用大模型）",
            "prompt_raw": "",
        }

    # agnes-2.0-flash 是推理模型，max_tokens 不够会导致 content 为空；
    # 失败（空 / 解析失败）时上调 max_tokens 重试，最多 3 次。
    raw: str = ""
    mt = AI_PROMPT_MAX_TOKENS
    for attempt in range(3):
        try:
            raw = _run_async(
                _chat_multimodal(_PROMPT_SYSTEM, user_text, image_url, AI_PROMPT_TEMPERATURE, max_tokens=mt)
            )
        except Exception as exc:
            logger.warning("AI 提示词调用异常（第%d次）：%s", attempt + 1, exc)
            continue
        data = _extract_json(raw)
        cn = (data or {}).get("prompt_cn", "").strip()
        en = _strip_cjk((data or {}).get("prompt_en", "") or "", type_id=getattr(item, "type_id", None)).strip()
        if cn and en:
            logger.info("AI 提示词生成成功（source=ai，第%d次），cn=%d字 en=%d字", attempt + 1, len(cn), len(en))
            return {
                "prompt": cn,
                "prompt_en": en,
                "prompt_source": "ai",
                "prompt_input": user_text,  # 溯源：喂给模型的输入（用户配置意图）
                "prompt_raw": raw,          # 溯源：模型原始输出（未解析）
            }
        logger.warning("AI 第%d次返回不可用（content 空/解析失败），上调 max_tokens 重试：%r", attempt + 1, (raw or "")[:120])
        mt = min(mt * 2, 8192)

    # 三次重试仍失败：降级模板，但保留「喂给 AI 的输入」与「最后一次原始返回」供排查
    logger.warning("AI 提示词生成失败（含重试），降级模板引擎：%r", (raw or "")[:200])
    pd = gallery_prompt.build_prompt_bilingual(
        project, item, model_name=model_name, effective_product_image=effective_product_image
    )
    return {
        "prompt": pd["prompt"],
        "prompt_en": pd["prompt_en"],
        "prompt_source": "template",
        "prompt_input": user_text,  # 即便降级也展示「我们实际喂给 AI 的配置」
        "prompt_raw": raw,          # 最后一次 AI 原始返回（可能为空，便于核对）
    }


# ─────────────────────────────────────────────────────────────
# 批量提示词生成：策略 A（单次批量调用）
# ─────────────────────────────────────────────────────────────

def _get_batch_mode() -> int:
    """读取批量提示词生成策略。
    默认方案 1（单次批量调用）；设置 AI_PROMPT_BATCH_MODE=2 切换到方案 2（并发并行调用）。"""
    return 2 if os.getenv("AI_PROMPT_BATCH_MODE", "1").strip() == "2" else 1


def _extract_json_array(text: str) -> list | None:
    """从模型返回中解析 JSON 数组（兼容 ```json ... ``` 代码块）。"""
    if not text:
        return None
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if m:
        text = m.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def build_batch_user_config_text(project: Any, meta: list[dict]) -> str:
    """为批量提示词生成构建组合输入：公共上下文 + 每个出图方向的侧重点。"""
    from app.gallery_config import get_plan_type

    lines = ["【任务】为同一款产品的多个出图方向批量生成图像提示词。"]
    sp = (getattr(project, "selling_points", "") or "").strip()
    if sp:
        lines.append(f"【核心卖点】{sp}")

    market = getattr(project, "market_config", None) or {}
    if market:
        mlines = []
        market_label_map = {
            "target_market": "目标市场",
            "platform": "销售平台",
            "audience": "目标人群",
            "category": "品类",
            "season": "季节/节点",
            "price_band": "价格带",
        }
        for k, v in market.items():
            if v:
                mlines.append(f"- {market_label_map.get(k, k)}：{v}")
        if mlines:
            lines.append("【市场配置】\n" + "\n".join(mlines))

    lines.append(
        "【参考图】已提供一张产品参考图，以下所有出图方向均基于同一款产品，"
        "请保持产品外观（颜色 / 版型 / 材质 / logo / 结构）严格一致，不得改变产品本身。"
    )
    lines.append("【出图方向列表】（按顺序，item_index 从 0 开始）")
    for i, m in enumerate(meta):
        item = m["item"]
        t = get_plan_type(item.type_id)
        title = t["title"] if t else (item.type_id or "未指定类型")
        lines.append(f"{i}. 【{title}】")
        personal = getattr(item, "personal_settings", None) or {}
        for k, v in personal.items():
            if v:
                lines.append(f"   - {k}：{v}")
        common = getattr(item, "common_settings", None) or {}
        for k, v in common.items():
            if v:
                lines.append(f"   - 通用/{k}：{v}")
        note = (getattr(item, "note", None) or "").strip()
        if note:
            lines.append(f"   - 补充说明：{note}")
        if getattr(item, "type_id", None) == "spec":
            lines.append(
                "   - 规格参数图：生成产品视觉并用淡淡测量引导线/指示点标出关键尺寸部位（衣长、胸围、袖长等，严禁带文字/数字），"
                "右侧预留浅灰面板供后端叠加尺码表；画面严禁任何文字/数字/表格。"
            )
        lines.append(f"   - 出图比例：{m['ratio']}")
        # 单图多视角/多场景：命中拼贴/分屏/宫格/多场景/多角度版式时，注入逐格构图指令
        mc = _detect_multi_cell(item)
        if mc:
            lines.append(f"   - 版式要求（单图多格）：{mc}")

    # 不再对每个方向重复「写差异化提示词」这类笼统指令——整批作为一套系列套图
    # 由结尾的【综合提示词要求】一次性统一说明（含「最简短场景提示词」要求）。
    lines.append(
        "【综合提示词要求】以下所有出图方向将作为同一款产品的系列套图一次性生成，"
        "请整体把握、统一输出，不要再对每个方向重复「写差异化提示词」这类笼统指令：\n"
        "1) 每个方向各输出一份【完整差异化提示词】：prompt_cn（中文展示版）、prompt_en（英文生成版），"
        "按该方向的「类型 + 个性配置 + 补充说明 + 版式要求」写成贴合该方向、彼此不雷同的内容；\n"
        "2) 每个方向额外输出一份【最简短场景提示词】：prompt_cn_short（中文）、prompt_en_short（纯英文，送图像模型），"
        "只保留该场景最核心的视觉要素（主体 + 场景 + 关键风格/角度），长度压缩到完整版的约 1/3，"
        "但仍须让图像模型生成符合该场景的结果；\n"
        "3) 返回纯 JSON 数组，每个元素含 item_index（从0开始）、prompt_cn、prompt_en、prompt_cn_short、prompt_en_short；"
        "prompt_cn_short 与 prompt_en_short 为必填字段，每个元素都必须包含，缺失视为不合格输出；"
        "prompt_en 与 prompt_en_short 必须纯英文、无中文；规格参数图画面严禁文字/数字/表格（由后端叠加）。"
        "整套提示词围绕同一款产品，整体风格统一、各方向侧重点明确。"
    )
    return "\n\n".join(lines)


def generate_prompts_batch_mode_1(
    project: Any,
    meta: list[dict],
    model_name: str | None = None,
) -> dict[int, dict]:
    """方案 A：一次性为多个非自定义策划项生成提示词（单 AI 调用，返回 JSON 数组）。

    返回 {item.id: {prompt, prompt_en, prompt_source, prompt_input, prompt_raw}}。
    如果调用失败或返回不完整，返回已解析到的部分，由调用方对缺失项做兜底。
    """
    if not meta or not _get_ai_key():
        return {}

    # 取首个有参考图的项作为共享参考图
    image_url = None
    main_image = next((m["effective_product_image"] for m in meta if m.get("effective_product_image")), None)
    if main_image:
        from app.gallery_service import _gallery_file_data_url

        image_url = _gallery_file_data_url(main_image)

    user_text = build_batch_user_config_text(project, meta)
    raw = ""
    results: dict[int, dict] = {}
    # 项数越多，需要输出越长；按 1024 token/项 估算，上限 8192
    mt = min(4096 + 1024 * len(meta), AI_PROMPT_BATCH_MAX_TOKENS)
    for attempt in range(3):
        try:
            raw = _run_async(
                _chat_multimodal(
                    _PROMPT_BATCH_SYSTEM,
                    user_text,
                    image_url,
                    AI_PROMPT_BATCH_TEMPERATURE,
                    max_tokens=mt,
                )
            )
        except Exception as exc:
            logger.warning("AI 批量提示词调用异常（第%d次）：%s", attempt + 1, exc)
            continue
        data = _extract_json_array(raw)
        if isinstance(data, list):
            for i, entry in enumerate(data):
                idx = entry.get("item_index", i)
                if not isinstance(idx, int) or idx < 0 or idx >= len(meta):
                    continue
                m = meta[idx]
                cn = str(entry.get("prompt_cn", "") or "").strip()
                en = _strip_cjk(
                    str(entry.get("prompt_en", "") or ""),
                    type_id=getattr(m["item"], "type_id", None),
                ).strip()
                if cn and en:
                    cn_short = str(entry.get("prompt_cn_short", "") or "").strip()
                    if not cn_short:
                        # 模型未返回最短中文版 → 从完整中文提示词规则提炼兜底
                        cn_short = _derive_short(cn, max_phrases=6)
                    en_short = _strip_cjk(
                        str(entry.get("prompt_en_short", "") or ""),
                        type_id=getattr(m["item"], "type_id", None),
                    ).strip()
                    if not en_short:
                        # 模型未返回最短英文版 → 从完整英文提示词规则提炼兜底
                        en_short = _strip_cjk(
                            _derive_short(en, max_phrases=8),
                            type_id=getattr(m["item"], "type_id", None),
                        ).strip()
                    results[m["item"].id] = {
                        "prompt": cn,
                        "prompt_en": en,
                        "prompt_source": "ai",
                        "prompt_input": user_text,
                        "prompt_raw": raw,
                        # 最简短场景提示词：实际出图时优先使用 prompt_en_short（降本提速），
                        # 完整版 prompt_en 仍保留用于前端展示与溯源。
                        "prompt_short": cn_short,
                        "prompt_en_short": en_short,
                    }
        if len(results) == len(meta):
            break
        logger.warning(
            "AI 批量提示词第%d次返回不完整（%d/%d），上调 max_tokens 重试",
            attempt + 1,
            len(results),
            len(meta),
        )
        mt = min(mt * 2, AI_PROMPT_BATCH_MAX_TOKENS)

    if len(results) < len(meta):
        missing = [m["item"].id for m in meta if m["item"].id not in results]
        logger.warning("AI 批量提示词仍有缺失项：%s，将由调用方兜底", missing)
    return results


# ─────────────────────────────────────────────────────────────
# 对外 2：卖点 AI 帮写（根据产品图）
# ─────────────────────────────────────────────────────────────

def ai_write_selling_points(project: Any, db: Any = None) -> dict:
    """根据项目首张产品图，AI 输出结构化卖点。

    返回 {product_name, selling_points, audience, scene, params}（均为中文）。
    失败时返回全部空字符串的兜底结构。
    """
    empty = {"product_name": "", "selling_points": "", "audience": "", "scene": "", "params": ""}
    try:
        if not _get_ai_key():
            raise RuntimeError("未配置 OPENAI_API_KEY / AGNES_API_KEY")
        images = getattr(project, "images", None) or []
        img = next((i for i in images if getattr(i, "filename", None)), None)
        image_url = None
        if img:
            from app.gallery_service import _gallery_file_data_url

            du = _gallery_file_data_url(img.filename)
            image_url = du if du and du.startswith("data:") else None

        hint = ""
        sp = (getattr(project, "selling_points", "") or "").strip()
        if sp:
            hint = f"\n商家已手写的部分卖点（请参考并补全，不要重复矛盾）：{sp}"

        text = (
            "请看这张产品图，理解它是什么产品，并输出结构化卖点信息。"
            + hint
        )
        raw = _run_async(
            _chat_multimodal(_FILL_SP_SYSTEM, text, image_url, AI_FILL_TEMPERATURE)
        )
        data = _extract_json(raw)
        if data:
            return {
                "product_name": str(data.get("product_name", "") or ""),
                "selling_points": str(data.get("selling_points", "") or ""),
                "audience": str(data.get("audience", "") or ""),
                "scene": str(data.get("scene", "") or ""),
                "params": str(data.get("params", "") or ""),
            }
        logger.warning("卖点 AI 返回结构异常：%r", raw[:200])
    except Exception as exc:
        logger.warning("卖点 AI 帮写失败：%s", exc)
    return empty


# ─────────────────────────────────────────────────────────────
# 对外 3：类型配置 AI 帮写（根据产品图 + 类型）
# ─────────────────────────────────────────────────────────────

def ai_write_type_config(project: Any, type_id: str, current: dict | None = None) -> dict:
    """根据产品图 + 已选类型，AI 帮商家补全/优化该类型的配置。

    返回 {common_settings, personal_settings, note}，与旧 ai_fill 结构兼容，
    便于前端无缝替换。AI 失败则返回空结构（前端保持用户已填内容）。
    """
    empty = {"common_settings": {}, "personal_settings": {}, "note": ""}
    try:
        if not _get_ai_key():
            raise RuntimeError("未配置 OPENAI_API_KEY / AGNES_API_KEY")
        from app.gallery_config import get_plan_type, get_personal_fields

        t = get_plan_type(type_id)
        type_title = t["title"] if t else type_id
        type_desc = t.get("desc", "") if t else ""

        personal_fields = get_personal_fields(type_id)
        field_labels = "、".join(f["label"] for f in personal_fields)

        current = current or {}
        sp = (getattr(project, "selling_points", "") or "").strip()

        # 组装发给 AI 的当前配置快照（自然语言）
        cur_lines = []
        for k, v in (current.get("personal_settings", {}) or {}).items():
            if v:
                cur_lines.append(f"- {k}：{v}")
        for k, v in (current.get("common_settings", {}) or {}).items():
            if v:
                cur_lines.append(f"- 通用/{k}：{v}")
        if current.get("note"):
            cur_lines.append(f"- 补充说明：{current['note']}")
        cur_text = "\n".join(cur_lines) if cur_lines else "（商家暂未填写任何配置）"

        images = getattr(project, "images", None) or []
        img = next((i for i in images if getattr(i, "filename", None)), None)
        image_url = None
        if img:
            from app.gallery_service import _gallery_file_data_url

            du = _gallery_file_data_url(img.filename)
            image_url = du if du and du.startswith("data:") else None

        text = (
            f"【生成方向】{type_title}"
            + (f"：{type_desc}" if type_desc else "")
            + f"\n【该类型的个性化字段】{field_labels}"
            + (f"\n【核心卖点】{sp}" if sp else "")
            + f"\n\n【商家已填配置】\n{cur_text}"
            + "\n\n请基于产品图与以上信息，输出更优的配置建议 JSON。"
        )
        raw = _run_async(
            _chat_multimodal(_FILL_CFG_SYSTEM, text, image_url, AI_FILL_TEMPERATURE)
        )
        data = _extract_json(raw)
        if data:
            return {
                "common_settings": dict(data.get("common_settings", {}) or {}),
                "personal_settings": dict(data.get("personal_settings", {}) or {}),
                "note": str(data.get("note", "") or ""),
            }
        logger.warning("配置 AI 返回结构异常：%r", raw[:200])
    except Exception as exc:
        logger.warning("类型配置 AI 帮写失败：%s", exc)
    return empty
