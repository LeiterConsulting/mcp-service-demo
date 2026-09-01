from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from openai import AsyncOpenAI

from .config import Settings
from .mcp_client import MCPBroker, MCPTool
from .splunk_mcp_adapter import SplunkCall, SplunkMCPAdapter

WRITE_TOOLS = {"tickets__add_work_note", "tickets__update_ticket_status"}


@dataclass
class ToolEvent:
    server: str
    tool: str
    title: str
    arguments: dict[str, Any]
    status: str
    summary: str
    duration_ms: int
    result: Any | None = None


@dataclass
class AgentResult:
    message: str
    mode: str
    timeline: list[ToolEvent] = field(default_factory=list)
    ticket_updated: bool = False
    ticket_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "mode": self.mode,
            "timeline": [asdict(event) for event in self.timeline],
            "ticket_updated": self.ticket_updated,
            "ticket_id": self.ticket_id,
        }


class DemoAgent:
    def __init__(self, settings: Settings, broker: MCPBroker):
        self.settings = settings
        self.broker = broker
        self.splunk = SplunkMCPAdapter(settings, broker)

    async def _call(
        self,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        timeline: list[ToolEvent],
        title: str | None = None,
    ) -> Any:
        started = time.perf_counter()
        try:
            result = await self.broker.call(server, tool, arguments)
        except Exception as exc:
            timeline.append(
                ToolEvent(
                    server=server,
                    tool=tool,
                    title=title or tool.replace("_", " ").title(),
                    arguments=arguments,
                    status="error",
                    summary=str(exc),
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            raise
        timeline.append(
            ToolEvent(
                server=server,
                tool=tool,
                title=title or tool.replace("_", " ").title(),
                arguments=arguments,
                status="complete",
                summary=self._result_summary(tool, result),
                duration_ms=int((time.perf_counter() - started) * 1000),
                result=result,
            )
        )
        return result

    @staticmethod
    def _result_summary(tool: str, result: Any) -> str:
        if not isinstance(result, dict):
            return "Tool completed"
        if tool == "get_ticket":
            return f"Loaded {result.get('id')} · {result.get('priority')} · {result.get('service')}"
        if tool == "list_my_tickets":
            return f"Found {len(result.get('tickets', []))} assigned tickets"
        if tool == "get_service_health":
            metrics = result.get("metrics", {})
            return (
                f"{result.get('state', 'unknown').title()} · "
                f"{metrics.get('error_rate_pct', 0)}% errors · p95 {metrics.get('p95_ms', 0)} ms"
            )
        if tool == "compare_service_baseline":
            return result.get("assessment", "Baseline comparison complete")
        if tool == "search_logs":
            pattern = (result.get("top_patterns") or [{}])[0].get("pattern", "no dominant pattern")
            return f"{result.get('match_count_returned', 0)} events · top pattern: {pattern}"
        if tool == "trace_request":
            return f"Found {len(result.get('events', []))} events across the request path"
        if tool == "splunk_run_query":
            return f"Splunk returned {len(result.get('results', []))} rows"
        if tool == "add_work_note":
            return f"Work note added to {result.get('ticket_id')}"
        if tool == "update_ticket_status":
            return "Ticket status updated"
        return "Tool completed"

    def _tracked_splunk_call(self, timeline: list[ToolEvent]) -> SplunkCall:
        async def call(tool: str, arguments: dict[str, Any], title: str) -> Any:
            return await self._call("splunk", tool, arguments, timeline, title)

        return call

    async def investigate(self, ticket_id: str, write_back: bool = True) -> AgentResult:
        """Run the ticket action through the selected agent mode."""
        if self.settings.agent_mode == "openai":
            write_instruction = " and update the ticket" if write_back else " without updating it"
            return await self.chat(
                f"Investigate {ticket_id} with Splunk{write_instruction}",
                ticket_id,
            )
        return await self.investigate_ticket(ticket_id, write_back=write_back)

    async def investigate_ticket(self, ticket_id: str, write_back: bool = True) -> AgentResult:
        timeline: list[ToolEvent] = []
        ticket = await self._call(
            "tickets", "get_ticket", {"ticket_id": ticket_id}, timeline, "Read ticket context"
        )
        service = ticket["service"]
        splunk_call = self._tracked_splunk_call(timeline)
        health = await self.splunk.get_service_health(
            service,
            30,
            call=splunk_call,
        )
        baseline = await self.splunk.compare_service_baseline(
            service,
            30,
            call=splunk_call,
        )
        logs = await self.splunk.search_logs(
            service,
            "ERROR 503",
            30,
            12,
            call=splunk_call,
        )

        trace = None
        events = logs.get("events", [])
        if events and events[0].get("trace_id"):
            trace = await self.splunk.trace_request(
                events[0]["trace_id"],
                call=splunk_call,
            )

        note_body = self._build_work_note(ticket, health, baseline, logs, trace)
        evidence_refs = self._evidence_refs(health, baseline, logs, trace)
        updated = False
        if write_back:
            await self._call(
                "tickets",
                "add_work_note",
                {
                    "ticket_id": ticket["id"],
                    "body": note_body,
                    "evidence_refs": evidence_refs,
                },
                timeline,
                "Enrich the ticket",
            )
            updated = True

        metrics = health["metrics"]
        recent_change = (health.get("recent_changes") or [{}])[0]
        change_text = (
            f" A deployment to {recent_change.get('version')} occurred shortly before "
            "the degradation."
            if recent_change
            else ""
        )
        action_text = (
            f" I added the sourced investigation to {ticket['id']} and moved it to Investigating."
            if updated
            else " I prepared a ticket-ready investigation note without changing the ticket."
        )
        message = (
            f"I found a material degradation in **{service}**: {metrics['error_rate_pct']}% errors "
            f"and {metrics['p95_ms']} ms p95 latency in the last 30 minutes. The repeated failure "
            "is `inventory-client connection pool exhausted`."
            f"{change_text}{action_text}"
        )
        return AgentResult(
            message=message,
            mode="guided",
            timeline=timeline,
            ticket_updated=updated,
            ticket_id=ticket["id"],
        )

    @staticmethod
    def _evidence_refs(*results: dict[str, Any] | None) -> list[str]:
        refs: list[str] = []
        for result in results:
            if result and result.get("evidence_ref") and result["evidence_ref"] not in refs:
                refs.append(result["evidence_ref"])
        return refs

    @staticmethod
    def _build_work_note(
        ticket: dict[str, Any],
        health: dict[str, Any],
        baseline: dict[str, Any],
        logs: dict[str, Any],
        trace: dict[str, Any] | None,
    ) -> str:
        current = health["metrics"]
        previous = health["baseline"]
        pattern = (logs.get("top_patterns") or [{}])[0].get("pattern", "No dominant error pattern")
        change = (health.get("recent_changes") or [{}])[0]
        trace_services = []
        if trace:
            trace_services = list(
                dict.fromkeys(event["service"] for event in trace.get("events", []))
            )
        lines = [
            "Splunk investigation · 30-minute window",
            "",
            (
                f"Finding: {ticket['service']} is degraded and the customer report is "
                "supported by telemetry."
            ),
            "",
            "Evidence",
            (
                f"• Error rate: {current['error_rate_pct']}% ({current['errors']} of "
                f"{current['requests']} requests); preceding window: "
                f"{previous['error_rate_pct']}%."
            ),
            (f"• Latency: p95 {current['p95_ms']} ms; preceding window: {previous['p95_ms']} ms."),
            f"• Repeated error: {pattern}.",
        ]
        if change:
            lines.append(f"• Recent change: {change.get('message')} at {change.get('timestamp')}.")
        if trace_services:
            lines.append(f"• Failed trace crosses: {' → '.join(trace_services)}.")
        lines.extend(
            [
                "",
                "Assessment",
                (
                    "The timing and error concentration indicate a likely regression or "
                    "connection-pool configuration mismatch introduced with checkout-api 4.18.2. "
                    "Inventory remains "
                    "responsive, but checkout callers are exhausting their client pool."
                ),
                "",
                "Recommended next actions",
                "1. Compare inventory-client pool settings between checkout-api 4.18.1 and 4.18.2.",
                "2. Prepare rollback of 4.18.2 if the pool cannot be corrected immediately.",
                "3. Monitor checkout error rate and p95 latency during mitigation.",
                "",
                f"Baseline comparison: {baseline['assessment']}",
            ]
        )
        return "\n".join(lines)

    async def chat(self, message: str, ticket_id: str | None = None) -> AgentResult:
        if self.settings.agent_mode == "openai":
            try:
                return await self._openai_chat(message, ticket_id)
            except Exception:
                # A live demo should remain usable if the model endpoint is unavailable.
                result = await self._guided_chat(message, ticket_id)
                result.message += (
                    "\n\n_Live model unavailable; completed with the guided MCP workflow._"
                )
                return result
        return await self._guided_chat(message, ticket_id)

    async def _guided_chat(self, message: str, ticket_id: str | None = None) -> AgentResult:
        text = message.lower()
        detected_ticket = ticket_id or self._ticket_id(message)
        authorized_write = self._write_authorized(text)
        if detected_ticket and any(
            word in text for word in ("investigate", "splunk", "enrich", "update", "analyze")
        ):
            return await self.investigate_ticket(detected_ticket, write_back=authorized_write)

        timeline: list[ToolEvent] = []
        if "queue" in text or "my tickets" in text:
            queue = await self._call(
                "tickets",
                "list_my_tickets",
                {"assignee": "Maya Chen"},
                timeline,
                "Read assigned queue",
            )
            tickets = queue["tickets"]
            lines = [
                f"• **{item['id']}** · {item['priority']} · {item['title']} ({item['status']})"
                for item in tickets
            ]
            return AgentResult(
                message="Maya Chen has three assigned tickets:\n\n" + "\n".join(lines),
                mode="guided",
                timeline=timeline,
            )

        trace_match = re.search(r"tr-[a-z0-9-]+", text)
        if trace_match:
            trace = await self.splunk.trace_request(
                trace_match.group(0),
                call=self._tracked_splunk_call(timeline),
            )
            services = list(dict.fromkeys(event["service"] for event in trace.get("events", [])))
            message_text = (
                f"Trace `{trace_match.group(0)}` contains {len(trace.get('events', []))} events"
                + (f" across {' → '.join(services)}." if services else ", with no matching events.")
            )
            return AgentResult(message=message_text, mode="guided", timeline=timeline)

        service = next(
            (name for name in ("checkout-api", "inventory-api", "payment-api") if name in text),
            "checkout-api",
        )
        splunk_call = self._tracked_splunk_call(timeline)
        health = await self.splunk.get_service_health(
            service,
            30,
            call=splunk_call,
        )
        logs = None
        if any(word in text for word in ("why", "error", "cause", "changed", "investigate")):
            logs = await self.splunk.search_logs(
                service,
                "ERROR",
                30,
                10,
                call=splunk_call,
            )
        metrics = health["metrics"]
        response = (
            f"**{service} is {health['state']}** over the last 30 minutes: "
            f"{metrics['error_rate_pct']}% error rate and {metrics['p95_ms']} ms p95 latency."
        )
        if logs:
            pattern = (logs.get("top_patterns") or [{}])[0].get("pattern")
            if pattern:
                response += f" The dominant error pattern is `{pattern}`."
        if health.get("recent_changes"):
            response += " A checkout-api deployment appears immediately before the degraded window."
        return AgentResult(message=response, mode="guided", timeline=timeline)

    async def _openai_chat(self, message: str, ticket_id: str | None) -> AgentResult:
        all_tools = await self.broker.list_tools()
        allow_writes = self._write_authorized(message.lower())
        tools = [tool for tool in all_tools if allow_writes or tool.agent_name not in WRITE_TOOLS]
        tool_lookup = {tool.agent_name: tool for tool in tools}
        openai_tools = [self._openai_tool(tool) for tool in tools]
        context = f"\nThe user is viewing ticket {ticket_id}." if ticket_id else ""
        instructions = (
            "You are a concise incident-response agent in a live MCP demonstration. Discover facts "
            "with tools before making operational claims. The telemetry is synthetic but tool "
            "calls "
            "are real. Cite evidence_ref values when available. Never imply a ticket was updated "
            "unless a write tool succeeded. Use markdown sparingly."
            f"{context}"
        )
        timeline: list[ToolEvent] = []
        current_input: Any = message
        previous_response_id: str | None = None
        ticket_updated = False

        async with AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
        ) as client:
            for _ in range(5):
                response = await client.responses.create(
                    model=self.settings.openai_model,
                    instructions=instructions,
                    input=current_input,
                    tools=openai_tools,
                    previous_response_id=previous_response_id,
                )
                calls = [item for item in response.output if item.type == "function_call"]
                if not calls:
                    return AgentResult(
                        message=response.output_text or "Investigation complete.",
                        mode="openai",
                        timeline=timeline,
                        ticket_updated=ticket_updated,
                        ticket_id=ticket_id,
                    )
                outputs = []
                for call in calls:
                    descriptor = tool_lookup[call.name]
                    arguments = json.loads(call.arguments or "{}")
                    result = await self._call(
                        descriptor.server,
                        descriptor.name,
                        arguments,
                        timeline,
                        descriptor.title,
                    )
                    if call.name in WRITE_TOOLS:
                        ticket_updated = True
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(result, default=str),
                        }
                    )
                previous_response_id = response.id
                current_input = outputs

        return AgentResult(
            message="The tool-call limit was reached. Review the completed evidence below.",
            mode="openai",
            timeline=timeline,
            ticket_updated=ticket_updated,
            ticket_id=ticket_id,
        )

    @staticmethod
    def _openai_tool(tool: MCPTool) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.agent_name,
            "description": f"[{tool.server} MCP] {tool.description}",
            "parameters": tool.input_schema,
        }

    @staticmethod
    def _ticket_id(message: str) -> str | None:
        match = re.search(r"\bINC-\d+\b", message, re.IGNORECASE)
        return match.group(0).upper() if match else None

    @staticmethod
    def _write_authorized(text: str) -> bool:
        return any(
            phrase in text
            for phrase in (
                "update the ticket",
                "update ticket",
                "add a note",
                "add work note",
                "write back",
                "enrich the ticket",
                "enrich ticket",
            )
        )
