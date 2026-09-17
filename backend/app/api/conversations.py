from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import current_user
from app.db.models import Conversation, Message
from app.db.session import get_db
from app.schemas import ConversationIn

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Conversation).where(Conversation.user_id == user["id"])
                             .order_by(Conversation.id.desc()))).all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at} for c in rows]


@router.post("")
async def create(body: ConversationIn, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    c = Conversation(user_id=user["id"], title=body.title)
    db.add(c)
    await db.commit()
    await db.refresh(c)  # created_at 由 DB 生成，async 下必须显式刷新
    return {"id": c.id, "title": c.title, "created_at": c.created_at}


@router.get("/{cid}/messages")
async def messages(cid: int, user: dict = Depends(current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Conversation, cid)
    if not c or c.user_id != user["id"]:
        raise HTTPException(404)
    rows = (await db.scalars(select(Message).where(Message.conversation_id == cid).order_by(Message.id))).all()
    return [{"id": m.id, "role": m.role, "content": m.content, "run_id": m.run_id, "created_at": m.created_at}
            for m in rows]
