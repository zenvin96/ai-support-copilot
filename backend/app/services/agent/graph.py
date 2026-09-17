"""LangGraph 状态机：

START -> classify_intent -> route
   knowledge_qa  -> retrieve -> answer -> END
   order_inquiry -> retrieve -> call_tools -> answer -> [confirm] -> create_ticket -> notify -> END
   chit_chat     -> answer -> END

每个节点：写 agent_steps，并通过 get_stream_writer 推 SSE 事件。
"""
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.core.config import get_settings
from app.db.models import AgentStep, Ticket
from app.db.session import SessionLocal
from app.services.agent import prompts
from app.services.agent.tools import LOCAL_TOOLS
from app.services.llm.service import llm_service
from app.services.mcp.client import mcp_service
from app.services.notify.email import email_enabled, send_email
from app.services.rag.retriever import format_context, retrieve
from app.services.usage.tracker import UsageCallback

log = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 4
TOOL_RETRIES = 2


class AgentState(TypedDict, total=False):
    query: str
    standalone_query: str
    history: list[dict]
    conversation_id: int | None
    intent: str
    order_id: int | None
    citations: list[dict]
    tool_results: list[dict]
    answer: str
    ticket_id: int | None
    notified: dict | None
    error: str | None


@dataclass
class RunContext:
    run_id: int
    model: str
    usage: UsageCallback
    seq: int = 0
    steps: list[dict] = field(default_factory=list)


def _ctx(config: RunnableConfig) -> RunContext:
    return config["configurable"]["ctx"]


async def _record(ctx: RunContext, node: str, *, tool_name: str | None = None, input_json: Any = None,
                  output_json: Any = None, latency_ms: int = 0, error: str | None = None) -> None:
    ctx.seq += 1
    step = {"seq": ctx.seq, "node": node, "tool_name": tool_name, "input": input_json,
            "output": output_json, "latency_ms": latency_ms, "error": error}
    ctx.steps.append(step)
    async with SessionLocal() as db:
        db.add(AgentStep(run_id=ctx.run_id, seq=ctx.seq, node=node, tool_name=tool_name,
                         input_json=_jsonable(input_json), output_json=_jsonable(output_json),
                         latency_ms=latency_ms, error=error))
        await db.commit()
    get_stream_writer()({"type": "step", "node": node, "status": "error" if error else "done", **step})


def _jsonable(v: Any) -> Any:
    if v is None:
        return None
    try:
        return json.loads(json.dumps(v, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return {"repr": repr(v)[:2000]}


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _history_messages(state: AgentState) -> list:
    out = []
    for h in state.get("history") or []:
        out.append(HumanMessage(h["content"]) if h["role"] == "user" else AIMessage(h["content"]))
    return out


# ---------- nodes ----------

async def classify_intent(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    get_stream_writer()({"type": "step", "node": "classify_intent", "status": "running"})
    t0 = time.perf_counter()
    llm = llm_service.chat(ctx.model, usage=ctx.usage)
    resp = await llm.ainvoke([SystemMessage(prompts.INTENT_SYSTEM), *_history_messages(state),
                              HumanMessage(f"<user_input>\n{state['query']}\n</user_input>")])
    data = _parse_json(resp.content)
    intent = data.get("intent") if data.get("intent") in ("knowledge_qa", "order_inquiry", "chit_chat") else "knowledge_qa"
    standalone = data.get("standalone_query")
    standalone = standalone.strip() if isinstance(standalone, str) and standalone.strip() else state["query"]
    order_id = data.get("order_id")
    if order_id is None:
        m = re.search(r"#?\s*(\d{3,})", standalone)
        order_id = int(m.group(1)) if m and intent == "order_inquiry" else None
    await _record(ctx, "classify_intent", input_json={"query": state["query"]},
                  output_json={"intent": intent, "order_id": order_id, "reason": data.get("reason")},
                  latency_ms=int((time.perf_counter() - t0) * 1000))
    return {"intent": intent, "order_id": order_id, "standalone_query": standalone}


async def retrieve_node(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    get_stream_writer()({"type": "step", "node": "retrieve", "status": "running"})
    t0 = time.perf_counter()
    try:
        query = state.get("standalone_query") or state["query"]
        cits = [c.to_dict() for c in await retrieve(query)]
        await _record(ctx, "retrieve", input_json={"query": query},
                      output_json={"hits": [{k: v for k, v in c.items() if k != "text"} for c in cits]},
                      latency_ms=int((time.perf_counter() - t0) * 1000))
        return {"citations": cits}
    except Exception as e:  # noqa: BLE001
        await _record(ctx, "retrieve", input_json={"query": state["query"]}, error=str(e)[:500],
                      latency_ms=int((time.perf_counter() - t0) * 1000))
        return {"citations": []}


async def _run_tool_with_retry(ctx: RunContext, tool, args: dict) -> Any:
    last_err: Exception | None = None
    for attempt in range(TOOL_RETRIES + 1):
        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(tool.ainvoke(args), timeout=30)
            await _record(ctx, "call_tools", tool_name=tool.name, input_json=args, output_json=result,
                          latency_ms=int((time.perf_counter() - t0) * 1000))
            return result
        except Exception as e:  # noqa: BLE001
            last_err = e
            await _record(ctx, "call_tools", tool_name=tool.name, input_json=args,
                          error=f"attempt {attempt + 1}: {e}"[:500],
                          latency_ms=int((time.perf_counter() - t0) * 1000))
            if attempt < TOOL_RETRIES:
                await asyncio.sleep(0.5 * 2 ** attempt)
    return {"error": str(last_err)}


async def call_tools(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    get_stream_writer()({"type": "step", "node": "call_tools", "status": "running"})
    _t0 = time.perf_counter()
    tools = [*mcp_service.tools, *LOCAL_TOOLS]
    tools = [t for t in tools if not t.name.startswith("slack_")]  # 通知由 notify 节点负责
    tool_map = {t.name: t for t in tools}
    llm = llm_service.chat(ctx.model, usage=ctx.usage).bind_tools(tools)
    hint = f"用户提到订单号 {state['order_id']}。" if state.get("order_id") else ""
    query = state.get("standalone_query") or state["query"]
    messages: list = [SystemMessage(prompts.TOOL_SYSTEM), *_history_messages(state),
                      HumanMessage(f"{hint}\n<user_input>\n{query}\n</user_input>")]
    results: list[dict] = []
    for _ in range(MAX_TOOL_ROUNDS):
        ai: AIMessage = await llm.ainvoke(messages)
        messages.append(ai)
        if not ai.tool_calls:
            break
        for tc in ai.tool_calls:
            tool = tool_map.get(tc["name"])
            if tool is None:
                out = {"error": f"unknown tool {tc['name']}"}
            elif tc["name"] == "execute_sql" and not _is_readonly_sql(tc["args"].get("query", "")):
                out = {"error": "只允许 SELECT 语句"}
                await _record(ctx, "call_tools", tool_name="execute_sql", input_json=tc["args"], error=out["error"])
            else:
                out = await _run_tool_with_retry(ctx, tool, tc["args"])
            results.append({"tool": tc["name"], "args": tc["args"], "result": _jsonable(out)})
            get_stream_writer()({"type": "tool_call", "name": tc["name"], "input": tc["args"], "output": _jsonable(out)})
            messages.append(ToolMessage(content=json.dumps(out, ensure_ascii=False, default=str)[:4000],
                                        tool_call_id=tc["id"]))
    get_stream_writer()({"type": "step", "node": "call_tools", "status": "done",
                         "output": {"tool_calls": len(results)},
                         "latency_ms": int((time.perf_counter() - _t0) * 1000)})
    return {"tool_results": results}


def _is_readonly_sql(sql: str) -> bool:
    s = sql.strip().lower().rstrip(";")
    return s.startswith(("select", "show", "describe", "explain")) and ";" not in s


async def answer(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    get_stream_writer()({"type": "step", "node": "answer", "status": "running"})
    t0 = time.perf_counter()
    cits = state.get("citations") or []
    parts = []
    if cits:
        from app.services.rag.retriever import Citation
        parts.append("「知识库片段」\n" + format_context([Citation(**c) for c in cits]))
    if state.get("tool_results"):
        parts.append("「工具查询结果」\n" + json.dumps(state["tool_results"], ensure_ascii=False, default=str)[:6000])
    context = "\n\n".join(parts) or "（无额外上下文）"
    llm = llm_service.chat(ctx.model, streaming=True, usage=ctx.usage)
    msgs = [SystemMessage(prompts.ANSWER_SYSTEM), *_history_messages(state),
            HumanMessage(f"{context}\n\n<user_input>\n{state['query']}\n</user_input>")]
    text = ""
    writer = get_stream_writer()
    async for chunk in llm.astream(msgs):
        if chunk.content:
            text += chunk.content
    # Buffer the complete answer: an email/phone can span arbitrary model chunks.
    text = redact(text)
    if text:
        writer({"type": "token", "content": text})
    await _record(ctx, "answer", output_json={"chars": len(text), "citations": len(cits)},
                  latency_ms=int((time.perf_counter() - t0) * 1000))
    return {"answer": text}


def redact(text: str) -> str:
    """回复前脱敏：手机号中间 4 位、邮箱用户名。"""
    text = re.sub(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)", r"\1****\2", text)
    return re.sub(r"([\w.+-])[\w.+-]*(@[\w-]+\.[\w.]+)", r"\1***\2", text)


async def confirm(state: AgentState, config: RunnableConfig) -> dict:
    """人工确认开关：开启时中断，等 /agent/resume。"""
    if not get_settings().require_human_confirm:
        return {}
    decision = interrupt({"type": "confirm", "message": "是否创建工单并通知客服？", "order_id": state.get("order_id")})
    if decision is not True:
        return {"error": "用户取消了工单创建"}
    return {}


async def create_ticket(state: AgentState, config: RunnableConfig) -> dict:
    ctx = _ctx(config)
    if state.get("error"):
        return {}
    get_stream_writer()({"type": "step", "node": "create_ticket", "status": "running"})
    t0 = time.perf_counter()
    llm = llm_service.chat(ctx.model, usage=ctx.usage)
    resp = await llm.ainvoke([SystemMessage(prompts.TICKET_SYSTEM),
                              HumanMessage(f"问题：{state['query']}\n回复：{state.get('answer', '')}")])
    data = _parse_json(resp.content)
    summary = data.get("summary") or state["query"][:60]
    priority = data.get("priority") if data.get("priority") in ("low", "normal", "high") else "normal"
    async with SessionLocal() as db:
        t = Ticket(order_id=state.get("order_id"), conversation_id=state.get("conversation_id"),
                   summary=summary, priority=priority)
        db.add(t)
        await db.commit()
        ticket_id = t.id
    await _record(ctx, "create_ticket", input_json={"summary": summary, "priority": priority},
                  output_json={"ticket_id": ticket_id}, latency_ms=int((time.perf_counter() - t0) * 1000))
    return {"ticket_id": ticket_id}


async def notify(state: AgentState, config: RunnableConfig) -> dict:
    """通知客服：Slack（MCP）和 Email（SMTP）配了哪个走哪个，可同时发；都没配走 mock。"""
    ctx = _ctx(config)
    if state.get("error"):
        return {}
    get_stream_writer()({"type": "step", "node": "notify", "status": "running"})
    _t0 = time.perf_counter()
    s = get_settings()
    subject = f"[客服 Copilot] 新工单 #{state.get('ticket_id')} | 订单 {state.get('order_id') or '-'}"
    text = (f"🎫 新工单 #{state.get('ticket_id')} | 订单 {state.get('order_id') or '-'}\n"
            f"{state['query'][:80]}\n---\n{(state.get('answer') or '')[:300]}")
    body = (f"新工单 #{state.get('ticket_id')}\n订单：{state.get('order_id') or '-'}\n"
            f"会话：{state.get('conversation_id') or '-'}\n\n用户问题：\n{state['query']}\n\n"
            f"AI 回复：\n{state.get('answer') or ''}\n")
    channels: list[dict] = []

    slack_tool = mcp_service.get("slack_post_message")
    if slack_tool and s.slack_channel_id:
        out = await _run_tool_with_retry(ctx, slack_tool, {"channel_id": s.slack_channel_id, "text": text})
        channels.append({"channel": "slack", "result": _jsonable(out)})

    if email_enabled():
        t1 = time.perf_counter()
        try:
            out = await send_email(subject, body)
            channels.append({"channel": "email", "result": out})
        except Exception as e:  # 邮件失败不阻断主链路，记录后继续
            log.warning("[email notify failed] %s", e)
            channels.append({"channel": "email", "error": str(e)})
        await _record(ctx, "notify", tool_name="send_email", input_json={"subject": subject, "to": s.notify_email_to},
                      output_json=channels[-1], latency_ms=int((time.perf_counter() - t1) * 1000))

    if not channels:
        log.info("[mock notify] %s", text)
        channels.append({"channel": "mock", "text": text})
        await _record(ctx, "notify", tool_name="mock_notify", input_json={"text": text}, output_json=channels[-1])

    result = channels[0] if len(channels) == 1 else {"channel": "multi", "channels": channels}
    get_stream_writer()({"type": "tool_call", "name": "notify", "input": {"subject": subject, "text": text},
                         "output": result})
    get_stream_writer()({"type": "step", "node": "notify", "status": "done", "output": result,
                         "latency_ms": int((time.perf_counter() - _t0) * 1000)})
    return {"notified": result}


def route(state: AgentState) -> str:
    return state.get("intent", "knowledge_qa")


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("classify_intent", classify_intent)
    g.add_node("retrieve", retrieve_node)
    g.add_node("call_tools", call_tools)
    g.add_node("answer", answer)
    g.add_node("confirm", confirm)
    g.add_node("create_ticket", create_ticket)
    g.add_node("notify", notify)

    g.add_edge(START, "classify_intent")
    g.add_conditional_edges("classify_intent", route,
                            {"knowledge_qa": "retrieve", "order_inquiry": "retrieve", "chit_chat": "answer"})
    g.add_conditional_edges("retrieve", lambda s: "call_tools" if s.get("intent") == "order_inquiry" else "answer")
    g.add_edge("call_tools", "answer")
    g.add_conditional_edges("answer", lambda s: "confirm" if s.get("intent") == "order_inquiry" else END)
    g.add_edge("confirm", "create_ticket")
    g.add_edge("create_ticket", "notify")
    g.add_edge("notify", END)
    return g.compile(checkpointer=MemorySaver())


graph = build_graph()
