import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, agent, auth, conversations, mcp, rag
from app.db.seed import init_db
from app.services.mcp.client import mcp_service
from app.services.rag.ingest import backfill_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await backfill_content()
    tools = await mcp_service.refresh()
    log.info("MCP tools discovered: %s", [t.name for t in tools])
    yield


app = FastAPI(title="AI 客服工单 Copilot", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for r in (auth, rag, agent, conversations, mcp, admin):
    app.include_router(r.router)


@app.get("/health")
async def health():
    return {"ok": True, "mcp_tools": [t.name for t in mcp_service.tools]}
