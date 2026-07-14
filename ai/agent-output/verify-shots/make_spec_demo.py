"""演示：规格参数图后端叠加层 V2（带双向箭头尺寸标注线）。
用一张合成的「服饰剪影」模拟 AI 生成的干净产品图，跑 overlay_spec_image 验证尺寸线。
"""
from PIL import Image, ImageDraw
from app.spec_overlay import overlay_spec_image, resolve_spec_font

W = H = 1024
base = Image.new("RGB", (W, H), (235, 236, 240))
d = ImageDraw.Draw(base)
# 画一个简单「上衣」剪影（浅色），占左侧
cx = int(W * 0.30)
top = int(H * 0.12)
bot = int(H * 0.92)
# 身体
d.rounded_rectangle([cx - 160, top + 120, cx + 160, bot], radius=40, fill=(180, 200, 220))
# 左袖
d.rounded_rectangle([cx - 300, top + 120, cx - 150, top + 360], radius=40, fill=(180, 200, 220))
# 右袖
d.rounded_rectangle([cx + 150, top + 120, cx + 300, top + 360], radius=40, fill=(180, 200, 220))
# 领口
d.ellipse([cx - 60, top + 90, cx + 60, top + 160], fill=(160, 185, 205))

out = overlay_spec_image(
    base,
    spec_text="110码 衣长62 胸围72 腰围66 肩宽30 袖长40；120码 衣长67 胸围76 腰围70 肩宽32 袖长42",
    note="领口加宽更显脸小，主图突出拼色设计",
    category="服饰穿戴产品",
)
out.save("ai/agent-output/verify-shots/spec_overlay_v2_demo.png")
print("saved spec_overlay_v2_demo.png", out.size, resolve_spec_font(24) is not None)

# 非服饰示例（数码）
base2 = Image.new("RGB", (W, H), (235, 236, 240))
d2 = ImageDraw.Draw(base2)
d2.rounded_rectangle([int(W * 0.18), int(H * 0.25), int(W * 0.42), int(H * 0.75)], radius=30, fill=(120, 120, 130))
out2 = overlay_spec_image(
    base2,
    spec_text="高度 200mm；宽度 120mm；厚度 18mm；重量 560g",
    note="标注机身三维尺寸",
    category="数码电子产品",
)
out2.save("ai/agent-output/verify-shots/spec_overlay_v2_demo_gadget.png")
print("saved spec_overlay_v2_demo_gadget.png", out2.size)
