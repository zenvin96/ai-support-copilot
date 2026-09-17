"""Redis：短期会话上下文 + run 状态 + 限流。长期数据在 MySQL。"""
import json

from redis.asyncio import Redis, from_url
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Message
from app.db.session import SessionLocal

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(get_settings().redis_url, decode_responses=True)
    return _redis


CTX_TTL = 3600
CTX_MAX = 10


async def push_context(conversation_id: int, role: str, content: str) -> None:
    r = get_redis()
    key = f"conv:{conversation_id}:ctx"
    await r.rpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
    await r.ltrim(key, -CTX_MAX * 2, -1)
    await r.expire(key, CTX_TTL)


async def get_context(conversation_id: int) -> list[dict]:
    r = get_redis()
    key = f"conv:{conversation_id}:ctx"
    items = await r.lrange(key, 0, -1)
    if items:
        return [json.loads(i) for i in items]
    async with SessionLocal() as db:
        rows = (await db.scalars(select(Message).where(Message.conversation_id == conversation_id)
                                 .order_by(Message.id.desc()).limit(CTX_MAX * 2))).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(rows)]
    if history:
        # Do not overwrite messages appended by another request during the DB read.
        await r.eval("""
            if redis.call('EXISTS', KEYS[1]) == 0 then
                for i = 2, #ARGV do redis.call('RPUSH', KEYS[1], ARGV[i]) end
                redis.call('EXPIRE', KEYS[1], ARGV[1])
            end
            return 1
        """, 1, key, CTX_TTL, *(json.dumps(h, ensure_ascii=False) for h in history))
    return history


async def set_run_status(run_id: int, status: str) -> None:
    await get_redis().set(f"run:{run_id}:status", status, ex=CTX_TTL)


async def check_rate_limit(user_id: int) -> bool:
    r = get_redis()
    key = f"ratelimit:{user_id}"
    n = await r.incr(key)
    if n == 1:
        await r.expire(key, 60)
    return n <= get_settings().rate_limit_per_minute
