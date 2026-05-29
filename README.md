# 语音版日历工具

语音版日历工具是一个以语音交互为核心的日历助手项目，目标是把“语音输入 -> 语义理解 -> 日程操作 -> 提醒通知 -> 结果播报”这条链路结构化实现。

当前仓库已经完成项目基础目录、后端基础配置、数据库与 Redis 连接、核心数据模型、初始化建表脚本、Repository 层、Pydantic schema、`CalendarService`、`ReminderService`、`ConflictService`、`TimeParser`、事件 REST API 和提醒 REST API。前端工程、语音入口、提醒调度和 WebSocket 尚未实现。

## 技术栈概览

- 前端：React、Vite、shadcn/ui、FullCalendar
- 语音转文字：Web Speech API / gpt-4o-transcribe
- 语音播报：Web Speech API SpeechSynthesis / OpenAI Text-to-Speech
- 后端：FastAPI
- 数据库：PostgreSQL
- 缓存与会话状态：Redis
- ORM / 数据访问：SQLAlchemy async
- 数据校验与配置：Pydantic、pydantic-settings
- 时间解析与重复规则：dateparser、python-dateutil rrule
- 提醒调度：APScheduler
- HTTP 客户端：httpx
- 部署：Docker

## 目录说明

- `docs/`：需求、技术选型、开发文档和开发提示词
- `frontend/`：前端应用预留目录，后续放置 React / Vite 工程
- `backend/`：FastAPI 后端目录
- `backend/app/core/`：配置读取、Redis client 管理等核心基础设施
- `backend/app/api/`：FastAPI 路由层，目前已实现事件和提醒 REST API
- `backend/app/db/`：SQLAlchemy engine、SessionLocal、Base、数据库会话 dependency
- `backend/app/models/`：核心 SQLAlchemy 模型
- `backend/app/repositories/`：核心模型的数据访问层
- `backend/app/schemas/`：Pydantic schema 与统一响应结构
- `backend/app/services/`：业务服务层，目前已实现 `CalendarService`、`ReminderService`、`ConflictService`、`TimeParser`
- `backend/scripts/`：后端维护脚本，目前包含数据库初始化脚本
- `scripts/`：项目级辅助脚本预留目录
- `docker/`：Docker 与部署相关文件预留目录

## 当前已完成

- 根目录 `.gitignore`
- 后端依赖清单：`backend/requirements.txt`
- 后端环境变量示例：`backend/.env.example`
- 配置管理：支持 `APP_ENV`、`APP_NAME`、`DATABASE_URL`、`REDIS_URL`、`JWT_SECRET`、`TIMEZONE`、`OPENAI_API_KEY`、`WS_HEARTBEAT_INTERVAL`、`REMINDER_SCAN_INTERVAL`
- 健康检查：`GET /api/health`
- PostgreSQL 异步连接基础设施
- Redis 统一 client 管理与健康检查
- 核心模型：`User`、`Event`、`Reminder`、`ConversationState`、`VoiceCommand`
- 数据库初始化脚本：`python -m scripts.init_db`
- Repository 层：`EventRepository`、`ReminderRepository`、`ConversationRepository`、`VoiceCommandRepository`
- Pydantic schema：event、reminder、voice、conversation、common
- 日历服务层：`CalendarService`
- 提醒服务层：`ReminderService`
- 冲突检测服务层：`ConflictService`
- 中文时间解析基础规则与进阶规则：`TimeParser`
- 事件 REST API：`GET/POST/PATCH/DELETE /api/events`
- 提醒 REST API：`GET/POST/PATCH/DELETE /api/reminders`

## 当前未实现

- 前端 React / Vite 初始化
- 统一语音命令入口 `/api/voice/command`
- NLU 服务
- 多轮对话业务
- 提醒调度 worker
- WebSocket 推送
- Docker 编排
- 自动化测试

## 后端快速开始

进入后端目录：

```powershell
cd backend
```

创建虚拟环境并安装依赖：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

复制环境变量示例：

```powershell
Copy-Item .env.example .env
```

初始化数据库表：

```powershell
python -m scripts.init_db
```

启动后端：

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

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

## 开发顺序

1. 实现更完整的 NLU 基础结构。
2. 实现统一语音命令入口 `/api/voice/command`。
3. 实现多轮对话状态服务。
4. 实现提醒调度 worker。
5. 实现 WebSocket 推送。
6. 初始化前端 React / Vite 工程。
7. 完成前后端联调和 Docker 编排。

## 文档维护约定

后续每次开发都需要同步补充 README 文档。

- 目录结构变化时，更新“目录说明”
- 新增能力时，更新“当前已完成”
- 尚未完成或被延后的内容，更新“当前未实现”
- 新增启动、初始化、测试、部署命令时，更新“快速开始”或对应模块 README
- 后端内部结构变化时，同步更新 `backend/README.md`
