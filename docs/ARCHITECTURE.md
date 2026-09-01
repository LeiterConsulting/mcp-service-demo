# Architecture

The demo uses three local processes and one shared SQLite scenario store.

```text
Browser
   │ REST
   ▼
Agent host :8100
   ├── Streamable HTTP MCP ──► Splunk Operations :8101 ──┐
   └── Streamable HTTP MCP ──► Northstar Desk :8102 ─────┤
                                                         ▼
                                                synthetic demo.db
```

## Why two MCP servers

The story is more useful when MCP is visibly a protocol between an agent host and independent systems. Splunk tools are read-only. Ticket tools include reads and explicitly gated writes. This resembles an enterprise deployment without requiring ServiceNow or a live Splunk instance for every presentation.

## Real versus synthetic

Real during the demo:

- MCP tool discovery
- Streamable HTTP transport
- typed tool inputs
- tool invocation and structured return values
- metrics calculated from event rows
- ticket database writes and status changes
- optional model-driven tool selection

Synthetic by design:

- the company, users, services, and tickets
- the event dataset
- the `splunk://` evidence links

## Replacement seams

The two server modules are the intended integration seams:

- `servers/splunk.py`: replace `DemoStore` calls with the Splunk SDK or REST API.
- `servers/tickets.py`: replace `DemoStore` calls with ServiceNow, Jira Service Management, Zammad, or another ticket API.

The agent host and browser workflow do not need to change when those adapters are replaced.

