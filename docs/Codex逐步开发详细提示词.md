# 语音版日历工具 - Codex 逐步开发详细提示词

这份文档是《Codex分阶段开发提示词.md》的细化版，适合你逐条复制给 Codex，让它按照《开发文档.md》的要求一步一步完成整个项目。

原来的阶段版只有 8 个大阶段，适合做总控；如果要真正开发，粒度应该更细。本文档把项目拆成 42 个小步骤，每一步只完成一个明确目标，并包含：

- 本步目标
- 验收结果
- 给 Codex 的完整提示词

建议使用方式：

1. 从第 0 步开始，逐步复制提示词给 Codex。
2. 每一步完成后，先按“验收结果”检查。
3. 验收通过后再进入下一步。
4. 不要一次性把所有提示词发给 Codex。
5. 如果某一步已经完成，可以让 Codex 检查并补齐，不要重复重建。

---

## 通用提示词前缀

每一步都可以先加上这段通用约束：

```text
你正在开发“语音版日历工具”项目。请先阅读 docs 目录下的《开发文档.md》《技术选型.md》《需求.md》，并严格按照文档中的技术栈和业务边界执行。

通用约束：
1. 只做当前步骤，不要提前实现下一步。
2. 先检查现有代码，再开始修改。
3. 不要删除用户已有文件，不要做无关重构。
4. 前端技术栈固定为 React + Vite + shadcn/ui + FullCalendar。
5. 后端技术栈固定为 FastAPI + PostgreSQL + Redis + SQLAlchemy。
6. 语义理解采用“大模型结构化解析 + NLU + 后端强校验”。
7. 时间解析采用“自定义中文规则 + dateparser”。
8. 重复日程采用 python-dateutil rrule。
9. 实时通知采用 WebSocket。
10. 每一步完成后都要说明：改了哪些文件、如何运行或测试、是否满足验收结果。
```

---

## 第 0 步：仓库和文档审查

### 本步目标

让 Codex 先理解项目现状，不做业务开发。

### 验收结果

- Codex 能说清楚当前仓库结构。
- Codex 能识别已有文档。
- Codex 能列出前后端缺失内容。
- 没有引入业务代码。

### 给 Codex 的完整提示词

```text
请只做仓库和文档审查。

请阅读 docs 目录下的《开发文档.md》《技术选型.md》《需求.md》，然后检查当前仓库结构。

你需要输出：
1. 当前仓库有哪些目录和关键文件。
2. 当前是否已有 frontend、backend、docker、数据库迁移等内容。
3. 与《开发文档.md》相比，当前缺少哪些模块。
4. 建议的开发顺序。

本步不要创建文件，不要修改代码，不要安装依赖。
```

---

## 第 1 步：建立项目基础目录

### 本步目标

建立前端、后端、文档、部署相关的基础目录。

### 验收结果

- 存在 `frontend/`
- 存在 `backend/`
- 存在 `docs/`
- 存在基础 README 或项目说明
- 没有业务实现

### 给 Codex 的完整提示词

```text
请只建立项目基础目录，不要实现业务功能。

请根据《开发文档.md》创建或整理以下结构：
- frontend/
- backend/
- docs/
- scripts/，如果有必要
- deploy/ 或 docker 相关目录，如果有必要

如果这些目录已经存在，请不要重复创建，只补齐缺失说明。

请补充一个项目根 README，说明：
1. 项目名称：语音版日历工具。
2. 技术栈概览。
3. 前后端目录说明。
4. 后续开发步骤。

本步不要初始化 React，不要初始化 FastAPI，不要实现接口。
```

---

## 第 2 步：后端依赖和虚拟环境配置

### 本步目标

准备 FastAPI 后端的依赖文件和运行说明。

### 验收结果

- backend 下有依赖声明文件。
- 包含 FastAPI、SQLAlchemy、PostgreSQL、Redis、dateparser、python-dateutil 等依赖。
- 有后端启动说明。

### 给 Codex 的完整提示词

```text
请只配置后端依赖，不要写业务代码。

请在 backend 目录下建立 Python 后端依赖配置，至少包含：
- fastapi
- uvicorn
- sqlalchemy
- psycopg2-binary 或 asyncpg，按项目实际同步/异步方案选择
- pydantic
- pydantic-settings
- redis
- dateparser
- python-dateutil
- apscheduler
- python-dotenv
- httpx

如果项目已经有 pyproject.toml、requirements.txt 或 uv 配置，请沿用现有方式，不要重复维护多套依赖。

请补充 backend 的启动说明，说明如何安装依赖和启动 FastAPI。

本步不要实现数据库模型，不要实现接口。
```

---

## 第 3 步：FastAPI 应用骨架

### 本步目标

创建可启动的 FastAPI 应用。

### 验收结果

- 后端服务可以启动。
- 有 `/api/health` 接口。
- 有基础 app 目录结构。

### 给 Codex 的完整提示词

```text
请只实现 FastAPI 应用骨架。

请在 backend 中创建 FastAPI 基础应用结构：
- app/main.py
- app/api/
- app/core/
- app/db/
- app/models/
- app/schemas/
- app/services/
- app/repositories/
- app/utils/
- app/workers/

请实现 GET /api/health，返回：
- status
- app_name
- environment

本步只要求服务可启动，不要连接数据库，不要连接 Redis，不要实现业务接口。

完成后请说明后端启动命令和健康检查地址。
```

---

## 第 4 步：后端配置管理和环境变量

### 本步目标

统一管理环境变量，避免硬编码。

### 验收结果

- 有 `backend/.env.example`
- 有配置读取模块
- FastAPI 能读取配置

### 给 Codex 的完整提示词

```text
请只实现后端配置管理。

请使用 pydantic-settings 或等价方式实现配置读取，支持：
- APP_ENV
- APP_NAME
- DATABASE_URL
- REDIS_URL
- JWT_SECRET
- TIMEZONE
- OPENAI_API_KEY
- WS_HEARTBEAT_INTERVAL
- REMINDER_SCAN_INTERVAL

请创建 backend/.env.example，并写入示例值。

请让 /api/health 能返回当前环境名，但不要暴露敏感配置。

本步不要连接数据库，不要实现业务。
```

---

## 第 5 步：数据库连接

### 本步目标

接入 PostgreSQL 数据库连接。

### 验收结果

- 后端有统一数据库 session。
- `/api/health` 能检查数据库连接。
- 数据库连接失败时返回明确状态。

### 给 Codex 的完整提示词

```text
请只实现 PostgreSQL 数据库连接。

请在 backend/app/db 下实现：
- SQLAlchemy engine
- SessionLocal
- Base
- 获取数据库会话的 dependency

请扩展 /api/health，让它检查数据库连通性。

如果连接失败，不要让服务崩溃，要在 health 结果中返回 database: "unavailable"。

本步不要创建业务模型，不要实现 CRUD。
```

---

## 第 6 步：Redis 连接

### 本步目标

接入 Redis，为后续会话状态和 WebSocket 在线状态做准备。

### 验收结果

- 有 Redis client。
- `/api/health` 能检查 Redis。
- Redis 失败时不会导致服务启动失败。

### 给 Codex 的完整提示词

```text
请只实现 Redis 连接。

请在 backend/app/core 或 backend/app/db 中实现 Redis client 管理，读取 REDIS_URL。

请扩展 /api/health，返回 redis 状态。

要求：
1. Redis 不可用时 health 显示 unavailable。
2. 不要在业务代码里直接创建散乱 Redis 连接。
3. 为后续 conversation_state 和 WebSocket 在线状态预留统一接口。

本步不要实现会话业务，不要实现 WebSocket。
```

---

## 第 7 步：数据库模型 - User 与 Event

### 本步目标

实现用户和日程模型。

### 验收结果

- 有 User 模型。
- 有 Event 模型。
- Event 支持软删除。
- Event 字段符合开发文档。

### 给 Codex 的完整提示词

```text
请只实现 User 和 Event 两个 SQLAlchemy 模型。

User 至少包含：
- id
- nickname
- timezone
- default_reminder_minutes
- created_at

Event 至少包含：
- id
- user_id
- title
- description
- start_time
- end_time
- location
- participants
- priority
- status
- source
- is_all_day
- recurrence_rule
- created_at
- updated_at
- deleted_at

要求：
1. Event 删除采用软删除，不要物理删除。
2. participants 和 recurrence_rule 可以使用 JSON 字段。
3. 建立 user_id、start_time、status 相关索引。

本步不要实现 API，不要写业务服务。
```

---

## 第 8 步：数据库模型 - Reminder、ConversationState、VoiceCommand

### 本步目标

补齐提醒、会话状态和语音命令日志模型。

### 验收结果

- 有 Reminder 模型。
- 有 ConversationState 模型。
- 有 VoiceCommand 模型。
- 关键索引存在。

### 给 Codex 的完整提示词

```text
请只实现 Reminder、ConversationState、VoiceCommand 三个 SQLAlchemy 模型。

Reminder 至少包含：
- id
- event_id
- user_id
- remind_time
- offset_minutes
- channel
- status
- created_at

ConversationState 至少包含：
- id
- user_id
- session_id
- pending_intent
- slots
- missing_slots
- candidate_events
- status
- expires_at
- updated_at

VoiceCommand 至少包含：
- id
- user_id
- session_id
- raw_text
- intent
- confidence
- entities
- status
- error_message
- created_at

要求：
1. JSON 数据使用 JSON 或 JSONB 字段。
2. 建立 reminder(user_id, remind_time, status) 索引。
3. 建立 conversation_state(user_id, session_id) 索引。
4. 建立 voice_command(user_id, created_at) 索引。

本步不要实现业务接口。
```

---

## 第 9 步：数据库迁移或建表脚本

### 本步目标

让数据库模型可以实际落表。

### 验收结果

- 有可执行的迁移或建表方式。
- 数据库能创建所有核心表。
- README 中写明初始化方式。

### 给 Codex 的完整提示词

```text
请只实现数据库迁移或建表脚本。

如果项目已经使用 Alembic，请补齐 Alembic 配置和初始迁移。
如果还没有迁移体系，请提供一个清晰的初始化脚本或命令，用于创建所有核心表。

要求：
1. 不要重复维护多套互相冲突的建表方式。
2. 确保 User、Event、Reminder、ConversationState、VoiceCommand 都能创建。
3. 补充 README 或 backend 文档，说明如何初始化数据库。

本步不要实现 CRUD 接口。
```

---

## 第 10 步：Repository 层基础

### 本步目标

建立数据访问层，避免业务逻辑直接写 SQL。

### 验收结果

- 有 EventRepository。
- 有 ReminderRepository。
- 有 ConversationRepository。
- 有 VoiceCommandRepository。

### 给 Codex 的完整提示词

```text
请只实现 Repository 层。

请为核心模型建立数据访问类：
- EventRepository
- ReminderRepository
- ConversationRepository
- VoiceCommandRepository

每个 repository 至少提供基础方法：
- create
- get_by_id
- update
- list 或 search

EventRepository 需要额外支持：
- 按 user_id 和时间范围查询
- 按关键词查询候选事件
- 软删除事件

ReminderRepository 需要额外支持：
- 查询 pending 且到期的提醒
- 更新提醒状态

本步不要实现 API 路由，不要实现复杂业务逻辑。
```

---

## 第 11 步：Schema 与统一响应格式

### 本步目标

建立 API 输入输出的数据结构。

### 验收结果

- 有 Event schema。
- 有 Reminder schema。
- 有 VoiceCommand schema。
- 有统一响应结构。

### 给 Codex 的完整提示词

```text
请只实现 Pydantic schema 和统一响应格式。

请创建或补齐：
- schemas/event.py
- schemas/reminder.py
- schemas/voice.py
- schemas/conversation.py
- schemas/common.py

统一语音命令响应必须包含：
- action
- need_user_reply
- reply
- data

Event 和 Reminder 的创建、更新、读取都要有明确 schema。

要求：
1. 不要让 API 直接返回 ORM 对象。
2. 字段命名与开发文档保持一致。
3. 时间字段使用 ISO 格式。

本步不要实现路由业务。
```

---

## 第 12 步：事件 CRUD Service

### 本步目标

实现日程创建、查询、修改、软删除的业务服务。

### 验收结果

- CalendarService 可创建事件。
- 可查询时间范围内事件。
- 可更新事件。
- 可软删除事件。

### 给 Codex 的完整提示词

```text
请只实现 CalendarService，不要写路由。

CalendarService 需要支持：
1. create_event
2. list_events_by_range
3. get_event
4. update_event
5. soft_delete_event
6. search_candidate_events

业务要求：
1. 删除必须是软删除。
2. 默认只查询 active 状态事件。
3. 时间范围查询要按 start_time 排序。
4. 更新事件时自动更新 updated_at。

本步不要实现提醒逻辑，不要实现语音入口。
```

---

## 第 13 步：提醒 CRUD Service

### 本步目标

实现提醒创建、查询、取消和状态更新。

### 验收结果

- ReminderService 可创建提醒。
- 可取消提醒。
- 可查到期提醒。
- 可标记 sent 或 failed。

### 给 Codex 的完整提示词

```text
请只实现 ReminderService，不要写调度器。

ReminderService 需要支持：
1. create_reminder
2. list_reminders
3. cancel_reminder
4. cancel_event_reminders
5. list_due_pending_reminders
6. mark_sent
7. mark_failed

业务要求：
1. remind_time 不能早于当前时间，除非用于测试并明确标记。
2. 删除日程时需要能够取消该日程下所有 pending 提醒。
3. 提醒状态至少包括 pending、sent、cancelled、failed。

本步不要实现 APScheduler，不要实现 WebSocket。
```

---

## 第 14 步：冲突检测服务

### 本步目标

实现新增或修改日程时的时间冲突检测。

### 验收结果

- 能判断两个事件是否时间重叠。
- 能查询某个时间段内的冲突事件。
- 不直接阻止创建，而是返回冲突信息。

### 给 Codex 的完整提示词

```text
请只实现 ConflictService。

需要实现：
1. 判断两个时间区间是否冲突。
2. 根据 user_id、start_time、end_time 查询冲突事件。
3. 修改事件时排除当前事件自身。

冲突规则：
new_start < existing_end 且 new_end > existing_start 即为冲突。

要求：
1. 冲突检测只返回冲突信息，不直接执行确认逻辑。
2. 返回内容要包含冲突事件 id、title、start_time、end_time。

本步不要实现语音入口，不要写前端。
```

---

## 第 15 步：事件 REST API

### 本步目标

暴露日程 CRUD 接口供前端使用。

### 验收结果

- `GET /api/events` 可查询事件。
- `POST /api/events` 可创建事件。
- `GET /api/events/{id}` 可查看事件。
- `PATCH /api/events/{id}` 可修改事件。
- `DELETE /api/events/{id}` 可软删除事件。

### 给 Codex 的完整提示词

```text
请只实现事件 REST API。

请基于 CalendarService 实现：
- GET /api/events
- POST /api/events
- GET /api/events/{event_id}
- PATCH /api/events/{event_id}
- DELETE /api/events/{event_id}

要求：
1. DELETE 执行软删除。
2. 查询接口支持 user_id、start、end 参数。
3. 返回 schema 要统一。
4. 路由中不要堆业务逻辑，业务交给 service。

本步不要实现语音命令入口，不要实现前端。
```

---

## 第 16 步：提醒 REST API

### 本步目标

暴露提醒管理接口。

### 验收结果

- 可查询提醒。
- 可创建提醒。
- 可更新提醒。
- 可取消提醒。

### 给 Codex 的完整提示词

```text
请只实现提醒 REST API。

请基于 ReminderService 实现：
- GET /api/reminders
- POST /api/reminders
- PATCH /api/reminders/{reminder_id}
- DELETE /api/reminders/{reminder_id}

要求：
1. DELETE 不物理删除，改为 cancelled。
2. 查询接口支持 user_id 和 status。
3. 返回格式和项目统一响应一致。

本步不要实现提醒调度器，不要实现 WebSocket。
```

---

## 第 17 步：中文时间解析基础规则

### 本步目标

实现常用中文时间表达解析。

### 验收结果

- 能解析今天、明天、后天。
- 能解析上午、下午、晚上。
- 能解析具体几点几分。
- 解析结果含时区。

### 给 Codex 的完整提示词

```text
请只实现中文时间解析基础规则。

请创建 TimeParser，使用“自定义中文规则 + dateparser”的方式解析中文时间。

至少支持：
- 今天
- 明天
- 后天
- 上午十点
- 下午三点
- 晚上八点半
- 明天下午三点
- 后天上午九点

要求：
1. 输入包含 base_time 和 timezone。
2. 输出标准 datetime 或结构化解析结果。
3. 如果只说“下午”“晚上”等模糊表达，不要直接猜具体时间，要返回需要追问。

本步不要做 NLU，不要做日程创建。
```

---

## 第 18 步：中文时间解析进阶规则

### 本步目标

支持周、月、相对时间和模糊时间。

### 验收结果

- 能解析本周几、下周几。
- 能解析月底前。
- 能识别模糊时间并要求追问。
- 能处理过去时间。

### 给 Codex 的完整提示词

```text
请扩展 TimeParser 的进阶中文时间规则。

至少支持：
- 本周一到本周日
- 下周一到下周日
- 周五下午三点
- 下周三上午十点半
- 月底前
- 一小时后
- 半小时后

要求：
1. 如果解析后的时间已经过去，要返回明确标记，供业务层追问。
2. “月底前”“周末”“睡前”“上班前”这类模糊表达不要自动执行，要返回 ambiguous。
3. 写出若干解析示例或测试。

本步不要改业务接口。
```

---

## 第 19 步：重复规则解析

### 本步目标

把“每天、每周、每月、工作日”等表达转成 rrule。

### 验收结果

- 每天可解析。
- 每周一可解析。
- 每月 1 号可解析。
- 工作日可解析。

### 给 Codex 的完整提示词

```text
请只实现重复日程解析。

请使用 python-dateutil rrule 或兼容格式，把中文重复表达解析为 recurrence_rule。

至少支持：
- 每天
- 每周一
- 每周三下午三点
- 每月 1 号
- 工作日

输出建议为 JSON 结构或标准 rrule 字符串，但要与 Event.recurrence_rule 字段兼容。

要求：
1. 不要在本步生成重复事件实例。
2. 只解析并保存规则。
3. 给出测试示例。
```

---

## 第 20 步：NLU 规则意图识别

### 本步目标

先用规则识别常见语音意图。

### 验收结果

- 能识别添加、查询、修改、删除。
- 能识别确认、取消。
- 输出统一结构。

### 给 Codex 的完整提示词

```text
请只实现规则版 NLU 意图识别。

请创建 NLUService 的规则解析部分，支持识别：
- create_event
- query_event
- update_event
- delete_event
- create_reminder
- cancel_reminder
- confirm
- deny
- undo
- help

规则示例：
- “提醒我”“添加”“安排”偏 create_event
- “今天有什么”“查一下”“安排”偏 query_event
- “删除”“取消”“不要了”偏 delete_event
- “改到”“换成”“提前到”偏 update_event
- “确认”“是的”“对”偏 confirm
- “不用了”“取消”“不是”偏 deny

输出必须包含：
- intent
- confidence
- slots
- missing_slots

本步不要接大模型，不要执行业务操作。
```

---

## 第 21 步：NLU 实体抽取

### 本步目标

从用户文本中抽取事件标题、时间、地点、提醒提前量等。

### 验收结果

- 能抽取 title。
- 能抽取 date_text 和 time_text。
- 能抽取 reminder_offset。
- 能抽取 location 的基础表达。

### 给 Codex 的完整提示词

```text
请只实现 NLU 实体抽取，不要执行业务。

请在 NLUService 中抽取以下 slots：
- title
- date_text
- time_text
- start_time
- end_time
- location
- participants
- reminder_offset_minutes
- recurrence_text
- target_event

至少支持这些句子：
- 明天下午三点提醒我交项目文档
- 下周三上午十点和王老师在图书馆开会
- 每周一上午九点提醒我开例会
- 把明天上午的会议改到下午三点
- 删除明天的健身

要求：
1. 时间解析可以调用 TimeParser。
2. 抽取不到必填字段时，返回 missing_slots。
3. 不要为了完美抽取写过度复杂规则，先保证常见场景稳定。
```

---

## 第 22 步：大模型结构化解析接口预留

### 本步目标

为复杂语音指令预留大模型结构化解析能力。

### 验收结果

- 有 LLM 解析服务接口。
- 有 JSON Schema 或固定输出结构。
- API Key 从环境变量读取。
- 无 Key 时自动降级到规则解析。

### 给 Codex 的完整提示词

```text
请只实现大模型结构化解析服务的封装，不要强制依赖外部服务成功。

请创建 LLMParseService 或在 NLUService 中封装 LLM 结构化解析能力。

要求：
1. 从 OPENAI_API_KEY 读取配置。
2. 输入用户自然语言文本和当前 conversation context。
3. 输出结构必须与 NLU 规则解析一致：
   - intent
   - confidence
   - slots
   - missing_slots
4. 如果没有 API Key 或调用失败，必须降级到规则解析。
5. 不要把业务操作交给大模型执行，大模型只负责结构化解析。
6. 增加清晰注释，说明这是增强能力。

本步不要改变语音命令入口，不要写前端。
```

---

## 第 23 步：ConversationState 服务

### 本步目标

实现多轮对话状态保存、读取和过期。

### 验收结果

- 能创建待补全状态。
- 能读取当前 session 状态。
- 能更新 slots。
- 能清除已完成状态。
- Redis 和数据库状态关系清晰。

### 给 Codex 的完整提示词

```text
请只实现多轮对话状态服务 DialogService。

DialogService 需要支持：
1. get_current_state
2. create_pending_state
3. update_state_slots
4. set_candidates
5. set_need_confirm
6. complete_state
7. cancel_state
8. expire_state

状态需要同时考虑：
- Redis 中的临时状态
- conversation_state 表中的持久化记录

要求：
1. Redis key 遵循开发文档：
   - voice:session:{session_id}
   - voice:user:{user_id}:state
   - voice:user:{user_id}:pending_confirm
2. 状态需要有 TTL。
3. 短句“确认”“取消”必须优先读取当前上下文。

本步不要实现日程业务执行。
```

---

## 第 24 步：VoiceCommand 日志服务

### 本步目标

记录每次语音命令的解析与执行结果。

### 验收结果

- 每次语音输入可写入 voice_command。
- 成功和失败都能记录。
- 日志包含 intent、entities、confidence。

### 给 Codex 的完整提示词

```text
请只实现 VoiceCommand 日志服务。

请创建 VoiceCommandService 或 VoiceCommandLogService，支持：
1. record_received
2. record_parsed
3. record_success
4. record_failed

voice_command 记录需要包含：
- user_id
- session_id
- raw_text
- intent
- confidence
- entities
- status
- error_message

要求：
1. 日志失败不能影响主业务流程。
2. 日志服务要被后续 /api/voice/command 调用。
3. 不要在本步实现语音命令业务入口。
```

---

## 第 25 步：统一语音命令入口 - 基础流程

### 本步目标

实现 `/api/voice/command` 的基础解析和响应。

### 验收结果

- 接口能接收文本。
- 能返回 intent、reply、need_user_reply。
- 能处理无法识别的输入。
- 能记录日志。

### 给 Codex 的完整提示词

```text
请实现 /api/voice/command 的基础流程，但先不要执行真实日程创建、修改、删除。

接口：
POST /api/voice/command

请求字段：
- user_id
- session_id
- text
- timezone
- client_time

处理流程：
1. 记录收到的 voice_command。
2. 读取当前 conversation_state。
3. 调用 NLUService 解析 intent 和 slots。
4. 调用 TimeParser 做时间归一化。
5. 如果缺字段，返回追问 reply，并保存 conversation_state。
6. 如果信息完整，先返回“已识别到操作，但业务执行将在下一步完成”的结构化响应。

响应必须包含：
- action
- need_user_reply
- reply
- data

本步不要真正创建、修改、删除事件。
```

---

## 第 26 步：语音创建日程业务

### 本步目标

让语音命令可以真正创建日程和提醒。

### 验收结果

- “明天下午三点提醒我交项目文档”能创建事件。
- 缺标题或缺时间会追问。
- 可创建默认提醒。

### 给 Codex 的完整提示词

```text
请只实现语音创建日程业务。

在 /api/voice/command 中，当 intent 为 create_event 时：
1. 校验 title、start_time 是否存在。
2. 如果缺字段，保存 conversation_state 并返回追问。
3. 如果完整，调用 CalendarService 创建事件。
4. 如果有 reminder_offset_minutes，调用 ReminderService 创建提醒。
5. 返回自然语言 reply，例如：
   “已为你创建明天下午 3 点的提醒：交项目文档。”

要求：
1. 先不处理冲突确认，冲突在后续步骤实现。
2. 创建结果要写入 voice_command。
3. 返回 data 中包含 event 和 reminder 信息。

本步不要实现查询、修改、删除。
```

---

## 第 27 步：语音查询日程业务

### 本步目标

支持通过语音查询日程。

### 验收结果

- “我今天有什么安排”可查询当天。
- “明天有什么安排”可查询明天。
- “最近有什么安排”可查询未来 7 天。
- 返回适合播报的摘要。

### 给 Codex 的完整提示词

```text
请只实现语音查询日程业务。

在 /api/voice/command 中，当 intent 为 query_event 时：
1. 解析查询范围。
2. 如果用户没有指定范围，默认查询今天。
3. “最近”默认查询未来 7 天。
4. “下午”默认查询当天 12:00 到 18:00。
5. 调用 CalendarService 查询事件。
6. 生成适合语音播报的 reply。

示例：
用户：“我今天有什么安排”
系统：“今天你有 3 个安排：上午 10 点项目讨论，下午 3 点提交文档，晚上 7 点健身。”

要求：
1. 查询结果按时间排序。
2. 结果为空时返回“暂无安排”。
3. 不要在本步实现修改和删除。
```

---

## 第 28 步：语音删除日程候选匹配

### 本步目标

通过语音找到待删除日程，但先不直接删除。

### 验收结果

- 找不到时返回未找到。
- 找到一个时进入确认状态。
- 找到多个时返回候选列表。

### 给 Codex 的完整提示词

```text
请只实现语音删除日程的候选匹配和确认准备，不要直接删除。

在 /api/voice/command 中，当 intent 为 delete_event 时：
1. 根据用户文本解析 target_event、日期、关键词。
2. 调用 CalendarService.search_candidate_events 查找候选。
3. 如果 0 个候选，返回“我没有找到相关日程”。
4. 如果 1 个候选，保存 pending_confirm 状态，返回“请确认是否删除...”。
5. 如果多个候选，保存 candidate_events，返回候选列表，让用户选择。

要求：
1. 不允许本步直接删除事件。
2. 候选事件需要包含 id、title、start_time。
3. 状态保存到 DialogService。

本步不要实现确认后的删除。
```

---

## 第 29 步：语音删除确认执行

### 本步目标

用户确认后执行软删除，并取消提醒。

### 验收结果

- 用户说“确认”后删除待确认事件。
- 删除为软删除。
- 对应 pending 提醒被取消。
- 用户说“取消”后不删除。

### 给 Codex 的完整提示词

```text
请只实现语音删除确认执行。

当 conversation_state 中存在 pending delete_event：
1. 用户输入 confirm 意图时：
   - 调用 CalendarService.soft_delete_event
   - 调用 ReminderService.cancel_event_reminders
   - 清除 conversation_state
   - 返回“已删除...”
2. 用户输入 deny 意图时：
   - 取消操作
   - 清除 conversation_state
   - 返回“已取消删除”
3. 如果之前是多个候选，用户选择候选后先进入确认状态，再等待确认。

要求：
1. 不允许物理删除。
2. 删除操作必须有日志。
3. 删除后保留可扩展 undo 的信息。
```

---

## 第 30 步：语音修改日程候选匹配

### 本步目标

通过语音定位要修改的日程，并生成修改草稿。

### 验收结果

- 能找到目标事件。
- 能识别修改后的时间或字段。
- 找到多个候选时让用户选择。
- 修改前进入确认状态。

### 给 Codex 的完整提示词

```text
请只实现语音修改日程的候选匹配和修改草稿，不要直接更新数据库。

当 intent 为 update_event 时：
1. 从用户文本中解析目标事件条件。
2. 解析 updates，例如新的 start_time、end_time、location、reminder_offset。
3. 查找候选事件。
4. 候选为 0 时返回未找到。
5. 候选为多个时返回候选列表。
6. 候选唯一时保存 pending update 状态，并返回确认文案。

示例：
用户：“把明天上午的会议改到下午三点”
系统：“找到明天上午 10 点的项目会议，是否将它改到明天下午 3 点？”

本步不要真正更新事件。
```

---

## 第 31 步：语音修改确认执行

### 本步目标

用户确认后执行日程修改。

### 验收结果

- 确认后可修改事件。
- 取消后不修改。
- 修改提醒时能同步更新提醒。

### 给 Codex 的完整提示词

```text
请只实现语音修改确认执行。

当 conversation_state 中存在 pending update_event：
1. 用户输入 confirm 时：
   - 调用 CalendarService.update_event
   - 如涉及提醒时间，调用 ReminderService 更新或重建提醒
   - 清除 conversation_state
   - 返回修改成功 reply
2. 用户输入 deny 时：
   - 不修改数据
   - 清除 conversation_state
   - 返回取消修改 reply

要求：
1. 修改前仍需检查事件是否存在且未删除。
2. 修改结果写入 voice_command 日志。
3. 返回 data 中包含更新后的 event。
```

---

## 第 32 步：创建和修改时的冲突检测确认

### 本步目标

将 ConflictService 接入创建和修改流程。

### 验收结果

- 时间冲突时返回冲突提示。
- 用户确认后仍可创建或修改。
- 用户取消后不执行。

### 给 Codex 的完整提示词

```text
请只把冲突检测接入语音创建和修改流程。

要求：
1. create_event 信息完整后，先调用 ConflictService。
2. update_event 修改时间前，也调用 ConflictService。
3. 如果存在冲突，不要直接执行，保存 pending_confirm 状态。
4. 返回 reply，例如：
   “这个时间你已经有项目会议，是否仍然创建新的日程？”
5. 用户确认后继续执行原操作。
6. 用户取消后清除 pending 状态。

冲突信息需要放到响应 data.conflicts 中。

本步不要实现前端。
```

---

## 第 33 步：提醒调度器

### 本步目标

实现到点提醒扫描和状态更新。

### 验收结果

- pending 且到期的提醒可被扫描。
- 触发后标记 sent。
- 失败时标记 failed。

### 给 Codex 的完整提示词

```text
请只实现提醒调度器。

请使用 APScheduler 或项目已有调度方式，实现定时扫描：
1. 查询 remind_time <= now 且 status = pending 的提醒。
2. 对每条提醒生成提醒消息。
3. 触发成功后 mark_sent。
4. 触发失败后 mark_failed，并记录错误信息。

要求：
1. 调度器不要阻塞 FastAPI 请求。
2. 扫描间隔读取 REMINDER_SCAN_INTERVAL。
3. 支持在本地开发环境启动。

本步先不要接 WebSocket 推送，只需要调度和状态更新。
```

---

## 第 34 步：WebSocket 连接管理

### 本步目标

建立后端 WebSocket 通道和连接管理。

### 验收结果

- 前端可连接 WebSocket。
- 后端能维护 user_id 到连接的映射。
- 支持心跳。

### 给 Codex 的完整提示词

```text
请只实现 WebSocket 连接管理。

请在 FastAPI 中增加 WebSocket endpoint，例如：
- /ws

连接需要携带：
- user_id
- session_id

请实现 WebSocketManager：
1. connect
2. disconnect
3. send_to_user
4. broadcast_to_user_sessions
5. heartbeat 处理

Redis 可以用于记录在线状态：
- voice:ws:online:{user_id}

本步不要接提醒调度，不要改前端。
```

---

## 第 35 步：提醒 WebSocket 推送

### 本步目标

让到点提醒通过 WebSocket 推送给前端。

### 验收结果

- 调度器触发提醒后能推送。
- 消息格式包含 type、user_id、data。
- 发送失败能记录。

### 给 Codex 的完整提示词

```text
请只把提醒调度器接入 WebSocket 推送。

当 ReminderScheduler 触发提醒时：
1. 生成 reminder_triggered 消息。
2. 通过 WebSocketManager 推送给对应 user_id。
3. 推送成功后标记 sent。
4. 推送失败后标记 failed 或保留重试信息。

消息示例：
{
  "type": "reminder_triggered",
  "user_id": "u001",
  "data": {
    "event_id": "e001",
    "title": "项目会议",
    "start_time": "2026-05-30T15:00:00+08:00"
  }
}

本步不要实现前端页面。
```

---

## 第 36 步：前端依赖和 Vite 工程

### 本步目标

初始化 React + Vite 前端。

### 验收结果

- 前端能启动。
- 已安装或配置 shadcn/ui。
- 已安装 FullCalendar。
- 有基础环境变量。

### 给 Codex 的完整提示词

```text
请只初始化前端工程。

请在 frontend 目录中配置 React + Vite 项目。

需要准备：
- React
- TypeScript，如果项目适合使用
- shadcn/ui
- FullCalendar
- API 请求工具
- .env.example

环境变量至少包括：
- VITE_API_BASE_URL
- VITE_WS_URL

本步只保证前端可以启动，不要实现完整页面和业务。
```

---

## 第 37 步：前端基础布局

### 本步目标

实现语音日历工具的主界面布局。

### 验收结果

- 有语音控制区。
- 有日历视图区。
- 有系统回复区。
- 有日程详情侧栏。
- 有确认区域。

### 给 Codex 的完整提示词

```text
请只实现前端基础布局。

页面应包含：
1. 语音输入区域
2. 识别文本展示区域
3. 系统回复区域
4. FullCalendar 日历视图区域
5. 日程详情侧栏
6. 对话确认区域
7. WebSocket 状态指示

要求：
1. 使用 shadcn/ui 组件。
2. 工具型界面，不要做营销页。
3. 不要使用大面积花哨装饰。
4. 组件拆分清晰，不要所有代码写在一个文件里。

本步不要接语音识别，不要接 WebSocket。
```

---

## 第 38 步：前端 API Client 与事件展示

### 本步目标

让前端能从后端获取事件并展示到 FullCalendar。

### 验收结果

- 能请求 `GET /api/events`。
- 事件显示在日历上。
- 点击事件可打开详情。

### 给 Codex 的完整提示词

```text
请只实现前端 API client 和事件展示。

需要完成：
1. 封装 API client，读取 VITE_API_BASE_URL。
2. 调用 GET /api/events 获取事件。
3. 将事件转换为 FullCalendar 需要的格式。
4. 在日历中展示事件。
5. 点击事件时打开 EventDrawer。

要求：
1. 请求失败时有错误提示。
2. loading 状态要可见。
3. 不要实现语音功能。
```

---

## 第 39 步：前端语音识别

### 本步目标

实现 Web Speech API 语音转文字。

### 验收结果

- 点击语音按钮可开始识别。
- 识别文本显示在界面上。
- 可提交文本到后端语音命令接口。

### 给 Codex 的完整提示词

```text
请只实现前端语音识别和提交文本。

使用 Web Speech API 实现：
1. 开始识别
2. 停止识别
3. 展示识别中状态
4. 展示最终识别文本
5. 将文本提交到 POST /api/voice/command

要求：
1. 浏览器不支持 Web Speech API 时，显示明确提示，并允许用户手动输入文本。
2. 提交后展示后端返回的 reply。
3. 保存 session_id，保持多轮对话连续。

本步不要实现 TTS，不要实现 WebSocket。
```

---

## 第 40 步：前端 TTS 语音播报

### 本步目标

实现系统回复的语音播报。

### 验收结果

- 后端 reply 可以被播报。
- 用户可开关播报。
- 浏览器不支持时有降级。

### 给 Codex 的完整提示词

```text
请只实现前端 TTS 语音播报。

使用 Web Speech API SpeechSynthesis：
1. 当后端返回 reply 时，可以自动播报。
2. 提供开启 / 关闭语音播报的控制。
3. 支持手动重播最近一次系统回复。
4. 浏览器不支持时不报错，只显示文字回复。

请预留 OpenAI Text-to-Speech 接入位置，但不要在本步实现云 TTS。

本步不要改后端业务逻辑。
```

---

## 第 41 步：前端多轮确认和候选选择

### 本步目标

让前端能处理后端返回的追问、确认和候选列表。

### 验收结果

- `need_user_reply = true` 时显示确认区。
- 删除和修改确认可操作。
- 多候选事件可选择。
- 用户选择会再次提交到语音命令接口。

### 给 Codex 的完整提示词

```text
请只实现前端多轮确认和候选选择 UI。

后端响应中如果 need_user_reply = true：
1. 显示 reply。
2. 如果 data 中有 missing_slots，显示补充输入框。
3. 如果 data 中有 candidate_events，显示候选列表。
4. 如果 action 是确认类操作，显示确认和取消按钮。

用户操作后：
1. 确认按钮提交“确认”。
2. 取消按钮提交“取消”。
3. 选择候选项后提交候选 id 或描述。

要求：
1. 保持同一个 session_id。
2. 所有系统回复都能进入 TTS 播报流程。
3. 不要改后端接口。
```

---

## 第 42 步：前端 WebSocket 接入

### 本步目标

让前端接收提醒和实时状态。

### 验收结果

- 前端可连接后端 WebSocket。
- 可显示连接状态。
- 可接收 reminder_triggered。
- 到点提醒能弹出并播报。

### 给 Codex 的完整提示词

```text
请只实现前端 WebSocket 接入。

需要完成：
1. 连接 VITE_WS_URL。
2. 发送 user_id 和 session_id。
3. 显示连接状态。
4. 处理 reminder_triggered 消息。
5. 处理 dialog_followup、command_completed 等消息，如果后端已支持。
6. 收到提醒时：
   - 弹出提醒
   - 高亮相关事件
   - 调用 TTS 播报

要求：
1. 支持断线重连。
2. 不要在 WebSocket 中重复执行 HTTP 业务。
3. 不要改变已有语音命令接口。
```

---

## 第 43 步：前后端联调

### 本步目标

跑通完整业务链路。

### 验收结果

- 添加、查询、修改、删除、提醒都可联调。
- 语音输入链路可演示。
- WebSocket 提醒可演示。

### 给 Codex 的完整提示词

```text
请只做前后端联调和必要修复，不要新增大功能。

请验证以下场景：
1. “明天下午三点提醒我交项目文档”
2. “我今天有什么安排”
3. “删除明天的会议”
4. “把下周三的会改到周四下午两点”
5. 创建一个 1 分钟后触发的提醒，验证 WebSocket 和 TTS。

如果发现前后端字段不一致，请按《开发文档.md》的接口约定修复。

完成后输出：
1. 已跑通场景。
2. 修复的问题。
3. 仍存在的风险。

不要做无关重构。
```

---

## 第 44 步：后端测试

### 本步目标

为后端核心逻辑补基础测试。

### 验收结果

- 时间解析有测试。
- NLU 有测试。
- 日程 CRUD 有测试。
- 会话状态有测试。
- 提醒调度有测试。

### 给 Codex 的完整提示词

```text
请只补后端测试。

请为以下模块增加测试：
1. TimeParser
2. NLUService
3. CalendarService
4. ReminderService
5. DialogService
6. /api/voice/command 基础场景

测试场景至少包含：
- 明天下午三点提醒我交项目文档
- 我今天有什么安排
- 删除明天的会议
- 把下周三的会改到周四下午两点
- 缺少时间时追问
- 删除前确认

要求：
1. 测试可本地运行。
2. 不要依赖真实大模型调用。
3. 大模型部分要 mock 或降级到规则解析。
```

---

## 第 45 步：前端基础测试和可用性检查

### 本步目标

确认前端核心交互不会明显崩溃。

### 验收结果

- 前端构建通过。
- 主要组件能渲染。
- 语音不支持时有降级。
- API 失败时有错误提示。

### 给 Codex 的完整提示词

```text
请只做前端基础测试和可用性检查。

请检查：
1. 前端 build 是否通过。
2. CalendarView 是否能渲染空事件列表。
3. API 请求失败时是否有错误提示。
4. Web Speech API 不支持时是否显示手动输入。
5. TTS 不支持时是否仍可显示文字回复。
6. WebSocket 断线时是否显示断开并尝试重连。

如果项目已有测试框架，请补基础测试。
如果没有测试框架，请至少保证 build 和核心交互手动验证清楚。

不要新增业务功能。
```

---

## 第 46 步：Docker Compose

### 本步目标

提供统一部署和本地运行环境。

### 验收结果

- Docker Compose 可启动 PostgreSQL。
- 可启动 Redis。
- 可启动后端。
- 可启动前端。
- 可启动调度器或后端内置 scheduler。

### 给 Codex 的完整提示词

```text
请只实现 Docker 和本地部署配置。

请根据项目现状补充：
1. backend Dockerfile
2. frontend Dockerfile
3. docker-compose.yml
4. PostgreSQL 服务
5. Redis 服务
6. 后端 API 服务
7. 前端服务
8. scheduler 或 worker 服务，如果项目采用独立调度进程

要求：
1. 环境变量从 .env 或 compose environment 读取。
2. 不要把密钥写死。
3. README 中写明如何启动。
4. 保证本地开发和 Docker 运行方式不冲突。

本步不要改业务逻辑。
```

---

## 第 47 步：最终 README 和演示脚本

### 本步目标

让项目可以交付、可以演示、可以答辩。

### 验收结果

- README 清楚。
- 有启动步骤。
- 有测试步骤。
- 有演示话术和场景。

### 给 Codex 的完整提示词

```text
请只完善最终文档和演示脚本，不要改业务代码。

请补充 README 或 docs 中的交付文档，包含：
1. 项目简介。
2. 技术栈。
3. 系统架构。
4. 本地启动方式。
5. Docker 启动方式。
6. 环境变量说明。
7. 数据库初始化方式。
8. 测试命令。
9. 演示场景。

演示场景至少包含：
1. 语音添加日程。
2. 语音查询今天安排。
3. 缺少时间时系统追问。
4. 删除日程前确认。
5. 修改日程前确认。
6. 到点提醒和语音播报。

完成后输出最终交付摘要。
```

---

## 第 48 步：最终验收和缺陷清单

### 本步目标

收尾检查，不再扩展功能。

### 验收结果

- Codex 输出完整验收报告。
- 列出已完成和未完成。
- 列出风险和后续优化。

### 给 Codex 的完整提示词

```text
请只做最终验收，不要继续开发新功能。

请根据《开发文档.md》逐项检查项目完成情况。

请输出：
1. 已完成模块清单。
2. 未完成模块清单。
3. P0 功能是否全部完成。
4. P1 功能完成情况。
5. 已知缺陷。
6. 运行和测试结果。
7. 比赛演示建议。
8. 后续优化建议。

验收重点：
- 语音添加
- 语音查询
- 语音修改
- 语音删除
- 多轮追问
- 二次确认
- 提醒调度
- WebSocket 推送
- TTS 播报
- voice_command 日志

不要在本步修改代码，除非发现极小且明确的阻塞问题，并先说明原因。
```

