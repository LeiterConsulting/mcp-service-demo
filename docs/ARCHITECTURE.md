# Architecture

The agent always talks to two independent MCP servers. Only the telemetry adapter changes between
fixture and live modes.

```text
Browser
   │ REST
   ▼
Agent host :8100
   ├── Guided router or Responses-compatible LLM
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

Environment variables establish the default connection profile. The **Splunk setup** panel can save an
encrypted override containing the agent's Splunk MCP endpoint and bearer token, the data mode,
management API connection, HEC connection, TLS verification, and optional CA bundle paths. Tokens
are masked in API responses, and blank secret fields preserve the existing value.

The separate **LLM setup** panel selects Guided or LLM-assisted mode and stores a
Responses-compatible endpoint, model, and encrypted API key. In LLM-assisted mode the model
interprets intent and selects tools; MCP servers still own the evidence and action boundaries.
Both chat and **Ask Splunk** resolve this choice at request time, so switching modes does not require
a restart. A failed model call falls back to the guided workflow for demo continuity.

The agent resolves the MCP transport profile whenever it discovers or invokes a tool. The web host
and local Splunk MCP server also resolve their effective platform profile from the same encrypted
file. Docker Compose stores that file and its encryption key in the dedicated `demo-settings`
volume, separate from resettable scenario data in `demo-data`. Existing profiles from the older
combined layout are copied into the settings volume automatically. A saved profile therefore takes
effect without restarting the processes and survives **Reset demo**.

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
