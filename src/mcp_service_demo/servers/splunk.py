from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ..config import get_settings
from ..splunk_backend import create_splunk_backend

splunk_mcp = MCPServer(
    name="splunk-demo",
    title="Splunk Operations",
    description="Read-only access to service health, logs, baselines, and traces.",
    instructions=(
        "Use these read-only tools to investigate service behavior. Start with service health, "
        "then narrow with log search or a trace. Cite the evidence_ref values in conclusions."
    ),
    version="0.3.0",
)


def _backend():
    return create_splunk_backend(get_settings())


@splunk_mcp.tool(
    title="Check Splunk data source",
    description=(
        "Confirm whether the MCP server is using fixture data or a real Splunk endpoint, "
        "and report the active seeded demo run."
    ),
)
def get_splunk_status() -> dict[str, Any]:
    """Check connectivity and identify the active telemetry source."""
    return _backend().status()


@splunk_mcp.tool(
    title="List monitored services",
    description="List the service names available in this Splunk demo dataset.",
)
def list_services() -> dict[str, Any]:
    """List services with telemetry available for investigation."""
    return _backend().list_services()


@splunk_mcp.tool(
    title="Get service health",
    description=(
        "Calculate request volume, error rate, latency, trend buckets, baseline comparison, "
        "and recent deployments for one service."
    ),
)
def get_service_health(service: str, minutes: int = 30) -> dict[str, Any]:
    """Get calculated health signals for a service over a recent time window."""
    return _backend().get_service_health(service, minutes)


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
    return _backend().search_logs(service, keywords, minutes, limit)


@splunk_mcp.tool(
    title="Compare service baseline",
    description="Compare a service's current error rate and latency to the preceding window.",
)
def compare_service_baseline(service: str, minutes: int = 30) -> dict[str, Any]:
    """Compare current service metrics with the immediately preceding time window."""
    return _backend().compare_service_baseline(service, minutes)


@splunk_mcp.tool(
    title="Trace a request",
    description="Retrieve the cross-service event sequence for a known trace identifier.",
)
def trace_request(trace_id: str) -> dict[str, Any]:
    """Follow a request across services using its trace identifier."""
    return _backend().trace_request(trace_id)


def run_splunk_server() -> None:
    settings = get_settings()
    splunk_mcp.run(
        transport="streamable-http",
        host=settings.splunk_mcp_host,
        port=settings.splunk_mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
