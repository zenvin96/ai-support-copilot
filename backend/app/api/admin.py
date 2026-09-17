from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_user
from app.db.models import AgentRun, AgentStep, LlmCall, Ticket
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(current_user)])


def _run(r: AgentRun) -> dict:
    return {"id": r.id, "conversation_id": r.conversation_id, "user_query": r.user_query, "intent": r.intent,
            "model": r.model, "status": r.status, "total_tokens": r.total_tokens, "latency_ms": r.latency_ms,
            "cost_usd": r.cost_usd, "ticket_id": r.ticket_id, "error": r.error, "created_at": r.created_at}


@router.get("/runs")
async def runs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(AgentRun).order_by(AgentRun.id.desc()).limit(limit))).all()
    return [_run(r) for r in rows]


@router.get("/runs/{run_id}")
async def run_detail(run_id: int, db: AsyncSession = Depends(get_db)):
    r = await db.get(AgentRun, run_id)
    if not r:
        raise HTTPException(404)
    steps = (await db.scalars(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.seq))).all()
    calls = (await db.scalars(select(LlmCall).where(LlmCall.run_id == run_id).order_by(LlmCall.id))).all()
    return {**_run(r),
            "steps": [{"seq": s.seq, "node": s.node, "tool_name": s.tool_name, "input": s.input_json,
                       "output": s.output_json, "latency_ms": s.latency_ms, "error": s.error} for s in steps],
            "llm_calls": [{"id": c.id, "provider": c.provider, "model": c.model, "prompt_tokens": c.prompt_tokens,
                           "completion_tokens": c.completion_tokens, "latency_ms": c.latency_ms,
                           "cost_usd": c.cost_usd} for c in calls]}


@router.get("/usage")
async def usage(days: int = 14, db: AsyncSession = Depends(get_db)):
    day = func.date(LlmCall.created_at)
    q = (select(day.label("day"), LlmCall.model, func.count().label("calls"),
                func.sum(LlmCall.prompt_tokens).label("prompt_tokens"),
                func.sum(LlmCall.completion_tokens).label("completion_tokens"),
                func.sum(LlmCall.cost_usd).label("cost_usd"),
                func.avg(LlmCall.latency_ms).label("avg_latency_ms"))
         .group_by(day, LlmCall.model).order_by(day.desc()).limit(days * 10))
    rows = (await db.execute(q)).all()
    return [{"day": str(r.day), "model": r.model, "calls": r.calls, "prompt_tokens": int(r.prompt_tokens or 0),
             "completion_tokens": int(r.completion_tokens or 0), "cost_usd": round(float(r.cost_usd or 0), 6),
             "avg_latency_ms": int(r.avg_latency_ms or 0)} for r in rows]


@router.get("/tickets")
async def tickets(db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Ticket).order_by(Ticket.id.desc()).limit(100))).all()
    return [{"id": t.id, "order_id": t.order_id, "conversation_id": t.conversation_id, "summary": t.summary,
             "priority": t.priority, "status": t.status, "created_at": t.created_at} for t in rows]
