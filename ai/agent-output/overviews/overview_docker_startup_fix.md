# Docker 启动失败 · 根因与修复

## 现象
在 `docker\` 目录下执行 `start.bat`，前两步（构建前端、移除旧容器）后卡在：
```
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running
```
随后 `start.bat` 仍打印假的「All services are running」。

## 根因
`npipe:////./pipe/dockerDesktopLinuxEngine` 是 Windows 上 Docker 守护进程的命名管道。
连不上 = **Docker Desktop 没在运行**（已安装，但进程未启动），守护进程自然没建立。

## 修复内容
1. **启动守护进程**：拉起 `Docker Desktop.exe`，守护进程就绪（server 29.6.1）。
2. **加固 `docker/start.bat`**：
   - 增加 daemon 预检——连不上立刻给出明确报错并退出，不再误导打印「All services are running」。
   - 把 `C:\Program Files\Docker\Docker\resources\bin` 注入 PATH，规避 `docker-credential-desktop` 凭据助手在 PATH 找不到导致的 `error getting credentials` 构建失败。
3. **让后端加载新代码（关键认知）**：
   - `docker-compose.yml` 中 `api`/`worker` 用 `volumes: - ../:/app` 将整个项目**绑定挂载**进容器。
   - 因此代码改动（如新增的 `custom` 策划类型）不在镜像里，盘上文件改了即生效。
   - **正确做法 = `docker compose restart api worker`（秒级）**，uvicorn 重启即重读挂载的新代码；**无需重建 12.7GB 重镜像**（会重装全部 ML 依赖，数分钟起步）。误启的 `--build` 重型重建已中止。

## 验证结果（全绿）
| 服务 | 状态 |
|------|------|
| ai-agent-api (8010) | `{"status":"ok"}` ✓ |
| ai-agent-web (80) | HTTP 200 ✓ |
| ai-agent-minio (9001) | HTTP 200 ✓ |
| ai-agent-mysql | healthy ✓ |
| ai-agent-worker | Up ✓ |

后端 `GET /api/gallery/types` 返回 **19 个类型且含 `custom`**，确认新策划类型已生效。

## 以后怎么跑
直接双击/在 `docker\` 下跑 `start.bat` 即可——前提是 **Docker Desktop 已启动**。
若报同样的 `npipe` 错，先确认系统托盘里 Docker 图标已变绿（守护进程就绪）再重跑。
