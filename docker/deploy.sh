#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────
# AI Agent Platform - 一键上线脚本 (Linux)
# 用法:
#   bash docker/deploy.sh
# 做了什么:
#   1. 检查 docker 是否在跑
#   2. 构建前端 web/dist
#   3. 生成随机 SECRET_KEY 写进 docker/.env (首次)
#   4. 去掉 Windows 开发沙箱代理 (HTTPS_PROXY/HTTP_PROXY) —— Linux 上不可达
#   5. docker compose up -d --build 拉起全部服务
# ───────────────────────────────────────────────────────────────
set -euo pipefail

# 项目根目录 (本脚本位于 <root>/docker/deploy.sh)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
WEB_DIR="$ROOT_DIR/web"
ENV_FILE="$SCRIPT_DIR/.env"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

echo "======================================"
echo " AI Agent Platform - 一键上线 (Linux)"
echo "======================================"

# 1. 检查 docker 守护进程
if ! docker info >/dev/null 2>&1; then
  echo "[ERROR] Docker 守护进程未运行，请先启动 Docker (systemctl start docker)"
  exit 1
fi
echo "[OK] Docker daemon 就绪"

# 2. 构建前端
echo "[1/4] 构建前端 web/dist ..."
cd "$WEB_DIR"
if [ ! -d node_modules ]; then
  echo "  安装前端依赖 (npm ci) ..."
  npm ci --no-audit --no-fund
fi
npm run build
echo "  前端构建完成"

# 3. 首次部署生成随机 SECRET_KEY
if ! grep -q "^SECRET_KEY=change-me-in-production$" "$ENV_FILE"; then
  echo "[2/4] SECRET_KEY 已设置，跳过"
else
  NEW_KEY="$(openssl rand -hex 32)"
  # 用 # 作分隔符避免 URL 中的 / 冲突
  sed -i "s#^SECRET_KEY=.*#SECRET_KEY=$NEW_KEY#" "$ENV_FILE"
  echo "[2/4] 已生成随机 SECRET_KEY 写入 docker/.env"
fi

# 4. 去掉 Windows 开发沙箱代理 (Linux 上不可达)
echo "[3/4] 清理 Linux 不可达的沙箱代理配置 ..."
if grep -q "host.docker.internal:33210" "$COMPOSE_FILE"; then
  # 删除 api/worker 中 export 的两行代理 (行内包含该字符串)
  sed -i "/host.docker.internal:33210/d" "$COMPOSE_FILE"
  echo "  已移除 HTTPS_PROXY/HTTP_PROXY (沙箱代理) 行"
else
  echo "  无需清理 (已无沙箱代理行)"
fi

# 5. 启动
echo "[4/4] docker compose up -d --build ..."
cd "$SCRIPT_DIR"
docker compose up -d --build

echo
echo "======================================"
echo " 全部服务已拉起"
echo "======================================"
echo " Web 前端:  http://<服务器IP>:80"
echo " API:       http://<服务器IP>:8010"
echo " MinIO 控制台: http://<服务器IP>:9001"
echo " 默认管理员: admin@example.com / admin123"
echo "--------------------------------------"
docker compose ps
echo "======================================"
