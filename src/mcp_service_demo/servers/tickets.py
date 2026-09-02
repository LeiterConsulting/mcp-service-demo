from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from ..config import get_settings
from ..storage import DemoStore

ticket_mcp = MCPServer(
    name="northstar-service-desk",
    title="Northstar Service Desk",
    description="Ticket queue access and controlled incident updates.",
    instructions=(
        "Read ticket context before investigating. Add a work note only when the user or an "
        "authorized workflow explicitly requests a ticket update. Include evidence references."
    ),
    version="0.1.0",
)


def _store() -> DemoStore:
    store = DemoStore(get_settings().database_path)
    store.ensure_seeded()
    return store


@ticket_mcp.tool(
    title="List assigned tickets",
    description="List tickets assigned to a service desk analyst, ordered by priority.",
)
def list_my_tickets(assignee: str = "Maya Chen") -> dict[str, Any]:
    """List the current ticket queue for an analyst."""
    return {"assignee": assignee, "tickets": _store().list_tickets(assignee)}


@ticket_mcp.tool(
    title="Get ticket",
    description="Read a ticket's fields and activity history using an ID such as INC-1042.",
)
def get_ticket(ticket_id: str) -> dict[str, Any]:
    """Get the complete context and notes for a service desk ticket."""
    ticket = _store().get_ticket(ticket_id)
    if ticket is None:
        raise ValueError(f"Ticket {ticket_id!r} was not found")
    return ticket


@ticket_mcp.tool(
    title="Add investigation work note",
    description=(
        "Write an internal investigation note to a ticket. This changes ticket state and must "
        "only be used after explicit authorization."
    ),
)
def add_work_note(
    ticket_id: str,
    body: str,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Add a sourced internal work note and move the ticket to Investigating."""
    note = _store().add_work_note(ticket_id, body, evidence_refs)
    return {"updated": True, "ticket_id": ticket_id.upper(), "note": note}


@ticket_mcp.tool(
    title="Update ticket status",
    description=(
        "Set a ticket to New, Investigating, Monitoring, or Resolved. This changes ticket state "
        "and requires explicit authorization."
    ),
)
def update_ticket_status(ticket_id: str, status: str) -> dict[str, Any]:
    """Update the workflow status of a service desk ticket."""
    return {"updated": True, "ticket": _store().update_ticket_status(ticket_id, status)}


@ticket_mcp.tool(
    title="Assign ticket",
    description="Assign or reassign a ticket to a named service desk analyst.",
)
def assign_ticket(ticket_id: str, assignee: str) -> dict[str, Any]:
    """Change the analyst responsible for a ticket and record the activity."""
    return {"updated": True, "ticket": _store().assign_ticket(ticket_id, assignee)}


@ticket_mcp.tool(
    title="Escalate ticket",
    description=(
        "Escalate a ticket to an assignment group with a recorded reason and move it to "
        "Investigating."
    ),
)
def escalate_ticket(ticket_id: str, assignment_group: str, reason: str) -> dict[str, Any]:
    """Route a ticket to an escalation group and preserve the reason as activity."""
    return {
        "updated": True,
        "ticket": _store().escalate_ticket(ticket_id, assignment_group, reason),
    }


def run_ticket_server() -> None:
    settings = get_settings()
    _store()
    ticket_mcp.run(
        transport="streamable-http",
        host=settings.ticket_mcp_host,
        port=settings.ticket_mcp_port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )
