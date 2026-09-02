from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from openai import AsyncOpenAI

from .config import Settings
from .mcp_client import MCPBroker, MCPTool
from .splunk_mcp_adapter import SplunkCall, SplunkMCPAdapter

WRITE_TOOLS = {"tickets__add_work_note", "tickets__update_ticket_status"}
logger = logging.getLogger(__name__)


def _object_schema(properties: dict[str, Any]) -> dict[str, Any]:
    """Return the strict object shape required by Responses function tools."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


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
    event_id: str = ""


@dataclass
class AgentResult:
    message: str
    mode: str
    timeline: list[ToolEvent] = field(default_factory=list)
    ticket_updated: bool = False
    ticket_id: str | None = None

    def to_dict(self, *, elapsed_ms: int | None = None) -> dict[str, Any]:
        systems = list(dict.fromkeys(event.server for event in self.timeline))
        evidence_refs: list[str] = []
        for event in self.timeline:
            if isinstance(event.result, dict):
                ref = event.result.get("evidence_ref")
                if ref and ref not in evidence_refs:
                    evidence_refs.append(ref)
            for ref in event.arguments.get("evidence_refs") or []:
                if ref not in evidence_refs:
                    evidence_refs.append(ref)
        return {
            "message": self.message,
            "mode": self.mode,
            "timeline": [asdict(event) for event in self.timeline],
            "ticket_updated": self.ticket_updated,
            "ticket_id": self.ticket_id,
            "outcomes": {
                "elapsed_seconds": round(elapsed_ms / 1000, 1) if elapsed_ms is not None else None,
                "systems_coordinated": len(systems),
                "systems": systems,
                "mcp_calls": len(self.timeline),
                "context_transfers_automated": max(0, len(systems) - 1),
                "evidence_refs_preserved": len(evidence_refs),
                "manual_rekeying": 0,
            },
        }


class DemoAgent:
    def __init__(
        self,
        settings: Settings,
        broker: MCPBroker,
        on_event: Callable[[ToolEvent], Awaitable[None] | None] | None = None,
    ):
        self.settings = settings
        self.broker = broker
        self.splunk = SplunkMCPAdapter(settings, broker)
        self.on_event = on_event

    async def _emit_event(self, event: ToolEvent) -> None:
        if self.on_event is None:
            return
        emitted = self.on_event(event)
        if asyncio.iscoroutine(emitted):
            await emitted

    async def _call(
        self,
        server: str,
        tool: str,
        arguments: dict[str, Any],
        timeline: list[ToolEvent],
        title: str | None = None,
    ) -> Any:
        started = time.perf_counter()
        event_id = f"{server}:{tool}:{time.monotonic_ns()}"
        await self._emit_event(
            ToolEvent(
                server=server,
                tool=tool,
                title=title or tool.replace("_", " ").title(),
                arguments=arguments,
                status="running",
                summary="Waiting for the MCP server",
                duration_ms=0,
                event_id=event_id,
            )
        )
        try:
            result = await self.broker.call(server, tool, arguments)
        except Exception as exc:
            event = ToolEvent(
                server=server,
                tool=tool,
                title=title or tool.replace("_", " ").title(),
                arguments=arguments,
                status="error",
                summary=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
                event_id=event_id,
            )
            timeline.append(event)
            await self._emit_event(event)
            raise
        event = ToolEvent(
            server=server,
            tool=tool,
            title=title or tool.replace("_", " ").title(),
            arguments=arguments,
            status="complete",
            summary=self._result_summary(tool, result),
            duration_ms=int((time.perf_counter() - started) * 1000),
            result=result,
            event_id=event_id,
        )
        timeline.append(event)
        await self._emit_event(event)
        return result

    @staticmethod
    def _result_summary(tool: str, result: Any) -> str:
        if not isinstance(result, dict):
            return "Tool completed"
        if tool == "get_ticket":
            return f"Loaded {result.get('id')} · {result.get('priority')} · {result.get('service')}"
        if tool == "list_my_tickets":
            return f"Found {len(result.get('tickets', []))} assigned tickets"
        if tool == "get_service_context":
            return (
                f"{result.get('criticality')} · owner {result.get('owner_team')} · "
                f"{len(result.get('dependencies', []))} dependencies"
            )
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
            if write_back:
                instruction = (
                    f"Complete the investigation for {ticket_id}. Read the ticket, establish "
                    "current service health over the last 30 minutes and compare it with the "
                    "preceding 30-minute baseline. Find the dominant error and trace a failed "
                    "request when a trace ID is available. Then update the "
                    "ticket with a concise work note containing the findings, evidence references, "
                    "and recommended next actions."
                )
            else:
                instruction = (
                    f"Complete the investigation for {ticket_id}. Read the ticket, establish "
                    "current service health over the last 30 minutes and compare it with the "
                    "preceding 30-minute baseline. Find the dominant error and trace a failed "
                    "request when a trace ID is available. This is read-only: "
                    "do not update the ticket or make any other change."
                )
            return await self.chat(instruction, ticket_id)
        return await self.investigate_ticket(ticket_id, write_back=write_back)

    async def investigate_ticket(self, ticket_id: str, write_back: bool = True) -> AgentResult:
        timeline: list[ToolEvent] = []
        ticket = await self._call(
            "tickets", "get_ticket", {"ticket_id": ticket_id}, timeline, "Read ticket context"
        )
        service = ticket["service"]
        service_context = await self._call(
            "catalog",
            "get_service_context",
            {"service": service},
            timeline,
            "Resolve ownership and dependencies",
        )
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

        dependency_health = None
        implicated_dependency = self._implicated_dependency(service_context, logs, trace)
        if implicated_dependency:
            dependency_health = await self.splunk.get_service_health(
                implicated_dependency,
                30,
                call=splunk_call,
            )

        note_body = self._build_work_note(
            ticket,
            service_context,
            health,
            baseline,
            logs,
            trace,
            dependency_health,
        )
        evidence_refs = self._evidence_refs(
            service_context,
            health,
            baseline,
            logs,
            trace,
            dependency_health,
        )
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
        innocence_text = ""
        if dependency_health and dependency_health.get("state") == "healthy":
            dependency_metrics = dependency_health["metrics"]
            innocence_text = (
                f" {dependency_health['service']} is healthy at "
                f"{dependency_metrics['error_rate_pct']}% errors and "
                f"{dependency_metrics['p95_ms']} ms p95, narrowing the fault to the "
                f"{service} client path rather than the dependency service."
            )
        message = (
            f"I found a material degradation in **{service}**: {metrics['error_rate_pct']}% errors "
            f"and {metrics['p95_ms']} ms p95 latency in the last 30 minutes. The repeated failure "
            "is `inventory-client connection pool exhausted`."
            f"{change_text}{innocence_text}{action_text}"
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
        service_context: dict[str, Any],
        health: dict[str, Any],
        baseline: dict[str, Any],
        logs: dict[str, Any],
        trace: dict[str, Any] | None,
        dependency_health: dict[str, Any] | None,
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
                f"• Service context: {service_context['criticality']}; owner "
                f"{service_context['owner_team']} / {service_context['on_call']}."
            ),
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
        if dependency_health:
            dependency_metrics = dependency_health["metrics"]
            lines.append(
                f"• Fault isolation: {dependency_health['service']} is "
                f"{dependency_health['state']} at {dependency_metrics['error_rate_pct']}% errors "
                f"and {dependency_metrics['p95_ms']} ms p95."
            )
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
                f"Runbook: {service_context['runbook']['reference']}",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _implicated_dependency(
        service_context: dict[str, Any],
        logs: dict[str, Any],
        trace: dict[str, Any] | None,
    ) -> str | None:
        evidence_text = " ".join(
            [
                *(str(item.get("pattern", "")) for item in logs.get("top_patterns", [])),
                *(str(item.get("message", "")) for item in logs.get("events", [])),
                *(
                    str(item.get("message", ""))
                    for item in (trace or {}).get("events", [])
                ),
            ]
        ).lower()
        for dependency in service_context.get("dependencies", []):
            signals = [dependency.get("service", ""), *dependency.get("signals", [])]
            if any(str(signal).lower().split("-")[0] in evidence_text for signal in signals):
                return str(dependency["service"])
        return None

    async def chat(self, message: str, ticket_id: str | None = None) -> AgentResult:
        if self.settings.agent_mode == "openai":
            try:
                return await self._openai_chat(message, ticket_id)
            except Exception as exc:
                # A live demo should remain usable if the model endpoint is unavailable.
                logger.warning("LLM workflow unavailable; using guided fallback: %s", exc)
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
        needs_cause = any(
            word in text for word in ("why", "error", "cause", "changed", "investigate")
        )
        service_context = None
        if needs_cause or any(word in text for word in ("owner", "runbook", "dependency")):
            service_context = await self._call(
                "catalog",
                "get_service_context",
                {"service": service},
                timeline,
                "Resolve ownership and dependencies",
            )
        splunk_call = self._tracked_splunk_call(timeline)
        health = await self.splunk.get_service_health(
            service,
            30,
            call=splunk_call,
        )
        logs = None
        if needs_cause:
            logs = await self.splunk.search_logs(
                service,
                "ERROR",
                30,
                10,
                call=splunk_call,
            )
        dependency_health = None
        if logs and service_context:
            dependency = self._implicated_dependency(service_context, logs, None)
            if dependency:
                dependency_health = await self.splunk.get_service_health(
                    dependency,
                    30,
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
        if service_context:
            response += (
                f" {service_context['owner_team']} owns the service; the first-response runbook is "
                f"`{service_context['runbook']['reference']}`."
            )
        if dependency_health and dependency_health.get("state") == "healthy":
            response += (
                f" {dependency_health['service']} is healthy, narrowing the fault to the "
                f"{service} client path."
            )
        if health.get("recent_changes"):
            response += " A checkout-api deployment appears immediately before the degraded window."
        return AgentResult(message=response, mode="guided", timeline=timeline)

    async def _openai_chat(self, message: str, ticket_id: str | None) -> AgentResult:
        discovered_tools = await self.broker.list_tools()
        allow_writes = self._write_authorized(message.lower())
        tools = self._agent_tools(discovered_tools, allow_writes=allow_writes)
        tool_lookup = {tool.agent_name: tool for tool in tools}
        openai_tools = [self._openai_tool(tool) for tool in tools]
        instructions = self._openai_instructions(ticket_id=ticket_id, allow_writes=allow_writes)
        timeline: list[ToolEvent] = []
        current_input: Any = message
        previous_response_id: str | None = None
        ticket_updated = False
        tool_call_count = 0

        async with AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
            timeout=self.settings.openai_timeout_seconds,
            max_retries=self.settings.openai_max_retries,
        ) as client:
            for _ in range(self.settings.openai_max_iterations):
                response = await client.responses.create(
                    model=self.settings.openai_model,
                    instructions=instructions,
                    input=current_input,
                    tools=openai_tools,
                    tool_choice="auto",
                    parallel_tool_calls=True,
                    max_output_tokens=self.settings.openai_max_output_tokens,
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
                remaining = self.settings.openai_max_tool_calls - tool_call_count
                accepted_calls = calls[:remaining]
                tool_call_count += len(accepted_calls)
                outputs = await self._execute_model_calls(
                    accepted_calls,
                    tool_lookup,
                    timeline,
                )
                ticket_updated = ticket_updated or any(
                    output.get("write_succeeded", False) for output in outputs
                )
                for output in outputs:
                    output.pop("write_succeeded", None)
                for call in calls[remaining:]:
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(
                                {
                                    "error": (
                                        "Tool budget reached. Summarize the evidence already "
                                        "collected."
                                    )
                                }
                            ),
                        }
                    )
                previous_response_id = response.id
                current_input = outputs

                if tool_call_count >= self.settings.openai_max_tool_calls:
                    final = await client.responses.create(
                        model=self.settings.openai_model,
                        instructions=(
                            instructions
                            + "\nThe tool budget is complete. Do not request more tools; provide "
                            "the "
                            "best final answer from the evidence already returned."
                        ),
                        input=current_input,
                        max_output_tokens=self.settings.openai_max_output_tokens,
                        previous_response_id=previous_response_id,
                    )
                    return AgentResult(
                        message=final.output_text or "Investigation complete.",
                        mode="openai",
                        timeline=timeline,
                        ticket_updated=ticket_updated,
                        ticket_id=ticket_id,
                    )

            final = await client.responses.create(
                model=self.settings.openai_model,
                instructions=(
                    instructions
                    + "\nThe operation-sequencing budget is complete. Do not request more tools; "
                    "provide the best final answer from the evidence already returned."
                ),
                input=current_input,
                max_output_tokens=self.settings.openai_max_output_tokens,
                previous_response_id=previous_response_id,
            )
            return AgentResult(
                message=final.output_text or "Investigation complete.",
                mode="openai",
                timeline=timeline,
                ticket_updated=ticket_updated,
                ticket_id=ticket_id,
            )

        return AgentResult(
            message="Investigation complete. Review the sourced evidence below.",
            mode="openai",
            timeline=timeline,
            ticket_updated=ticket_updated,
            ticket_id=ticket_id,
        )

    async def _execute_model_calls(
        self,
        calls: list[Any],
        tool_lookup: dict[str, MCPTool],
        timeline: list[ToolEvent],
    ) -> list[dict[str, Any]]:
        """Execute independent reads concurrently, while serializing any write batch."""
        semaphore = asyncio.Semaphore(self.settings.openai_max_parallel_tools)

        async def execute(call: Any) -> dict[str, Any]:
            descriptor = tool_lookup.get(call.name)
            if descriptor is None:
                return self._model_tool_output(call.call_id, error="Unknown or unavailable tool")
            try:
                arguments = json.loads(call.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                return self._model_tool_output(call.call_id, error=str(exc))

            if descriptor.server == "tickets" and descriptor.name == "add_work_note":
                arguments = self._prepare_work_note_arguments(arguments, timeline)

            try:
                async with semaphore:
                    result = await self._execute_agent_tool(descriptor, arguments, timeline)
            except Exception as exc:
                return self._model_tool_output(call.call_id, error=str(exc))
            return {
                **self._model_tool_output(call.call_id, result=result),
                "write_succeeded": call.name in WRITE_TOOLS,
            }

        if any(call.name in WRITE_TOOLS for call in calls):
            results = []
            for call in calls:
                results.append(await execute(call))
            return results
        return list(await asyncio.gather(*(execute(call) for call in calls)))

    async def _execute_agent_tool(
        self,
        descriptor: MCPTool,
        arguments: dict[str, Any],
        timeline: list[ToolEvent],
    ) -> Any:
        if descriptor.server != "splunk":
            return await self._call(
                descriptor.server,
                descriptor.name,
                arguments,
                timeline,
                descriptor.title,
            )

        call = self._tracked_splunk_call(timeline)
        timeline_start = len(timeline)
        if descriptor.name == "get_service_health":
            result = await self.splunk.get_service_health(
                arguments["service"], arguments["minutes"], call=call
            )
        elif descriptor.name == "compare_service_baseline":
            result = await self.splunk.compare_service_baseline(
                arguments["service"], arguments["minutes"], call=call
            )
        elif descriptor.name == "search_logs":
            result = await self.splunk.search_logs(
                arguments["service"],
                arguments["keywords"],
                arguments["minutes"],
                arguments["limit"],
                call=call,
            )
        elif descriptor.name == "trace_request":
            result = await self.splunk.trace_request(arguments["trace_id"], call=call)
        else:
            raise ValueError(f"Unsupported Splunk incident operation: {descriptor.name}")

        # A generic Splunk MCP exposes splunk_run_query, while the model works with the focused
        # incident operation above it. Retain that focused, evidence-bearing result on the visible
        # event so provenance and work-note safeguards do not depend on model transcription.
        for event in reversed(timeline[timeline_start:]):
            if event.server == "splunk":
                event.result = result
                break
        return result

    @staticmethod
    def _prepare_work_note_arguments(
        arguments: dict[str, Any], timeline: list[ToolEvent]
    ) -> dict[str, Any]:
        """Preserve read evidence and verified routing facts before an LLM-authored write."""
        prepared = dict(arguments)
        refs: list[str] = []
        context: dict[str, Any] | None = None
        health_by_service: dict[str, dict[str, Any]] = {}

        for event in timeline:
            if not isinstance(event.result, dict):
                continue
            result = event.result
            ref = result.get("evidence_ref")
            if ref and ref not in refs:
                refs.append(ref)
            if event.server == "catalog" and result.get("service"):
                context = result
            if event.server == "splunk" and result.get("service") and result.get("state"):
                health_by_service[str(result["service"])] = result

        for ref in prepared.get("evidence_refs") or []:
            if ref not in refs:
                refs.append(ref)
        prepared["evidence_refs"] = refs

        body = str(prepared.get("body", "")).strip()
        additions: list[str] = []
        body_lower = body.lower()
        if context:
            owner = str(context.get("owner_team", ""))
            runbook = str((context.get("runbook") or {}).get("reference", ""))
            context_ref = str(context.get("evidence_ref", ""))
            if owner.lower() not in body_lower or (runbook and runbook.lower() not in body_lower):
                additions.append(
                    f"Routing context: {owner} owns {context['service']}; on-call "
                    f"{context.get('on_call')}. Runbook: {runbook}. Context: {context_ref}."
                )

            for dependency in context.get("dependencies", []):
                service = str(dependency.get("service", ""))
                health = health_by_service.get(service)
                normalized_phrase = f"{service.replace('-', ' ')} is healthy"
                if (
                    health
                    and health.get("state") == "healthy"
                    and normalized_phrase not in body_lower.replace("-", " ")
                ):
                    metrics = health.get("metrics") or {}
                    additions.append(
                        f"Fault isolation: {service} is healthy at "
                        f"{metrics.get('error_rate_pct', 0)}% errors and "
                        f"{metrics.get('p95_ms', 0)} ms p95, narrowing the fault to the "
                        f"{context['service']} client path before dependency escalation."
                    )

        if additions:
            body = f"{body}\n\n" if body else ""
            body += "\n".join(additions)
        prepared["body"] = body
        return prepared

    @staticmethod
    def _model_tool_output(
        call_id: str,
        *,
        result: Any | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        content = {"error": error} if error else result
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(content, default=str),
        }

    def _openai_instructions(self, *, ticket_id: str | None, allow_writes: bool) -> str:
        context = f" The user is viewing ticket {ticket_id}." if ticket_id else ""
        write_policy = (
            "Ticket writes are authorized for this request. Add one evidence-based work note only "
            "after the investigation is complete; include the service owner and runbook, any "
            "verified healthy dependency and the resulting fault isolation, and every evidence_ref "
            "returned by any MCP read. Do not resolve the incident."
            if allow_writes
            else "This request is read-only. No ticket write tools are available."
        )
        return (
            "You are the incident-response agent in a live MCP demonstration. The company and "
            "telemetry are synthetic, but every displayed tool operation uses the configured MCP "
            "connections. The application exposes a focused set of incident operations; Splunk "
            "operations automatically scope searches to the active deterministic demo run. Never "
            "invent raw SPL, field names, metrics, ticket state, or evidence.\n\n"
            "Investigation policy:\n"
            "- Read a ticket before using its service as context.\n"
            "- For a ticket or full investigation, call get_service_context after reading the "
            "ticket. Use it for ownership, criticality, dependencies, and the runbook.\n"
            "- For service health, call get_service_health. For a cause or full investigation, "
            "also call compare_service_baseline and search_logs. These independent reads may be "
            "requested together. Use a 30-minute window unless the user explicitly asks for "
            "another period.\n"
            "- If search_logs returns a trace_id, call trace_request once to confirm the affected "
            "service path. Do not repeat a successful operation.\n"
            "- When logs or a trace implicate a named catalog dependency, call "
            "get_service_health once for that dependency. If it is healthy, say that the evidence "
            "narrows fault away from the dependency service; do not assign blame from a trace "
            "alone.\n"
            "- Complete the investigation in this turn. Do not ask the user which search to run "
            "next when the available operations can answer the request.\n"
            "- Cite evidence_ref values when available. Clearly distinguish observations from "
            "inference. Never claim a ticket changed unless a write tool succeeded.\n"
            "- Keep the final answer under 180 words. Lead with one finding sentence, then use no "
            "more than five bullets total for ownership, metrics/baseline, fault isolation, "
            "recommended action, and ticket update status. Do not add a second analysis section, "
            "ask a follow-up "
            "question, or print raw SPL unless the user asks for it.\n\n"
            f"{write_policy}{context}\n"
            f"Demo data contract: app={self.settings.splunk_app}, "
            f"index={self.settings.splunk_index}, "
            f"sourcetype={self.settings.splunk_sourcetype}, "
            f"scenario_id={self.settings.splunk_scenario_id}."
        )

    @staticmethod
    def _agent_tools(discovered: list[MCPTool], *, allow_writes: bool) -> list[MCPTool]:
        """Expose a focused, strict incident surface backed by discovered MCP capabilities."""
        names = {(tool.server, tool.name) for tool in discovered}
        supports_query = ("splunk", "splunk_run_query") in names
        tools: list[MCPTool] = []

        def add_if_supported(tool: MCPTool) -> None:
            supported = (tool.server, tool.name) in names
            if tool.server == "splunk":
                supported = supported or supports_query
            if supported:
                tools.append(tool)

        add_if_supported(
            MCPTool(
                server="tickets",
                name="list_my_tickets",
                title="Read assigned queue",
                description=(
                    "List the service-desk tickets assigned to an analyst, in priority order."
                ),
                input_schema=_object_schema(
                    {"assignee": {"type": "string", "description": "Analyst name; use Maya Chen."}}
                ),
            )
        )
        add_if_supported(
            MCPTool(
                server="catalog",
                name="get_service_context",
                title="Resolve ownership and dependencies",
                description=(
                    "Return the authoritative owner, criticality, dependencies, escalation "
                    "channel, and runbook for a service. Use before assigning fault or routing "
                    "the incident."
                ),
                input_schema=_object_schema(
                    {
                        "service": {
                            "type": "string",
                            "description": "Service name from the ticket.",
                        }
                    }
                ),
            )
        )
        add_if_supported(
            MCPTool(
                server="tickets",
                name="get_ticket",
                title="Read ticket context",
                description="Read a ticket and its activity before investigating its service.",
                input_schema=_object_schema(
                    {"ticket_id": {"type": "string", "description": "Ticket ID such as INC-1042."}}
                ),
            )
        )
        add_if_supported(
            MCPTool(
                server="splunk",
                name="get_service_health",
                title="Check service health",
                description=(
                    "Required first telemetry step. Return current error rate, latency, baseline, "
                    "recent deployments, and an evidence reference from the active demo run."
                ),
                input_schema=_object_schema(
                    {
                        "service": {
                            "type": "string",
                            "description": "Service name from the ticket.",
                        },
                        "minutes": {
                            "type": "integer",
                            "minimum": 5,
                            "maximum": 90,
                            "description": "Use 30 unless the user requests another window.",
                        },
                    }
                ),
            )
        )
        add_if_supported(
            MCPTool(
                server="splunk",
                name="compare_service_baseline",
                title="Compare with baseline",
                description=(
                    "Compare current service error rate and p95 latency with the preceding window."
                ),
                input_schema=_object_schema(
                    {
                        "service": {
                            "type": "string",
                            "description": "Service name from the ticket.",
                        },
                        "minutes": {
                            "type": "integer",
                            "minimum": 5,
                            "maximum": 90,
                            "description": "Use 30 unless the user requests another window.",
                        },
                    }
                ),
            )
        )
        add_if_supported(
            MCPTool(
                server="splunk",
                name="search_logs",
                title="Find correlated errors",
                description=(
                    "Find dominant error patterns and representative events for a service. Use for "
                    "cause analysis and preserve any returned trace_id for trace_request."
                ),
                input_schema=_object_schema(
                    {
                        "service": {
                            "type": "string",
                            "description": "Service name from the ticket.",
                        },
                        "keywords": {
                            "type": "string",
                            "description": (
                                "Narrow error terms, or ERROR for the incident workflow."
                            ),
                        },
                        "minutes": {
                            "type": "integer",
                            "minimum": 5,
                            "maximum": 90,
                            "description": "Use 30 unless the user requests another window.",
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    }
                ),
            )
        )
        add_if_supported(
            MCPTool(
                server="splunk",
                name="trace_request",
                title="Trace the failed request",
                description="Follow one trace_id returned by search_logs across the service path.",
                input_schema=_object_schema(
                    {"trace_id": {"type": "string", "description": "Trace ID from a log result."}}
                ),
            )
        )

        if allow_writes:
            add_if_supported(
                MCPTool(
                    server="tickets",
                    name="add_work_note",
                    title="Enrich the ticket",
                    description=(
                        "Add one internal investigation note after evidence collection. This is a "
                        "real write and moves a new incident to Investigating."
                    ),
                    input_schema=_object_schema(
                        {
                            "ticket_id": {"type": "string"},
                            "body": {
                                "type": "string",
                                "description": (
                                    "Concise findings, evidence, assessment, and next actions."
                                ),
                            },
                            "evidence_refs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": (
                                    "Unique evidence_ref values returned by every MCP read, "
                                    "including service catalog and Splunk operations."
                                ),
                            },
                        }
                    ),
                )
            )
            add_if_supported(
                MCPTool(
                    server="tickets",
                    name="update_ticket_status",
                    title="Update ticket status",
                    description=(
                        "Explicitly change incident status only when the user requested that "
                        "status. "
                        "Adding a work note already moves a New incident to Investigating."
                    ),
                    input_schema=_object_schema(
                        {
                            "ticket_id": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["New", "Investigating", "Monitoring", "Resolved"],
                            },
                        }
                    ),
                )
            )
        return tools

    @staticmethod
    def _openai_tool(tool: MCPTool) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.agent_name,
            "description": f"[{tool.server} MCP] {tool.description}",
            "parameters": tool.input_schema,
            "strict": True,
        }

    @staticmethod
    def _ticket_id(message: str) -> str | None:
        match = re.search(r"\bINC-\d+\b", message, re.IGNORECASE)
        return match.group(0).upper() if match else None

    @staticmethod
    def _write_authorized(text: str) -> bool:
        if any(
            phrase in text
            for phrase in (
                "do not update",
                "don't update",
                "without updating",
                "do not change",
                "don't change",
                "read-only",
                "read only",
                "no changes",
            )
        ):
            return False
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
