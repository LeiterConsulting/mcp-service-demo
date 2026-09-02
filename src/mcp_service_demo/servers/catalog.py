from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ..config import get_settings

catalog_mcp = MCPServer(
    name="northstar-service-catalog",
    title="Northstar Service Catalog",
    description="Authoritative service ownership, dependency, criticality, and runbook context.",
    instructions=(
        "Use service context to identify the accountable team and known dependencies before "
        "assigning fault. Treat ownership and runbook data as authoritative but verify health in "
        "Splunk before concluding that a dependency is responsible."
    ),
    version="0.1.0",
)


_SERVICES: dict[str, dict[str, Any]] = {
    "checkout-api": {
        "service": "checkout-api",
        "display_name": "Checkout API",
        "business_service": "Online ordering",
        "criticality": "Tier 1 · revenue critical",
        "owner_team": "Digital Commerce",
        "on_call": "Commerce Platform",
        "support_channel": "#commerce-incident",
        "dependencies": [
            {
                "service": "inventory-api",
                "role": "Inventory reservation",
                "signals": ["inventory", "reservation", "stock"],
            },
            {
                "service": "payment-api",
                "role": "Payment authorization",
                "signals": ["payment", "authorization", "card"],
            },
        ],
        "runbook": {
            "title": "Checkout latency and 5xx response",
            "reference": "runbook://commerce/checkout-degradation",
            "first_actions": [
                "Compare current error rate and latency with the preceding window.",
                "Trace a failed checkout across inventory and payment dependencies.",
                "Check client-pool saturation before escalating a dependency team.",
            ],
        },
    },
    "inventory-api": {
        "service": "inventory-api",
        "display_name": "Inventory API",
        "business_service": "Inventory availability",
        "criticality": "Tier 1 · order path",
        "owner_team": "Supply Platform",
        "on_call": "Inventory Services",
        "support_channel": "#inventory-incident",
        "dependencies": [],
        "runbook": {
            "title": "Inventory availability degradation",
            "reference": "runbook://supply/inventory-degradation",
            "first_actions": ["Verify request volume, latency, and database connection health."],
        },
    },
    "payment-api": {
        "service": "payment-api",
        "display_name": "Payment API",
        "business_service": "Payment authorization",
        "criticality": "Tier 1 · revenue critical",
        "owner_team": "Payments Platform",
        "on_call": "Payment Services",
        "support_channel": "#payments-incident",
        "dependencies": [],
        "runbook": {
            "title": "Payment authorization degradation",
            "reference": "runbook://payments/authorization-degradation",
            "first_actions": ["Verify processor responses before retrying failed authorizations."],
        },
    },
}


@catalog_mcp.tool(
    title="Get service context",
    description=(
        "Return authoritative ownership, business criticality, dependencies, escalation channel, "
        "and the first-response runbook for a service."
    ),
)
def get_service_context(service: str) -> dict[str, Any]:
    """Read one service record from the demo service catalog."""
    normalized = service.strip().lower()
    context = _SERVICES.get(normalized)
    if context is None:
        raise ValueError(f"Service {service!r} was not found in the service catalog")
    return {
        **context,
        "source": "Northstar Service Catalog",
        "evidence_ref": f"catalog://services/{normalized}",
    }


def run_catalog_server() -> None:
    settings = get_settings()
    catalog_mcp.run(
        transport="streamable-http",
        host=settings.catalog_mcp_host,
        port=settings.catalog_mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
