from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.security import current_user
from app.db.models import Conversation
from app.db.session import get_db
from app.schemas import AgentRunIn, ResumeIn
from app.services.agent.access import owned_conversation, owned_run
from app.services.agent.runner import resume_agent, run_agent
from app.services.llm.service import llm_service
from app.services.memory.redis_memory import check_rate_limit

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/run")
async def run(body: AgentRunIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    conversation_id = body.conversation_id
    if conversation_id is not None:
        await owned_conversation(db, conversation_id, user["id"])
    if not await check_rate_limit(user["id"]):
        raise HTTPException(429, "请求过于频繁")
    if conversation_id is None:
        conversation = Conversation(user_id=user["id"], title=body.query[:60])
        db.add(conversation)
        await db.commit()
        conversation_id = conversation.id
    return EventSourceResponse(run_agent(body.query, conversation_id, body.model, user_id=user["id"]), ping=15)


@router.post("/resume")
async def resume(body: ResumeIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    run = await owned_run(db, body.run_id, user["id"])
    if run.status != "waiting_confirm":
        raise HTTPException(409, "运行不在等待确认状态")
    return EventSourceResponse(resume_agent(body.run_id, body.approved, user_id=user["id"]), ping=15)


@router.get("/models")
async def models(user: dict = Depends(current_user)):
    return llm_service.available_models()
