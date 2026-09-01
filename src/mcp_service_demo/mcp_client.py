from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
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


@dataclass(frozen=True)
class MCPRemoteTarget:
    """Streamable HTTP MCP endpoint with optional bearer authentication and TLS policy."""

    url: str
    token: str | None = None
    verify: bool | str = True


MCPClientTarget = str | MCPServer | MCPRemoteTarget
MCPClientTargetProvider = Callable[[], MCPClientTarget]


class MCPBroker:
    """Discovers and invokes tools across named MCP servers."""

    def __init__(self, targets: dict[str, MCPClientTarget | MCPClientTargetProvider]):
        self.targets = targets

    def _target(self, server_name: str) -> MCPClientTarget:
        target = self.targets[server_name]
        return target() if callable(target) else target

    @staticmethod
    @asynccontextmanager
    async def _client(target: MCPClientTarget) -> AsyncIterator[Client]:
        if not isinstance(target, MCPRemoteTarget):
            async with Client(target, raise_exceptions=True) as client:
                yield client
            return

        headers = {"Authorization": f"Bearer {target.token}"} if target.token else None
        timeout = httpx2.Timeout(30.0, read=300.0)
        async with httpx2.AsyncClient(
            headers=headers,
            verify=target.verify,
            timeout=timeout,
            follow_redirects=True,
        ) as http_client:
            transport = streamable_http_client(target.url, http_client=http_client)
            async with Client(transport, raise_exceptions=True) as client:
                yield client

    async def list_tools(self) -> list[MCPTool]:
        discovered: list[MCPTool] = []
        for server_name in self.targets:
            async with self._client(self._target(server_name)) as client:
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
        async with self._client(self._target(server)) as client:
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
