"""eval 等离线脚本用：建表 + 发现 MCP 工具。"""
from app.db.seed import init_db
from app.services.mcp.client import mcp_service
from app.services.rag.ingest import backfill_content


async def ensure_ready() -> None:
    await init_db()
    await backfill_content()
    await mcp_service.refresh()
