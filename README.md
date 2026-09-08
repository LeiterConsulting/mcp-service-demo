# MCP Service Demo

A deliberately small demonstration of an AI agent using the Model Context Protocol (MCP) across three familiar enterprise systems:

- a read-only **Splunk MCP server** backed by either a real Splunk endpoint or a local fixture
- a read/write **service desk MCP server** backed by a local ticket store
- a read-only **service catalog MCP server** with ownership, dependencies, escalation, and runbooks
- an **agent host** that discovers and calls those tools
- a browser experience with an agent chat and a ServiceNow-like ticket queue
- a companion **Splunk app and HEC scenario loader** for repeatable live demonstrations

The main story is one complete, visible loop:

> An analyst opens `INC-1042`, clicks **Investigate with MCP**, and watches the agent resolve ownership,
> collect evidence, prove an implicated dependency is healthy, and write a sourced investigation
> note back to the ticket.

The incident is synthetic, but the interfaces and operations are real. MCP discovery and calls,
Splunk MCP searches, HEC publication, database reads, and ticket writes execute during the demo.
Fixture mode remains available when a Splunk instance is not nearby.

## Quick start

The supported demo installation uses Docker Desktop or Docker Engine with Docker Compose. Clone the
repository, then run the installer from its root.

### macOS or Linux

```bash
git clone https://github.com/LeiterConsulting/mcp-service-demo.git
cd mcp-service-demo
chmod +x install.sh
./install.sh
```

### Windows PowerShell

```powershell
git clone https://github.com/LeiterConsulting/mcp-service-demo.git
Set-Location mcp-service-demo
.\install.ps1
```

The installer creates `.env` from the safe example when needed, builds the image, starts all three
MCP servers and the agent host, waits for a healthy application, and prints the web address. Open
[http://127.0.0.1:8100](http://127.0.0.1:8100) unless you selected another port.

Common lifecycle and installation options are matched across both scripts:

| Purpose | macOS/Linux | Windows PowerShell |
| --- | --- | --- |
| Start | `./install.sh --start` | `.\install.ps1 -Start` |
| Stop, preserving settings | `./install.sh --stop` | `.\install.ps1 -Stop` |
| Rebuild and restart | `./install.sh --restart --build` | `.\install.ps1 -Restart -Build` |
| Show status | `./install.sh --status` | `.\install.ps1 -Status` |
| Follow logs | `./install.sh --logs` | `.\install.ps1 -Logs` |
| Use another web port | `./install.sh --web-port 8200` | `.\install.ps1 -WebPort 8200` |
| Show all options | `./install.sh --help` | `.\install.ps1 -Help` |

Port overrides and an optional Compose project name are saved in `.env`, so later lifecycle commands
use the same installation. `--uninstall`/`-Uninstall` removes containers and the locally built image
but deliberately preserves encrypted settings and ticket data. Add `--remove-data`/`-RemoveData` only
when those volumes should also be permanently removed.

An LLM is optional. Open **Setup → Agent & LLM** to switch between the deterministic Guided agent and an
LLM-assisted agent that selects and sequences focused incident operations backed by the discovered
MCP capabilities. The setup supports an OpenAI or Responses-compatible endpoint, model, encrypted
API key, and connection test. A balanced runtime profile bounds retries and downstream concurrency
while leaving enough turns and tool calls for the complete ticket workflow. Guided mode remains the
presentation-safe fallback if the model endpoint is unavailable.

The default `SPLUNK_DATA_MODE=fixture` is the zero-dependency path. To use a real endpoint,
install the companion Splunk app, open **Setup → Splunk** in the demo header, enter the MCP and HEC
connections, and switch to live mode. Direct REST credentials are only needed for the bundled
local Splunk MCP server. The same values can still be
supplied through environment variables. See [`docs/SPLUNK_SETUP.md`](docs/SPLUNK_SETUP.md).

The settings experience mirrors the larger discovery tool's useful connection pattern—MCP
endpoint, masked bearer token, TLS verification, optional CA bundle, and a connection test—using
this demo's language and visual design. The panel separately configures optional direct REST access
and the HEC publisher. Splunk and LLM overrides are encrypted in the persistent
`demo-settings` volume and take effect without a restart.

The connection indicator opens a live inventory of the three MCP servers, their access boundaries,
and their discovered tools. Tool chips explain why each capability matters in the incident story.
During an agent run, the protocol timeline streams tool selection and completion as it happens.
The service desk also exposes catalog context, Splunk evidence links, and resettable assignment,
escalation, and status controls so the full cross-system workflow is visible without leaving the ticket.

**Setup → Demo controls → Audience** switches the complete presentation lens between Executive
(default), Engineering, Security, and Finance. Each lens changes the briefing, architecture
annotations, value proof, story, highlighted tools, agent prompts and response guidance, protocol
detail, ticket framing, and outcome labels. The underlying incident, MCP permissions, and real
operations stay unchanged, making it possible to tailor the conversation without presenting a
different or less truthful demo. Audience selection is saved with connection settings and survives
**Reset demo**.

### Manual Docker alternative

```bash
docker compose up --build
```

Then open [http://127.0.0.1:8100](http://127.0.0.1:8100). Scenario data and encrypted connection
settings are kept in separate named volumes.

Docker Compose honors the four port values in `.env`. When an external Splunk, HEC, or compatible
LLM endpoint is entered with `localhost`, `127.0.0.1`, or another loopback address, the container
automatically reaches it through `host.docker.internal`; the saved URL stays unchanged and portable.
The bundled MCP endpoint remains inside the demo container. For a private CA, place the certificate
in `certs/` and use a container path such as `/app/certs/customer-ca.pem` in Setup. Certificate files
in that directory are ignored by Git.

### Native developer alternative

Python 3.11 or newer is required for a native run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
mcp-service-demo run
```

The Docker installer is recommended for a presentation machine because it starts and health-checks
the entire service set with one command. The native path is useful for development and testing.

## Move a configured demo to another machine

Open **Setup → Demo controls → Move this demo profile** to create a portable `.mcpdemo` package.
The export contains the effective Splunk MCP, REST, HEC, TLS, companion-app contract, LLM, tuning,
and audience settings—including credentials. Configured CA bundles are embedded so they do not
depend on a source-machine path. Ticket records and synthetic scenario data are deliberately not
included.

The package is encrypted with a passphrase of at least 12 characters. The passphrase is neither
stored in the package nor recoverable, so transfer it separately. On the target machine, choose the
package, enter the passphrase, review the non-secret summary, and confirm the import. The current
connection profile is replaced and becomes active without a restart. Treat the package as a
sensitive credential backup even though its contents are encrypted.

## Demo services

| Service | Address | Purpose |
| --- | --- | --- |
| Demo web app | `http://127.0.0.1:8100` | Briefing, agent chat, and ticket UI |
| Splunk MCP | `http://127.0.0.1:8101/mcp` | Read-only telemetry tools |
| Ticket MCP | `http://127.0.0.1:8102/mcp` | Ticket reads and controlled updates |
| Service Catalog MCP | `http://127.0.0.1:8103/mcp` | Read-only ownership, dependency, and runbook context |

The `run` command starts all four processes and seeds the scenario. Press `Ctrl+C` to stop them.

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
mcp-service-demo catalog-mcp  # run only the service catalog MCP server
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
The service catalog is synthetic and deliberately small, but its discovery and tool calls are real.
