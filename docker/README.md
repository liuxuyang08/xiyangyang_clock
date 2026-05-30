# docker

Docker 本地部署入口位于项目根目录：

- `docker-compose.yml`
- `.env.example`
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`

启动步骤：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

如果本机 Docker CLI 不支持 `docker compose` 子命令，可以使用：

```powershell
docker-compose up --build
```

根目录 `.env` 仅用于 Docker Compose。本地非 Docker 开发继续使用 `backend/.env` 和 `frontend/.env`。

当前提醒调度器随后端 API 进程启动，compose 中没有单独的 scheduler/worker 服务。
