# 语音版日历工具

这是一个以语音交互为核心的日历助手项目。
当前仓库仅完成基础目录和文档整理，尚未初始化 React、FastAPI 或任何业务接口。

## 技术栈概览

- 前端：React、Vite、shadcn/ui、FullCalendar
- 语音转文字：Web Speech API / gpt-4o-transcribe
- 语音播报：Web Speech API SpeechSynthesis / OpenAI Text-to-Speech
- 后端：FastAPI
- 数据库：PostgreSQL
- 缓存与会话状态：Redis
- ORM / 数据访问：SQLAlchemy
- 实时通知：WebSocket
- 时间解析与重复规则：自定义中文规则、dateparser、python-dateutil rrule
- 部署：Docker

## 前后端目录说明

- `docs/`：需求、技术选型、开发文档和开发提示词
- `frontend/`：前端应用预留目录，后续放置 React / Vite 工程
- `backend/`：后端应用预留目录，后续放置 FastAPI 工程
- `scripts/`：开发、测试、迁移、校验等辅助脚本预留目录
- `docker/`：容器编排、镜像构建和部署相关文件预留目录

## 后续开发步骤

1. 按文档补齐前后端工程骨架。
2. 定义数据模型和数据库迁移方案。
3. 实现统一语音命令入口和核心业务服务。
4. 搭建前端交互页面和实时消息接收。
5. 补充 Docker 编排、环境变量和联调脚本。
6. 完成测试、验证和部署准备。

