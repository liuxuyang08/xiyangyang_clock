# backend

FastAPI 后端目录。

当前阶段已包含配置管理、健康检查、PostgreSQL 异步连接、Redis 统一 client 管理、核心 SQLAlchemy 模型、初始化建表脚本、Repository 层、Pydantic schema、`CalendarService`、`ReminderService`、`ConflictService`、`TimeParser`、事件 REST API 和提醒 REST API。

尚未实现语音入口、提醒调度、WebSocket 和前端。

## 依赖配置

本项目当前采用单一依赖清单：

- `backend/requirements.txt`

数据库访问方案采用异步栈：

- `SQLAlchemy[asyncio]`
- `asyncpg`

## 安装依赖

在 `backend/` 目录下执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 配置文件

- `.env.example`：环境变量示例
- `.env`：本地实际配置文件，建议由 `.env.example` 复制生成
- `app/core/config.py`：配置读取入口，使用 `pydantic-settings`

支持的环境变量：

- `APP_ENV`
- `APP_NAME`
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `TIMEZONE`
- `OPENAI_API_KEY`
- `WS_HEARTBEAT_INTERVAL`
- `REMINDER_SCAN_INTERVAL`

复制配置：

```powershell
Copy-Item .env.example .env
```

## 数据库

数据库连接相关文件：

- `app/db/base.py`：SQLAlchemy `Base`
- `app/db/session.py`：异步 `engine`、`SessionLocal`、数据库会话 dependency、数据库健康检查

当前项目还没有引入 Alembic。为了避免重复维护多套互相冲突的建表方式，现阶段只提供一个初始化脚本：

- `scripts/init_db.py`

该脚本会基于 SQLAlchemy `Base.metadata.create_all` 创建当前核心表：

- `users`
- `events`
- `reminders`
- `conversation_states`
- `voice_commands`

初始化数据库：

```powershell
python -m scripts.init_db
```

该脚本只创建尚不存在的表，不实现迁移版本管理，也不写入业务数据。

## Redis

Redis 统一 client 管理位于：

- `app/core/redis.py`

当前能力：

- 读取 `REDIS_URL`
- 统一创建 Redis async client
- 提供 Redis 健康检查
- 在 FastAPI lifespan 结束时关闭 Redis client

后续 `conversation_state` 临时缓存和 WebSocket 在线状态都应复用这里的统一入口，不要在业务代码中散乱创建 Redis 连接。

## 模型

核心 SQLAlchemy 模型位于 `app/models/`：

- `user.py`：`User`
- `event.py`：`Event`
- `reminder.py`：`Reminder`
- `conversation_state.py`：`ConversationState`
- `voice_command.py`：`VoiceCommand`

模型约定：

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

API 后续不应直接返回 ORM 对象，应转换为 schema 或结构化响应。

## Service 层

Service 位于 `app/services/`。

当前已实现：

- `CalendarService`
- `ReminderService`
- `ConflictService`
- `TimeParser`

`CalendarService` 支持：

- `create_event`
- `list_events_by_range`
- `get_event`
- `update_event`
- `soft_delete_event`
- `search_candidate_events`

当前行为：

- 默认只处理 `active` 事件
- 删除必须软删除
- 时间范围查询按 `start_time` 排序
- 更新事件时自动更新 `updated_at`

`ReminderService` 支持：

- `create_reminder`
- `list_reminders`
- `cancel_reminder`
- `cancel_event_reminders`
- `list_due_pending_reminders`
- `mark_sent`
- `mark_failed`

当前行为：

- `remind_time` 不能早于当前时间，除非显式启用测试标记
- 取消日程时可以取消该日程下所有 `pending` 提醒
- 提醒状态至少覆盖 `pending`、`sent`、`cancelled`、`failed`

`ConflictService` 支持：

- 判断两个时间区间是否冲突
- 根据 `user_id`、`start_time`、`end_time` 查询冲突事件
- 修改事件时排除当前事件自身

当前行为：

- 冲突规则为 `new_start < existing_end` 且 `new_end > existing_start`
- 只返回冲突事件摘要，不做确认逻辑
- 返回内容包含冲突事件 `id`、`title`、`start_time`、`end_time`

`TimeParser` 支持：

- 输入 `text`、`base_time`、`timezone`
- 优先使用自定义中文规则解析
- 使用 `dateparser` 作为兜底解析
- 输出结构化 `TimeParseResult`
- 保留兼容字段 `datetime`
- 对区间表达返回 `start_datetime`、`end_datetime`、`is_range`
- 对已过去的时间返回 `is_past=True` 并标记需要追问
- 对模糊表达返回 `ambiguous=True`

当前支持的基础表达：

- `今天`
- `明天`
- `后天`
- `本周一` 到 `本周日`
- `下周一` 到 `下周日`
- `上午十点`
- `下午三点`
- `晚上八点半`
- `周五下午三点`
- `下周三上午十点半`
- `明天下午三点`
- `后天上午九点`
- `一小时后`
- `半小时后`

当前行为：

- 只说 `月底前`、`周末`、`睡前`、`上班前` 等表达时，返回 `ambiguous=True`
- 可解析但已经过去的时间，会返回 `is_past=True`，供业务层追问
- 缺少明确钟点的表达仍会返回 `need_followup=True`
- 不创建日程，不做 NLU

## API 路由

路由位于 `app/api/`。

当前已实现事件 REST API：

- `GET /api/events`
- `POST /api/events`
- `GET /api/events/{event_id}`
- `PATCH /api/events/{event_id}`
- `DELETE /api/events/{event_id}`

接口约定：

- `GET /api/events` 支持 `user_id`、`start`、`end` 查询参数
- `DELETE /api/events/{event_id}` 执行软删除
- 返回统一使用 `ApiResponse`
- 路由层只负责参数接收、服务调用和 schema 转换，不堆业务逻辑

当前已实现提醒 REST API：

- `GET /api/reminders`
- `POST /api/reminders`
- `PATCH /api/reminders/{reminder_id}`
- `DELETE /api/reminders/{reminder_id}`

接口约定：

- `GET /api/reminders` 支持 `user_id` 和 `status` 查询参数
- `DELETE /api/reminders/{reminder_id}` 不物理删除，改为 `cancelled`
- 返回统一使用 `ApiResponse`
- 路由层只负责参数接收、服务调用和 schema 转换，不实现调度逻辑

## 启动 FastAPI

在 `backend/` 目录下启动：

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 健康检查

启动后可访问：

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

该接口只返回环境名和依赖连通状态，不暴露数据库地址、密钥或其他敏感配置。

## 目录结构

```text
backend/
  app/
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
    api/
      events.py
      reminders.py
    schemas/
      common.py
      event.py
      reminder.py
      voice.py
      conversation.py
    services/
      calendar_service.py
      conflict_service.py
      reminder_service.py
      time_parser.py
    main.py
  scripts/
    init_db.py
  .env.example
  requirements.txt
  README.md
```

## 后续开发

建议顺序：

1. 实现 NLU 服务
2. 实现多轮对话服务
3. 实现 `/api/voice/command`
4. 实现提醒调度 worker
5. 实现 WebSocket 推送
6. 补充测试与 Docker 编排

## 文档维护约定

后续每次后端开发都需要同步更新本文档。

- 新增依赖时，更新“依赖配置”
- 新增环境变量时，更新“配置文件”
- 新增表、索引、初始化方式时，更新“数据库”
- 新增 Redis 用法时，更新“Redis”
- 新增模型、Repository、Schema、Service、API 时，更新对应章节
- 新增启动、测试、部署命令时，更新对应使用说明
