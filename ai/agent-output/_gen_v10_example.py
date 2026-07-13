from app.gallery_prompt import build_prompt
import types

mk = {'target_market':'北美','ecommerce_platform':'淘宝 / 天猫','visual_style':'高级质感风','tone_tendency':'高饱和色调'}
proj = types.SimpleNamespace(market_config=mk, selling_points='360度静音万向轮，承重强，适合办公')

def mkitem(tid, ps, sp=None):
    return types.SimpleNamespace(type_id=tid, personal_settings=ps, common_settings={}, note='',
        product_image='p.png', reference_images=[], output_settings={})

examples = {
    "亚马逊主图 amz（白底/无人物）": mkitem('amz', {
        '摆放状态':'斜放','拍摄角度':'俯视','有无模特':'无模特平铺展示','价值聚焦':'功能'}),
    "试穿试戴 tryon（人像/有场景）": mkitem('tryon', {
        '人种肤色':'亚洲','性别风格':'女性','展示排版':'全身穿搭全景','场景类型':'居家空间','动作姿态':'自然行走'}),
    "活动海报 promo（允许文字）": mkitem('promo', {
        '主题定位':'新品首发','主标题':'夏日清凉特惠','卖点文案':'买一送一','字体风格':'现代无衬线'}),
    "场景图 scene（生活化）": mkitem('scene', {
        '场景类型':'居家空间','氛围营造':'简约高级风','产品展示':'使用状态展示'}),
}

out = ["# 提示词引擎 V10 重构 · 视觉分桶结构示例", "",
       "> 结构：【主体】→【动作神态】→【穿搭配饰细节】→【场景地点+时间天气】→【背景环境细节】",
       "> →【光影类型】→【色调色彩】→【镜头构图+相机参数】→【画质质感】→【渲染媒介】+ 品质增强 + 负面词",
       "> 每个设置项按 BUCKET_ROUTING 进入对应桶，选择不同 → 提示词实时变化；每类带不同渲染媒介。", ""]

for title, item in examples.items():
    out.append(f"## {title}")
    out.append("")
    out.append("```")
    out.append(build_prompt(proj, item))
    out.append("```")
    out.append("")

open('ai/agent-output/prompt_v10_bucket_example.md','w',encoding='utf-8').write("\n".join(out))
print("written", len(out), "lines")
