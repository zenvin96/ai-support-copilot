# AI 客服工单 Copilot

企业客服收到问题后，AI Agent 自动：查知识库（RAG）-> 识别意图 -> 通过 MCP 查订单 -> 查物流 -> 生成回复 -> 创建工单 -> Slack 通知，全过程可回溯。

**技术栈**：React + Vite + TypeScript · FastAPI · LangGraph · OpenAI / DeepSeek · ChromaDB · MySQL · Redis · MCP（MySQL MCP Server、Slack MCP Server）· Docker Compose · Nginx · GitHub Actions

详细需求见 [PRD.md](PRD.md)。

## 快速开始

```bash
cp .env.example .env        # 填入 OPENAI_API_KEY（必填，embedding 用）；DEEPSEEK_API_KEY / SLACK_* 可选
docker compose up --build
```

打开 http://localhost ，默认账号 `admin@example.com` / `admin123`。

| 服务 | 地址 |
|---|---|
| 前端（经 Nginx） | http://localhost |
| 后端 API 文档 | http://localhost:8000/docs |
| ChromaDB | http://localhost:8001 |
| MySQL | localhost:3306（app/app，只读账号 readonly/readonly） |

## 演示（5 分钟）

1. `/knowledge` 上传 `backend/sample_docs/` 下的三个 Markdown
2. `/chat` 点击演示问题：「订单 #123 为什么没发货？帮我查一下并通知客户。」
3. 右侧面板实时显示：意图识别 -> RAG 检索 -> `execute_sql`（MySQL MCP）-> `get_shipping_status` -> 生成回复 -> 创建工单 -> 通知
4. `/admin/runs` 查看步骤树、工具入参出参、每次 LLM 调用的 token 与成本
5. 评估：`docker compose exec backend python -m eval.run`

通知节点支持 Slack（MCP）和 Email（SMTP，配 `SMTP_HOST` + `NOTIFY_EMAIL_TO`），可同时启用；都没配时走本地 mock 并记录日志，链路不中断。

## 架构

```text
Browser (React) --REST/SSE--> Nginx --> FastAPI
                                          |-- LlmService        OpenAI / DeepSeek（统一 Provider 接口 + 用量回调）
                                          |-- RagService        ChromaDB（切片 / embedding / top-k / 引用）
                                          |-- McpClientService  stdio 拉起 MySQL MCP、Slack MCP，动态 list_tools
                                          |-- LangGraph         意图 -> 检索 -> 工具循环（重试）-> 回复 -> [确认] -> 工单 -> 通知
                                          |-- Redis             会话上下文 / run 状态 / 限流
                                          +-- MySQL             用户、会话、订单、工单、agent_runs / agent_steps / llm_calls
```

## 目录

```text
backend/app/api        auth / rag / agent / conversations / mcp / admin
backend/app/services   llm / rag / mcp / agent / memory / usage
backend/eval           评估集 + 评估脚本
backend/tests          单元测试
frontend/src/pages     Login / Chat / Knowledge / Runs / Usage
```

## 本地开发（不用 Docker 跑应用）

```bash
docker compose up mysql redis chroma -d
cd backend && uv venv --python 3.12 && uv pip install -e ".[dev]" && MYSQL_HOST=localhost CHROMA_PORT=8001 REDIS_URL=redis://localhost:6379/0 .venv/bin/uvicorn app.main:app --reload
cd frontend && pnpm install && pnpm dev     # Vite 代理 /api -> localhost:8000
```

测试与 lint：`cd backend && pytest && ruff check app tests eval`

## 安全措施

- MySQL MCP 使用只读账号，且应用层拦截非 SELECT 语句
- 用户输入用 `<user_input>` 标签与系统指令隔离，提示词明确忽略注入指令
- 回复前脱敏手机号、邮箱
- Redis 限流：每用户每分钟 20 次
- 密钥只走环境变量

## 正确性与回归验证

- Agent 创建和恢复运行时校验会话归属；未传会话 ID 时自动创建当前用户的会话。
- 文档索引先写入独立版本，再通过 MySQL 切换生效版本；失败时继续检索旧版本。后端启动会补充 `documents.index_version` 列并迁移旧 Chroma 元数据，升级时应先停止旧后端实例，再启动新版本。
- 回复正文完整生成、脱敏后才发送到前端，避免手机号或邮箱跨 token 时泄漏；步骤进度仍通过 SSE 实时发送。
- 意图识别结合对话历史生成独立检索问题；Redis 历史过期后从 MySQL 恢复最近 20 条消息。
- `cd backend && .venv/bin/python -m pytest -q` 可运行回归测试：外部模型、MySQL 和 Redis 使用模拟依赖，索引验证使用临时本地 Chroma，确认流程使用真实 LangGraph。
