"""把一次 Agent 运行包装成 SSE 事件流：token / step / tool_call / interrupt / done / error。"""
import json
import logging
import time
from collections.abc import AsyncIterator

from langgraph.types import Command

from app.core.config import get_settings
from app.db.models import AgentRun, Message
from app.db.session import SessionLocal
from app.services.agent.access import owned_conversation, owned_run
from app.services.agent.graph import RunContext, graph
from app.services.memory.redis_memory import get_context, push_context, set_run_status
from app.services.usage.tracker import UsageCallback

log = logging.getLogger(__name__)


def _sse(obj: dict) -> dict:
    return {"event": obj.get("type", "message"), "data": json.dumps(obj, ensure_ascii=False, default=str)}


async def _stream(run_id: int, ctx: RunContext, payload, config: dict, t0: float,
                  conversation_id: int | None, query: str) -> AsyncIterator[dict]:
    final_answer = ""
    interrupted = False
    interrupt_event = None
    try:
        async for mode, chunk in graph.astream(payload, config=config, stream_mode=["custom", "updates"]):
            if mode == "custom":
                if chunk.get("type") == "token":
                    final_answer += chunk["content"]
                yield _sse(chunk)
            elif mode == "updates" and "__interrupt__" in chunk:
                interrupted = True
                intr = chunk["__interrupt__"][0]
                interrupt_event = {**intr.value, "type": "interrupt", "run_id": run_id}

        state = graph.get_state(config).values
        answer = state.get("answer") or final_answer
        async with SessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.intent = state.get("intent")
            run.status = "waiting_confirm" if interrupted else "done"
            run.total_tokens = ctx.usage.total_tokens
            run.cost_usd = round(ctx.usage.cost_usd, 6)
            run.latency_ms = int((time.perf_counter() - t0) * 1000)
            run.ticket_id = state.get("ticket_id")
            run.error = state.get("error")
            if not interrupted and answer and conversation_id:
                db.add(Message(conversation_id=conversation_id, role="assistant", content=answer, run_id=run_id))
            await db.commit()
        if not interrupted and answer and conversation_id:
            await push_context(conversation_id, "assistant", answer)
        await set_run_status(run_id, run.status)
        if interrupt_event:
            yield _sse(interrupt_event)
        if not interrupted:
            yield _sse({"type": "done", "run_id": run_id, "intent": state.get("intent"),
                        "ticket_id": state.get("ticket_id"), "citations": state.get("citations") or [],
                        "notified": state.get("notified"), "usage": {
                            "prompt_tokens": ctx.usage.prompt_tokens, "completion_tokens": ctx.usage.completion_tokens,
                            "cost_usd": round(ctx.usage.cost_usd, 6), "latency_ms": run.latency_ms}})
    except Exception as e:
        log.exception("agent run %s failed", run_id)
        async with SessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            run.status, run.error = "failed", str(e)[:2000]
            run.latency_ms = int((time.perf_counter() - t0) * 1000)
            await db.commit()
        yield _sse({"type": "error", "run_id": run_id, "message": str(e)})


_contexts: dict[int, RunContext] = {}


async def run_agent(query: str, conversation_id: int, model: str | None, *, user_id: int) -> AsyncIterator[dict]:
    model = model or get_settings().default_model
    t0 = time.perf_counter()
    async with SessionLocal() as db:
        await owned_conversation(db, conversation_id, user_id)
    # Load history before persisting the new user message, so a cache miss cannot duplicate it.
    history = await get_context(conversation_id)
    async with SessionLocal() as db:
        run = AgentRun(conversation_id=conversation_id, user_query=query, model=model)
        db.add(run)
        if conversation_id:
            db.add(Message(conversation_id=conversation_id, role="user", content=query))
        await db.commit()
        run_id = run.id
    if conversation_id:
        await push_context(conversation_id, "user", query)
    await set_run_status(run_id, "running")

    ctx = RunContext(run_id=run_id, model=model, usage=UsageCallback(run_id))
    _contexts[run_id] = ctx
    config = {"configurable": {"thread_id": f"run-{run_id}", "ctx": ctx}}
    yield _sse({"type": "start", "run_id": run_id, "model": model, "conversation_id": conversation_id})
    payload = {"query": query, "history": history, "conversation_id": conversation_id}
    async for ev in _stream(run_id, ctx, payload, config, t0, conversation_id, query):
        yield ev


async def resume_agent(run_id: int, approved: bool, *, user_id: int) -> AsyncIterator[dict]:
    async with SessionLocal() as db:
        run = await owned_run(db, run_id, user_id, lock=True)
        if run.status != "waiting_confirm":
            yield _sse({"type": "error", "run_id": run_id, "message": "运行不在等待确认状态"})
            return
        ctx = _contexts.get(run_id)
        if ctx is None:
            yield _sse({"type": "error", "run_id": run_id, "message": "run 不存在或已过期"})
            return
        conversation_id, query = run.conversation_id, run.user_query
        run.status = "running"
        await db.commit()
    config = {"configurable": {"thread_id": f"run-{run_id}", "ctx": ctx}}
    async for ev in _stream(run_id, ctx, Command(resume=approved), config, time.perf_counter(), conversation_id, query):
        yield ev
