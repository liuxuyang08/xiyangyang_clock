# Docker 本地部署

Docker Compose 配置位于项目根目录：

- `docker-compose.yml`
- `.env.example`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`

## 服务组成

- `postgres`：PostgreSQL 16
- `redis`：Redis 7
- `db-init`：数据库建表和演示用户初始化任务
- `api`：FastAPI 后端
- `frontend`：nginx 静态前端和反向代理

依赖关系：

```text
postgres healthy
  -> db-init completed
  -> api healthy
  -> frontend

redis healthy
  -> api
```

`db-init` 会执行：

```powershell
python -m scripts.init_db
```

该脚本会创建核心表，并幂等插入前端演示用户 `u001`。

## 启动

在项目根目录执行：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少替换：

```env
POSTGRES_PASSWORD=postgres
JWT_SECRET=your-local-dev-secret
```

启动完整环境：

```powershell
docker compose up --build
```

后台启动：

```powershell
docker compose up -d --build
```

如果本机 Docker CLI 不支持 `docker compose` 子命令，可以使用：

```powershell
docker-compose up --build
```

## 访问地址

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:8000/api/health
- 前端代理健康检查：http://localhost:5173/api/health
- WebSocket：ws://localhost:5173/ws
- PostgreSQL：localhost:5432
- Redis：localhost:6379

Docker 前端通过 nginx 代理：

- `/api/` -> `http://api:8000/api/`
- `/ws` -> `http://api:8000/ws`

因此 Docker 模式下，前端构建参数默认是：

```env
VITE_API_BASE_URL=http://localhost:5173
VITE_WS_URL=ws://localhost:5173/ws
```

## 常用命令

查看服务状态：

```powershell
docker compose ps
```

查看日志：

```powershell
docker compose logs -f
```

只看后端和前端日志：

```powershell
docker compose logs -f api frontend
```

重新构建后端：

```powershell
docker compose build api
docker compose up -d api
```

重新构建前端：

```powershell
docker compose build frontend
docker compose up -d frontend
```

重新执行数据库初始化：

```powershell
docker compose run --build --rm db-init
```

停止服务：

```powershell
docker compose down
```

清空数据卷并重建：

```powershell
docker compose down -v
docker compose up --build
```

## 环境变量

根目录 `.env` 仅用于 Docker Compose。本地非 Docker 开发继续使用：

- `backend/.env`
- `frontend/.env`

常用变量：

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_PORT`
- `REDIS_PORT`
- `API_PORT`
- `FRONTEND_PORT`
- `APP_ENV`
- `APP_NAME`
- `JWT_SECRET`
- `TIMEZONE`
- `OPENAI_API_BASE_URL`
- `OPENAI_API_KEY`
- `API_BASE_URL`
- `API_KEY`
- `WS_HEARTBEAT_INTERVAL`
- `REMINDER_SCAN_INTERVAL`
- `VITE_API_BASE_URL`
- `VITE_WS_URL`

`OPENAI_API_BASE_URL` / `OPENAI_API_KEY` 用于 OpenAI 或 OpenAI-compatible 中转站。`API_BASE_URL` / `API_KEY` 是兼容别名，方便直接粘贴部分中转站提供的配置命名。

如果修改 `FRONTEND_PORT`，需要同步修改：

```env
VITE_API_BASE_URL=http://localhost:{FRONTEND_PORT}
VITE_WS_URL=ws://localhost:{FRONTEND_PORT}/ws
```

然后重新构建前端镜像。

## 数据持久化

Compose 使用两个命名卷：

- `postgres_data`
- `redis_data`

普通重启不会清空数据：

```powershell
docker compose down
docker compose up
```

如果执行：

```powershell
docker compose down -v
```

PostgreSQL 和 Redis 数据都会被删除。下次启动时需要重新执行 `db-init`，完整 `docker compose up --build` 会自动处理。

## 常见问题

### Docker 拉取镜像失败

如果出现：

```text
failed to fetch oauth token
connectex: A connection attempt failed
```

通常是 Docker Hub 认证服务网络不可达。可以在 Docker Desktop 的 Docker Engine 配置中配置可用镜像加速器。

阿里云加速器需要使用阿里云 ACR 控制台里的专属地址，通常形如：

```text
https://xxxxxx.mirror.aliyuncs.com
```

不要把下面这个地址当作通用 Docker Hub mirror：

```text
https://registry.cn-hangzhou.aliyuncs.com
```

它是 Registry 地址，不是通用 Docker Hub 加速器地址。

### 创建日程时报外键错误

如果后端日志出现 `events_user_id_fkey`，说明 `users` 表中缺少前端默认用户 `u001`。

执行：

```powershell
docker compose run --build --rm db-init
```

验证：

```powershell
docker compose exec -T postgres psql -U postgres -d voice_calendar -c "select id, nickname from users where id = 'u001';"
```

### WebSocket 一直重连

查看后端日志：

```powershell
docker compose logs --tail 80 api
```

如果看到：

```text
No supported WebSocket library detected.
```

说明后端镜像缺少 WebSocket 协议依赖。当前项目已在 `backend/requirements.txt` 中使用 `uvicorn[standard]`，重新构建后端即可：

```powershell
docker compose build api
docker compose up -d api
```

正常日志：

```text
WebSocket /ws?user_id=u001&session_id=... [accepted]
connection open
```

### 前端修改环境变量后不生效

Docker 前端环境变量在镜像构建时写入静态包。修改根目录 `.env` 后，需要重新构建前端：

```powershell
docker compose build frontend
docker compose up -d frontend
```

### API 健康检查失败

先查看服务状态：

```powershell
docker compose ps
```

再查看后端日志：

```powershell
docker compose logs --tail 120 api
```

常见原因：

- PostgreSQL 密码和 `DATABASE_URL` 不一致
- PostgreSQL 或 Redis 未 healthy
- `db-init` 执行失败
- 后端依赖镜像未重新构建

## 调度器说明

当前提醒调度器随后端 API 进程启动，Compose 中没有单独的 scheduler/worker 服务。

这样做可以避免本地单机环境中多个 worker 同时扫描同一批提醒。后续如果拆分生产部署，需要引入单实例调度约束或分布式锁。
