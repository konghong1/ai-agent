# AI Agent Platform — Docker 启动流程

## 前提条件

- Docker Engine 20.10+
- Docker Compose v2.0+
- 至少 4GB 可用内存
- 至少 10GB 磁盘空间

## 快速启动（一键命令）

```bash
# 1. 进入 docker 目录
cd C:/workspace/ai-agent/docker

# 2. 一键启动所有服务
docker compose up -d --build

# 3. 查看启动状态
docker compose ps

# 4. 查看日志（可选）
docker compose logs -f api
```

启动成功后，访问：
- **API**: `http://localhost:8010`
- **Web 前端**: `http://localhost:80`
- **MinIO 控制台**: `http://localhost:9001` (minioadmin/minioadmin)
- **MySQL**: `localhost:3306` (用户名: ai_agent, 密码: ai_agent_secure_2026)

## 手动步骤（详细版）

### Step 1: 配置环境变量

```bash
cd C:/workspace/ai-agent/docker
# 环境变量已预配置，如有需要可编辑 .env 文件
notepad .env
```

关键配置项：
```ini
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_PASSWORD=ai_agent_secure_2026
AGNES_API_KEY=your_aghes_api_key
SECRET_KEY=your_secret_key
```

### Step 2: 启动基础设施服务

```bash
# 只启动 MySQL 和 MinIO（不启动 API/Worker）
docker compose up -d mysql minio minio-init
```

验证 MySQL 就绪：
```bash
docker compose exec mysql mysql -u root -p${MYSQL_ROOT_PASSWORD} -e "SHOW DATABASES;"
```

验证 MinIO 就绪：
```bash
docker compose exec minio mc alias list local
```

### Step 3: 启动 API 和 Worker

```bash
# 启动完整栈
docker compose up -d api worker
```

验证 API 就绪：
```bash
curl http://localhost:8010/health
# 应返回: {"status":"ok"}
```

### Step 4: 启动前端（可选）

```bash
# 如果已有前端构建文件
docker compose up -d web
```

## 数据库初始化

数据库在首次启动时自动初始化：
1. MySQL 容器启动时执行 `docker/db/init.sql`
2. API 容器启动时运行 `python -m app.db.init_db`（种子数据）

如需手动初始化：
```bash
docker compose exec api python -m app.db.init_db
```

## 常用运维命令

### 查看所有服务状态
```bash
docker compose ps
```

### 查看日志
```bash
# 所有服务
docker compose logs -f

# 单个服务
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f mysql
docker compose logs -f minio
```

### 重启服务
```bash
# 重启 API
docker compose restart api

# 重启 Worker
docker compose restart worker

# 重启全部
docker compose restart
```

### 停止服务
```bash
# 停止所有服务
docker compose down

# 停止并删除数据卷（⚠️ 危险操作）
docker compose down -v
```

### 查看容器资源占用
```bash
docker stats
```

### 进入容器 Shell
```bash
docker compose exec api bash
docker compose exec mysql bash
docker compose exec minio bash
```

### 备份数据库
```bash
docker compose exec mysql mysqldump -u root -p${MYSQL_ROOT_PASSWORD} ai_agent > backup.sql
```

### 恢复数据库
```bash
cat backup.sql | docker compose exec -T mysql mysql -u root -p${MYSQL_ROOT_PASSWORD} ai_agent
```

### 更新代码并重启
```bash
# 1. 拉取最新代码
git pull

# 2. 重建并重启
docker compose up -d --build api worker

# 3. 重新初始化数据库（如果有 schema 变更）
docker compose exec api python -m app.db.init_db
```

## 故障排查

### MySQL 启动失败
```bash
# 查看错误日志
docker compose logs mysql

# 常见原因：端口冲突（3306 已被占用）
# 解决方法：修改 .env 中的 API_PORT 或使用其他端口
```

### MinIO 无法访问
```bash
# 检查 bucket 是否创建
docker compose exec minio mc ls local

# 手动创建 bucket
docker compose exec minio-init sh -c "mc mb local/media-assets"
```

### API 无法连接数据库
```bash
# 检查环境变量
docker compose exec api env | grep DATABASE_URL

# 测试连接
docker compose exec api python -c "from sqlalchemy import create_engine; print(create_engine('mysql+pymysql://ai_agent:ai_agent_secure_2026@mysql:3306/ai_agent').connect())"
```

### Worker 未下载媒体
```bash
# 查看 worker 日志
docker compose logs worker

# 检查 MinIO 存储
docker compose exec minio mc ls local/media-assets
```

### 清除所有数据重新开始
```bash
# ⚠️ 这会删除所有数据！
docker compose down -v
docker compose up -d
```

## 生产环境部署

### 1. 修改敏感信息
```bash
# 编辑 .env 文件
MYSQL_ROOT_PASSWORD=<strong-random-password>
MYSQL_PASSWORD=<strong-random-password>
SECRET_KEY=<generated-secret-key>
AGNES_API_KEY=<your-real-api-key>
```

### 2. 启用 HTTPS
```bash
# 配置 Nginx SSL
# 编辑 docker/nginx.conf
```

### 3. 设置数据备份
```bash
# 添加 cron job 定期备份
0 2 * * * docker compose exec mysql mysqldump -u root -p$MYSQL_ROOT_PASSWORD ai_agent > /backup/ai_agent_$(date +\%Y\%m\%d).sql
```

### 4. 监控和资源限制
```yaml
# 在 docker-compose.yml 中添加
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 1G
```

## 服务端口映射

| 服务 | 容器端口 | 主机端口 | 说明 |
|------|---------|---------|------|
| API | 8010 | 8010 | FastAPI 后端 |
| MySQL | 3306 | 3306 | 数据库 |
| MinIO API | 9000 | 9000 | 对象存储 API |
| MinIO Console | 9001 | 9001 | 对象存储管理界面 |
| Web (Nginx) | 80 | 80 | 前端 + API 代理 |

## 数据持久化

所有数据通过 Docker volumes 持久化：
- `mysql_data` — MySQL 数据库文件
- `minio_data` — MinIO 对象存储文件

查看数据卷：
```bash
docker volume ls | grep ai-agent
```

## 更新数据库 Schema

当修改模型时：
1. 更新 `app/models/__init__.py`
2. 手动添加 ALTER TABLE 语句到 `docker/db/migrations/`
3. 运行 `docker compose restart api`（会自动执行迁移）

## 注意事项

1. **首次启动较慢** — 需要下载 MySQL、MinIO 等镜像，约需 2-5 分钟
2. **数据持久化** — 所有数据通过 Docker volumes 保存，`docker compose down -v` 会清除
3. **端口冲突** — 确保 3306、8010、9000、9001 未被占用
4. **MinIO 兼容性** — 使用 MinIO 完全兼容 AWS S3 和 RustFS，可随时替换

## 完整启动脚本（推荐）

创建 `docker/start.sh`：

```bash
#!/bin/bash
set -e

echo "======================================"
echo "AI Agent Platform - Docker 启动流程"
echo "======================================"

# 1. 停止旧容器
echo "[1/5] 停止旧容器..."
docker compose down 2>/dev/null || true

# 2. 清理旧数据（可选，默认不清理）
echo "[2/5] 保留数据卷..."

# 3. 启动基础设施
echo "[3/5] 启动基础设施 (MySQL + MinIO)..."
docker compose up -d mysql minio minio-init

# 等待 MySQL 就绪
echo "  等待 MySQL 就绪..."
until docker compose exec mysql mysqladmin ping -h localhost -u root -p${MYSQL_ROOT_PASSWORD:-root_secure_2026} &>/dev/null; do
  sleep 2
done
echo "  ✓ MySQL 就绪"

# 4. 启动 API 和 Worker
echo "[4/5] 启动 API 和 Worker..."
docker compose up -d api worker

# 等待 API 就绪
echo "  等待 API 就绪..."
for i in {1..30}; do
  if curl -s http://localhost:8010/health | grep -q '"ok"'; then
    echo "  ✓ API 就绪"
    break
  fi
  sleep 2
done

# 5. 初始化数据库
echo "[5/5] 初始化数据库种子数据..."
docker compose exec api python -m app.db.init_db

echo ""
echo "======================================"
echo "✓ 所有服务启动完成！"
echo "======================================"
echo "API:      http://localhost:8010"
echo "Web:      http://localhost:80"
echo "MinIO:    http://localhost:9001"
echo "MySQL:    localhost:3306"
echo ""
echo "默认管理员账号:"
echo "  用户名: admin"
echo "  密码: admin123"
echo "======================================"
```

赋予执行权限后一键启动：
```bash
chmod +x docker/start.sh
./docker/start.sh
```
