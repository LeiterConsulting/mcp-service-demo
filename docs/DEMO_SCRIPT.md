# Presenter script

This is designed as an 8–10 minute customer conversation, not a feature tour.

## Before the room joins

Open **Splunk setup**. Use **Test MCP endpoint** to confirm that the agent can discover the six
Splunk tools. In fixture mode, **Test Splunk search** confirms the local scenario is ready. In live
mode, confirm the search test identifies the Splunk server and reports an active demo run. The
panel keeps tokens masked, so it is safe to show the connection shape without displaying
credentials.

Use **Reset demo** shortly before presenting. The header reports when the active live run has aged
outside its incident window; resetting publishes a fresh run while preserving Splunk and LLM setup.

Open **LLM setup** and choose the mode for this presentation. **Guided demo** produces the same
tool sequence every time. **LLM-assisted** lets the configured model interpret the request and
select focused incident operations backed by the tools discovered over MCP. The panel shows the
Balanced execution profile so you can confirm the workflow has headroom for a complete
investigation. Use **Test model** before enabling LLM-assisted mode.

## 1. Explain MCP in one minute

Open **MCP in 60 seconds**.

Suggested framing:

> An agent can already reason and write. MCP gives it a standard way to discover what a system can do, provide typed arguments, invoke an operation, and receive structured results. The systems keep owning their data and actions; the agent becomes the coordinator.

Point out the live tool count and three independent servers. The agent discovers those capabilities
at runtime rather than duplicating each system's integration logic in the UI.

If using live mode, also point out **Real Splunk endpoint** in the briefing and **Splunk live** in
the header. Those labels are populated from runtime status rather than presenter copy.

## 2. Show the investigation agent

Open **Agent** and choose **Find the cause**.

Call attention to the MCP timeline as the answer is built:

1. `catalog.get_service_context` resolves ownership, dependencies, and the first-response runbook.
2. `splunk.get_service_health` calculates error rate and p95 latency.
3. `splunk.search_logs` finds the repeated connection-pool failure.
4. A second health check verifies that the implicated inventory service is healthy, narrowing the
   fault to the checkout client path before another team is escalated.
5. The answer summarizes the structured tool results; in live mode, those results come from SPL
   executed through Splunk's REST API.

Optional follow-up: choose **Show my queue** to demonstrate that the same host discovers tools from another MCP server.

## 3. Complete the service-desk loop

Reset the demo, then open **Service desk** and select `INC-1042`.

Explain that the ticket contains only the customer's symptoms and business context. Click **Ask Splunk**.

The authorized workflow:

1. reads the ticket through the service-desk MCP server;
2. resolves the service owner, dependencies, escalation path, and runbook through the catalog;
3. calculates current Splunk health and compares it to a baseline;
4. searches correlated errors, follows a failed trace, and verifies the implicated dependency;
5. writes a sourced internal work note through the service-desk MCP server;
6. moves the incident to **Investigating**.

End on the outcome strip and new work note. The strip makes four employee outcomes explicit:

- three systems coordinated without switching interfaces;
- two context transfers completed without copy/paste;
- evidence references preserved in the system of record;
- the implicated inventory team reaches innocence before an unnecessary escalation.

## 4. Connect it to the customer's environment

Suggested close:

> The incident content and service-desk brand are fictional, but the operations you saw are real:
> HEC ingestion, Splunk searches, MCP calls, catalog lookups, and a persistent ticket update. The
> value is not another chat window: it is less re-keying, fewer handoff errors, faster completion,
> and faster proof of where the problem is—and is not. In the customer's environment, the same
> tool contracts can wrap their approved Splunk searches, service catalog, and ServiceNow
> operations without changing the employee experience.

## Reset between demonstrations

Use **Reset demo** in the header, or run:

```bash
mcp-service-demo reset
```

Reset restores the ticket queue and publishes a fresh scenario. It does not change **Splunk setup**
or **LLM setup**, or remove saved MCP, HEC, REST, model, API-key, or TLS settings.
