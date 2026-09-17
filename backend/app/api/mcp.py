from fastapi import APIRouter, Depends, HTTPException

from app.core.security import current_user
from app.schemas import McpCallIn
from app.services.mcp.client import mcp_service

router = APIRouter(prefix="/mcp", tags=["mcp"], dependencies=[Depends(current_user)])


@router.get("/tools")
async def tools():
    return mcp_service.describe()


@router.post("/tools/refresh")
async def refresh():
    await mcp_service.refresh()
    return mcp_service.describe()


@router.post("/call")
async def call(body: McpCallIn):
    try:
        return {"result": await mcp_service.call(body.name, body.args)}
    except KeyError as e:
        raise HTTPException(404, str(e))
