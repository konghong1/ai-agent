# 图片模型下拉仍不显示 — 排查与修复

## 现象
全局输出配置里的「模型」下拉仍提示：
> 尚未配置 AI 提供商的图片生成模型，将使用默认模型；若未设置则生成示例图。可在「AI 提供商」中添加图片模型。

下拉里只显示「默认（自动选择 AI 提供商默认图片模型）」，没有列出具体的图片模型。

## 根因
后端 `list_image_models()` 之前**只按当前用户自己的 `provider` 过滤**；我之前的补丁虽然加了兜底，但兜底只给 `admin`。如果当前账号是普通用户、且没有自己名下的图片模型，即使系统里有其它用户（如管理员）配置好的图片模型，也不会显示出来。

> 另一个常见原因：后端代码已改，但 FastAPI 进程没重启，内存里仍在跑旧代码。

## 已修复
文件：`app/gallery_service.py`

1. `list_image_models()`：只要当前用户没有自己的图片模型，就兜底返回系统中所有已启用的图片模型（不再区分是否 admin）。
2. `_resolve_image_model()`：生成时 likewise，无自有模型则使用系统级图片模型，保证真实出图链路能走到 Agnes AI。
3. 增加 `logger.info` 日志，方便后台确认走了兜底还是用了自有模型。

## 验证

```text
user 1 (devuser, 无自有图片模型): providers=2, default=True
  兜底解析到: agnes · agnes-image-2.1-flash
user 2 (konghong, 自有 provider 2): providers=1, default=True
  解析到: agnes · agnes-image-2.1-flash
user 5 (admin, 自有 provider 3): providers=1, default=True
  解析到: Agnes AI · agnes-image-2.1-flash
```

- `python -m py_compile app/gallery_service.py`：通过
- `web/tsc --noEmit`：通过

## 必须操作
1. **重启 FastAPI 后端服务**（让新代码生效）。
2. 浏览器刷新电商套图页面（Ctrl+F5 或 Cmd+Shift+R）。
3. 再次打开「全局输出配置」→「模型」下拉，应能看到类似：
   - `agnes · agnes-image-2.1-flash`
   - `agnes · agnes-image-2.0-flash`
   - `Agnes AI · agnes-image-2.1-flash`

## 若仍不显示
请执行下面命令，把后端输出贴给我，我可以确认是用户过滤、启用状态还是模型类型问题：

```bash
cd /c/workspace/ai-agent
.venv/Scripts/python.exe -c "
import sqlite3
c = sqlite3.connect('agent.db')
print('--- users ---')
for r in c.execute('SELECT id, username, role FROM users'):
    print(r)
print('--- providers ---')
for r in c.execute('SELECT id, user_id, name, enabled FROM providers'):
    print(r)
print('--- image models ---')
for r in c.execute('''SELECT id, provider_id, model_name, enabled, is_default_image FROM provider_models WHERE model_type='image' '''):
    print(r)
"
```
