# Presenter script

This is designed as an 8–10 minute customer conversation, not a feature tour.

## 1. Explain MCP in one minute

Open **MCP in 60 seconds**.

Suggested framing:

> An agent can already reason and write. MCP gives it a standard way to discover what a system can do, provide typed arguments, invoke an operation, and receive structured results. The systems keep owning their data and actions; the agent becomes the coordinator.

Point out the live tool count. The catalog is discovered from the two running MCP servers rather than duplicated in the UI.

## 2. Show the investigation agent

Open **Agent** and choose **Find the cause**.

Call attention to the MCP timeline as the answer is built:

1. `splunk.get_service_health` calculates error rate and p95 latency.
2. `splunk.search_logs` finds the repeated connection-pool failure.
3. The answer summarizes tool results; it does not contain a prewritten incident narrative.

Optional follow-up: choose **Show my queue** to demonstrate that the same host discovers tools from another MCP server.

## 3. Complete the service-desk loop

Reset the demo, then open **Service desk** and select `INC-1042`.

Explain that the ticket contains only the customer's symptoms and business context. Click **Ask Splunk**.

The authorized workflow:

1. reads the ticket through the service-desk MCP server;
2. calculates current Splunk health and compares it to a baseline;
3. searches correlated errors and follows a failed trace;
4. writes a sourced internal work note through the service-desk MCP server;
5. moves the incident to **Investigating**.

End on the new work note and its evidence references.

## 4. Connect it to the customer's environment

Suggested close:

> Today these are synthetic events and a fictional service desk. In a real environment the MCP tools would wrap the customer's existing Splunk searches and ServiceNow operations. The agent experience remains the same; the implementation behind each server changes.

## Reset between demonstrations

Use **Reset demo** in the header, or run:

```bash
mcp-service-demo reset
```

