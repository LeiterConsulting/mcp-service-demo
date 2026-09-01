from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import DemoAgent
from .config import get_environment_settings, get_settings
from .connection_settings import SplunkConnectionStore
from .mcp_client import MCPBroker
from .scenario import seed_splunk_scenario
from .splunk_backend import LiveSplunkBackend
from .storage import DemoStore

settings = get_settings()
store = DemoStore(settings.database_path)
store.ensure_seeded()
broker = MCPBroker({"splunk": settings.splunk_mcp_url, "tickets": settings.ticket_mcp_url})
agent = DemoAgent(settings, broker)

app = FastAPI(
    title="MCP Service Demo",
    description="Agent host and service-desk API for the Splunk MCP demonstration.",
    version="0.3.0",
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    ticket_id: str | None = None


class InvestigateRequest(BaseModel):
    write_back: bool = True


class SplunkConnectionUpdate(BaseModel):
    data_mode: str | None = None
    rest_url: str | None = None
    rest_token: str | None = None
    rest_token_scheme: str | None = None
    rest_verify_ssl: bool | None = None
    rest_ca_bundle_path: str | None = None
    hec_url: str | None = None
    hec_token: str | None = None
    hec_verify_ssl: bool | None = None
    hec_ca_bundle_path: str | None = None
    clear_rest_token: bool = False
    clear_hec_token: bool = False


@app.get("/api/health")
async def health() -> dict[str, Any]:
    runtime_settings = get_settings()
    return {
        "status": "ok",
        "agent_mode": settings.agent_mode,
        "splunk_data_mode": runtime_settings.splunk_data_mode,
        "scenario": "checkout-degradation",
        "mcp_servers": {
            "splunk": settings.splunk_mcp_url,
            "tickets": settings.ticket_mcp_url,
        },
    }


@app.get("/api/settings/splunk")
async def get_splunk_settings() -> dict[str, Any]:
    base = get_environment_settings()
    return SplunkConnectionStore.for_settings(base).safe_export(base)


@app.put("/api/settings/splunk")
async def update_splunk_settings(update: SplunkConnectionUpdate) -> dict[str, Any]:
    base = get_environment_settings()
    connection_store = SplunkConnectionStore.for_settings(base)
    try:
        connection_store.save(base, update.model_dump(exclude_none=True))
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "success",
        "message": "Splunk connection saved and available to the MCP server.",
        "settings": connection_store.safe_export(base),
    }


@app.post("/api/settings/splunk/test")
async def test_splunk_settings(update: SplunkConnectionUpdate) -> dict[str, Any]:
    base = get_environment_settings()
    connection_store = SplunkConnectionStore.for_settings(base)
    try:
        candidate = connection_store.preview(base, update.model_dump(exclude_none=True))
        if candidate.splunk_data_mode == "fixture":
            return {
                "status": "success",
                "message": "Fixture telemetry is ready. No external Splunk connection is used.",
                "details": {"mode": "fixture", "ready": True},
            }
        details = await asyncio.to_thread(LiveSplunkBackend(candidate).status)
        scenario_message = (
            f"Demo run {details['active_run_id']} is searchable."
            if details.get("ready")
            else "Connection works; publish the demo scenario before presenting."
        )
        return {
            "status": "success",
            "message": f"Connected to Splunk. {scenario_message}",
            "details": details,
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }


@app.get("/api/splunk/status")
async def splunk_status() -> dict[str, Any]:
    try:
        return await broker.call("splunk", "get_splunk_status", {})
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Splunk is not ready: {exc}") from exc


@app.get("/api/mcp/tools")
async def mcp_tools() -> dict[str, Any]:
    try:
        tools = await broker.list_tools()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MCP servers are not ready: {exc}") from exc
    return {
        "servers": [
            {"name": "splunk", "title": "Splunk Operations", "url": settings.splunk_mcp_url},
            {
                "name": "tickets",
                "title": "Northstar Service Desk",
                "url": settings.ticket_mcp_url,
            },
        ],
        "tools": [
            {
                "server": tool.server,
                "name": tool.name,
                "title": tool.title,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
        ],
    }


@app.get("/api/tickets")
async def list_tickets(assignee: str = "Maya Chen") -> dict[str, Any]:
    return {"tickets": store.list_tickets(assignee)}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: str) -> dict[str, Any]:
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@app.post("/api/agent/chat")
async def agent_chat(request: ChatRequest) -> dict[str, Any]:
    try:
        result = await agent.chat(request.message, request.ticket_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Agent workflow failed: {exc}") from exc
    return result.to_dict()


@app.post("/api/agent/investigate/{ticket_id}")
async def investigate_ticket(ticket_id: str, request: InvestigateRequest) -> dict[str, Any]:
    try:
        result = await agent.investigate_ticket(ticket_id, write_back=request.write_back)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Investigation failed: {exc}") from exc
    return result.to_dict()


@app.post("/api/demo/reset")
async def reset_demo() -> dict[str, Any]:
    try:
        runtime_settings = get_settings()
        if runtime_settings.splunk_data_mode == "live":
            return await asyncio.to_thread(seed_splunk_scenario, runtime_settings, store)
        return store.reset()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Unable to reset the demo: {exc}") from exc


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/{path:path}", include_in_schema=False)
async def browser_fallback(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(static_dir / "index.html")
