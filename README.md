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

## Configure a live Splunk environment

The demo starts in **Fixture telemetry** mode and works without Splunk. Complete the following steps
to make the presentation use real MCP calls, real Splunk searches, and real HEC ingestion. The
service-desk tickets and service catalog remain local demo systems.

### 1. Confirm the Splunk prerequisites

You need:

- Splunk Enterprise or an approved Splunk environment you can administer;
- Splunk Web access to install an app and create an HTTP Event Collector token;
- ports `8088` (HEC) and `8089` (management API/MCP) reachable from the demo machine; and
- either an existing Splunk MCP endpoint and bearer token, or a Splunk search token for the bundled
  MCP-to-REST bridge.

If Splunk runs in Docker, publish ports `8000`, `8088`, and `8089` to the host. The demo container
automatically maps configured `localhost` URLs to `host.docker.internal`.

The companion app and the MCP endpoint are separate components. The app creates the deterministic
demo data contract; it does not add `/services/mcp` to Splunk. If the Splunk environment does not
already expose MCP, use the bundled MCP bridge described in step 4.

### 2. Install the companion Splunk app

Download
[`mcp_service_demo-0.3.0.tar.gz`](https://github.com/LeiterConsulting/mcp-service-demo/releases/latest/download/mcp_service_demo-0.3.0.tar.gz)
from the latest release. Then, in Splunk Web:

1. Open **Apps → Manage Apps**.
2. Select **Install app from file**.
3. Upload `mcp_service_demo-0.3.0.tar.gz` and allow an upgrade if an older copy is installed.
4. Restart Splunk if prompted.
5. Confirm that **MCP Service Demo** appears in the Apps menu and that `mcp_demo` appears under
   **Settings → Indexes**.

The app installs:

- index `mcp_demo`;
- source type `mcp:demo:event`;
- app namespace `mcp_service_demo`;
- scenario-selection macros and saved searches; and
- an **MCP Service Demo** dashboard for inspecting the exact evidence used by the agent.

The archive contains no credentials or event data.

### 3. Create the HEC publisher token

HEC is the write path used by **Reset demo** to publish a fresh synthetic incident. It is not the
same credential as the MCP or search token.

1. In Splunk Web, open **Settings → Data Inputs → HTTP Event Collector**.
2. Open **Global Settings**, enable HEC, and note whether SSL is enabled. The normal HEC port is
   `8088`.
3. Select **New Token** and name it `MCP Service Demo`.
4. Use **Automatic** source type selection; each event payload declares `mcp:demo:event`.
5. Set the app context to `mcp_service_demo` when Splunk offers that choice.
6. Add `mcp_demo` to the token's allowed indexes and select it as the default index.
7. Review the settings, create the token, and copy its value before leaving the page.

The HEC URL entered in the demo is normally `https://<splunk-host>:8088`. The demo appends
`/services/collector/event`; entering the full collector URL also works.

### 4. Choose the Splunk read path

Both options still demonstrate MCP. The difference is where the Splunk-specific MCP adapter runs.

| Read path | MCP setup | Direct REST setup |
| --- | --- | --- |
| Existing Splunk MCP endpoint | Enter `https://<splunk-host>:8089/services/mcp` and its MCP bearer token. The endpoint must expose a query tool such as `splunk_run_query`. | Leave the REST token blank; it is not required. |
| Bundled demo MCP bridge | Keep `http://127.0.0.1:8101/mcp`; no MCP bearer token is required. | Enter `https://<splunk-host>:8089`, a search-capable token, and the matching `Bearer` or `Splunk session` token type. |

The MCP or REST search identity needs permission to search `mcp_demo` in the `mcp_service_demo` app
namespace. Keep this identity separate from the HEC token, which only needs permission to write to
`mcp_demo`.

### 5. Enter and test the connection

Open [http://127.0.0.1:8100](http://127.0.0.1:8100), select **Setup → Splunk**, and configure:

1. Under **Source**, choose **Live Splunk**.
2. Under **MCP transport**, enter the endpoint and bearer token for the read path selected above.
3. Under **Direct REST access**, enter values only when using the bundled MCP bridge.
4. Under **Scenario publisher**, enter the HEC URL and HEC token from step 3.
5. Leave the companion-app contract at `mcp_service_demo`, `mcp_demo`, `mcp:demo:event`, and
   `checkout-degradation-v1` unless you deliberately changed the Splunk app.
6. Select **Test MCP endpoint**. Success reports the discovered tool count.
7. Select **Test live paths**. This verifies both the Splunk read path and the HEC listener without
   publishing events. Before the first publication, “Connection works; publish the demo scenario”
   is a successful and expected result.
8. Select **Save connection** before resetting the scenario.

TLS verification should remain enabled for trusted remote certificates. For a private CA, place a
PEM bundle in `certs/` and enter its container path, such as `/app/certs/customer-ca.pem`. Disabling
verification is available for a controlled local lab using a self-signed certificate.

### 6. Publish and verify the scenario

Open **Setup → Demo controls → Reset demo**. In live mode this action:

1. restores the local ticket workflow;
2. creates a unique `demo_run_id`;
3. sends the deterministic event stream through HEC; and
4. waits until that exact run is searchable through the configured MCP endpoint.

When complete, the MCP connections modal reports **Scenario ready**. Open the **MCP Service Demo**
app in Splunk to see the indexed run, then return to the service desk and investigate `INC-1042`.

The reset confirmation reports the event count returned through the configured MCP search identity
and includes **Open this exact run in Splunk**. That link runs the same index-, source type-, scenario-,
and run-scoped search in Splunk Web. If MCP reports events but Splunk Web reports zero, the logged-in
Splunk Web user is either connected to a different Splunk instance or does not have `mcp_demo` in its
searchable-index permissions. Use `index=mcp_demo | stats count` while signed in as an administrator,
then add `mcp_demo` to the presenter's role under **Settings → Roles → Indexes** if needed.

For a command-line verification from the Docker installation, use:

```bash
docker compose exec demo mcp-service-demo test-splunk
docker compose exec demo mcp-service-demo seed-splunk
```

`test-splunk` validates the saved read path. `seed-splunk` republishes the scenario through the
saved HEC connection. The browser reset performs the same coordinated publication while also making
the presentation state visible.

Common first-run failures usually identify one boundary:

- **Reset finishes immediately and Splunk stays empty:** the saved source is still **Fixture
  telemetry**. A successful MCP endpoint test does not switch the evidence source. Choose **Live
  Splunk** under **Setup → Splunk**, then select **Save connection** before resetting.
- **MCP cannot connect:** confirm port `8089` is published and the MCP URL is reachable from Docker.
- **MCP returns unauthorized:** use the MCP bearer token, not the HEC token.
- **HEC reports `host.docker.internal:8088` as unreachable:** Splunk's HEC listener may be enabled
  inside its container without port `8088` being published. Either publish `8088:8088`, or connect
  the Splunk and demo containers to a shared user-defined Docker network and use the Splunk
  container name in the HEC URL. For example:

  ```bash
  docker network create mcp-splunk-demo
  docker network connect mcp-splunk-demo splunk-ubuntu
  docker network connect mcp-splunk-demo mcp-service-demo-demo-1
  ```

  Then configure `https://splunk-ubuntu:8088/services/collector/event`. Replace the example
  container names with those reported by `docker ps`. A manually attached network must be
  reconnected if either container is recreated.
- **HEC rejects the batch:** confirm HEC is enabled and its token can write to `mcp_demo`.
- **Events publish but cannot be found:** grant the MCP/search identity access to `mcp_demo` and the
  `mcp_service_demo` app.
- **Certificate verification fails:** configure the issuing PEM CA bundle, or disable verification
  only for a controlled self-signed lab.

For additional environment-variable configuration and troubleshooting, see
[`docs/SPLUNK_SETUP.md`](docs/SPLUNK_SETUP.md).

## Optional LLM setup

An LLM is optional. Open **Setup → Agent & LLM** to switch between the deterministic Guided agent and an
LLM-assisted agent that selects and sequences focused incident operations backed by the discovered
MCP capabilities. The setup supports an OpenAI or Responses-compatible endpoint, model, encrypted
API key, TLS verification, an optional custom CA bundle, and a connection test. A balanced runtime
profile bounds retries and downstream concurrency
while leaving enough turns and tool calls for the complete ticket workflow. Guided mode remains the
presentation-safe fallback if the model endpoint is unavailable.

For OpenAI cloud, use `https://api.openai.com/v1` as the endpoint. If **Test model** reports a
network or TLS failure, this credential-free check runs from the same container network path:

```bash
docker compose exec demo python -c "import httpx; print(httpx.get('https://api.openai.com/v1/models', timeout=15).status_code)"
```

An HTTP `401` is expected without a key and proves DNS, outbound HTTPS, and certificate validation
are working. A socket, proxy, or certificate exception identifies the machine-level path that needs
attention. The in-app test reports the nested cause and the effective Docker runtime URL. For a
corporate TLS-inspection certificate, place the issuing PEM bundle in `certs/`, keep verification
enabled, and select its `/app/certs/...` path under **Setup → Agent & LLM**. See
[`docs/LLM_SETUP.md`](docs/LLM_SETUP.md) for the macOS and Docker procedure. Disabling verification
is retained as a controlled-demo workaround only.

## What the demo exposes

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

## Manual Docker alternative

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

## Native developer alternative

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
and audience settings—including credentials. This includes the LLM TLS policy. Configured CA
bundles are embedded so they do not depend on a source-machine path. Ticket records and synthetic
scenario data are deliberately not included.

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
- [`docs/LLM_SETUP.md`](docs/LLM_SETUP.md) — model endpoint, Docker TLS, and custom CA setup

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
