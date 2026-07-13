"""电商套图：验证比例映射与提示词参考图感知。"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.gallery_service import _ratio_to_size, GALLERY_UPLOAD_ROOT
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


def _make_test_image(filename: str, width: int, height: int) -> str:
    """在 uploads/gallery 下创建一张临时测试图，返回文件名。

    优先用 Pillow（与线上一致）；无 Pillow 时写一张最小 PNG，
    确保 _infer_size_from_reference 的兜底读取也能被测试覆盖。
    """
    GALLERY_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    p = GALLERY_UPLOAD_ROOT / filename
    try:
        from PIL import Image

        img = Image.new("RGB", (width, height), color=(128, 128, 128))
        img.save(p, "JPEG")
    except Exception:
        p.write_bytes(_minimal_png(width, height))
    return filename


def _minimal_png(width: int, height: int) -> bytes:
    """生成一张最小可读的灰度 PNG，仅用于测试文件头解析。"""
    import struct, zlib

    raw = bytes([128] * (width * height))
    # 1-bit depth灰度图，滤波器字节在每一行前面
    def line(y):
        return bytes([0]) + raw[y * width:(y + 1) * width]

    idat = zlib.compress(b"".join(line(y) for y in range(height)), 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    chunks = [
        b"\x89PNG\r\n\x1a\n",
        _png_chunk(b"IHDR", ihdr),
        _png_chunk(b"IDAT", idat),
        _png_chunk(b"IEND", b""),
    ]
    return b"".join(chunks)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    import struct, zlib

    chunk = chunk_type + data
    crc = zlib.crc32(chunk) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", crc)


def test_ratio_to_size():
    assert _ratio_to_size("方图 1:1") == "1024x1024"
    assert _ratio_to_size("竖图 3:4") == "768x1024"
    assert _ratio_to_size("竖图 4:5") == "832x1024"
    assert _ratio_to_size("竖图 9:16") == "576x1024"
    assert _ratio_to_size("竖图 2:3") == "704x1024"
    assert _ratio_to_size("横图 16:9") == "1024x576"
    assert _ratio_to_size("横图 4:3") == "1024x768"
    # 自适应 / 未选 / 空：无参考图时不再越权锁定 1024x1024，交由模型默认
    assert _ratio_to_size("自适应尺寸") is None
    assert _ratio_to_size(None) is None
    assert _ratio_to_size("") is None


def test_ratio_to_size_adaptive_by_reference():
    """自适应尺寸应按参考图实际比例推断，避免模型默认方图压扁原图。"""
    # 竖版连衣裙比例 800x1200（≈2:3）
    v_name = _make_test_image("ratio-test-vertical.jpg", 800, 1200)
    assert _ratio_to_size("自适应尺寸", reference_filename=v_name) == "704x1024"

    # 横版 Banner 比例 1600x900（16:9）
    h_name = _make_test_image("ratio-test-horizontal.jpg", 1600, 900)
    assert _ratio_to_size("自适应尺寸", reference_filename=h_name) == "1024x576"

    # 方图
    s_name = _make_test_image("ratio-test-square.jpg", 1000, 1000)
    assert _ratio_to_size("自适应尺寸", reference_filename=s_name) == "1024x1024"

    # 清理临时文件
    for f in (v_name, h_name, s_name):
        try:
            (GALLERY_UPLOAD_ROOT / f).unlink()
        except Exception:
            pass


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
    test_ratio_to_size_adaptive_by_reference()
    test_resolve_config_reference_detection()
    test_resolve_config_ratio()
    print("All tests passed.")
