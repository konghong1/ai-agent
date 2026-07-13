"""双语提示词审计脚本（临时校验工具）。

1. 扫描 TYPE_PERSONAL 中所有下拉选项值，检查是否被 OPTIONS_EN 覆盖（未覆盖→中文泄漏）。
2. 对多个推荐类型调用 build_prompt_bilingual，检查 prompt_en 是否含中文字符、统计长度。
"""
from __future__ import annotations

import os
import sys
import re
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import gallery_config as cfg  # noqa: E402
from app.gallery_prompt import build_prompt_bilingual, _t  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def audit_option_coverage() -> list[str]:
    gaps: list[str] = []
    for type_id, fields in cfg.TYPE_PERSONAL.items():
        for f in fields:
            label = f.get("label", "?")
            for opt in f.get("options", []) or []:
                translated = _t(opt)
                if translated == opt and CJK.search(opt):
                    gaps.append(f"[{type_id}/{label}] 未翻译: {opt!r}")
    return gaps


def _project(market_config: dict, selling_points: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(market_config=market_config, selling_points=selling_points)


def _item(type_id, personal_settings=None, common_settings=None, product_image="", reference_images=None, output_settings=None):
    return types.SimpleNamespace(
        type_id=type_id,
        personal_settings=personal_settings or {},
        common_settings=common_settings or {},
        note="",
        product_image=product_image,
        reference_images=reference_images or [],
        output_settings=output_settings or {},
    )


def audit_bilingual_samples() -> list[str]:
    issues: list[str] = []

    # 用户主示例：angle 类型，日韩市场 + 淘宝/天猫 + 白底 + 多角度拼贴 + 三角度 + 轮廓强调
    samples = [
        ("angle(用户主示例)", _item(
            "angle",
            personal_settings={
                "展示角度": "多角度拼接",
                "角度数量": "三个角度（全面覆盖）",
                "细节强化": "突出轮廓线条",
                "视觉强化": "轮廓强化",
                "排版呈现": "多场景拼接",
            },
            common_settings={"target_market": "日韩", "ecommerce_platform": "淘宝 / 天猫", "visual_style": "高级质感风"},
            product_image="http://example.com/p.png",
            output_settings={"ratio": "自适应尺寸"},
        )),
        ("hero", _item(
            "hero",
            personal_settings={
                "价值聚焦": "功能核心", "视觉强化": "焦点突出", "产品呈现": "整体形态",
                "氛围浓度": "轻度氛围", "价值暗示": "品质细节",
            },
            common_settings={"target_market": "北美", "ecommerce_platform": "亚马逊", "visual_style": "高级质感风"},
            product_image="http://example.com/p.png",
        )),
        ("scene", _item(
            "scene",
            personal_settings={
                "场景类型": "居家空间", "产品展示": "真实使用场景", "排版呈现": "多场景拼接",
                "氛围营造": "生活化温馨风", "价值导向": "使用幸福感",
            },
            common_settings={"target_market": "欧洲", "ecommerce_platform": "独立站", "visual_style": "自然清新风"},
        )),
        ("tryon", _item(
            "tryon",
            personal_settings={
                "展示排版": "全身穿搭全景", "场景类型": "居家空间", "互动方式": "人物互动展示",
            },
            common_settings={"target_market": "日韩", "ecommerce_platform": "淘宝 / 天猫", "visual_style": "高级质感风"},
            product_image="http://example.com/p.png",
        )),
        ("usp", _item(
            "usp",
            personal_settings={
                "主标题": "自动生成主标题", "卖点文案": "生成主卖点搭配2~3个辅卖点",
                "表现形式": "产品居中展示卖点两侧分布", "卖点重心": "材质优势",
            },
            common_settings={"target_market": "北美", "ecommerce_platform": "亚马逊"},
        )),
    ]

    for name, item in samples:
        proj = _project(item.common_settings, selling_points="轻量便携，防水耐磨")
        d = build_prompt_bilingual(proj, item)
        en = d["prompt_en"]
        cn = d["prompt"]
        leaks = CJK.findall(en)
        status = "OK" if not leaks else f"LEAK({len(leaks)})"
        issues.append(f"=== {name} [{status}] en_len={len(en)} cn_len={len(cn)} ===")
        if leaks:
            issues.append(f"    中文泄漏字符: {set(leaks)}")
            issues.append(f"    EN: {en}")
        else:
            issues.append(f"    EN: {en}")
    return issues


if __name__ == "__main__":
    print("── 1. 选项值翻译覆盖审计 ──")
    gaps = audit_option_coverage()
    if gaps:
        print(f"发现 {len(gaps)} 处未翻译选项值：")
        for g in gaps:
            print("  ", g)
    else:
        print("全部选项值均已翻译覆盖 ✅")

    print("\n── 2. 双语生成抽样（检查中文泄漏 + 长度） ──")
    for line in audit_bilingual_samples():
        print(line)
