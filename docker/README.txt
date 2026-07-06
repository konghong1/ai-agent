# 启动脚本

双击 `docker/start.bat` 即可：
1. 完全清理旧容器
2. 重新构建镜像
3. 启动所有服务

# 切换数据库

编辑 `docker/.env` 中的 `DATABASE_TYPE=mysql|postgresql`，然后重新运行 start.bat

# 常用命令

```powershell
# 查看日志
docker compose logs -f api
docker compose logs -f worker

# 进入容器
docker compose exec api bash

# 停止但不删除数据
docker compose down

# 完全停止并删除数据
docker compose down -v
```
