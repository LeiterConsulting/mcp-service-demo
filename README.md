# MCP Service Demo

A deliberately small demonstration of an AI agent using the Model Context Protocol (MCP) across two familiar enterprise systems:

- a read-only **Splunk MCP server** backed by either a real Splunk endpoint or a local fixture
- a read/write **service desk MCP server** backed by a local ticket store
- an **agent host** that discovers and calls those tools
- a browser experience with an agent chat and a ServiceNow-like ticket queue
- a companion **Splunk app and HEC scenario loader** for repeatable live demonstrations

The main story is one complete, visible loop:

> An analyst opens `INC-1042`, clicks **Ask Splunk**, watches the agent collect evidence through MCP, and sees a sourced investigation note written back to the ticket.

The incident is synthetic, but the interfaces and operations are real. MCP discovery and calls,
Splunk MCP searches, HEC publication, database reads, and ticket writes execute during the demo.
Fixture mode remains available when a Splunk instance is not nearby.

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

An LLM is optional. Open **LLM setup** to switch between the deterministic Guided agent and an
LLM-assisted agent that selects and sequences the same discovered MCP tools. The setup supports an
OpenAI or Responses-compatible endpoint, model, encrypted API key, and connection test. Guided
mode remains the presentation-safe fallback if the model endpoint is unavailable.

The default `SPLUNK_DATA_MODE=fixture` is the zero-dependency path. To use a real endpoint,
install the companion Splunk app, open **Splunk setup** in the demo header, enter the MCP and HEC
connections, and switch to live mode. Direct REST credentials are only needed for the bundled
local Splunk MCP server. The same values can still be
supplied through environment variables. See [`docs/SPLUNK_SETUP.md`](docs/SPLUNK_SETUP.md).

The settings experience mirrors the larger discovery tool's useful connection pattern—MCP
endpoint, masked bearer token, TLS verification, optional CA bundle, and a connection test—using
this demo's language and visual design. The panel separately configures optional direct REST access
and the HEC publisher. Splunk and LLM overrides are encrypted in the persistent
`demo-settings` volume and take effect without a restart.

### Docker alternative

```bash
docker compose up --build
```

Then open [http://127.0.0.1:8100](http://127.0.0.1:8100). Scenario data and encrypted connection
settings are kept in separate named volumes.

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
- [`docs/SPLUNK_SETUP.md`](docs/SPLUNK_SETUP.md) — companion app, HEC, and live REST setup

## Useful commands

```bash
mcp-service-demo reset        # restore the original ticket and telemetry
mcp-service-demo test-splunk  # verify the configured telemetry source
mcp-service-demo seed-splunk  # publish a fresh scenario through HEC (live mode)
mcp-service-demo package-splunk-app # create the installable Splunk app archive
mcp-service-demo splunk-mcp   # run only the Splunk MCP server
mcp-service-demo ticket-mcp   # run only the ticket MCP server
mcp-service-demo web          # run only the browser/API host
pytest                        # run the test suite
```

CLI commands resolve the same active profile saved through the browser, with environment variables
serving as defaults.

## Demo boundaries

This project is intentionally not a discovery platform, RAG system, workflow engine, or
ServiceNow clone. It optimizes for a reliable 8–10 minute customer demonstration and a codebase
that can be understood in one sitting. The local service desk is a facsimile, but its queue,
ticket reads, notes, and status changes are persistent operations made through its MCP server.
