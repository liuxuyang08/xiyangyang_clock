# backend

后端预留目录。

当前阶段只实现后端配置管理和健康检查，不连接数据库，不实现业务接口。

## 依赖配置

本项目当前采用单一依赖清单：

- `backend/requirements.txt`

之所以选用 `requirements.txt`，是因为仓库目前还没有 `pyproject.toml` 或 `uv` 配置，不需要同时维护多套依赖定义。

数据库访问方案采用异步栈，因此这里选用 `asyncpg`，并配合 `SQLAlchemy[asyncio]` 使用。

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
  "environment": "dev"
}
```

该接口只返回当前环境名，不暴露数据库、密钥或其他敏感配置。

## 目录约定

后续后端代码会按以下方向展开：

- `app/api/`：路由层
- `app/services/`：业务层
- `app/repositories/`：数据访问层
- `app/models/`：数据模型
- `app/db/`：数据库连接与基础配置
- `app/workers/`：调度与异步任务
