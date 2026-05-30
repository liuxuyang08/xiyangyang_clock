# 语音版日历工具

语音版日历工具是一个以语音交互为核心的日历助手项目，目标是把“语音输入 -> 语义理解 -> 日程操作 -> 提醒通知 -> 结果播报”这条链路结构化实现。

当前项目已经具备可运行的前后端联调环境：前端提供语音输入、日历视图、实时通知和语音播报；后端提供 FastAPI REST API、WebSocket 推送、规则版 NLU、可选 LLM 结构化解析、多轮对话状态、日程与提醒服务、提醒调度器、PostgreSQL 持久化和 Redis 状态缓存。

## 技术栈

- 前端：React、TypeScript、Vite、Tailwind CSS、shadcn/ui 兼容组件结构、FullCalendar
- 语音转文字：浏览器 Web Speech API
- 语音播报：浏览器 SpeechSynthesis
- 后端：FastAPI、Uvicorn
- WebSocket：FastAPI WebSocket、`uvicorn[standard]`
- 数据库：PostgreSQL
- 缓存与在线状态：Redis
- ORM / 数据访问：SQLAlchemy async、asyncpg
- 数据校验与配置：Pydantic、pydantic-settings
- 时间解析与重复规则：dateparser、python-dateutil rrule
- 提醒调度：APScheduler
- HTTP 客户端：httpx
- 部署：Docker Compose、nginx

## 目录结构

```text
.
  backend/              FastAPI 后端
  frontend/             React + Vite 前端
  docker/               Docker 使用说明
  docs/                 开发文档、交付文档、演示脚本
  scripts/              项目级辅助脚本预留目录
  docker-compose.yml    本地完整环境编排
  .env.example          Docker Compose 环境变量示例
```

后端关键目录：

```text
backend/app/
  api/                  REST API 与 WebSocket 路由
  core/                 配置与 Redis client
  db/                   SQLAlchemy engine、session、Base
  models/               User、Event、Reminder 等 ORM 模型
  repositories/         数据访问层
  schemas/              Pydantic schema
  services/             日程、提醒、NLU、对话、调度等业务服务
```

前端关键目录：

```text
frontend/src/
  components/           日历、语音、工作区 UI 组件
  hooks/                语音识别、语音播报、WebSocket、事件数据 hooks
  lib/                  API、WebSocket、日历转换、实时消息工具
  pages/                Dashboard 页面
  types/                事件、语音、实时消息类型
```

## 当前能力

- 健康检查：`GET /api/health`
- 事件 REST API：`GET/POST/PATCH/DELETE /api/events`
- 提醒 REST API：`GET/POST/PATCH/DELETE /api/reminders`
- 统一语音命令入口：`POST /api/voice/command`
- WebSocket 实时连接：`/ws?user_id=...&session_id=...`
- PostgreSQL 异步连接与核心表建表
- Redis client 管理、对话状态缓存、WebSocket 在线状态缓存
- 核心模型：`User`、`Event`、`Reminder`、`ConversationState`、`VoiceCommand`
- 初始化脚本：`python -m scripts.init_db`
- 初始化脚本会幂等创建开发演示用户 `u001`
- Repository 层：`EventRepository`、`ReminderRepository`、`ConversationRepository`、`VoiceCommandRepository`
- Service 层：`CalendarService`、`ReminderService`、`ConflictService`、`TimeParser`、`RecurrenceParser`、`NLUService`、`LLMParseService`、`DialogService`、`ReminderScheduler`
- 规则版中文 NLU 与可选 OpenAI LLM 结构化解析
- 多轮对话状态与确认流程
- 提醒到期扫描与 WebSocket 推送
- React + Vite 前端日历工作台
- Web Speech API 语音输入与浏览器语音播报
- Docker Compose 本地部署：PostgreSQL、Redis、后端 API、前端 nginx、数据库初始化任务

## 推荐启动方式：Docker

Docker 模式使用根目录 `.env`。本地非 Docker 开发使用 `backend/.env` 和 `frontend/.env`，两套配置互不覆盖。

1. 复制环境变量：

```powershell
Copy-Item .env.example .env
```

2. 编辑根目录 `.env`，至少替换：

```env
POSTGRES_PASSWORD=postgres
JWT_SECRET=your-local-dev-secret
```

本地开发可以使用简单值；生产环境必须换成强密码和长随机密钥。

3. 启动完整环境：

```powershell
docker compose up --build
```

如果本机 Docker CLI 不支持 `docker compose` 子命令，可以使用：

```powershell
docker-compose up --build
```

4. 访问服务：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:8000/api/health
- PostgreSQL：localhost:5432
- Redis：localhost:6379

`db-init` 服务会在 API 启动前执行 `python -m scripts.init_db`，用于创建表并写入演示用户 `u001`。提醒调度器随后端 API 的 FastAPI lifespan 启动，当前没有拆出独立 scheduler/worker 容器，避免本地单机环境重复扫描提醒。

## 常用 Docker 命令

查看服务状态：

```powershell
docker compose ps
```

查看后端和前端日志：

```powershell
docker compose logs -f api frontend
```

只重建后端：

```powershell
docker compose build api
docker compose up -d api
```

重新执行数据库初始化：

```powershell
docker compose run --build --rm db-init
```

停止服务：

```powershell
docker compose down
```

清空数据库和 Redis 数据卷后重建：

```powershell
docker compose down -v
docker compose up --build
```

## 本地分开启动

如果不使用完整 Docker 编排，需要先保证 PostgreSQL 和 Redis 正在运行。可以只用 Docker 启动依赖服务：

```powershell
docker compose up postgres redis
```

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -m scripts.init_db
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端 `.env` 中的默认连接为：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/voice_calendar
REDIS_URL=redis://localhost:6379/0
```

如果你修改了 Docker 根目录 `.env` 中的 PostgreSQL 用户、密码、端口或库名，需要同步修改 `backend/.env`。

### 前端

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

前端本地开发默认访问：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

## 环境变量

根目录 `.env` 用于 Docker Compose：

- `POSTGRES_DB`：PostgreSQL 数据库名
- `POSTGRES_USER`：PostgreSQL 用户名
- `POSTGRES_PASSWORD`：PostgreSQL 密码，必填
- `POSTGRES_PORT`：暴露到宿主机的 PostgreSQL 端口
- `REDIS_PORT`：暴露到宿主机的 Redis 端口
- `API_PORT`：后端 API 暴露端口
- `FRONTEND_PORT`：前端 nginx 暴露端口
- `APP_ENV`：后端运行环境名
- `APP_NAME`：后端应用名
- `JWT_SECRET`：后端密钥，必填
- `TIMEZONE`：默认时区
- `OPENAI_API_BASE_URL`：可选。OpenAI 或 OpenAI-compatible 中转站基础地址，默认 `https://api.openai.com/v1`
- `OPENAI_API_KEY`：可选。OpenAI 或中转站提供的 API key；配置后 NLU 会优先尝试 LLM 结构化解析，失败后回落到规则解析
- `API_BASE_URL` / `API_KEY`：兼容别名。若中转站文档使用这两个名称，后端也能读取
- `WS_HEARTBEAT_INTERVAL`：WebSocket 心跳相关配置
- `REMINDER_SCAN_INTERVAL`：提醒扫描间隔
- `VITE_API_BASE_URL`：Docker 前端构建时写入的 API 地址
- `VITE_WS_URL`：Docker 前端构建时写入的 WebSocket 地址

Docker 模式下前端 nginx 会代理 `/api/` 和 `/ws` 到后端 API，所以根目录 `.env.example` 默认使用：

```env
VITE_API_BASE_URL=http://localhost:5173
VITE_WS_URL=ws://localhost:5173/ws
```

本地 Vite 开发模式下应使用后端直连地址：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

## 验证方式

健康检查：

```powershell
curl http://localhost:8000/api/health
```

返回示例：

```json
{
  "status": "ok",
  "environment": "docker",
  "database": "available",
  "redis": "available"
}
```

确认演示用户存在：

```powershell
docker compose exec -T postgres psql -U postgres -d voice_calendar -c "select id, nickname, timezone from users where id = 'u001';"
```

查看 WebSocket 是否被后端接受：

```powershell
docker compose logs --tail 80 api
```

正常日志中应出现：

```text
WebSocket /ws?user_id=u001&session_id=... [accepted]
connection open
```

运行前端构建检查：

```powershell
cd frontend
npm run build
```

运行后端测试：

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m unittest discover tests
```

## 常见问题

### 创建日程时报 `events_user_id_fkey`

现象：

```text
insert or update on table "events" violates foreign key constraint "events_user_id_fkey"
```

原因是前端默认使用 `user_id = "u001"`，但 `users` 表中没有这条用户记录。

解决方式：

```powershell
docker compose run --build --rm db-init
```

该脚本会幂等创建表并插入演示用户 `u001`。如果你清空过数据卷，例如执行了 `docker compose down -v`，需要重新启动完整环境或重新执行 `db-init`。

### 页面 WebSocket 一直显示“重连中”

先查看后端日志：

```powershell
docker compose logs --tail 80 api
```

如果出现：

```text
No supported WebSocket library detected.
Please use "pip install 'uvicorn[standard]'", or install 'websockets' or 'wsproto' manually.
```

说明后端环境没有安装 WebSocket 协议依赖。当前依赖清单已经使用 `uvicorn[standard]`，Docker 模式下重新构建 API 即可：

```powershell
docker compose build api
docker compose up -d api
```

本地虚拟环境模式下重新安装依赖：

```powershell
cd backend
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Docker 拉取镜像时报 `failed to fetch oauth token`

这通常是 Docker Hub 认证服务网络不可达。可以在 Docker Desktop 的 Docker Engine 配置中加入可用的镜像加速器。

阿里云加速器需要使用你自己阿里云 ACR 控制台提供的专属地址，通常形如：

```text
https://xxxxxx.mirror.aliyuncs.com
```

不要把 `https://registry.cn-hangzhou.aliyuncs.com` 当作通用 Docker Hub mirror 使用；它是 Registry 地址，不是 Docker Hub 加速器地址。

### 端口冲突

如果本机端口被占用，可以修改根目录 `.env`：

```env
API_PORT=8001
FRONTEND_PORT=5174
POSTGRES_PORT=5433
REDIS_PORT=6380
```

修改 `FRONTEND_PORT` 后，如果 Docker 前端仍通过 nginx 代理访问后端，需要同步修改：

```env
VITE_API_BASE_URL=http://localhost:5174
VITE_WS_URL=ws://localhost:5174/ws
```

然后重新构建前端镜像：

```powershell
docker compose build frontend
docker compose up -d frontend
```

## 文档维护约定

后续每次开发都需要同步补充 README 文档。

- 目录结构变化时，更新“目录结构”
- 新增能力时，更新“当前能力”
- 新增环境变量时，更新“环境变量”
- 新增启动、初始化、测试、部署命令时，更新对应使用说明
- 后端内部结构变化时，同步更新 `backend/README.md`
- 前端运行方式或构建参数变化时，同步更新 `frontend/README.md`
- Docker Compose 服务或端口变化时，同步更新 `docker/README.md`
