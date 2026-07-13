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

依赖：``app.settings`` 中的 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
（已配置为 Agnes 2.0 Flash）。多模态图片以 base64 data URL 内联传入。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.settings import get_settings

logger = logging.getLogger(__name__)

# ── 超时与温度 ────────────────────────────────────────────────
# 提示词生成需要「看懂图 + 写文案」，给足 90s；温度略高以放大产品差异，
# 但不过高以免同一产品每次跳变太大。
AI_PROMPT_TIMEOUT = 90
AI_FILL_TIMEOUT = 75
AI_PROMPT_TEMPERATURE = 0.75
AI_FILL_TEMPERATURE = 0.7

_PROMPT_SYSTEM = """你是一位顶尖的电商视觉创意总监与图像提示词工程师，精通 Midjourney / DALL·E / Stable Diffusion / 通义万相等主流图像生成模型的中英文提示词写法。

任务：根据商家提供的【产品参考图】+【生成方向】+【核心卖点】+【配置项】，写一份可直接用于图像生成模型的高质量提示词。

硬性要求：
1. 必须严格尊重参考图中的产品外观（颜色、版型、材质、logo、结构），不得改变产品本身，只能优化构图、背景、光影、氛围与画面语言。
2. 提示词要能适配「该真实产品」，而非套用通用模板——请基于图片中产品的真实特征（形状、材质反光、使用场景线索）展开。
3. 根据【生成方向】调整：白底图=纯白背景居中产品；平台主图=合规留白；场景图=真实使用环境；模特图=自然姿态人物；海报=版面与营销元素。
4. 输出**纯 JSON**，不要任何额外解释，格式严格如下：
{
  "prompt_cn": "用于给用户展示的中文提示词（详细、画面感强、含风格与质感描述）",
  "prompt_en": "用于直接喂给图像模型的英文提示词（纯英文，绝不含任何中文字符，逗号分隔的短语风格，含负面词用 --no 或 'without' 表达）"
}
5. prompt_en 必须为纯英文，不得出现任何中文或中文字符（这是硬性约束）。"""

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


# ─────────────────────────────────────────────────────────────
# 底层：Agnes 多模态 chat 调用（OpenAI 兼容，proxy=None 直连）
# ─────────────────────────────────────────────────────────────

def _build_client():
    from openai import AsyncOpenAI
    import httpx

    s = get_settings()
    return AsyncOpenAI(
        api_key=s.openai_api_key or "",
        base_url=s.openai_base_url,
        http_client=httpx.AsyncClient(proxy=None),
        timeout=AI_PROMPT_TIMEOUT,
    )


async def _chat_multimodal(system: str, text: str, image_data_url: str | None, temperature: float) -> str:
    """调用 Agnes 2.0 Flash 多模态接口，返回模型文本。"""
    client = _build_client()
    s = get_settings()
    model = s.openai_model or "agnes-2.0-flash"

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
        max_tokens=1200,
    )
    return resp.choices[0].message.content or ""


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

    这里**不做任何提示词拼装**——只忠实描述「用户想要什么」，创意交给模型。
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

    # 个性化设置
    personal = getattr(item, "personal_settings", None) or {}
    if personal:
        plines = []
        for k, v in personal.items():
            if v:
                plines.append(f"- {k}：{v}")
        if plines:
            lines.append("【个性化设置】\n" + "\n".join(plines))

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

    lines.append(
        "【参考图】已提供产品参考图，请据此理解产品的真实外观（颜色 / 版型 / 材质 / logo / 结构），"
        "并在提示词中保持产品一致，不得改变产品本身。"
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


def _strip_cjk(s: str) -> str:
    """把英文提示词里残留的中文字符清掉（硬约束兜底）。"""
    return re.sub(r"[\u4e00-\u9fff]", "", s).strip()


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

    返回 {"prompt": 中文展示版, "prompt_en": 英文生成版, "prompt_source": "ai"|"template"}。
    AI 路径失败时降级到 ``gallery_prompt.build_prompt_bilingual``（source=template）。
    """
    from app import gallery_prompt

    try:
        if not get_settings().openai_api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY，跳过 AI 提示词")

        # 参考图内联为 base64（本地图非公开 URL，必须内联）
        image_url = None
        if effective_product_image:
            from app.gallery_service import _gallery_file_data_url

            image_url = _gallery_file_data_url(effective_product_image)

        user_text = build_user_config_text(
            project, item, effective_product_image=effective_product_image, ratio=ratio
        )

        raw = _run_async(
            _chat_multimodal(_PROMPT_SYSTEM, user_text, image_url, AI_PROMPT_TEMPERATURE)
        )
        data = _extract_json(raw)
        cn = (data or {}).get("prompt_cn", "").strip()
        en = (data or {}).get("prompt_en", "").strip()
        en = _strip_cjk(en)
        if cn and en:
            logger.info("AI 提示词生成成功（source=ai），cn=%d字 en=%d字", len(cn), len(en))
            return {"prompt": cn, "prompt_en": en, "prompt_source": "ai"}

        logger.warning("AI 返回结构异常，降级模板引擎：%r", raw[:200])
    except Exception as exc:  # 网络/超时/解析任意异常都降级
        logger.warning("AI 提示词生成失败，降级到模板引擎：%s", exc)

    # 降级：旧模板引擎
    pd = gallery_prompt.build_prompt_bilingual(
        project, item, model_name=model_name, effective_product_image=effective_product_image
    )
    return {"prompt": pd["prompt"], "prompt_en": pd["prompt_en"], "prompt_source": "template"}


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
        if not get_settings().openai_api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY")
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
        if not get_settings().openai_api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY")
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
