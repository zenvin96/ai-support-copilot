from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas import LoginIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
async def register(body: LoginIn, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(400, "email exists")
    u = User(email=body.email, password_hash=hash_password(body.password))
    db.add(u)
    await db.commit()
    return TokenOut(access_token=create_token(u.id, u.email), email=u.email)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    u = await db.scalar(select(User).where(User.email == body.email))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "邮箱或密码错误")
    return TokenOut(access_token=create_token(u.id, u.email), email=u.email)
