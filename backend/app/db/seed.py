"""启动时建表 + 演示数据。"""
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import Base, Order, User
from app.db.session import SessionLocal, engine

DEMO_ORDERS = [
    dict(id=123, customer_name="王小明", customer_phone="13800001234", product="无线降噪耳机",
         amount=899.0, status="pending_stock", tracking_no=None, note="仓库缺货，预计 3 天补货"),
    dict(id=124, customer_name="李华", customer_phone="13900005678", product="机械键盘",
         amount=459.0, status="shipped", tracking_no="SF1234567890", note=None),
    dict(id=125, customer_name="Alice Chen", customer_phone="13700009999", product="显示器 27 寸",
         amount=1899.0, status="delivered", tracking_no="YT9876543210", note=None),
    dict(id=126, customer_name="张伟", customer_phone="13600002222", product="USB-C 扩展坞",
         amount=299.0, status="paid", tracking_no=None, note="等待出库"),
    dict(id=127, customer_name="赵敏", customer_phone="13500003333", product="蓝牙音箱",
         amount=399.0, status="cancelled", tracking_no=None, note="用户主动取消"),
]


async def init_db() -> None:
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 轻量迁移：给已存在的 documents 表补 content 列
        has = await conn.scalar(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name='documents' AND column_name='content'"))
        if not has:
            await conn.execute(text("ALTER TABLE documents ADD COLUMN content LONGTEXT NULL AFTER filename"))

        has_version = await conn.scalar(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name='documents' AND column_name='index_version'"))
        if not has_version:
            await conn.execute(text(
                "ALTER TABLE documents ADD COLUMN index_version VARCHAR(32) NOT NULL DEFAULT 'legacy'"))

    async with SessionLocal() as db:
        if not await db.scalar(select(User).limit(1)):
            db.add(User(email="admin@example.com", password_hash=hash_password("admin123")))
        if not await db.scalar(select(Order).limit(1)):
            for o in DEMO_ORDERS:
                db.add(Order(**o))
        await db.commit()
