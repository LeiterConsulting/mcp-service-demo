# Connect the demo to Splunk

Live mode keeps the scenario deterministic while making the operational path real:

1. the service desk stores real local tickets in SQLite;
2. the loader publishes a fresh synthetic incident to Splunk through HEC;
3. the configured Splunk MCP endpoint runs scoped SPL with `splunk_run_query` (or the bundled local
   MCP server runs the same searches through Splunk's management REST API);
4. the agent reads the ticket, uses its service context to query Splunk, and writes evidence back
   through the ticket MCP server.

Every published scenario has a unique `demo_run_id`. All agent searches first discover the newest
run and then filter on that identifier, so an old rehearsal cannot contaminate the current demo.

## 1. Install the companion app

From the repository root:

```bash
mcp-service-demo package-splunk-app
```

This creates `dist/mcp_service_demo-0.3.0.tar.gz`. In Splunk Web, open **Apps → Manage Apps →
Install app from file**, upload the archive, and restart Splunk if prompted.

The app supplies:

- the `mcp_demo` index and `mcp:demo:event` source type;
- macros that select the active deterministic run;
- saved searches for health, the expected error pattern, and cross-service traces;
- an **MCP Service Demo** dashboard for inspecting exactly what the agent can see.

The archive contains no credentials or event data. Installing apps and creating indexes generally
requires Splunk administrator access. In a managed Splunk Cloud environment, use the app install
and management API process approved for that tenant.

## 2. Create HEC and search credentials

Create an HTTP Event Collector token that is allowed to write to `mcp_demo`. The loader sends
structured events to `/services/collector/event` with `Authorization: Splunk <HEC token>`.

When using Splunk's MCP endpoint, its bearer token is the search identity and direct REST
credentials are not required. If you use the bundled local Splunk MCP server instead, it needs one
of the following identities for the management REST API:

- a bearer/JWT token (`SPLUNK_REST_TOKEN_SCHEME=Bearer`);
- a Splunk session token (`SPLUNK_REST_TOKEN_SCHEME=Splunk`); or
- `SPLUNK_USERNAME` and `SPLUNK_PASSWORD` basic authentication for a local lab.

Use a narrowly scoped demo account and keep its secrets in `.env`, which is ignored by Git.

## 3. Configure live mode

### Browser setup

Start the demo, open **Splunk setup** in the header, and choose **Live Splunk**. The panel separates
the three responsibilities:

- **MCP transport** — Streamable HTTP endpoint, masked bearer token, TLS verification, and an
  optional CA bundle;
- **Direct REST access** — optional management API fallback for the bundled local MCP server;
- **Scenario publisher** — HEC URL, masked HEC token, TLS verification, and an optional CA bundle.

Use **Test MCP endpoint** to prove tool discovery, then **Test live search** before saving. A
successful search test uses either the MCP query tool or the configured REST fallback and reports
whether a deterministic demo run is already searchable. Blank token fields preserve the current secret. Saved secrets are encrypted
locally and are never returned by the settings API. The new profile is picked up without restarting
the demo.

The encrypted profile and its local key live beside `demo.db` in the `data` directory, which is a
named volume in the supplied Docker Compose configuration. Treat that directory as sensitive and
use the settings panel only on a trusted demo host.

### Environment setup

Copy `.env.example` to `.env` and set at least:

```dotenv
SPLUNK_MCP_URL=https://your-splunk-management-host:8089/services/mcp
SPLUNK_MCP_TOKEN=your-remote-mcp-bearer-token

SPLUNK_DATA_MODE=live

# Only required when SPLUNK_MCP_URL points to the bundled local MCP server:
# SPLUNK_REST_URL=https://your-splunk-management-host:8089
# SPLUNK_REST_TOKEN=your-rest-token
# SPLUNK_REST_TOKEN_SCHEME=Bearer

SPLUNK_HEC_URL=https://your-hec-host:8088
SPLUNK_HEC_TOKEN=your-hec-token
```

The defaults expect app `mcp_service_demo`, index `mcp_demo`, source type `mcp:demo:event`, and
scenario `checkout-degradation-v1`. If these names are changed, update both the environment and
the companion app configuration.

Environment variables are defaults. Values saved through **Splunk setup** take precedence for the
MCP endpoint, MCP bearer token, data mode, REST connection, HEC connection, TLS settings, and CA
paths. The CLI uses that same effective profile.

TLS verification is enabled. A CA file can be supplied with `SPLUNK_REST_CA_BUNDLE` and
`SPLUNK_HEC_CA_BUNDLE`. Disabling verification is provided only for a self-signed local lab.

## 4. Verify, seed, and run

```bash
mcp-service-demo test-splunk
mcp-service-demo seed-splunk
mcp-service-demo run
```

`test-splunk` proves MCP search access (or REST fallback authentication) and shows whether an active
run exists. `seed-splunk` resets the local tickets, publishes a new event stream, and waits through
the MCP search connection until the run is searchable.
Once the application is running, **Reset demo** repeats that coordinated reset and publication.

Open [http://127.0.0.1:8100](http://127.0.0.1:8100). The header will say **Splunk live**, and the
briefing will identify a real Splunk endpoint as the telemetry source.

When the demo itself runs in Docker and Splunk runs on the host, use a host-reachable name such as
`host.docker.internal` in the Splunk URLs instead of `127.0.0.1`.

## Troubleshooting

- **Search works but the scenario is not found:** confirm the HEC token can write to `mcp_demo`, the
  source type is `mcp:demo:event`, and the MCP or REST identity can search that index.
- **Certificate verification fails:** install the issuing CA and configure the relevant CA bundle.
- **The reset times out:** increase `SPLUNK_INDEX_WAIT_SECONDS` above its 30-second default.
- **Splunk Cloud endpoints differ:** use the HEC and management API URLs assigned to the tenant;
  they do not always use the local Enterprise ports shown in the examples.

The integration uses Splunk's current v2 export endpoint at
`/services/search/v2/jobs/export` (under the configured app/owner namespace) and does not require
shell access to the Splunk host.
