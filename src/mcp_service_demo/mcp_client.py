from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from mcp import Client
from mcp.server.mcpserver import MCPServer


@dataclass(frozen=True)
class MCPTool:
    server: str
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]

    @property
    def agent_name(self) -> str:
        return f"{self.server}__{self.name}"


class MCPBroker:
    """Discovers and invokes tools across named MCP servers."""

    def __init__(self, targets: dict[str, str | MCPServer]):
        self.targets = targets

    async def list_tools(self) -> list[MCPTool]:
        discovered: list[MCPTool] = []
        for server_name, target in self.targets.items():
            async with Client(target, raise_exceptions=True) as client:
                result = await client.list_tools()
            for tool in result.tools:
                discovered.append(
                    MCPTool(
                        server=server_name,
                        name=tool.name,
                        title=tool.title or tool.name.replace("_", " ").title(),
                        description=tool.description or "",
                        input_schema=tool.input_schema,
                    )
                )
        return discovered

    async def call(self, server: str, tool: str, arguments: dict[str, Any]) -> Any:
        if server not in self.targets:
            raise KeyError(f"Unknown MCP server {server!r}")
        async with Client(self.targets[server], raise_exceptions=True) as client:
            result = await client.call_tool(tool, arguments)
        if result.is_error:
            message = "\n".join(
                item.text for item in result.content if getattr(item, "type", None) == "text"
            )
            raise RuntimeError(message or f"MCP tool {server}.{tool} failed")
        if result.structured_content is not None:
            return result.structured_content
        text_parts = [item.text for item in result.content if getattr(item, "type", None) == "text"]
        if not text_parts:
            return None
        combined = "\n".join(text_parts)
        try:
            return json.loads(combined)
        except json.JSONDecodeError:
            return combined

    async def call_agent_tool(self, agent_name: str, arguments: dict[str, Any]) -> Any:
        server, separator, tool = agent_name.partition("__")
        if not separator:
            raise ValueError(f"Invalid namespaced tool name: {agent_name!r}")
        return await self.call(server, tool, arguments)
