# Architecture

The agent coordinates three independent MCP servers. Only the telemetry adapter changes between
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
   ├── Streamable HTTP MCP ──► Northstar Desk :8102    │
   │                                  │                 │
   │                                  ▼                 │
   │                          ticket SQLite store ──► scenario loader
   └── Streamable HTTP MCP ──► Service Catalog :8103
                                      │
                                      └── owners · dependencies · runbooks
```

## Why three MCP servers

The story is more useful when MCP is visibly a protocol between an agent host and independent
systems. Splunk tools are read-only. Catalog tools provide authoritative operational context.
Ticket tools include reads and explicitly gated writes. The agent joins context at runtime: it
reads the service named by a ticket, resolves its owner and dependencies, investigates it in
Splunk, verifies the health of an implicated dependency, then sends its sourced result back to the
ticket system.

That extra verification demonstrates **time to innocence**. A trace may cross `inventory-api`, but
healthy service-level telemetry prevents a premature escalation to the inventory team and narrows
the likely fault to the checkout client's connection pool.

The browser makes each system boundary inspectable. The header connection modal shows endpoint,
health, permissions, and discovered tools. The service-desk view renders the current catalog record
beside the ticket and deep-links portable `splunk://` evidence references into the configured
Splunk Web search experience. Ticket assignment and escalation controls call the ticket MCP server,
record activity, and remain inside the resettable demo boundary.

Agent endpoints also offer newline-delimited streaming responses. A workflow-start event is emitted
immediately, followed by running and completed MCP tool events carrying stable event IDs. The final
result retains the same shape as the non-streaming API, so the UI can show honest protocol progress
without changing the agent's evidence or authorization rules.

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
interprets intent and selects a focused set of strict incident operations. Those operations are
enabled only when their backing MCP capability is discovered. With Splunk's generic
`splunk_run_query` tool, the adapter generates deterministic, scenario-scoped SPL and returns the
same structured health, baseline, error, and trace results as the bundled tools. MCP servers still
own the evidence and action boundaries.
Both chat and **Ask Splunk** resolve this choice at request time, so switching modes does not require
a restart. A failed model call falls back to the guided workflow for demo continuity.

The default **Balanced** profile allows eight model turns and twelve tool calls, runs at most three
independent reads concurrently, limits each model request to 60 seconds with one retry, and caps
model output at 2,000 tokens. Individual tool failures are returned to the model as evidence rather
than restarting the entire workflow. These values can be changed with the `OPENAI_*` environment
variables documented in `.env.example` without adding presenter-facing complexity.

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
- service ownership, dependency, and runbook reads through the catalog MCP server;
- optional model-driven tool selection.

Synthetic by design:

- the company, users, services, tickets, and incident event content;
- the Northstar service-desk visual design;
- the Northstar service catalog records;
- the `splunk://` evidence references, which are portable references rather than clickable Splunk
  deep links.

## Integration seams

- `splunk_backend.py` implements fixture and REST-backed telemetry behind one interface.
- `scenario.py` handles HEC publication and coordinated resets.
- `servers/tickets.py` is the seam for a future ServiceNow, Jira Service Management, Zammad, or
  other ticket adapter.
- `servers/catalog.py` is the seam for a future CMDB, service catalog, or ownership registry.

The agent workflow and browser do not need to change when another implementation is placed behind
any MCP server.
