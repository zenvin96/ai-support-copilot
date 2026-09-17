from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Conversation


async def owned_conversation(db: AsyncSession, conversation_id: int, user_id: int) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(404, "会话不存在")
    return conversation


async def owned_run(db: AsyncSession, run_id: int, user_id: int, *, lock: bool = False) -> AgentRun:
    run = await db.get(AgentRun, run_id, with_for_update=lock)
    if run is None or run.conversation_id is None:
        raise HTTPException(404, "运行不存在")
    await owned_conversation(db, run.conversation_id, user_id)
    return run
