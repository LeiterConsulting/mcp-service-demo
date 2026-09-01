# Architecture

The agent always talks to two independent MCP servers. Only the telemetry adapter changes between
fixture and live modes.

```text
Browser
   │ REST
   ▼
Agent host :8100
   ├── Streamable HTTP MCP ──► Splunk Operations :8101
   │                              ├── fixture ──► local event rows
   │                              └── live ─────► Splunk REST search API
   │                                                   ▲
   │                                            scenario data
   │                                                   │ HEC
   └── Streamable HTTP MCP ──► Northstar Desk :8102    │
                                      │                 │
                                      ▼                 │
                              ticket SQLite store ──► scenario loader
```

## Why two MCP servers

The story is more useful when MCP is visibly a protocol between an agent host and independent
systems. Splunk tools are read-only. Ticket tools include reads and explicitly gated writes. The
agent joins context at runtime: it reads the service named by a ticket, investigates that service
in Splunk, then sends its sourced result back to the ticket system.

## Deterministic live data

The scenario loader is part of this repository, not part of the agent. It resets the ticket store,
generates the known checkout degradation, and publishes the event stream through HEC. Every
publication receives a unique `demo_run_id`.

The Splunk adapter first finds the newest run for `checkout-degradation-v1`. Every subsequent SPL
query is constrained by index, source type, scenario, and run ID. This keeps health metrics,
errors, deployments, and traces repeatable even when the same Splunk instance has hosted many
rehearsals.

## Runtime connection settings

Environment variables establish the default Splunk profile. The **Splunk setup** panel can save an
encrypted override containing the data mode, management API connection, HEC connection, TLS
verification, and optional CA bundle paths. Tokens are masked in API responses, and blank secret
fields preserve the existing value.

The web host and Splunk MCP server are separate processes, so both resolve the effective profile
from the same encrypted file in the `data` directory. The MCP server does this when a tool is
called; a saved profile therefore takes effect without restarting the processes.

## Real versus synthetic

Real during a live-mode demo:

- MCP discovery, Streamable HTTP transport, typed arguments, and tool results;
- Splunk HEC ingestion and REST searches using deterministic SPL;
- SQLite ticket reads, work-note writes, and status changes through the ticket MCP server;
- optional model-driven tool selection.

Synthetic by design:

- the company, users, services, tickets, and incident event content;
- the Northstar service-desk visual design;
- the `splunk://` evidence references, which are portable references rather than clickable Splunk
  deep links.

## Integration seams

- `splunk_backend.py` implements fixture and REST-backed telemetry behind one interface.
- `scenario.py` handles HEC publication and coordinated resets.
- `servers/tickets.py` is the seam for a future ServiceNow, Jira Service Management, Zammad, or
  other ticket adapter.

The agent workflow and browser do not need to change when another implementation is placed behind
either MCP server.
