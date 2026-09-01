from __future__ import annotations

import mcp_service_demo.mcp_client as mcp_client_module
from mcp_service_demo.agent import DemoAgent
from mcp_service_demo.config import get_settings
from mcp_service_demo.mcp_client import MCPBroker, MCPRemoteTarget
from mcp_service_demo.servers.splunk import splunk_mcp
from mcp_service_demo.servers.tickets import ticket_mcp
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


def test_chat_write_tools_require_explicit_authorization():
    assert DemoAgent._write_authorized("investigate inc-1042") is False
    assert DemoAgent._write_authorized("investigate inc-1042 and update the ticket") is True


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
