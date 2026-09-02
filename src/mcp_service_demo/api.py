from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from .agent import DemoAgent
from .config import Settings, get_environment_settings, get_settings
from .connection_settings import SplunkConnectionStore
from .mcp_client import MCPBroker, MCPRemoteTarget
from .scenario import seed_splunk_scenario_via_mcp
from .splunk_backend import LiveSplunkBackend
from .splunk_mcp_adapter import SplunkMCPAdapter
from .storage import DemoStore

settings = get_settings()
store = DemoStore(settings.database_path)
store.ensure_seeded()


def _splunk_mcp_target(runtime_settings: Settings | None = None) -> MCPRemoteTarget:
    resolved = runtime_settings or get_settings()
    return MCPRemoteTarget(
        url=resolved.splunk_mcp_url,
        token=resolved.splunk_mcp_token,
        verify=resolved.splunk_mcp_verify,
    )


broker = MCPBroker(
    {
        "splunk": _splunk_mcp_target,
        "tickets": settings.ticket_mcp_url,
        "catalog": settings.catalog_mcp_url,
    }
)


def _runtime_agent(on_event: Callable[[Any], Awaitable[None] | None] | None = None) -> DemoAgent:
    return DemoAgent(get_settings(), broker, on_event=on_event)


app = FastAPI(
    title="MCP Service Demo",
    description="Agent host and service-desk API for the Splunk MCP demonstration.",
    version="0.8.0",
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    ticket_id: str | None = None
    audience: Literal["executive", "engineering", "security", "finance"] = "executive"


class InvestigateRequest(BaseModel):
    write_back: bool = True
    audience: Literal["executive", "engineering", "security", "finance"] = "executive"


class DemoSettingsUpdate(BaseModel):
    audience: Literal["executive", "engineering", "security", "finance"] = "executive"


class TicketAssignmentUpdate(BaseModel):
    assignee: str = Field(min_length=1, max_length=80)


class TicketEscalationUpdate(BaseModel):
    assignment_group: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=240)


class TicketStatusUpdate(BaseModel):
    status: str


class SplunkConnectionUpdate(BaseModel):
    mcp_url: str | None = None
    mcp_token: str | None = None
    mcp_verify_ssl: bool | None = None
    mcp_ca_bundle_path: str | None = None
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
    clear_mcp_token: bool = False
    clear_rest_token: bool = False
    clear_hec_token: bool = False


class LLMConnectionUpdate(BaseModel):
    agent_mode: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    clear_api_key: bool = False

    def as_store_update(self) -> dict[str, Any]:
        payload = self.model_dump(exclude_none=True)
        return {
            "agent_mode": payload.get("agent_mode"),
            "openai_base_url": payload.get("base_url"),
            "openai_api_key": payload.get("api_key"),
            "openai_model": payload.get("model"),
            "clear_openai_api_key": payload.get("clear_api_key", False),
        }


@app.get("/api/health")
async def health() -> dict[str, Any]:
    runtime_settings = get_settings()
    demo_settings = SplunkConnectionStore.for_settings(
        get_environment_settings()
    ).safe_export_demo()
    return {
        "status": "ok",
        "demo_audience": demo_settings["audience"],
        "agent_mode": runtime_settings.agent_mode,
        "agent_mode_preference": runtime_settings.agent_mode_preference,
        "agent_model": runtime_settings.openai_model,
        "llm_configured": runtime_settings.llm_configured,
        "agent_tuning": {
            "profile": "balanced",
            "max_iterations": runtime_settings.openai_max_iterations,
            "max_tool_calls": runtime_settings.openai_max_tool_calls,
            "max_parallel_tools": runtime_settings.openai_max_parallel_tools,
            "request_timeout_seconds": runtime_settings.openai_timeout_seconds,
        },
        "splunk_data_mode": runtime_settings.splunk_data_mode,
        "scenario": "checkout-degradation",
        "mcp_servers": {
            "splunk": runtime_settings.splunk_mcp_url,
            "tickets": settings.ticket_mcp_url,
            "catalog": settings.catalog_mcp_url,
        },
    }


@app.get("/api/settings/llm")
async def get_llm_settings() -> dict[str, Any]:
    base = get_environment_settings()
    return SplunkConnectionStore.for_settings(base).safe_export_llm(base)


@app.get("/api/settings/demo")
async def get_demo_settings() -> dict[str, Any]:
    base = get_environment_settings()
    return SplunkConnectionStore.for_settings(base).safe_export_demo()


@app.put("/api/settings/demo")
async def update_demo_settings(update: DemoSettingsUpdate) -> dict[str, Any]:
    base = get_environment_settings()
    connection_store = SplunkConnectionStore.for_settings(base)
    try:
        connection_store.save(base, {"demo_audience": update.audience})
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "success",
        "message": f"{update.audience.title()} audience selected.",
        "settings": connection_store.safe_export_demo(),
    }


@app.put("/api/settings/llm")
async def update_llm_settings(update: LLMConnectionUpdate) -> dict[str, Any]:
    base = get_environment_settings()
    connection_store = SplunkConnectionStore.for_settings(base)
    payload = update.as_store_update()
    try:
        candidate = connection_store.preview(base, payload)
        if candidate.agent_mode_preference == "openai" and not candidate.llm_configured:
            raise ValueError("Add an API key before enabling LLM-assisted mode")
        connection_store.save(base, payload)
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "success",
        "message": "Agent and LLM settings saved. The selected mode is active now.",
        "settings": connection_store.safe_export_llm(base),
    }


@app.post("/api/settings/llm/test")
async def test_llm_settings(update: LLMConnectionUpdate) -> dict[str, Any]:
    base = get_environment_settings()
    connection_store = SplunkConnectionStore.for_settings(base)
    try:
        candidate = connection_store.preview(base, update.as_store_update())
        if not candidate.openai_api_key:
            raise ValueError("Enter an API key before testing the model connection")
        async with AsyncOpenAI(
            api_key=candidate.openai_api_key,
            base_url=candidate.openai_base_url,
            timeout=20.0,
            max_retries=0,
        ) as client:
            response = await client.responses.create(
                model=candidate.openai_model,
                input="Reply with the single word READY.",
                max_output_tokens=16,
                store=False,
            )
        return {
            "status": "success",
            "message": (
                f"Connected to {candidate.openai_model}. "
                "LLM-assisted mode can use the discovered MCP tools."
            ),
            "details": {
                "base_url": candidate.openai_base_url,
                "model": candidate.openai_model,
                "response_id": response.id,
            },
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
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
        "message": "Splunk connections saved and available to the agent and MCP server.",
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
        if candidate.splunk_rest_configured:
            details = await asyncio.to_thread(LiveSplunkBackend(candidate).status)
        else:
            candidate_broker = MCPBroker({"splunk": _splunk_mcp_target(candidate)})
            details = await SplunkMCPAdapter(candidate, candidate_broker).status()
        if details.get("ready") and details.get("fresh", True):
            scenario_message = f"Demo run {details['active_run_id']} is searchable and fresh."
        elif details.get("ready"):
            scenario_message = (
                f"Demo run {details['active_run_id']} is searchable but outside its live incident "
                "window; use Reset demo before presenting."
            )
        else:
            scenario_message = "Connection works; publish the demo scenario before presenting."
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


@app.post("/api/settings/splunk/mcp/test")
async def test_splunk_mcp_settings(update: SplunkConnectionUpdate) -> dict[str, Any]:
    base = get_environment_settings()
    connection_store = SplunkConnectionStore.for_settings(base)
    try:
        candidate = connection_store.preview(base, update.model_dump(exclude_none=True))
        tools = await MCPBroker({"splunk": _splunk_mcp_target(candidate)}).list_tools()
        tls_policy = (
            "verify certificates" if candidate.splunk_mcp_verify is not False else "do not verify"
        )
        return {
            "status": "success",
            "message": (
                f"Connected to the MCP endpoint. {len(tools)} tools are available. "
                f"TLS policy: {tls_policy}."
            ),
            "details": {
                "endpoint": candidate.splunk_mcp_url,
                "tls_verification": candidate.splunk_mcp_verify is not False,
                "ca_bundle": (
                    candidate.splunk_mcp_verify
                    if isinstance(candidate.splunk_mcp_verify, str)
                    else None
                ),
                "tool_count": len(tools),
                "tools": [tool.name for tool in tools],
            },
        }
    except Exception as exc:
        return {
            "status": "error",
            "message": str(exc),
        }


@app.get("/api/splunk/status")
async def splunk_status() -> dict[str, Any]:
    try:
        return await SplunkMCPAdapter(get_settings(), broker).status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Splunk is not ready: {exc}") from exc


@app.get("/api/mcp/tools")
async def mcp_tools() -> dict[str, Any]:
    runtime_settings = get_settings()
    try:
        tools = await broker.list_tools()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MCP servers are not ready: {exc}") from exc
    return {
        "servers": [
            {
                "name": "splunk",
                "title": "Splunk Operations",
                "url": runtime_settings.splunk_mcp_url,
                "web_url": _splunk_web_url(runtime_settings),
            },
            {
                "name": "tickets",
                "title": "Northstar Service Desk",
                "url": settings.ticket_mcp_url,
            },
            {
                "name": "catalog",
                "title": "Northstar Service Catalog",
                "url": settings.catalog_mcp_url,
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


def _splunk_web_url(runtime_settings: Settings) -> str:
    mcp_host = urlsplit(runtime_settings.splunk_mcp_url).hostname
    source = (
        runtime_settings.splunk_mcp_url
        if mcp_host not in {None, "127.0.0.1", "localhost", "0.0.0.0"}
        else runtime_settings.splunk_rest_url or runtime_settings.splunk_mcp_url
    )
    parsed = urlsplit(source)
    hostname = parsed.hostname or "127.0.0.1"
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    port = parsed.port
    if port in {8089, 8088, 8101}:
        port = 8000
    netloc = f"{host}:{port}" if port else host
    return urlunsplit((parsed.scheme or "https", netloc, "", "", ""))


@app.get("/api/tickets")
async def list_tickets(assignee: str = "Maya Chen") -> dict[str, Any]:
    return {"tickets": store.list_tickets(assignee)}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket(ticket_id: str) -> dict[str, Any]:
    ticket = store.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@app.get("/api/catalog/services/{service}")
async def get_catalog_service(service: str) -> dict[str, Any]:
    try:
        return await broker.call("catalog", "get_service_context", {"service": service})
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Service context unavailable: {exc}") from exc


@app.post("/api/tickets/{ticket_id}/assign")
async def assign_ticket(ticket_id: str, update: TicketAssignmentUpdate) -> dict[str, Any]:
    try:
        return await broker.call(
            "tickets", "assign_ticket", {"ticket_id": ticket_id, "assignee": update.assignee}
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tickets/{ticket_id}/escalate")
async def escalate_ticket(ticket_id: str, update: TicketEscalationUpdate) -> dict[str, Any]:
    try:
        return await broker.call(
            "tickets",
            "escalate_ticket",
            {
                "ticket_id": ticket_id,
                "assignment_group": update.assignment_group,
                "reason": update.reason,
            },
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tickets/{ticket_id}/status")
async def update_ticket_status(ticket_id: str, update: TicketStatusUpdate) -> dict[str, Any]:
    try:
        return await broker.call(
            "tickets", "update_ticket_status", {"ticket_id": ticket_id, "status": update.status}
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/agent/chat")
async def agent_chat(request: ChatRequest) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await _runtime_agent().chat(request.message, request.ticket_id, request.audience)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Agent workflow failed: {exc}") from exc
    return result.to_dict(elapsed_ms=int((time.perf_counter() - started) * 1000))


def _stream_agent_workflow(
    operation: Callable[[DemoAgent], Awaitable[Any]],
) -> StreamingResponse:
    async def stream():
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        started = time.perf_counter()

        async def on_event(event: Any) -> None:
            await queue.put({"type": "tool", "event": asdict(event)})

        async def produce() -> None:
            try:
                result = await operation(_runtime_agent(on_event))
                await queue.put(
                    {
                        "type": "result",
                        "result": result.to_dict(
                            elapsed_ms=int((time.perf_counter() - started) * 1000)
                        ),
                    }
                )
            except Exception as exc:
                await queue.put({"type": "error", "message": str(exc)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(produce())
        yield json.dumps(
            {
                "type": "workflow",
                "message": "Interpreting the request and selecting discovered MCP tools",
            }
        ) + "\n"
        while True:
            item = await queue.get()
            if item is None:
                break
            yield json.dumps(item, default=str) + "\n"
        await task

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/agent/chat/stream")
async def stream_agent_chat(request: ChatRequest) -> StreamingResponse:
    return _stream_agent_workflow(
        lambda agent: agent.chat(request.message, request.ticket_id, request.audience)
    )


@app.post("/api/agent/investigate/{ticket_id}")
async def investigate_ticket(ticket_id: str, request: InvestigateRequest) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await _runtime_agent().investigate(
            ticket_id,
            write_back=request.write_back,
            audience=request.audience,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Investigation failed: {exc}") from exc
    return result.to_dict(elapsed_ms=int((time.perf_counter() - started) * 1000))


@app.post("/api/agent/investigate/{ticket_id}/stream")
async def stream_ticket_investigation(
    ticket_id: str, request: InvestigateRequest
) -> StreamingResponse:
    return _stream_agent_workflow(
        lambda agent: agent.investigate(
            ticket_id,
            write_back=request.write_back,
            audience=request.audience,
        )
    )


@app.post("/api/demo/reset")
async def reset_demo() -> dict[str, Any]:
    try:
        runtime_settings = get_settings()
        if runtime_settings.splunk_data_mode == "live":
            result = await seed_splunk_scenario_via_mcp(runtime_settings, broker, store)
        else:
            result = store.reset()
        return {
            **result,
            "settings_preserved": True,
            "splunk_settings_preserved": True,
        }
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
