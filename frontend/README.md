# frontend

React + Vite 前端应用，提供语音输入、日历视图、实时提醒通知、WebSocket 状态展示和浏览器语音播报。

## 技术栈

- React
- TypeScript
- Vite
- Tailwind CSS
- shadcn/ui 兼容组件结构
- FullCalendar
- lucide-react
- Web Speech API
- SpeechSynthesis
- WebSocket

## 快速启动

本地 Vite 开发模式：

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

默认访问：

```text
http://localhost:5173
```

构建检查：

```powershell
npm run build
```

构建产物预览：

```powershell
npm run preview
```

## 环境变量

本地开发使用 `frontend/.env`：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

含义：

- `VITE_API_BASE_URL`：REST API 基础地址
- `VITE_WS_URL`：WebSocket 基础地址

本地 Vite 模式下，前端直接访问后端：

```text
http://localhost:8000
ws://localhost:8000/ws
```

Docker 模式下，前端由 nginx 提供静态文件并代理 `/api/` 和 `/ws` 到后端 API。根目录 `.env.example` 因此默认使用：

```env
VITE_API_BASE_URL=http://localhost:5173
VITE_WS_URL=ws://localhost:5173/ws
```

如果修改根目录 `FRONTEND_PORT`，需要同步修改 Docker 构建时使用的 `VITE_API_BASE_URL` 和 `VITE_WS_URL`，然后重新构建前端镜像：

```powershell
docker compose build frontend
docker compose up -d frontend
```

## 默认用户

当前前端演示页面默认使用：

```ts
const DEFAULT_USER_ID = "u001";
```

后端初始化脚本 `python -m scripts.init_db` 会幂等创建该演示用户。若数据库中缺少 `u001`，创建日程时会触发后端外键错误。

Docker 模式下可执行：

```powershell
docker compose run --build --rm db-init
```

## 主要功能

- 语音输入面板
- 浏览器语音识别
- 语音命令提交
- 助手回复展示
- 浏览器语音播报
- 多轮确认面板
- 日历视图
- 日程详情侧栏
- 实时提醒通知层
- WebSocket 在线状态展示
- WebSocket 手动重连

## WebSocket 状态

页面右上角的 WebSocket 状态用于展示实时连接状态。

常见状态：

- `连接中`：正在建立连接
- `已连接`：后端已接受 WebSocket 连接
- `重连中`：连接断开后前端正在按退避策略重试
- `异常`：连接过程中触发错误
- `已断开`：组件卸载或明确停止连接

如果一直显示“重连中”，先查看后端日志：

```powershell
docker compose logs --tail 80 api
```

如果后端日志出现：

```text
No supported WebSocket library detected.
```

说明后端没有安装 WebSocket 协议依赖，需要重新安装后端依赖或重建 API 镜像。当前后端依赖已使用 `uvicorn[standard]`。

## 目录结构

```text
frontend/
  src/
    components/
      calendar/
      ui/
      voice/
      workspace/
    hooks/
      use-events.ts
      use-speech-recognition.ts
      use-speech-synthesis.ts
      use-voice-websocket.ts
    lib/
      api.ts
      events-api.ts
      websocket.ts
      voice-api.ts
      voice-session.ts
    pages/
      dashboard-page.tsx
    types/
      event.ts
      realtime.ts
      voice.ts
    App.tsx
    main.tsx
  Dockerfile
  nginx.conf
  package.json
  vite.config.ts
```

## 常见问题

### 页面能打开，但事件列表为空

确认后端健康检查正常：

```powershell
curl http://localhost:8000/api/health
```

Docker 模式下如果前端从 `http://localhost:5173` 访问，API 会走 nginx 代理：

```powershell
curl http://localhost:5173/api/health
```

### 语音识别不可用

浏览器 Web Speech API 支持情况与浏览器、系统权限和访问协议有关。建议使用 Chrome / Edge，并允许麦克风权限。

### WebSocket 一直重连

优先检查后端是否已安装 `uvicorn[standard]` 并重启。正常后端日志应出现：

```text
WebSocket /ws?user_id=u001&session_id=... [accepted]
connection open
```

### 修改 `.env` 后没有生效

Vite 只会在启动或构建时读取环境变量。修改 `frontend/.env` 后，需要重启 `npm run dev`。

Docker 模式下环境变量是在镜像构建阶段写入前端静态包，修改根目录 `.env` 后需要重新构建前端镜像：

```powershell
docker compose build frontend
docker compose up -d frontend
```
