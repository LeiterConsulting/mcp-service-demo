from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ..config import get_settings
from ..storage import DemoStore

splunk_mcp = MCPServer(
    name="splunk-demo",
    title="Splunk Operations",
    description="Read-only access to service health, logs, baselines, and traces.",
    instructions=(
        "Use these read-only tools to investigate service behavior. Start with service health, "
        "then narrow with log search or a trace. Cite the evidence_ref values in conclusions."
    ),
    version="0.1.0",
)


def _store() -> DemoStore:
    store = DemoStore(get_settings().database_path)
    store.ensure_seeded()
    return store


@splunk_mcp.tool(
    title="List monitored services",
    description="List the service names available in this Splunk demo dataset.",
)
def list_services() -> dict[str, list[str]]:
    """List services with telemetry available for investigation."""
    return {"services": _store().list_services()}


@splunk_mcp.tool(
    title="Get service health",
    description=(
        "Calculate request volume, error rate, latency, trend buckets, baseline comparison, "
        "and recent deployments for one service."
    ),
)
def get_service_health(service: str, minutes: int = 30) -> dict[str, Any]:
    """Get calculated health signals for a service over a recent time window."""
    return _store().get_service_health(service, minutes)


@splunk_mcp.tool(
    title="Search service logs",
    description=(
        "Search recent events for a service using plain keywords such as 'ERROR', "
        "'connection pool', or '503'. Returns matching events and common patterns."
    ),
)
def search_logs(
    service: str,
    keywords: str = "",
    minutes: int = 30,
    limit: int = 20,
) -> dict[str, Any]:
    """Search recent log events and identify repeated patterns."""
    return _store().search_logs(service, keywords, minutes, limit)


@splunk_mcp.tool(
    title="Compare service baseline",
    description="Compare a service's current error rate and latency to the preceding window.",
)
def compare_service_baseline(service: str, minutes: int = 30) -> dict[str, Any]:
    """Compare current service metrics with the immediately preceding time window."""
    return _store().compare_service_baseline(service, minutes)


@splunk_mcp.tool(
    title="Trace a request",
    description="Retrieve the cross-service event sequence for a known trace identifier.",
)
def trace_request(trace_id: str) -> dict[str, Any]:
    """Follow a request across services using its trace identifier."""
    return _store().trace_request(trace_id)


def run_splunk_server() -> None:
    settings = get_settings()
    _store()
    splunk_mcp.run(
        transport="streamable-http",
        host=settings.splunk_mcp_host,
        port=settings.splunk_mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
