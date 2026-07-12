"""电商套图：验证比例映射与提示词参考图感知。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.gallery_service import _ratio_to_size
from app.gallery_prompt import _resolve_config


def make_item(type_id: str, output_settings: dict | None = None, product_image: str | None = None):
    class FakeItem:
        def __init__(self):
            self.type_id = type_id
            self.personal_settings = {}
            self.common_settings = {}
            self.output_settings = output_settings or {}
            self.note = ""
            self.reference_images = []
            self.product_image = product_image or ""

    return FakeItem()


def make_project():
    class FakeProject:
        def __init__(self):
            self.market_config = {}
            self.selling_points = ""

    return FakeProject()


def test_ratio_to_size():
    assert _ratio_to_size("方图 1:1") == "1024x1024"
    assert _ratio_to_size("竖图 3:4") == "768x1024"
    assert _ratio_to_size("竖图 4:5") == "832x1024"
    assert _ratio_to_size("竖图 9:16") == "576x1024"
    assert _ratio_to_size("竖图 2:3") == "704x1024"
    assert _ratio_to_size("横图 16:9") == "1024x576"
    assert _ratio_to_size("横图 4:3") == "1024x768"
    assert _ratio_to_size("自适应尺寸") == "1024x1024"
    assert _ratio_to_size(None) == "1024x1024"
    assert _ratio_to_size("") == "1024x1024"


def test_resolve_config_reference_detection():
    proj = make_project()

    # 1. 没有任何参考图 → has_reference False
    item = make_item("bg")
    cfg = _resolve_config(proj, item)
    assert cfg["has_reference"] is False

    # 2. 仅项目产品图回退（item.product_image 为空）→ 必须被识别为有参考图
    item = make_item("bg", product_image="")
    cfg = _resolve_config(proj, item, effective_product_image="proj-1.jpg")
    assert cfg["has_reference"] is True

    # 3. item 本身有 product_image → True
    item = make_item("bg", product_image="item-1.jpg")
    cfg = _resolve_config(proj, item)
    assert cfg["has_reference"] is True

    # 4. item 有 reference_images → True
    item = make_item("bg")
    item.reference_images = ["ref-1.jpg"]
    cfg = _resolve_config(proj, item)
    assert cfg["has_reference"] is True


def test_resolve_config_ratio():
    proj = make_project()
    item = make_item("hero", output_settings={"ratio": "竖图 3:4"})
    cfg = _resolve_config(proj, item)
    assert cfg["ratio"] == "竖图 3:4"

    item = make_item("hero")
    cfg = _resolve_config(proj, item)
    assert cfg["ratio"] == "自适应尺寸"


if __name__ == "__main__":
    test_ratio_to_size()
    test_resolve_config_reference_detection()
    test_resolve_config_ratio()
    print("All tests passed.")
