"""MCP Client：以 stdio 拉起现成 MCP Server，动态发现工具，转成 LangChain tool 给 Agent 用。

- MySQL MCP Server: pip 包 mysql-mcp-server，只读账号
- Slack MCP Server: npx @modelcontextprotocol/server-slack，没配 token 则不加载
"""
import asyncio
import logging
import sys

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core.config import get_settings

log = logging.getLogger(__name__)


def server_config() -> dict:
    s = get_settings()
    cfg = {
        "mysql": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "mysql_mcp_server"],
            "env": {
                "MYSQL_HOST": s.mysql_host, "MYSQL_PORT": str(s.mysql_port),
                "MYSQL_USER": s.mysql_readonly_user, "MYSQL_PASSWORD": s.mysql_readonly_password,
                "MYSQL_DATABASE": s.mysql_database,
            },
        }
    }
    if s.slack_bot_token:
        cfg["slack"] = {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-slack"],
            "env": {"SLACK_BOT_TOKEN": s.slack_bot_token, "SLACK_TEAM_ID": s.slack_team_id,
                    "SLACK_CHANNEL_IDS": s.slack_channel_id},
        }
    return cfg


class McpClientService:
    def __init__(self) -> None:
        self._client: MultiServerMCPClient | None = None
        self._tools: list[BaseTool] = []
        self._tool_server: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def refresh(self) -> list[BaseTool]:
        async with self._lock:
            cfg = server_config()
            self._client = MultiServerMCPClient(cfg)
            tools: list[BaseTool] = []
            server_map: dict[str, str] = {}
            for name in cfg:
                try:
                    t = await asyncio.wait_for(self._client.get_tools(server_name=name), timeout=60)
                    tools += t
                    server_map.update({x.name: name for x in t})
                    log.info("MCP server %s: %d tools", name, len(t))
                except Exception as e:  # noqa: BLE001
                    log.warning("MCP server %s unavailable: %s", name, e)
            self._tools, self._tool_server = tools, server_map
            return tools

    @property
    def tools(self) -> list[BaseTool]:
        return self._tools

    def get(self, name: str) -> BaseTool | None:
        return next((t for t in self._tools if t.name == name), None)

    def describe(self) -> list[dict]:
        return [{"name": t.name, "server": self._tool_server.get(t.name, "?"),
                 "description": t.description,
                 "input_schema": t.args_schema.model_json_schema() if hasattr(t.args_schema, "model_json_schema")
                 else t.args_schema} for t in self._tools]

    async def call(self, name: str, args: dict):
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"tool not found: {name}")
        return await tool.ainvoke(args)


mcp_service = McpClientService()
