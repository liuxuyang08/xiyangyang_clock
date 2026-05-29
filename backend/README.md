# backend

后端目录。

当前阶段已包含配置管理、健康检查、数据库连接、Redis 连接、核心 SQLAlchemy 模型和初始化建表脚本。
尚未实现业务接口和 CRUD。

## 依赖配置

本项目当前采用单一依赖清单：

- `backend/requirements.txt`

之所以选用 `requirements.txt`，是因为仓库目前还没有 `pyproject.toml` 或 `uv` 配置，不需要同时维护多套依赖定义。

数据库访问方案采用异步栈，因此这里选用 `asyncpg`，并配合 `SQLAlchemy[asyncio]` 使用。

## 数据库初始化

当前项目还没有引入 Alembic。为了避免重复维护多套互相冲突的建表方式，现阶段只提供一个初始化脚本：

- `backend/scripts/init_db.py`

该脚本会基于 SQLAlchemy `Base.metadata.create_all` 创建当前核心表：

- `users`
- `events`
- `reminders`
- `conversation_states`
- `voice_commands`

使用前请先复制环境变量示例，并确认 `DATABASE_URL` 指向可连接的 PostgreSQL 数据库：

```powershell
Copy-Item .env.example .env
```

然后在 `backend/` 目录下执行：

```powershell
python -m scripts.init_db
```

该脚本只创建尚不存在的表，不实现迁移版本管理，也不写入业务数据。

## 配置文件

- `backend/.env.example`：环境变量示例
- `backend/.env`：本地实际配置文件，建议由 `.env.example` 复制生成
- `backend/app/core/config.py`：配置读取入口，使用 `pydantic-settings`

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

## 安装依赖

在 `backend/` 目录下执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 启动 FastAPI

当前已经提供最小应用入口 `backend/app/main.py`。

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

## 目录约定

后续后端代码会按以下方向展开：

- `app/api/`：路由层
- `app/services/`：业务层
- `app/repositories/`：数据访问层
- `app/models/`：数据模型
- `app/db/`：数据库连接与基础配置
- `app/workers/`：调度与异步任务
