# PRD：AI 客服工单 Copilot

版本：v1.0 定稿
日期：2026-09-16
目标：面试用 mini project，10 个工作日内可演示。

---

## 1. 一句话定义

企业客服收到用户问题后，AI Agent 自动查知识库、通过 MCP 查订单、生成回复、创建工单、Slack 通知客服，全过程可回溯。

不是聊天套壳，是 **LLM + LangGraph Agent + RAG + MCP Client + 工单闭环**。

---

## 2. 目标与非目标

### 目标

1. 演示一条完整链路：用户提问 -> Agent 多步推理 -> 工具调用 -> 回复 + 工单 + 通知
2. 覆盖 JD 技术栈：React/TS、FastAPI、MySQL、Redis、Docker、LLM API、LangGraph、RAG、ChromaDB、MCP
3. 每一步可观测：工具调用链、Token、延迟、失败重试
4. 有一份评估集，能量化 RAG 召回和工具选择正确率

### 非目标（面试口头讲，不写代码）

- 多租户、权限体系
- Prompt 版本管理、Few-shot 库
- 长期记忆向量化、用户画像
- n8n / Make / Zapier、定时任务、邮件通知
- 模型成本路由（只保留 `model` 参数手动切换）
- Kubernetes

---

## 3. 用户与场景

**用户**：企业客服人员（单角色，登录后进入唯一工作区）。

**核心演示场景**：

> 客服输入：“订单 #123 为什么没发货？帮我查一下并通知客户。”

Agent 执行：

1. 意图识别 -> `order_inquiry`
2. RAG 检索“发货政策”，带引用
3. MCP 调 MySQL Server 查订单 #123
4. 调本地 mock 物流函数
5. 生成回复，附引用来源
6. 本地 tool 创建工单（MySQL）
7. MCP 调 Slack Server 通知客服频道
8. 全过程写入 `agent_runs` / `agent_steps`

**次要场景**：

- 纯知识问答：“退款政策是什么？” -> 只走 RAG，不调工具
- 闲聊/无关问题 -> 直接回复，不调工具，不建工单

---

## 4. 功能范围（MVP 5 项）

| # | 功能 | 验收标准 |
|---|---|---|
| F1 | 登录 + 工作区 | 邮箱密码登录，JWT，刷新页面不掉登录 |
| F2 | 知识库 RAG | 上传 Markdown/PDF，可提问，回复附 chunk 引用和来源文件名 |
| F3 | Agent 对话 | LangGraph 状态机，SSE 流式，前端逐 token 显示，显示当前步骤 |
| F4 | MCP 工具 | 启动时 `list_tools` 动态发现，接 MySQL MCP + Slack MCP 两个现成 Server |
| F5 | 管理后台 | 会话列表、每次 run 的步骤树、工具入参/出参、Token/延迟/成本 |

工单：MySQL 一张 `tickets` 表 + 本地 tool `create_ticket`，不走 MCP。
物流：本地 mock 函数 `get_shipping_status(order_id)`。

---

## 5. 技术栈

| 模块 | 选型 | 说明 |
|---|---|---|
| 前端 | Vite + React 19 + TypeScript + Tailwind | pnpm，react-router |
| 后端 | Python 3.12 + FastAPI | async，Pydantic v2 |
| Agent | LangGraph | 状态机，非简单 Chain |
| LLM | OpenAI + DeepSeek | 抽象 `LlmProvider` 接口，Claude/Gemini 留 adapter 位 |
| Embedding | OpenAI text-embedding-3-small | |
| 向量库 | ChromaDB | 独立容器 |
| 业务库 | MySQL 8 | 用户、会话、消息、订单、工单、run 日志 |
| 缓存 | Redis 7 | 会话短期上下文、SSE 任务状态、限流 |
| MCP | MCP Python SDK（Client） | stdio 方式拉起现成 Server |
| 流式 | SSE | `POST /agent/run` 返回 event stream |
| 部署 | Docker Compose + Nginx | 单机 Linux |
| CI | GitHub Actions | lint + pytest + build image |

---

## 6. 系统架构

```text
Browser (React + Vite)
   |  REST + SSE
   v
Nginx
   |
   v
FastAPI
   |-- LlmService        -> OpenAI / DeepSeek
   |-- RagService        -> ChromaDB
   |-- McpClientService  -> MySQL MCP Server (stdio)
   |                     -> Slack MCP Server (stdio)
   |-- AgentService      -> LangGraph
   |-- MemoryService     -> Redis
   |-- UsageService      -> MySQL (agent_runs, agent_steps, llm_calls)
   |
   +-- MySQL   +-- Redis   +-- ChromaDB
```

---

## 7. Agent 状态机

```text
START
 -> classify_intent        (LLM，结构化输出 JSON)
 -> route
      | knowledge_qa  -> retrieve -> answer -> END
      | order_inquiry -> retrieve -> call_tools -> observe -> answer -> create_ticket -> notify -> END
      | chit_chat     -> answer -> END
```

节点约束：

- `call_tools` 由 LLM 选工具，工具列表来自 MCP `list_tools` + 本地 tools
- 工具失败重试 2 次，指数退避，仍失败则进入 `answer` 并说明
- `create_ticket` 和 `notify` 前可开启人工确认开关（配置项，默认关）
- 每个节点写一条 `agent_steps`

---

## 8. 数据模型（MySQL）

```text
users          id, email, password_hash, created_at
conversations  id, user_id, title, created_at
messages       id, conversation_id, role, content, created_at
documents      id, filename, chunk_count, status, created_at
orders         id, customer_name, status, created_at        # 演示数据
tickets        id, order_id, conversation_id, summary, status, created_at
agent_runs     id, conversation_id, intent, model, status, total_tokens, latency_ms, cost_usd, created_at
agent_steps    id, run_id, seq, node, tool_name, input_json, output_json, latency_ms, error
llm_calls      id, run_id, provider, model, prompt_tokens, completion_tokens, latency_ms
```

Redis key：

```text
conv:{id}:ctx      最近 10 轮消息，TTL 1h
run:{id}:status    SSE 任务状态
ratelimit:{user}   每分钟请求数
```

ChromaDB collection：`kb_default`，metadata 含 `doc_id`、`filename`、`chunk_index`。

---

## 9. API

```text
POST /auth/login
POST /auth/register

POST /rag/documents          上传文件，异步切片入库
GET  /rag/documents
POST /rag/query              调试用，直接检索

POST /agent/run              SSE：token / step / tool_call / done
GET  /conversations
GET  /conversations/{id}/messages

GET  /mcp/tools              当前已发现的工具列表
POST /mcp/call               调试用，直接调一个工具

GET  /admin/runs
GET  /admin/runs/{id}        步骤树 + llm_calls
GET  /admin/usage            按天汇总 Token / 成本
```

SSE 事件格式：

```json
{"type": "step",      "node": "retrieve", "status": "running"}
{"type": "tool_call", "name": "mysql_query", "input": {...}, "output": {...}}
{"type": "token",     "content": "您的"}
{"type": "done",      "run_id": 42, "ticket_id": 7}
```

---

## 10. 前端页面

| 路由 | 内容 |
|---|---|
| `/login` | 登录 |
| `/chat` | 左侧会话列表，中间对话流，右侧当前 run 的步骤面板 |
| `/knowledge` | 文档上传、列表、状态 |
| `/admin/runs` | run 列表，点开看步骤树和工具入参出参 |
| `/admin/usage` | Token / 成本 / 延迟 图表 |

---

## 11. 安全

- Prompt Injection：system prompt 与用户内容分隔，工具入参 Pydantic 校验，MySQL MCP 只给只读账号
- 敏感信息：回复前正则脱敏手机号、邮箱
- 限流：Redis 每用户每分钟 20 次
- 密钥：全部走 `.env`，不入库

---

## 12. 可观测与评估

**日志**：每次 LLM 调用、每个工具调用落库，管理后台可查。

**评估集**：`eval/cases.jsonl`，20 条，每条含问题、期望意图、期望工具、期望引用文档。

**指标**：

- 意图准确率
- 工具选择正确率
- RAG 命中率（期望文档是否出现在 top-3）

运行：`python -m eval.run`，输出表格到终端。

---

## 13. 里程碑

| 阶段 | 交付 | 用时 |
|---|---|---|
| M1 | Docker Compose 起 MySQL + Redis + ChromaDB + FastAPI + React 空壳 | 1 天 |
| M2 | 登录 + LlmService + SSE 流式对话 | 2 天 |
| M3 | RAG 上传 / 切片 / 检索 / 引用展示 | 2 天 |
| M4 | MCP Client + LangGraph + 演示场景跑通 | 3 天 |
| M5 | 管理后台 + 评估集 + README + GitHub Actions | 2 天 |

共 10 个工作日。

---

## 14. 演示脚本（面试 5 分钟）

1. 打开 `/knowledge`，上传 `shipping_policy.md`
2. 打开 `/chat`，输入演示问题
3. 右侧面板实时显示：意图 -> 检索 -> mysql_query -> 物流 -> 回复 -> 建单 -> Slack
4. 切到 Slack 频道看通知
5. 打开 `/admin/runs/{id}`，展示步骤树和 Token
6. 终端跑 `python -m eval.run`，展示指标

---

## 15. 面试谈资清单

- 为什么 FastAPI：async、SSE、Pydantic、OpenAPI、Python AI 生态
- 为什么 LangGraph 不用 Chain：分支、重试、人工确认、状态持久化
- RAG 不准怎么办：chunk 大小、overlap、混合检索、rerank
- MCP Client 如何动态发现工具并转成 LangGraph tool
- Tool 失败重试策略与降级
- Prompt Injection 防护
- Redis 和 MySQL 在 AI 应用里的分工
- 怎么评估 Agent：评估集 + 三项指标
- 成本：Token 落库，按天汇总
