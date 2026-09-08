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

Download the packaged app from the
[`latest release`](https://github.com/LeiterConsulting/mcp-service-demo/releases/latest), or
build it from a native development environment at the repository root:

```bash
mcp-service-demo package-splunk-app
```

This creates `dist/mcp_service_demo-0.3.0.tar.gz`. In Splunk Web, open **Apps → Manage Apps →
Install app from file**, upload the archive, and restart Splunk if prompted.

Confirm that **MCP Service Demo** appears in the Apps menu and that `mcp_demo` appears under
**Settings → Indexes**. The companion app provides the demo data contract and dashboard; it does
not create a Splunk MCP endpoint.

The app supplies:

- the `mcp_demo` index and `mcp:demo:event` source type;
- macros that select the active deterministic run;
- saved searches for health, the expected error pattern, and cross-service traces;
- an **MCP Service Demo** dashboard for inspecting exactly what the agent can see.

The archive contains no credentials or event data. Installing apps and creating indexes generally
requires Splunk administrator access. In a managed Splunk Cloud environment, use the app install
and management API process approved for that tenant.

## 2. Create HEC and search credentials

In Splunk Web, open **Settings → Data Inputs → HTTP Event Collector**. Enable HEC under **Global
Settings**, then create a token named `MCP Service Demo` with:

- source type selection set to **Automatic** because each payload declares `mcp:demo:event`;
- app context `mcp_service_demo` when that option is available; and
- `mcp_demo` selected as an allowed and default index.

Copy the token after creating it. The loader sends structured events to
`/services/collector/event` with `Authorization: Splunk <HEC token>`. HEC is a separate write path;
do not reuse the HEC token as the MCP bearer or REST search token.

When using Splunk's MCP endpoint, its bearer token is the search identity and direct REST
credentials are not required. If you use the bundled local Splunk MCP server instead, it needs one
of the following identities for the management REST API:

- a bearer/JWT token (`SPLUNK_REST_TOKEN_SCHEME=Bearer`);
- a Splunk session token (`SPLUNK_REST_TOKEN_SCHEME=Splunk`); or
- `SPLUNK_USERNAME` and `SPLUNK_PASSWORD` basic authentication for a local lab.

Use a narrowly scoped demo account and keep its secrets in `.env`, which is ignored by Git.

There are two supported Splunk read paths:

| Read path | MCP connection | Additional credential |
| --- | --- | --- |
| Existing Splunk MCP | `https://<splunk-host>:8089/services/mcp` plus its bearer token | No direct REST credential required |
| Bundled demo MCP bridge | `http://127.0.0.1:8101/mcp` with no token | Splunk REST URL and a search-capable REST token |

Both paths are MCP interactions from the agent's perspective. The bundled bridge translates its
scoped MCP tools into management REST searches when Splunk does not provide an MCP endpoint.

## 3. Configure live mode

### Browser setup

Start the demo, open **Setup → Splunk** in the header, and choose **Live Splunk**. The panel separates
the three responsibilities:

- **MCP transport** — Streamable HTTP endpoint, masked bearer token, TLS verification, and an
  optional CA bundle;
- **Direct REST access** — optional management API fallback for the bundled local MCP server;
- **Scenario publisher** — HEC URL, masked HEC token, TLS verification, and an optional CA bundle.

Use **Test MCP endpoint** to prove tool discovery, then **Test live paths** before saving. The live
test checks both the configured search path and the HEC listener without publishing events, then
reports whether a deterministic demo run is already searchable. Before the first seed, a message
that the connection works and the scenario still needs to be published is expected. Select **Save
connection** before using **Setup → Demo controls → Reset demo**. Blank token fields preserve the
current secret. Saved secrets are encrypted locally and are never returned by the settings API. The
new profile is picked up without restarting the demo.

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

Environment variables are defaults. Values saved through **Setup → Splunk** take precedence for the
MCP endpoint, MCP bearer token, data mode, REST connection, HEC connection, TLS settings, and CA
paths. The CLI uses that same effective profile.

TLS verification is enabled. A CA file can be supplied with `SPLUNK_REST_CA_BUNDLE` and
`SPLUNK_HEC_CA_BUNDLE`. Disabling verification is provided only for a self-signed local lab.
For Docker, place private CA files in the repository's ignored `certs/` directory (or set
`DEMO_CERTS_PATH` to another directory) and configure the in-container path, for example
`/app/certs/customer-ca.pem`. The same mount supports `SPLUNK_MCP_CA_BUNDLE`.

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
It restores only scenario and ticket state; the saved Splunk profile, credentials, and TLS choices
are preserved. Docker Compose keeps that encrypted profile in the separate `demo-settings` volume.

Open [http://127.0.0.1:8100](http://127.0.0.1:8100). The header will say **Splunk live**, and the
briefing will identify a real Splunk endpoint as the telemetry source.

When the demo itself runs in Docker and Splunk is published on the host, URLs using `localhost`,
`127.0.0.1`, `::1`, or `0.0.0.0` are automatically routed through `host.docker.internal`. This applies
to external MCP, REST, HEC, and compatible LLM endpoints; it does not redirect the bundled Splunk MCP
server running inside the demo container. The configured URL remains unchanged, so an exported profile
stays portable between native and Docker installations. The supplied Compose file maps the host alias
on Docker Desktop and native Linux.

## Move the connection profile

After validating Splunk and the LLM, open **Setup → Demo controls → Move this demo profile** and
download an encrypted `.mcpdemo` package. It includes the effective MCP, REST, HEC, TLS, companion
app, LLM, tuning, and audience settings. Any configured CA bundle is embedded and installed into
the target's persistent settings volume during import. Scenario events and service-desk tickets are
not part of the package.

Use a unique passphrase of at least 12 characters and send it separately from the package. On the
target demo host, start the application, choose the package and passphrase, review the non-secret
summary, and confirm replacement of the existing connection profile. Imported settings take effect
without restarting. A wrong passphrase, modified package, unsupported schema, or missing source CA
file is rejected before the active profile is changed.

## Troubleshooting

- **HEC is enabled but `host.docker.internal:8088` is unreachable:** enabling HEC in Splunk does
  not publish the port from a Splunk container. Publish `8088:8088` when creating that container.
  If recreating Splunk would risk an existing lab, connect the current containers directly instead:

  ```bash
  docker network create mcp-splunk-demo
  docker network connect mcp-splunk-demo splunk-ubuntu
  docker network connect mcp-splunk-demo mcp-service-demo-demo-1
  ```

  Use `https://splunk-ubuntu:8088/services/collector/event` as the HEC URL and leave TLS verification
  disabled only for the self-signed lab certificate. Substitute the names shown by `docker ps`.
  Docker drops a manually attached network when a container is recreated, so reconnect a rebuilt
  container or declare the shared network in its Compose configuration.
- **Search works but the scenario is not found:** confirm the HEC token can write to `mcp_demo`, the
  source type is `mcp:demo:event`, and the MCP or REST identity can search that index.
- **Certificate verification fails:** install the issuing CA and configure the relevant CA bundle.
- **The reset times out:** increase `SPLUNK_INDEX_WAIT_SECONDS` above its 30-second default.
- **Splunk Cloud endpoints differ:** use the HEC and management API URLs assigned to the tenant;
  they do not always use the local Enterprise ports shown in the examples.

The integration uses Splunk's current v2 export endpoint at
`/services/search/v2/jobs/export` (under the configured app/owner namespace) and does not require
shell access to the Splunk host.
