# MCP Service Demo

A deliberately small demonstration of an AI agent using the Model Context Protocol (MCP) across two familiar enterprise systems:

- a read-only **Splunk MCP server** backed by realistic synthetic telemetry
- a read/write **service desk MCP server** backed by a local ticket store
- an **agent host** that discovers and calls those tools
- a browser experience with an agent chat and a ServiceNow-like ticket queue

The main story is one complete, visible loop:

> An analyst opens `INC-1042`, clicks **Ask Splunk**, watches the agent collect evidence through MCP, and sees a sourced investigation note written back to the ticket.

Everything is local and synthetic, but the interfaces and operations are real. MCP tool discovery, tool calls, database reads, and ticket writes all execute during the demo.

## Quick start

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
mcp-service-demo run
```

Open [http://127.0.0.1:8100](http://127.0.0.1:8100).

An OpenAI API key is optional. Without one, the app uses a deterministic guided agent that still discovers and invokes the live MCP tools. With `OPENAI_API_KEY` configured, free-form chat uses an OpenAI model to select and sequence the same tools.

### Docker alternative

```bash
docker compose up --build
```

Then open [http://127.0.0.1:8100](http://127.0.0.1:8100). The scenario database is kept in a named volume.

## Demo services

| Service | Address | Purpose |
| --- | --- | --- |
| Demo web app | `http://127.0.0.1:8100` | Briefing, agent chat, and ticket UI |
| Splunk MCP | `http://127.0.0.1:8101/mcp` | Read-only telemetry tools |
| Ticket MCP | `http://127.0.0.1:8102/mcp` | Ticket reads and controlled updates |

The `run` command starts all three services and seeds the scenario. Press `Ctrl+C` to stop them.

## Presenter resources

- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — an 8–10 minute customer narrative
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system boundaries and replacement seams

## Useful commands

```bash
mcp-service-demo reset        # restore the original ticket and telemetry
mcp-service-demo splunk-mcp   # run only the Splunk MCP server
mcp-service-demo ticket-mcp   # run only the ticket MCP server
mcp-service-demo web          # run only the browser/API host
pytest                        # run the test suite
```

## Demo boundaries

This project is intentionally not a discovery platform, RAG system, workflow engine, or ServiceNow clone. The first release optimizes for a reliable 8–10 minute customer demonstration and a codebase that can be understood in one sitting.
