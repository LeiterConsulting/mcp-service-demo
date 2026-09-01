from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

from .config import Settings
from .mcp_client import MCPBroker
from .splunk_backend import SplunkConnectionError

SplunkCall = Callable[[str, dict[str, Any], str], Awaitable[Any]]

_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_KEYWORD = re.compile(r"[A-Za-z0-9_.:-]+")


class SplunkMCPAdapter:
    """Expose the demo's guided operations through either Splunk MCP tool shape.

    The bundled demo MCP server offers purpose-built tools. Splunk's companion MCP
    endpoint offers the more general ``splunk_run_query`` tool. This adapter keeps
    the guided story deterministic while ensuring the latter executes real SPL.
    """

    def __init__(self, settings: Settings, broker: MCPBroker):
        self.settings = settings
        self.broker = broker
        self._tool_names: set[str] | None = None

    async def tool_names(self) -> set[str]:
        if self._tool_names is None:
            tools = await self.broker.list_tools()
            self._tool_names = {tool.name for tool in tools if tool.server == "splunk"}
        return self._tool_names

    async def _invoke(
        self,
        tool: str,
        arguments: dict[str, Any],
        title: str,
        call: SplunkCall | None,
    ) -> Any:
        if call is not None:
            return await call(tool, arguments, title)
        return await self.broker.call("splunk", tool, arguments)

    async def _supports_rich_tool(self, tool: str) -> bool:
        names = await self.tool_names()
        if tool in names:
            return True
        if "splunk_run_query" in names:
            return False
        raise SplunkConnectionError(
            f"The configured Splunk MCP server provides neither {tool} nor splunk_run_query."
        )

    async def _query(
        self,
        spl: str,
        *,
        title: str,
        call: SplunkCall | None = None,
        earliest_time: str = "-7d",
        row_limit: int = 100,
    ) -> list[dict[str, Any]]:
        result = await self._invoke(
            "splunk_run_query",
            {
                "query": spl,
                "app": self.settings.splunk_app,
                "earliest_time": earliest_time,
                "latest_time": "now",
                "row_limit": row_limit,
            },
            title,
            call,
        )
        if isinstance(result, dict) and isinstance(result.get("results"), list):
            return [row for row in result["results"] if isinstance(row, dict)]
        if isinstance(result, list):
            return [row for row in result if isinstance(row, dict)]
        return []

    def _active_base(self, service: str | None = None) -> str:
        parts = [
            "search",
            f"index={_spl_literal(self.settings.splunk_index)}",
            f"sourcetype={_spl_literal(self.settings.splunk_sourcetype)}",
            f"scenario_id={_spl_literal(self.settings.splunk_scenario_id)}",
            (
                "[ search "
                f"index={_spl_literal(self.settings.splunk_index)} "
                f"sourcetype={_spl_literal(self.settings.splunk_sourcetype)} "
                f"scenario_id={_spl_literal(self.settings.splunk_scenario_id)} earliest=-7d "
                "| stats max(_time) as latest by demo_run_id "
                "| sort 0 - latest | head 1 | return demo_run_id ]"
            ),
        ]
        if service:
            parts.append(f"service={_spl_literal(_safe_value(service, 'service'))}")
        return " ".join(parts)

    def _evidence_ref(self, service: str, window: int, run_id: str | None = None) -> str:
        suffix = f"&run={quote(run_id)}" if run_id else ""
        return (
            f"splunk://search?app={self.settings.splunk_app}&service={quote(service)}"
            f"&earliest=-{window}m{suffix}"
        )

    async def status(self, call: SplunkCall | None = None) -> dict[str, Any]:
        if await self._supports_rich_tool("get_splunk_status"):
            return await self._invoke("get_splunk_status", {}, "Check Splunk status", call)
        rows = await self._query(
            (
                f"search index={_spl_literal(self.settings.splunk_index)} "
                f"sourcetype={_spl_literal(self.settings.splunk_sourcetype)} "
                f"scenario_id={_spl_literal(self.settings.splunk_scenario_id)} earliest=-7d "
                "| stats max(_time) as latest count as events by demo_run_id "
                "| sort 0 - latest | head 1"
            ),
            title="Find the active demo run",
            call=call,
            row_limit=1,
        )
        active = rows[0] if rows else {}
        return {
            "ready": bool(active.get("demo_run_id")),
            "mode": "live",
            "source": self.settings.splunk_mcp_url,
            "index": self.settings.splunk_index,
            "sourcetype": self.settings.splunk_sourcetype,
            "scenario_id": self.settings.splunk_scenario_id,
            "active_run_id": active.get("demo_run_id"),
            "event_count": _integer(active.get("events")),
        }

    async def wait_for_run(self, run_id: str) -> bool:
        normalized = _safe_value(run_id, "demo_run_id")
        deadline = time.monotonic() + self.settings.splunk_index_wait_seconds
        while True:
            rows = await self._query(
                (
                    f"search index={_spl_literal(self.settings.splunk_index)} "
                    f"sourcetype={_spl_literal(self.settings.splunk_sourcetype)} "
                    f"scenario_id={_spl_literal(self.settings.splunk_scenario_id)} "
                    f"demo_run_id={_spl_literal(normalized)} earliest=-15m "
                    "| stats count as events"
                ),
                title="Confirm the demo data is searchable",
                earliest_time="-15m",
                row_limit=1,
            )
            if rows and _integer(rows[0].get("events")) > 0:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(1.0, remaining))

    async def get_service_health(
        self,
        service: str,
        minutes: int = 30,
        *,
        call: SplunkCall | None = None,
    ) -> dict[str, Any]:
        if await self._supports_rich_tool("get_service_health"):
            return await self._invoke(
                "get_service_health",
                {"service": service, "minutes": minutes},
                "Check service health",
                call,
            )
        normalized = _safe_value(service, "service")
        window = min(max(minutes, 5), 90)
        base = self._active_base(normalized)
        rows = await self._query(
            (
                f"{base} event_type=request earliest=-{window * 2}m "
                f'| eval period=if(_time>=relative_time(now(),"-{window}m"),"current","baseline") '
                "| stats count as requests count(eval(tonumber(status_code)>=500)) as errors "
                "perc50(duration_ms) as p50_ms perc95(duration_ms) as p95_ms by period "
                "| eval error_rate_pct=if(requests=0,0,round(errors*100/requests,1)), "
                'row_kind="metric" '
                f"| append [ {base} event_type=deployment earliest=-{window + 10}m "
                "| sort 0 - _time | head 10 "
                '| eval row_kind="change" '
                "| table row_kind _time message version host ]"
            ),
            title="Check service health",
            call=call,
            earliest_time=f"-{window * 2}m",
            row_limit=100,
        )
        metrics = _metrics_by_period(rows)
        current = metrics.get("current", _empty_metrics())
        baseline = metrics.get("baseline", _empty_metrics())
        changes = [
            {
                "timestamp": row.get("_time"),
                "message": row.get("message"),
                "version": row.get("version"),
                "host": row.get("host"),
            }
            for row in rows
            if row.get("row_kind") == "change"
        ]
        return {
            "service": normalized,
            "window_minutes": window,
            "state": (
                "degraded"
                if current["error_rate_pct"] >= 5 or current["p95_ms"] >= 1500
                else "healthy"
            ),
            "metrics": current,
            "baseline": baseline,
            "change": {
                "error_rate_points": round(
                    current["error_rate_pct"] - baseline["error_rate_pct"], 1
                ),
                "p95_ms": current["p95_ms"] - baseline["p95_ms"],
            },
            "timeline": [],
            "recent_changes": changes,
            "backend": "live-mcp",
            "run_id": None,
            "evidence_ref": self._evidence_ref(normalized, window),
        }

    async def compare_service_baseline(
        self,
        service: str,
        minutes: int = 30,
        *,
        call: SplunkCall | None = None,
    ) -> dict[str, Any]:
        if await self._supports_rich_tool("compare_service_baseline"):
            return await self._invoke(
                "compare_service_baseline",
                {"service": service, "minutes": minutes},
                "Compare with baseline",
                call,
            )
        normalized = _safe_value(service, "service")
        window = min(max(minutes, 5), 90)
        rows = await self._query(
            (
                f"{self._active_base(normalized)} event_type=request earliest=-{window * 2}m "
                f'| eval period=if(_time>=relative_time(now(),"-{window}m"),"current","baseline") '
                "| stats count as requests count(eval(tonumber(status_code)>=500)) as errors "
                "perc50(duration_ms) as p50_ms perc95(duration_ms) as p95_ms by period "
                "| eval error_rate_pct=if(requests=0,0,round(errors*100/requests,1))"
            ),
            title="Compare with baseline",
            call=call,
            earliest_time=f"-{window * 2}m",
            row_limit=10,
        )
        metrics = _metrics_by_period(rows)
        current = metrics.get("current", _empty_metrics())
        baseline = metrics.get("baseline", _empty_metrics())
        return {
            "service": normalized,
            "window_minutes": window,
            "current": current,
            "baseline": baseline,
            "assessment": (
                f"Error rate is {current['error_rate_pct']:.1f}% versus "
                f"{baseline['error_rate_pct']:.1f}% in the preceding window; p95 latency is "
                f"{current['p95_ms']} ms versus {baseline['p95_ms']} ms."
            ),
            "backend": "live-mcp",
            "run_id": None,
            "evidence_ref": self._evidence_ref(normalized, window),
        }

    async def search_logs(
        self,
        service: str,
        keywords: str = "",
        minutes: int = 30,
        limit: int = 20,
        *,
        call: SplunkCall | None = None,
    ) -> dict[str, Any]:
        if await self._supports_rich_tool("search_logs"):
            return await self._invoke(
                "search_logs",
                {
                    "service": service,
                    "keywords": keywords,
                    "minutes": minutes,
                    "limit": limit,
                },
                "Find correlated errors",
                call,
            )
        normalized = _safe_value(service, "service")
        window = min(max(minutes, 5), 90)
        result_limit = min(max(limit, 1), 50)
        terms = _KEYWORD.findall(keywords)[:8]
        term_clause = " ".join(_spl_literal(term) for term in terms)
        rows = await self._query(
            (
                f"{self._active_base(normalized)} earliest=-{window}m {term_clause} "
                '| eval trace_priority=if(match(trace_id,"^tr-hot-"),0,1) '
                f"| sort 0 trace_priority - _time | head {result_limit} "
                "| table _time service level event_type message status_code duration_ms "
                "host trace_id version"
            ),
            title="Find correlated errors",
            call=call,
            earliest_time=f"-{window}m",
            row_limit=result_limit,
        )
        events = [_event(row) for row in rows]
        patterns = Counter(_error_pattern(event.get("message") or "") for event in events)
        return {
            "service": normalized,
            "keywords": keywords,
            "window_minutes": window,
            "match_count_returned": len(events),
            "top_patterns": [
                {"pattern": pattern, "count": count}
                for pattern, count in patterns.most_common(3)
            ],
            "events": events,
            "backend": "live-mcp",
            "run_id": None,
            "evidence_ref": (
                f"splunk://search?app={self.settings.splunk_app}&service={quote(normalized)}"
                f"&q={quote(keywords or '*')}&earliest=-{window}m"
            ),
        }

    async def trace_request(
        self,
        trace_id: str,
        *,
        call: SplunkCall | None = None,
    ) -> dict[str, Any]:
        if await self._supports_rich_tool("trace_request"):
            return await self._invoke(
                "trace_request",
                {"trace_id": trace_id},
                "Follow a failed request",
                call,
            )
        normalized = _safe_value(trace_id, "trace_id")
        rows = await self._query(
            (
                f"{self._active_base()} trace_id={_spl_literal(normalized)} "
                "| sort _time | table _time service level event_type message status_code "
                "duration_ms host trace_id version"
            ),
            title="Follow a failed request",
            call=call,
            earliest_time="-7d",
            row_limit=100,
        )
        events = [_event(row) for row in rows]
        return {
            "trace_id": normalized,
            "found": bool(events),
            "events": events,
            "backend": "live-mcp",
            "run_id": None,
            "evidence_ref": f"splunk://trace/{quote(normalized)}",
        }


def _safe_value(value: str, label: str) -> str:
    normalized = value.strip()
    if not _SAFE_VALUE.fullmatch(normalized):
        raise ValueError(f"{label} contains unsupported characters")
    return normalized


def _spl_literal(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _integer(value: Any) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return round(float(value or 0), 1)
    except (TypeError, ValueError):
        return 0.0


def _empty_metrics() -> dict[str, Any]:
    return {"requests": 0, "errors": 0, "error_rate_pct": 0.0, "p50_ms": 0, "p95_ms": 0}


def _metrics_by_period(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row["period"]): {
            "requests": _integer(row.get("requests")),
            "errors": _integer(row.get("errors")),
            "error_rate_pct": _number(row.get("error_rate_pct")),
            "p50_ms": _integer(row.get("p50_ms")),
            "p95_ms": _integer(row.get("p95_ms")),
        }
        for row in rows
        if row.get("period")
    }


def _event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": row.get("_time"),
        "service": row.get("service"),
        "level": row.get("level"),
        "event_type": row.get("event_type"),
        "message": row.get("message"),
        "status_code": _integer(row.get("status_code")),
        "duration_ms": _integer(row.get("duration_ms")),
        "host": row.get("host"),
        "trace_id": row.get("trace_id"),
        "version": row.get("version"),
    }


def _error_pattern(message: str) -> str:
    if "connection pool exhausted" in message.lower():
        return "inventory-client connection pool exhausted"
    if "request completed" in message.lower():
        return "request completed"
    return message[:80] or "unknown"
