# backend

FastAPI 后端目录，负责日程、提醒、语音命令解析、多轮对话状态、WebSocket 实时推送和提醒调度。

## 技术栈

- FastAPI
- Uvicorn，依赖使用 `uvicorn[standard]`，用于提供 WebSocket 协议支持
- SQLAlchemy async
- asyncpg
- PostgreSQL
- Redis
- Pydantic / pydantic-settings
- dateparser
- python-dateutil
- APScheduler
- httpx

## 快速启动

在 `backend/` 目录下执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -m scripts.init_db
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

启动后访问：

```http
GET /api/health
```

返回示例：

```json
{
  "status": "ok",
  "environment": "dev",
  "database": "available",
  "redis": "available"
}
```

## 配置文件

- `.env.example`：环境变量示例
- `.env`：本地实际配置文件，建议从 `.env.example` 复制生成
- `app/core/config.py`：配置读取入口，使用 `pydantic-settings`

支持的环境变量：

- `APP_ENV`
- `APP_NAME`
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `TIMEZONE`
- `OPENAI_API_BASE_URL`
- `OPENAI_API_KEY`
- `API_BASE_URL` / `API_KEY`，作为 OpenAI-compatible 中转站常见命名的兼容别名
- `WS_HEARTBEAT_INTERVAL`
- `REMINDER_SCAN_INTERVAL`

本地默认数据库和 Redis 配置：

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/voice_calendar
REDIS_URL=redis://localhost:6379/0
```

如果使用根目录 Docker Compose 启动 PostgreSQL / Redis，并且修改过根目录 `.env` 中的数据库账号、密码、端口或库名，需要同步更新 `backend/.env`。

OpenAI 官方接口默认配置：

```env
OPENAI_API_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=
```

如果使用 OpenAI-compatible 中转站，将 `OPENAI_API_BASE_URL` 改为中转站提供的基础地址，将 `OPENAI_API_KEY` 改为中转站提供的 key。后端也兼容读取 `API_BASE_URL` 和 `API_KEY`。

## 数据库

数据库连接相关文件：

- `app/db/base.py`：SQLAlchemy `Base`
- `app/db/session.py`：异步 `engine`、`SessionLocal`、数据库会话 dependency、数据库健康检查
- `scripts/init_db.py`：建表和开发演示数据初始化脚本

当前项目还没有引入 Alembic。现阶段通过以下命令创建表：

```powershell
python -m scripts.init_db
```

该脚本会基于 `Base.metadata.create_all` 创建以下表：

- `users`
- `events`
- `reminders`
- `conversation_states`
- `voice_commands`

脚本还会幂等插入一个开发演示用户：

```text
id: u001
nickname: Demo User
timezone: Asia/Shanghai
default_reminder_minutes: 15
```

前端当前默认使用 `user_id = "u001"`。如果数据库中缺少该用户，创建日程时会触发 `events_user_id_fkey` 外键错误，因此初始化数据库后必须确保该用户存在。

## Redis

Redis 统一 client 管理位于：

- `app/core/redis.py`

当前用途：

- Redis 健康检查
- 多轮对话状态临时缓存
- WebSocket 在线状态缓存
- FastAPI lifespan 结束时统一关闭 Redis client

多轮对话状态使用的 Redis key：

- `voice:session:{session_id}`
- `voice:user:{user_id}:state`
- `voice:user:{user_id}:pending_confirm`

WebSocket 在线状态使用的 Redis key：

- `voice:ws:online:{user_id}`

## 模型

核心 SQLAlchemy 模型位于 `app/models/`：

- `user.py`：`User`
- `event.py`：`Event`
- `reminder.py`：`Reminder`
- `conversation_state.py`：`ConversationState`
- `voice_command.py`：`VoiceCommand`

模型约定：

- `Event.user_id`、`Reminder.user_id`、`ConversationState.user_id`、`VoiceCommand.user_id` 均通过外键关联 `users.id`
- `Event` 删除采用软删除，通过 `status = "deleted"` 和 `deleted_at` 表达
- `participants`、`recurrence_rule`、`slots`、`missing_slots`、`candidate_events`、`entities` 使用 JSON 字段
- 已建立核心查询索引，包括事件时间查询、提醒到期查询、会话状态查询和语音命令日志查询

## Repository 层

Repository 位于 `app/repositories/`：

- `EventRepository`
- `ReminderRepository`
- `ConversationRepository`
- `VoiceCommandRepository`

Repository 只负责数据访问：

- `create`
- `get_by_id`
- `update`
- `list` / `search`

补充能力：

- `EventRepository.list_by_time_range`
- `EventRepository.search_candidates`
- `EventRepository.soft_delete`
- `ReminderRepository.list_due_pending`
- `ReminderRepository.update_status`

Repository 方法只 `flush`，不主动 `commit`，事务边界由上层服务或 API 控制。

## Schema

Pydantic schema 位于 `app/schemas/`：

- `common.py`：统一响应结构
- `event.py`：`EventCreate`、`EventUpdate`、`EventRead`
- `reminder.py`：`ReminderCreate`、`ReminderUpdate`、`ReminderRead`
- `voice.py`：`VoiceCommandRequest`、`VoiceCommandResponse`、`VoiceCommandRead`
- `conversation.py`：`ConversationStateRead`

统一语音命令响应格式：

```json
{
  "action": "event_created",
  "need_user_reply": false,
  "reply": "已为你创建明天下午 3 点的提醒：交项目文档。",
  "data": {}
}
```

API 不应直接返回 ORM 对象，应转换为 schema 或结构化响应。

## Service 层

Service 位于 `app/services/`。

当前已实现：

- `CalendarService`
- `ReminderService`
- `ConflictService`
- `NLUService`
- `LLMParseService`
- `DialogService`
- `TimeParser`
- `RecurrenceParser`
- `ReminderScheduler`
- `WebSocketManager`
- `VoiceCommandLogService`

核心职责：

- `CalendarService`：创建、查询、更新、软删除日程
- `ReminderService`：创建、查询、取消和标记提醒
- `ConflictService`：检测时间区间冲突
- `TimeParser`：解析中文时间表达，识别模糊和过去时间
- `RecurrenceParser`：解析中文重复规则，输出兼容结构和 `RRULE:` 字符串
- `NLUService`：规则版意图识别与实体抽取，可选 LLM 结构化解析
- `LLMParseService`：封装大模型结构化解析，不执行业务操作
- `DialogService`：管理多轮对话状态、候选项和确认流程
- `ReminderScheduler`：扫描到期提醒并通过 WebSocket 推送
- `WebSocketManager`：管理用户会话连接、心跳和广播
- `VoiceCommandLogService`：记录语音命令处理过程

## API 路由

路由位于 `app/api/`。

健康检查：

- `GET /api/health`

事件 API：

- `GET /api/events`
- `POST /api/events`
- `GET /api/events/{event_id}`
- `PATCH /api/events/{event_id}`
- `DELETE /api/events/{event_id}`

提醒 API：

- `GET /api/reminders`
- `POST /api/reminders`
- `PATCH /api/reminders/{reminder_id}`
- `DELETE /api/reminders/{reminder_id}`

语音命令 API：

- `POST /api/voice/command`

WebSocket：

- `/ws?user_id={user_id}&session_id={session_id}`

WebSocket 客户端可以发送心跳：

```json
{
  "type": "heartbeat",
  "user_id": "u001",
  "session_id": "session-1",
  "client_time": "2026-05-30T12:00:00+08:00"
}
```

## 测试

在 `backend/` 目录下执行：

```powershell
.venv\Scripts\Activate.ps1
python -m unittest discover tests
```

如果还没有创建虚拟环境，先执行“快速启动”中的依赖安装步骤。

## Docker 使用

推荐从项目根目录使用 Docker Compose 启动完整环境：

```powershell
Copy-Item .env.example .env
docker compose up --build
```

单独重建后端镜像：

```powershell
docker compose build api
docker compose up -d api
```

重新执行数据库初始化：

```powershell
docker compose run --build --rm db-init
```

## 常见问题

### 创建日程时报 `events_user_id_fkey`

原因是 `events.user_id` 外键要求用户必须先存在于 `users` 表。前端默认使用 `u001`，需要执行：

```powershell
python -m scripts.init_db
```

Docker 模式下执行：

```powershell
docker compose run --build --rm db-init
```

### WebSocket 一直重连

先检查后端日志：

```powershell
docker compose logs --tail 80 api
```

如果看到：

```text
No supported WebSocket library detected.
Please use "pip install 'uvicorn[standard]'"
```

说明当前运行环境缺少 WebSocket 协议依赖。当前 `requirements.txt` 已使用 `uvicorn[standard]`，重新安装依赖或重建后端镜像即可：

```powershell
pip install -r requirements.txt
```

或：

```powershell
docker compose build api
docker compose up -d api
```

正常连接时日志应出现：

```text
WebSocket /ws?user_id=u001&session_id=... [accepted]
connection open
```

## 目录结构

```text
backend/
  app/
    api/
      events.py
      reminders.py
      voice.py
      ws.py
    core/
      config.py
      redis.py
    db/
      base.py
      session.py
    models/
      user.py
      event.py
      reminder.py
      conversation_state.py
      voice_command.py
    repositories/
      event_repository.py
      reminder_repository.py
      conversation_repository.py
      voice_command_repository.py
    schemas/
      common.py
      event.py
      reminder.py
      voice.py
      conversation.py
    services/
      calendar_service.py
      conflict_service.py
      dialog_service.py
      llm_parse_service.py
      nlu_service.py
      recurrence_parser.py
      reminder_scheduler.py
      reminder_service.py
      time_parser.py
      voice_command_log_service.py
      websocket_manager.py
    main.py
  scripts/
    init_db.py
  tests/
  .env.example
  requirements.txt
  README.md
```

## 文档维护约定

后续每次后端开发都需要同步更新本文档。

- 新增依赖时，更新“技术栈”和“常见问题”
- 新增环境变量时，更新“配置文件”
- 新增表、索引、初始化方式时，更新“数据库”
- 新增 Redis key 时，更新“Redis”
- 新增模型、Repository、Schema、Service、API 时，更新对应章节
- 新增启动、测试、部署命令时，更新对应使用说明
