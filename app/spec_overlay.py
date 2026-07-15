"""规格参数图 · 后端文字叠加层（方案 A：纯视觉图 + 文字叠加）。

为什么要这么做：
- 扩散模型（Agnes / SD 系列）对**汉字字形**渲染能力极弱，直接让模型在画面里写
  「衣长/裙长/尺码表」必然出现乱码。
- 因此 spec 类型的图像模型只负责生成「干净无文字」的产品视觉（产品居左、右侧预留
  空白面板区、可含测量引导线/人体剪影），**所有中文文字（尺码表、测量标注、补充说明）
  由本模块用真实 CJK 字体精确绘制叠加**，彻底消除乱码。

本模块不依赖任何外部出图模型，纯 PIL 合成，可在生成完成后本地执行。
"""

from __future__ import annotations

import math
import os
import re
import uuid

from PIL import Image, ImageDraw, ImageFont

# ── CJK 字体解析：捆绑 simhei.ttf 优先，系统字体回退 ──────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_CANDIDATES = [
    os.path.join(_THIS_DIR, "assets", "fonts", "simhei.ttf"),
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/Library/Fonts/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttc",
]


def resolve_spec_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """返回指定像素大小的 CJK 字体。找不到真实 CJK 字体时回退到 PIL 默认字体（不出错）。"""
    for p in _FONT_CANDIDATES:
        if p and os.path.exists(p):
            try:
                # .ttc 集合字体取第一个字形（index=0）
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── 规格数据解析 ─────────────────────────────────────────────────
_SIZE_PATTERNS = [
    (r"(\d+\s*码)", lambda m: m.group(1).replace(" ", "")),          # 110码
    (r"\s*(S|M|L|XL|XXL|XXXL|均码|大码|中码|小码)\b", lambda m: m.group(1)),  # S/M/L
    (r"\s*(\d{2,3})\b", lambda m: m.group(1) + "码"),                 # 110（无"码"字）
]


def _extract_size(seg: str) -> str:
    for pat, fn in _SIZE_PATTERNS:
        m = re.search(pat, seg, re.I)
        if m:
            return fn(m)
    toks = seg.split()
    return toks[0][:8] if toks else "尺码"


def parse_spec_data(text: str | None) -> dict:
    """把用户粘贴的「规格参数原文」解析为结构化表格。

    返回 {"headers": ["尺码", "衣长", "胸围", ...], "rows": [{"尺码": "110码", "衣长": "62", ...}, ...]}
    解析不到行时 rows 为空，调用方改用示例占位。
    """
    rows: list[dict] = []
    if not text:
        return {"headers": [], "rows": rows}
    segments = re.split(r"[;\n；]+", text)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        size = _extract_size(seg)
        rest = seg
        # 去掉尺码标记后的残余，避免被当成测量项
        m = re.search(r"(\d+\s*码)", seg)
        if m:
            rest = seg[m.end():]
        else:
            # 去掉开头的 size token
            for pat, _ in _SIZE_PATTERNS[1:]:
                mm = re.match(pat, seg, re.I)
                if mm:
                    rest = seg[mm.end():]
                    break
        kv: dict[str, str] = {}
        for k, v, unit in re.findall(
            r"([一-龥A-Za-z]{2,8})\s*[:：]?\s*([0-9]+(?:\.[0-9]+)?)\s*(cm|CM|厘米|公分|寸|cm)?",
            rest,
        ):
            if k == "码":
                continue
            val = v + (unit or "")
            kv[k] = val
        row = {"尺码": size}
        row.update(kv)
        rows.append(row)
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k != "尺码" and k not in keys:
                keys.append(k)
    return {"headers": ["尺码"] + keys, "rows": rows}


# ── 文字绘制辅助 ─────────────────────────────────────────────────
def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    """按像素宽度换行（CJK 按字符断，英文按单词断）。"""
    lines: list[str] = []
    cur = ""
    for ch in text:
        test = cur + ch
        if draw.textlength(test, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def _draw_centered_cell(
    draw: ImageDraw.ImageDraw,
    x0: int, y0: int, x1: int, y1: int,
    text: str, font: ImageFont.ImageFont, fill: tuple,
):
    """在单元格内左对齐、垂直居中绘制（预留 8px 内边距）。"""
    pad = max(4, int((x1 - x0) * 0.04))
    ty = y0 + (y1 - y0 - font.size) // 2
    draw.text((x0 + pad, ty), text, font=font, fill=fill)


# ── 尺寸标注线（带双向箭头 + 数值标签，由后端精确叠加） ──────────
def _arrow_tips(draw, x1, y1, x2, y2, color, width=2, head=12):
    """画一条双向箭头尺寸标注线（箭头朝外）。"""
    draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
    ang = math.atan2(y2 - y1, x2 - x1)
    # 终点箭头（朝外）
    for a in (ang + math.pi - 0.42, ang + math.pi + 0.42):
        draw.line([(x2, y2), (x2 + head * math.cos(a), y2 + head * math.sin(a))], fill=color, width=width)
    # 起点箭头（朝外）
    for a in (ang - 0.42, ang + 0.42):
        draw.line([(x1, y1), (x1 + head * math.cos(a), y1 + head * math.sin(a))], fill=color, width=width)


def _dim_value(data, *names):
    """从解析后的规格数据首行取出某尺寸的数值（按名称模糊匹配）。"""
    if not data or not data.get("rows"):
        return None
    row = data["rows"][0]
    for n in names:
        for h in data["headers"]:
            if n in h and str(row.get(h, "")).strip():
                return str(row.get(h, "")).strip()
    return None


def _draw_measurement_lines(draw, W, H, lw, data, f_num):
    """在产品左侧区域绘制规格尺寸标注线（双向箭头 + 数值标签）。

    - 数值仅用真实字体绘制数字/单位（CJK 安全）；尺寸名在右侧尺码表中体现，避免在线上写中文。
    - 未提供数据时仍绘制代表性标注线（无数值），确保画面始终带「尺寸」视觉语言。
    - 服饰类画 衣长/胸围/肩宽(+袖长)；非服饰类画 高/宽(+厚)，按实际表头自适应。
    """
    # 优雅的紫灰色（接近参考图中的测量线色调）
    color = (140, 130, 170, 220)
    lw_ = max(1, int(lw))
    headers = [h for h in (data.get("headers") or [])]
    apparel_kw = ("衣长", "裙长", "裤长", "胸围", "肩宽", "袖长", "腰围", "臀围")
    is_apparel = any(any(k in h for k in apparel_kw) for h in headers) or not headers

    if is_apparel:
        # 位置微调：箭头线稍微靠内，不和边缘重叠；留出标签空间
        margin_x = int(lw_ * 0.08)
        specs = [
            # 衣长/总长 — 左侧竖向
            (("衣长", "裙长", "裤长"), margin_x, int(H * 0.08), margin_x, int(H * 0.92), "v"),
            # 胸围 — 横跨产品中部
            (("胸围",), int(lw_ * 0.22), int(H * 0.42), int(lw_ * 0.78), int(H * 0.42), "h"),
            # 肩宽 — 靠近顶部横向
            (("肩宽",), int(lw_ * 0.25), int(H * 0.15), int(lw_ * 0.75), int(H * 0.15), "h"),
        ]
        if _dim_value(data, "袖长"):
            specs.append((("袖长",), int(lw_ * 0.82), int(H * 0.18), int(lw_ * 0.82), int(H * 0.50), "v"))
    else:
        margin_x = int(lw_ * 0.08)
        specs = [
            (("高度", "高", "长", "长度"), margin_x, int(H * 0.10), margin_x, int(H * 0.90), "v"),
            (("宽度", "宽", "径"), int(lw_ * 0.20), int(H * 0.55), int(lw_ * 0.80), int(H * 0.55), "h"),
        ]
        if _dim_value(data, "厚度", "厚"):
            specs.append((("厚度", "厚"), int(lw_ * 0.82), int(H * 0.30), int(lw_ * 0.82), int(H * 0.55), "v"))

    for keys, x1, y1, x2, y2, orient in specs:
        val = _dim_value(data, *keys)
        _arrow_tips(draw, x1, y1, x2, y2, color, width=2, head=10)
        if val:
            # 标签用「表头中文名 + 数值」（如「衣长 62」），中文由后端真实字体精确绘制，不会乱码
            matched_header = next((h for h in data["headers"] if any(k in h for k in keys)), "")
            label = f"{matched_header} {val}".strip()
            tw = draw.textlength(label, font=f_num)
            pad = 4
            if orient == "v":
                bx = x1 - int(tw) - pad * 2 - 8
                by = (y1 + y2) // 2 - f_num.size // 2
            else:
                bx = (x1 + x2) // 2 - int(tw) // 2 - pad
                by = y1 - f_num.size - 10
            bx = max(2, bx)
            by = max(2, by)
            # 标签背景：半透明白色圆角效果
            draw.rectangle(
                [bx, by, bx + int(tw) + pad * 2, by + f_num.size + 4],
                fill=(255, 255, 255, 230),
            )
            draw.text((bx + pad, by + 2), label, font=f_num, fill=(60, 55, 80, 255))


def _draw_scale_silhouette(draw, px, pw, H):
    """在右侧面板底部画一个精致的人体/比例剪影，作尺寸参照。

    仿电商规格参数图风格，绘制带基本人体特征的儿童/人物轮廓（头+颈+躯干+腿），
    比纯几何图形更直观专业。仅作比例示意，不承载任何用户补充说明文字。
    """
    cx = px + pw // 2
    base_y = H - int(H * 0.03)
    fig_h = int(H * 0.38)  # 略高一点，更接近真人比例
    top_y = base_y - fig_h
    color = (210, 208, 218, 255)   # 更淡的灰紫色

    # ── 头部（椭圆）──
    head_r = max(10, int(fig_h * 0.10))
    head_cx = cx
    head_cy = top_y + head_r + int(fig_h * 0.01)
    draw.ellipse(
        [head_cx - head_r, head_cy - head_r,
         head_cx + head_r, head_cy + head_r],
        fill=color,
    )

    # ── 颈部（细长矩形）──
    neck_w = max(4, int(head_r * 0.35))
    neck_h = max(4, int(fig_h * 0.04))
    neck_y = head_cy + head_r - 2
    draw.rounded_rectangle(
        [cx - neck_w // 2, neck_y, cx + neck_w // 2, neck_y + neck_h],
        radius=neck_w // 2, fill=color,
    )

    # ── 躯干（肩 → 腰的梯形，更接近真实身形）──
    shoulder_y = neck_y + neck_h
    shoulder_w = int(fig_h * 0.22)     # 肩宽
    waist_w = int(fig_h * 0.16)        # 腰宽
    hip_y = base_y - int(fig_h * 0.22) # 臀线位置
    hip_w = int(fig_h * 0.18)          # 臀宽
    # 上半躯干（肩到腰）
    mid_y = shoulder_y + (hip_y - shoulder_y) // 2
    mid_w = (shoulder_w + waist_w) // 2
    body_top = [
        (cx - shoulder_w, shoulder_y),
        (cx + shoulder_w, shoulder_y),
        (cx + mid_w, mid_y),
        (cx - mid_w, mid_y),
    ]
    draw.polygon(body_top, fill=color)
    # 下半躯干（腰到臀）
    body_bot = [
        (cx - mid_w, mid_y),
        (cx + mid_w, mid_y),
        (cx + hip_w, hip_y),
        (cx - hip_w, hip_y),
    ]
    draw.polygon(body_bot, fill=color)

    # ── 腿（略分开的圆角矩形，模拟双腿）──
    leg_w = max(8, int(hip_w * 0.45))
    leg_gap = max(4, int(hip_w * 0.22))
    leg_r = leg_w // 2
    draw.rounded_rectangle(
        [cx - leg_gap - leg_w, hip_y + 2, cx - leg_gap, base_y],
        radius=leg_r, fill=color,
    )
    draw.rounded_rectangle(
        [cx + leg_gap, hip_y + 2, cx + leg_gap + leg_w, base_y],
        radius=leg_r, fill=color,
    )

    # ── 手臂（可选：淡淡的手臂轮廓）──
    arm_w = max(5, int(fig_h * 0.035))
    arm_len = int((hip_y - shoulder_y) * 0.75)
    arm_inner_y = shoulder_y + int(arm_len * 0.25)
    arm_outer_y = shoulder_y + int(arm_len * 0.7)
    # 左臂
    draw.rounded_rectangle(
        [cx - shoulder_w - arm_w, arm_inner_y,
         cx - shoulder_w + 1, arm_outer_y],
        radius=arm_w // 2, fill=color,
    )
    # 右臂
    draw.rounded_rectangle(
        [cx + shoulder_w - 1, arm_inner_y,
         cx + shoulder_w + arm_w, arm_outer_y],
        radius=arm_w // 2, fill=color,
    )

    # ── 底部标注（非用户文字，UI 元素）──
    f_cap = resolve_spec_font(max(11, int(pw * 0.055)))
    cap = "比例参考"
    tw = draw.textlength(cap, font=f_cap)
    draw.text((cx - int(tw) // 2, base_y + 2), cap, font=f_cap, fill=(155, 153, 165, 255))


# ── 主入口：叠加合成 ─────────────────────────────────────────────
def overlay_spec(
    result_path: str,
    spec_text: str = "",
    note: str = "",
    title: str = "规格参数图",
    category: str = "",
) -> str | None:
    """把尺码表/测量标注/补充说明叠加到生成图上。

    - result_path：原始生成图（本地绝对/相对路径）。
    - 返回新文件相对名（results/xxx.png）；失败返回 None（调用方保留原图）。
    """
    try:
        base = Image.open(result_path).convert("RGBA")
    except Exception:
        return None

    W, H = base.size
    canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))

    # 左侧：产品视觉（cover 裁剪到左 65% 宽 — 新 prompt 让 AI 把产品画到 70-75%，多留一点余量）
    left_ratio = 0.65
    lw = max(1, int(W * left_ratio))
    bw, bh = base.size
    scale = max(lw / bw, H / bh)
    nw, nh = int(bw * scale), int(bh * scale)
    base_resized = base.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - lw) // 2)
    top = max(0, (nh - H) // 2)
    base_left = base_resized.crop((left, top, left + lw, top + H))
    canvas.paste(base_left, (0, 0))

    draw = ImageDraw.Draw(canvas)

    # 右侧白底面板
    px = lw
    pw = W - lw
    draw.rectangle([px, 0, W, H], fill=(245, 245, 247, 255))
    draw.line([(px, 0), (px, H)], fill=(210, 210, 215, 255), width=2)

    # 字号随图宽缩放
    fs_title = max(24, int(W * 0.030))
    fs_head = max(16, int(W * 0.019))
    fs_cell = max(14, int(W * 0.018))

    f_title = resolve_spec_font(fs_title)
    f_head = resolve_spec_font(fs_head)
    f_cell = resolve_spec_font(fs_cell)

    pad = int(pw * 0.08)
    x0 = px + pad
    x1 = W - pad
    inner_w = x1 - x0

    # 标题（更接近参考图的规格参数表风格）
    y = int(H * 0.04)
    title_text = f"{category} · 规格参数" if category else (title or "规格参数")
    draw.text((x0, y), title_text, font=f_title, fill=(35, 35, 40, 255))
    y += fs_title + int(H * 0.025)

    # 尺码表
    data = parse_spec_data(spec_text)
    table_top = y
    if data["rows"]:
        headers = data["headers"]
        rows = data["rows"][:8]  # 最多 8 行，超出截断
        ncols = len(headers)
        col_w = inner_w / ncols
        row_h = int(fs_cell * 1.9)
        # 表头
        draw.rectangle([x0, y, x1, y + row_h], fill=(90, 90, 110, 255))
        for c, hname in enumerate(headers):
            _draw_centered_cell(draw, x0 + col_w * c, y, x0 + col_w * (c + 1), y + row_h,
                                hname, f_head, (255, 255, 255, 255))
        y += row_h
        # 数据行
        for ri, row in enumerate(rows):
            bg = (255, 255, 255, 255) if ri % 2 == 0 else (232, 232, 238, 255)
            draw.rectangle([x0, y, x1, y + row_h], fill=bg)
            for c, hname in enumerate(headers):
                _draw_centered_cell(draw, x0 + col_w * c, y, x0 + col_w * (c + 1), y + row_h,
                                    str(row.get(hname, "")), f_cell, (40, 40, 45, 255))
            y += row_h
        # 表格外边框 + 纵向分隔线
        draw.rectangle([x0, table_top, x1, y], outline=(200, 200, 205, 255), width=1)
        for c in range(1, ncols):
            lx = int(x0 + col_w * c)
            draw.line([(lx, table_top), (lx, y)], fill=(215, 215, 220, 255), width=1)
    else:
        draw.text((x0, y), "（未提供规格数据，示例占位）", font=f_cell, fill=(120, 120, 130, 255))
        y += int(fs_cell * 1.9)

    # 左侧产品上的尺寸标注线（带双向箭头 + 数值标签，由后端精确叠加）
    _draw_measurement_lines(draw, W, H, lw, data, f_cell)

    # 右侧面板底部：比例/人体剪影参照（绝不写任何用户补充说明文字）
    _draw_scale_silhouette(draw, px, pw, H)

    # 保存为新文件（PNG 通用；保留原始图不动）
    out_dir = os.path.dirname(os.path.abspath(result_path))
    new_name = f"results/{uuid.uuid4().hex}.png"
    # result_path 位于 GALLERY_UPLOAD_ROOT/results/ 下；沿用同目录写入
    out_path = os.path.join(out_dir, os.path.basename(new_name))
    try:
        canvas.convert("RGB").save(out_path, "PNG", quality=92)
    except Exception:
        return None
    return new_name


# 便于测试/调试用：直接对一张图做叠加并返回 PIL 对象
def overlay_spec_image(base_image: Image.Image, spec_text: str = "", note: str = "",
                       title: str = "规格参数图", category: str = "") -> Image.Image:
    """纯内存版本（不落盘），供单测/预览复用。"""
    W, H = base_image.size
    canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    left_ratio = 0.65
    lw = max(1, int(W * left_ratio))
    base = base_image.convert("RGBA")
    bw, bh = base.size
    scale = max(lw / bw, H / bh)
    nw, nh = int(bw * scale), int(bh * scale)
    base_resized = base.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - lw) // 2)
    top = max(0, (nh - H) // 2)
    canvas.paste(base_resized.crop((left, top, left + lw, top + H)), (0, 0))
    draw = ImageDraw.Draw(canvas)
    px = lw
    pw = W - lw
    draw.rectangle([px, 0, W, H], fill=(245, 245, 247, 255))
    draw.line([(px, 0), (px, H)], fill=(210, 210, 215, 255), width=2)
    fs_title = max(24, int(W * 0.030))
    fs_head = max(16, int(W * 0.019))
    fs_cell = max(14, int(W * 0.018))
    f_title = resolve_spec_font(fs_title)
    f_head = resolve_spec_font(fs_head)
    f_cell = resolve_spec_font(fs_cell)
    pad = int(pw * 0.08)
    x0 = px + pad
    x1 = W - pad
    inner_w = x1 - x0
    y = int(H * 0.05)
    title_text = f"{category} · 规格参数" if category else (title or "规格参数图")
    draw.text((x0, y), title_text, font=f_title, fill=(30, 30, 35, 255))
    y += fs_title + int(H * 0.03)
    data = parse_spec_data(spec_text)
    table_top = y
    if data["rows"]:
        headers = data["headers"]
        rows = data["rows"][:8]
        ncols = len(headers)
        col_w = inner_w / ncols
        row_h = int(fs_cell * 1.9)
        draw.rectangle([x0, y, x1, y + row_h], fill=(90, 90, 110, 255))
        for c, hname in enumerate(headers):
            _draw_centered_cell(draw, x0 + col_w * c, y, x0 + col_w * (c + 1), y + row_h,
                                hname, f_head, (255, 255, 255, 255))
        y += row_h
        for ri, row in enumerate(rows):
            bg = (255, 255, 255, 255) if ri % 2 == 0 else (232, 232, 238, 255)
            draw.rectangle([x0, y, x1, y + row_h], fill=bg)
            for c, hname in enumerate(headers):
                _draw_centered_cell(draw, x0 + col_w * c, y, x0 + col_w * (c + 1), y + row_h,
                                    str(row.get(hname, "")), f_cell, (40, 40, 45, 255))
            y += row_h
        draw.rectangle([x0, table_top, x1, y], outline=(200, 200, 205, 255), width=1)
        for c in range(1, ncols):
            lx = int(x0 + col_w * c)
            draw.line([(lx, table_top), (lx, y)], fill=(215, 215, 220, 255), width=1)
    else:
        draw.text((x0, y), "（未提供规格数据，示例占位）", font=f_cell, fill=(120, 120, 130, 255))
        y += int(fs_cell * 1.9)
    # 左侧产品上的尺寸标注线（带双向箭头 + 数值标签，由后端精确叠加）
    _draw_measurement_lines(draw, W, H, lw, data, f_cell)

    # 右侧面板底部：比例/人体剪影参照（绝不写任何用户补充说明文字）
    _draw_scale_silhouette(draw, px, pw, H)
    return canvas.convert("RGB")
