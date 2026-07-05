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
