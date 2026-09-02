from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import mcp_service_demo.agent as agent_module
import mcp_service_demo.mcp_client as mcp_client_module
from mcp_service_demo.agent import DemoAgent
from mcp_service_demo.config import get_settings
from mcp_service_demo.mcp_client import MCPBroker, MCPRemoteTarget, MCPTool
from mcp_service_demo.servers.splunk import splunk_mcp
from mcp_service_demo.servers.tickets import ticket_mcp
from mcp_service_demo.splunk_mcp_adapter import SplunkMCPAdapter
from mcp_service_demo.storage import DemoStore


async def test_broker_discovers_and_calls_both_mcp_servers(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    DemoStore(tmp_path / "demo.db").reset()
    resolved = 0

    def current_splunk_target():
        nonlocal resolved
        resolved += 1
        return splunk_mcp

    broker = MCPBroker({"splunk": current_splunk_target, "tickets": ticket_mcp})

    tools = await broker.list_tools()
    health = await broker.call(
        "splunk", "get_service_health", {"service": "checkout-api", "minutes": 30}
    )
    ticket = await broker.call("tickets", "get_ticket", {"ticket_id": "INC-1042"})

    assert len(tools) == 10
    assert {tool.server for tool in tools} == {"splunk", "tickets"}
    assert health["state"] == "degraded"
    assert ticket["service"] == "checkout-api"
    assert resolved == 2


async def test_ticket_investigation_completes_the_cross_system_loop(tmp_path, monkeypatch):
    database_path = tmp_path / "demo.db"
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(database_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    store = DemoStore(database_path)
    store.reset()
    broker = MCPBroker({"splunk": splunk_mcp, "tickets": ticket_mcp})
    agent = DemoAgent(get_settings(), broker)

    result = await agent.investigate_ticket("INC-1042", write_back=True)
    updated = store.get_ticket("INC-1042")

    assert result.ticket_updated is True
    assert [event.tool for event in result.timeline] == [
        "get_ticket",
        "get_service_health",
        "compare_service_baseline",
        "search_logs",
        "trace_request",
        "add_work_note",
    ]
    assert updated is not None
    assert updated["status"] == "Investigating"
    assert updated["notes"][-1]["author"] == "Splunk Investigation Agent"
    assert "connection pool" in updated["notes"][-1]["body"]


async def test_guided_agent_uses_real_splunk_query_tool_when_available(tmp_path, monkeypatch):
    database_path = tmp_path / "demo.db"
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(database_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    store = DemoStore(database_path)
    store.reset()
    ticket_broker = MCPBroker({"tickets": ticket_mcp})

    class QueryToolBroker:
        async def list_tools(self):
            ticket_tools = await ticket_broker.list_tools()
            return [
                MCPTool(
                    server="splunk",
                    name="splunk_run_query",
                    title="Run Splunk Query",
                    description="Run SPL in Splunk",
                    input_schema={"type": "object"},
                ),
                *ticket_tools,
            ]

        async def call(self, server, tool, arguments):
            if server == "tickets":
                return await ticket_broker.call(server, tool, arguments)
            assert tool == "splunk_run_query"
            query = arguments["query"]
            if 'row_kind="metric"' in query:
                rows = [
                    {
                        "row_kind": "metric",
                        "period": "current",
                        "requests": "100",
                        "errors": "18",
                        "error_rate_pct": "18.0",
                        "p50_ms": "410",
                        "p95_ms": "2840",
                    },
                    {
                        "row_kind": "metric",
                        "period": "baseline",
                        "requests": "100",
                        "errors": "1",
                        "error_rate_pct": "1.0",
                        "p50_ms": "90",
                        "p95_ms": "240",
                    },
                    {
                        "row_kind": "change",
                        "_time": "2026-09-01T12:00:00",
                        "message": "deployed checkout-api 4.18.2",
                        "version": "4.18.2",
                        "host": "deploy-01",
                    },
                ]
            elif " by period " in query:
                rows = [
                    {
                        "period": "current",
                        "requests": "100",
                        "errors": "18",
                        "error_rate_pct": "18.0",
                        "p50_ms": "410",
                        "p95_ms": "2840",
                    },
                    {
                        "period": "baseline",
                        "requests": "100",
                        "errors": "1",
                        "error_rate_pct": "1.0",
                        "p50_ms": "90",
                        "p95_ms": "240",
                    },
                ]
            elif "trace_id=" in query:
                rows = [
                    {
                        "_time": "2026-09-01T12:05:00",
                        "service": service,
                        "level": "ERROR",
                        "event_type": "request",
                        "message": "inventory-client connection pool exhausted",
                        "status_code": "503",
                        "duration_ms": "2840",
                        "host": f"{service}-01",
                        "trace_id": "tr-hot-001",
                        "version": "4.18.2",
                    }
                    for service in ("edge-gateway", "checkout-api", "inventory-api")
                ]
            else:
                rows = [
                    {
                        "_time": "2026-09-01T12:05:00",
                        "service": "checkout-api",
                        "level": "ERROR",
                        "event_type": "request",
                        "message": "inventory-client connection pool exhausted",
                        "status_code": "503",
                        "duration_ms": "2840",
                        "host": "checkout-01",
                        "trace_id": "tr-hot-001",
                        "version": "4.18.2",
                    }
                ]
            return {"results": rows, "truncated": False, "total_rows": len(rows)}

    agent = DemoAgent(get_settings(), QueryToolBroker())
    result = await agent.investigate_ticket("INC-1042", write_back=True)
    updated = store.get_ticket("INC-1042")

    splunk_events = [event for event in result.timeline if event.server == "splunk"]
    assert [event.tool for event in splunk_events] == ["splunk_run_query"] * 4
    assert all(event.arguments["app"] == "mcp_service_demo" for event in splunk_events)
    assert result.ticket_updated is True
    assert updated is not None
    assert "18.0%" in updated["notes"][-1]["body"]
    assert "connection pool" in updated["notes"][-1]["body"]


async def test_live_splunk_status_distinguishes_searchable_from_fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))

    class StatusBroker:
        async def list_tools(self):
            return [
                MCPTool(
                    server="splunk",
                    name="splunk_run_query",
                    title="Run query",
                    description="Run SPL",
                    input_schema={"type": "object"},
                )
            ]

        async def call(self, server, tool, arguments):
            assert server == "splunk"
            assert tool == "splunk_run_query"
            assert "age_minutes" in arguments["query"]
            return {
                "results": [
                    {
                        "demo_run_id": "demo-old",
                        "events": "2557",
                        "age_minutes": "18.4",
                    }
                ]
            }

    status = await SplunkMCPAdapter(get_settings(), StatusBroker()).status()

    assert status["ready"] is True
    assert status["fresh"] is False
    assert status["age_minutes"] == 18.4
    assert status["event_count"] == 2557


def test_chat_write_tools_require_explicit_authorization():
    assert DemoAgent._write_authorized("investigate inc-1042") is False
    assert DemoAgent._write_authorized("investigate inc-1042 and update the ticket") is True
    assert DemoAgent._write_authorized("investigate but do not update the ticket") is False
    assert DemoAgent._write_authorized("update the ticket read-only") is False


def test_llm_tool_surface_is_focused_strict_and_discovery_backed():
    discovered = [
        MCPTool(
            server="splunk",
            name="splunk_run_query",
            title="Run query",
            description="Run arbitrary SPL",
            input_schema={"type": "object"},
        ),
        MCPTool(
            server="splunk",
            name="splunk_get_user_list",
            title="List users",
            description="Administrative tool",
            input_schema={"type": "object"},
        ),
        *[
            MCPTool(
                server="tickets",
                name=name,
                title=name,
                description=name,
                input_schema={"type": "object"},
            )
            for name in (
                "list_my_tickets",
                "get_ticket",
                "add_work_note",
                "update_ticket_status",
            )
        ],
    ]

    read_tools = DemoAgent._agent_tools(discovered, allow_writes=False)
    write_tools = DemoAgent._agent_tools(discovered, allow_writes=True)

    assert {tool.agent_name for tool in read_tools} == {
        "tickets__list_my_tickets",
        "tickets__get_ticket",
        "splunk__get_service_health",
        "splunk__compare_service_baseline",
        "splunk__search_logs",
        "splunk__trace_request",
    }
    assert {tool.agent_name for tool in write_tools} == {
        *(tool.agent_name for tool in read_tools),
        "tickets__add_work_note",
        "tickets__update_ticket_status",
    }
    openai_tools = [DemoAgent._openai_tool(tool) for tool in write_tools]
    assert all(tool["strict"] is True for tool in openai_tools)
    assert all(tool["parameters"]["additionalProperties"] is False for tool in openai_tools)
    assert all(
        set(tool["parameters"]["required"]) == set(tool["parameters"]["properties"])
        for tool in openai_tools
    )


async def test_remote_mcp_target_applies_bearer_token_and_tls_policy(monkeypatch):
    captured = {}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            captured["http"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, transport, **kwargs):
            captured["transport"] = transport
            captured["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    def fake_transport(url, *, http_client):
        captured["url"] = url
        captured["http_client"] = http_client
        return object()

    monkeypatch.setattr(mcp_client_module.httpx2, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(mcp_client_module, "Client", FakeClient)
    monkeypatch.setattr(mcp_client_module, "streamable_http_client", fake_transport)

    target = MCPRemoteTarget(
        url="https://mcp.example/mcp",
        token="demo-secret",
        verify="/certs/customer-ca.pem",
    )
    async with MCPBroker._client(target):
        pass

    assert captured["url"] == "https://mcp.example/mcp"
    assert captured["http"]["headers"] == {"Authorization": "Bearer demo-secret"}
    assert captured["http"]["verify"] == "/certs/customer-ca.pem"
    assert captured["http"]["follow_redirects"] is True
    assert captured["client"] == {"raise_exceptions": True}


async def test_llm_mode_uses_saved_endpoint_model_and_responses_api(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))
    base = get_settings()
    settings = replace(
        base,
        agent_mode_preference="openai",
        openai_base_url="https://llm.example/v1",
        openai_api_key="demo-key",
        openai_model="demo-model",
    )
    captured = {}

    class FakeResponses:
        async def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(output=[], output_text="LLM response", id="resp-demo")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = FakeResponses()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class EmptyBroker:
        async def list_tools(self):
            return []

    monkeypatch.setattr(agent_module, "AsyncOpenAI", FakeOpenAI)
    result = await DemoAgent(settings, EmptyBroker()).chat("Summarize the incident")

    assert result.mode == "openai"
    assert result.message == "LLM response"
    assert captured["client"] == {
        "api_key": "demo-key",
        "base_url": "https://llm.example/v1",
        "timeout": 60.0,
        "max_retries": 1,
    }
    assert captured["request"]["model"] == "demo-model"
    assert captured["request"]["input"] == "Summarize the incident"
    assert captured["request"]["tool_choice"] == "auto"
    assert captured["request"]["parallel_tool_calls"] is True
    assert captured["request"]["max_output_tokens"] == 2000


async def test_guided_mode_does_not_use_a_stored_llm_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))
    settings = replace(
        get_settings(),
        agent_mode_preference="guided",
        openai_api_key="configured-but-disabled",
    )
    agent = DemoAgent(settings, object())

    async def guided(message, ticket_id):
        return SimpleNamespace(message=message, mode="guided", ticket_id=ticket_id)

    async def unexpected_llm(*_args):
        raise AssertionError("LLM should not be called in Guided mode")

    monkeypatch.setattr(agent, "_guided_chat", guided)
    monkeypatch.setattr(agent, "_openai_chat", unexpected_llm)

    result = await agent.chat("Stay deterministic", "INC-1042")

    assert result.mode == "guided"
