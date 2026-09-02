# Presenter script

This is designed as an 8–10 minute customer conversation, not a feature tour.

## Before the room joins

Open **Setup → Splunk**. Use **Test MCP endpoint** to confirm that the agent can discover the
configured Splunk tools. In fixture mode, **Test Splunk search** confirms the local scenario is ready. In live
mode, confirm the search test identifies the Splunk server and reports an active demo run. The
panel keeps tokens masked, so it is safe to show the connection shape without displaying
credentials.

Use **Setup → Demo controls → Reset demo** shortly before presenting. The header reports when the active live run has aged
outside its incident window; resetting publishes a fresh run while preserving Splunk and LLM setup.

Open **Setup → Agent & LLM** and choose the mode for this presentation. **Guided demo** produces the same
tool sequence every time. **LLM-assisted** lets the configured model interpret the request and
select focused incident operations backed by the tools discovered over MCP. The panel shows the
Balanced execution profile so you can confirm the workflow has headroom for a complete
investigation. Use **Test model** before enabling LLM-assisted mode.

In **Setup → Demo controls**, choose the audience. **Executive** is the default. The selection
changes the headline, value proof, architecture annotations, six-step story, tool emphasis,
suggested agent prompts, ticket action language, result framing, and visual accent. It does not
change the source data, MCP permissions, or allowed operations. The selected audience survives a
demo reset.

## 1. Explain MCP in one minute

Open **MCP in 60 seconds**.

Suggested framing:

> An agent can already reason and write. MCP gives it a standard way to discover what a system can do, provide typed arguments, invoke an operation, and receive structured results. The systems keep owning their data and actions; the agent becomes the coordinator.

Use the connection pill in the header to open the live topology. It shows three independent MCP
servers, their endpoints, permission boundaries, and every tool discovered at runtime:

- **Northstar Service Desk** owns the employee request and the durable action record;
- **Northstar Service Catalog** owns responsibility, dependencies, escalation, and runbooks;
- **Splunk Operations** owns the operational evidence used to verify the fault domain.

Click any tool to explain why it matters in this incident, when the agent uses it, and whether it is
read-only or a controlled write. The agent discovers these capabilities rather than duplicating
each system's integration logic in the UI.

If using live mode, also point out **Real Splunk endpoint** in the briefing and **Splunk live** in
the header. Those labels are populated from runtime status rather than presenter copy.

## 2. Show the investigation agent

Open **Agent** and choose the prompt that matches the selected audience. For the default Executive
view, use **Executive summary**. For the Engineering view, use **Find the failure**.

Call attention to the MCP timeline immediately after submitting the request. It begins with intent
and tool selection, then updates each operation from running to complete as the servers respond:

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

Explain that the ticket contains only the customer's symptoms and business context. Click the
audience-specific primary action—for Executive, **Investigate with MCP**.

The authorized six-step workflow:

1. reads the ticket through the service-desk MCP server;
2. resolves the service owner, dependencies, escalation path, and runbook through the catalog;
3. calculates current Splunk health and compares it to a baseline;
4. searches correlated errors and follows a failed trace;
5. tests the alternative hypothesis by checking the implicated inventory dependency and proving
   that it is healthy;
6. writes the finding, routing context, next actions, and deep-linked evidence back to the ticket.

The right side of the ticket makes the other systems tangible. **Service Catalog** displays the
live owner, on-call team, dependencies, and runbook. The action panel offers a full investigation,
a focused Splunk health check, or a catalog lookup. Human-facing service-desk controls demonstrate
real assignment, escalation, and status operations; all are persistent and restored by reset.

End on the outcome strip and new work note. The strip makes four employee outcomes explicit:

- three systems coordinated without switching interfaces;
- two context transfers completed without copy/paste;
- evidence references preserved in the system of record;
- the implicated inventory team reaches innocence before an unnecessary escalation.

## Audience pivots

Use the same incident and execution path; change only the lens:

- **Executive:** lead with material impact, accountable ownership, faster decision evidence, and a
  completed system-of-record update. Keep implementation detail collapsed.
- **Engineering:** expand Technical inputs when useful. Emphasize the baseline comparison,
  dominant error, representative trace, healthy dependency, and mitigation path.
- **Security:** open the connection inventory and a tool detail first. Emphasize read-only Splunk
  and catalog access, controlled ticket writes, explicit intent, provenance, and visible activity.
- **Finance:** focus on the revenue-critical path, reduced coordination effort, avoided false
  handoffs, and accountable completion. Do not invent dollar savings; the demo intentionally uses
  observed workflow measures only.

## 4. Connect it to the customer's environment

Suggested close:

> The incident content and service-desk brand are fictional, but the operations you saw are real:
> HEC ingestion, Splunk searches, MCP calls, catalog lookups, and a persistent ticket update. The
> value is not another chat window: it is less re-keying, fewer handoff errors, faster completion,
> and faster proof of where the problem is—and is not. In the customer's environment, the same
> tool contracts can wrap their approved Splunk searches, service catalog, and ServiceNow
> operations without changing the employee experience.

## Reset between demonstrations

Use **Setup → Demo controls → Reset demo**, or run:

```bash
mcp-service-demo reset
```

Reset restores the ticket queue and publishes a fresh scenario. It does not change the saved
audience, Splunk profile, or agent profile, or remove saved MCP, HEC, REST, model, API-key, or TLS
settings.
