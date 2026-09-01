from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from .config import Settings
from .storage import DemoStore

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_KEYWORD = re.compile(r"[A-Za-z0-9_.:-]+")


class SplunkBackend(Protocol):
    mode: str

    def status(self) -> dict[str, Any]: ...

    def list_services(self) -> dict[str, Any]: ...

    def get_service_health(self, service: str, minutes: int = 30) -> dict[str, Any]: ...

    def search_logs(
        self, service: str, keywords: str = "", minutes: int = 30, limit: int = 20
    ) -> dict[str, Any]: ...

    def compare_service_baseline(self, service: str, minutes: int = 30) -> dict[str, Any]: ...

    def trace_request(self, trace_id: str) -> dict[str, Any]: ...


class SplunkConnectionError(RuntimeError):
    """Raised when the live Splunk API cannot be reached or queried."""


@dataclass
class FixtureSplunkBackend:
    store: DemoStore
    mode: str = "fixture"

    def status(self) -> dict[str, Any]:
        self.store.ensure_seeded()
        return {
            "ready": True,
            "mode": self.mode,
            "source": "local synthetic event store",
            "scenario_id": "checkout-degradation-v1",
            "active_run_id": "local-fixture",
        }

    def list_services(self) -> dict[str, Any]:
        return {
            "services": self.store.list_services(),
            "backend": self.mode,
            "run_id": "local-fixture",
        }

    def get_service_health(self, service: str, minutes: int = 30) -> dict[str, Any]:
        result = self.store.get_service_health(service, minutes)
        return {**result, "backend": self.mode, "run_id": "local-fixture"}

    def search_logs(
        self, service: str, keywords: str = "", minutes: int = 30, limit: int = 20
    ) -> dict[str, Any]:
        result = self.store.search_logs(service, keywords, minutes, limit)
        return {**result, "backend": self.mode, "run_id": "local-fixture"}

    def compare_service_baseline(self, service: str, minutes: int = 30) -> dict[str, Any]:
        result = self.store.compare_service_baseline(service, minutes)
        return {**result, "backend": self.mode, "run_id": "local-fixture"}

    def trace_request(self, trace_id: str) -> dict[str, Any]:
        result = self.store.trace_request(trace_id)
        return {**result, "backend": self.mode, "run_id": "local-fixture"}


class SplunkRestClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        for label, value in (
            ("SPLUNK_APP", self.settings.splunk_app),
            ("SPLUNK_OWNER", self.settings.splunk_owner),
            ("SPLUNK_INDEX", self.settings.splunk_index),
            ("SPLUNK_SOURCETYPE", self.settings.splunk_sourcetype),
            ("SPLUNK_SCENARIO_ID", self.settings.splunk_scenario_id),
        ):
            if not _SAFE_NAME.fullmatch(value):
                raise ValueError(f"{label} contains unsupported characters")
        if not self.settings.splunk_rest_configured:
            raise ValueError(
                "Live Splunk mode requires SPLUNK_REST_TOKEN or SPLUNK_USERNAME/SPLUNK_PASSWORD"
            )

    def _client(self) -> httpx.Client:
        headers = {"Accept": "application/json"}
        auth: tuple[str, str] | None = None
        if self.settings.splunk_rest_token:
            headers["Authorization"] = (
                f"{self.settings.splunk_rest_token_scheme} "
                f"{self.settings.splunk_rest_token}"
            )
        elif self.settings.splunk_username and self.settings.splunk_password:
            auth = (self.settings.splunk_username, self.settings.splunk_password)
        return httpx.Client(
            base_url=self.settings.splunk_rest_url,
            headers=headers,
            auth=auth,
            verify=self.settings.splunk_rest_verify,
            timeout=self.settings.splunk_search_timeout_seconds,
            transport=self.transport,
        )

    def server_info(self) -> dict[str, Any]:
        with self._client() as client:
            response = client.get("/services/server/info", params={"output_mode": "json"})
        self._raise_for_status(response, "read Splunk server information")
        payload = response.json()
        entries = payload.get("entry", []) if isinstance(payload, dict) else []
        content = entries[0].get("content", {}) if entries else {}
        return {
            "server_name": content.get("serverName") or content.get("server_name"),
            "version": content.get("version"),
            "build": content.get("build"),
        }

    def search(self, spl: str) -> list[dict[str, Any]]:
        owner = quote(self.settings.splunk_owner, safe="")
        app = quote(self.settings.splunk_app, safe="")
        endpoint = f"/servicesNS/{owner}/{app}/search/v2/jobs/export"
        with self._client() as client:
            response = client.post(
                endpoint,
                data={"search": spl, "output_mode": "json"},
            )
        self._raise_for_status(response, "run a Splunk search")
        return self._parse_export(response.text)

    @staticmethod
    def _raise_for_status(response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        detail = response.text.strip().replace("\n", " ")[:400]
        raise SplunkConnectionError(
            f"Unable to {action}: Splunk returned HTTP {response.status_code}. {detail}"
        )

    @staticmethod
    def _parse_export(body: str) -> list[dict[str, Any]]:
        text = body.strip()
        if not text:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            if isinstance(payload.get("results"), list):
                return payload["results"]
            if isinstance(payload.get("result"), dict):
                return [payload["result"]]
        if isinstance(payload, list):
            return [item.get("result", item) for item in payload if isinstance(item, dict)]

        results: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SplunkConnectionError(
                    "Splunk returned an unreadable search response"
                ) from exc
            if isinstance(item, dict) and isinstance(item.get("result"), dict):
                results.append(item["result"])
        return results


class LiveSplunkBackend:
    mode = "live"

    def __init__(self, settings: Settings, client: SplunkRestClient | None = None):
        self.settings = settings
        self.client = client or SplunkRestClient(settings)

    def status(self) -> dict[str, Any]:
        server = self.client.server_info()
        active = self._latest_run(required=False)
        return {
            "ready": bool(active),
            "mode": self.mode,
            "source": self.settings.splunk_rest_url,
            "server": server,
            "index": self.settings.splunk_index,
            "sourcetype": self.settings.splunk_sourcetype,
            "scenario_id": self.settings.splunk_scenario_id,
            "active_run_id": active.get("demo_run_id") if active else None,
            "event_count": _integer(active.get("events")) if active else 0,
        }

    def list_services(self) -> dict[str, Any]:
        run_id = self._latest_run_id()
        rows = self.client.search(
            f"{self._base(run_id)} | stats count as event_count max(_time) as last_seen "
            "by service | sort service"
        )
        return {
            "services": [row["service"] for row in rows if row.get("service")],
            "details": rows,
            "backend": self.mode,
            "run_id": run_id,
        }

    def get_service_health(self, service: str, minutes: int = 30) -> dict[str, Any]:
        normalized = _safe_tool_value(service, "service")
        window = min(max(minutes, 5), 90)
        run_id = self._latest_run_id()
        metrics = self._metrics(run_id, normalized, window)
        current = metrics.get("current", _empty_metrics())
        baseline = metrics.get("baseline", _empty_metrics())
        timeline_rows = self.client.search(
            f"{self._base(run_id, normalized)} event_type=request earliest=-{window}m "
            "| bin _time span=5m | stats count as requests "
            "count(eval(tonumber(status_code)>=500)) as errors "
            "perc95(duration_ms) as p95_ms by _time "
            "| eval error_rate_pct=if(requests=0,0,round(errors*100/requests,1)) "
            '| eval label=strftime(_time,"%H:%M") | sort _time'
        )
        changes = self.client.search(
            f"{self._base(run_id, normalized)} event_type=deployment "
            f"earliest=-{window + 10}m | sort 0 - _time | head 10 "
            "| table _time message version host"
        )
        state = (
            "degraded"
            if current["error_rate_pct"] >= 5 or current["p95_ms"] >= 1500
            else "healthy"
        )
        return {
            "service": normalized,
            "window_minutes": window,
            "state": state,
            "metrics": current,
            "baseline": baseline,
            "change": {
                "error_rate_points": round(
                    current["error_rate_pct"] - baseline["error_rate_pct"], 1
                ),
                "p95_ms": current["p95_ms"] - baseline["p95_ms"],
            },
            "timeline": [
                {
                    "label": row.get("label") or row.get("_time"),
                    "error_rate_pct": _number(row.get("error_rate_pct")),
                    "p95_ms": _integer(row.get("p95_ms")),
                }
                for row in timeline_rows
            ],
            "recent_changes": [
                {
                    "timestamp": row.get("_time"),
                    "message": row.get("message"),
                    "version": row.get("version"),
                    "host": row.get("host"),
                }
                for row in changes
            ],
            "backend": self.mode,
            "run_id": run_id,
            "evidence_ref": self._evidence_ref(normalized, window, run_id),
        }

    def compare_service_baseline(self, service: str, minutes: int = 30) -> dict[str, Any]:
        normalized = _safe_tool_value(service, "service")
        window = min(max(minutes, 5), 90)
        run_id = self._latest_run_id()
        metrics = self._metrics(run_id, normalized, window)
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
            "backend": self.mode,
            "run_id": run_id,
            "evidence_ref": self._evidence_ref(normalized, window, run_id),
        }

    def search_logs(
        self,
        service: str,
        keywords: str = "",
        minutes: int = 30,
        limit: int = 20,
    ) -> dict[str, Any]:
        normalized = _safe_tool_value(service, "service")
        window = min(max(minutes, 5), 90)
        result_limit = min(max(limit, 1), 50)
        run_id = self._latest_run_id()
        terms = _KEYWORD.findall(keywords)[:8]
        term_clause = " ".join(_spl_literal(term) for term in terms)
        rows = self.client.search(
            f"{self._base(run_id, normalized)} earliest=-{window}m {term_clause} "
            f"| sort 0 - _time | head {result_limit} "
            "| table _time service level event_type message status_code duration_ms "
            "host trace_id version"
        )
        events = [
            {
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
            for row in rows
        ]
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
            "backend": self.mode,
            "run_id": run_id,
            "evidence_ref": (
                f"splunk://search?app={self.settings.splunk_app}&service={normalized}"
                f"&q={quote(keywords or '*')}&earliest=-{window}m&run={run_id}"
            ),
        }

    def trace_request(self, trace_id: str) -> dict[str, Any]:
        normalized = _safe_tool_value(trace_id, "trace_id")
        run_id = self._latest_run_id()
        rows = self.client.search(
            f"{self._base(run_id)} trace_id={_spl_literal(normalized)} "
            "| sort _time | table _time service level event_type message status_code "
            "duration_ms host trace_id version"
        )
        events = [
            {
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
            for row in rows
        ]
        return {
            "trace_id": normalized,
            "found": bool(events),
            "events": events,
            "backend": self.mode,
            "run_id": run_id,
            "evidence_ref": f"splunk://trace/{normalized}?run={run_id}",
        }

    def _metrics(self, run_id: str, service: str, window: int) -> dict[str, dict[str, Any]]:
        rows = self.client.search(
            f"{self._base(run_id, service)} event_type=request earliest=-{window * 2}m "
            f'| eval period=if(_time>=relative_time(now(),"-{window}m"),"current","baseline") '
            "| stats count as requests count(eval(tonumber(status_code)>=500)) as errors "
            "perc50(duration_ms) as p50_ms perc95(duration_ms) as p95_ms by period "
            "| eval error_rate_pct=if(requests=0,0,round(errors*100/requests,1))"
        )
        return {
            row["period"]: {
                "requests": _integer(row.get("requests")),
                "errors": _integer(row.get("errors")),
                "error_rate_pct": _number(row.get("error_rate_pct")),
                "p50_ms": _integer(row.get("p50_ms")),
                "p95_ms": _integer(row.get("p95_ms")),
            }
            for row in rows
            if row.get("period")
        }

    def _latest_run(self, required: bool = True) -> dict[str, Any] | None:
        rows = self.client.search(
            f"search index={_spl_literal(self.settings.splunk_index)} "
            f"sourcetype={_spl_literal(self.settings.splunk_sourcetype)} "
            f"scenario_id={_spl_literal(self.settings.splunk_scenario_id)} earliest=-7d "
            "| stats max(_time) as latest count as events by demo_run_id "
            "| sort 0 - latest | head 1"
        )
        if rows and rows[0].get("demo_run_id"):
            return rows[0]
        if required:
            raise SplunkConnectionError(
                "No seeded MCP demo run was found in Splunk. Run 'mcp-service-demo seed-splunk'."
            )
        return None

    def _latest_run_id(self) -> str:
        latest = self._latest_run()
        assert latest is not None
        return str(latest["demo_run_id"])

    def _base(self, run_id: str, service: str | None = None) -> str:
        parts = [
            "search",
            f"index={_spl_literal(self.settings.splunk_index)}",
            f"sourcetype={_spl_literal(self.settings.splunk_sourcetype)}",
            f"scenario_id={_spl_literal(self.settings.splunk_scenario_id)}",
            f"demo_run_id={_spl_literal(run_id)}",
        ]
        if service:
            parts.append(f"service={_spl_literal(service)}")
        return " ".join(parts)

    def _evidence_ref(self, service: str, window: int, run_id: str) -> str:
        return (
            f"splunk://search?app={self.settings.splunk_app}&service={service}"
            f"&earliest=-{window}m&run={run_id}"
        )


def create_splunk_backend(
    settings: Settings,
    *,
    rest_client: SplunkRestClient | None = None,
) -> SplunkBackend:
    if settings.splunk_data_mode == "fixture":
        store = DemoStore(settings.database_path)
        store.ensure_seeded()
        return FixtureSplunkBackend(store)
    return LiveSplunkBackend(settings, client=rest_client)


def _safe_tool_value(value: str, label: str) -> str:
    normalized = value.strip()
    if not _SAFE_NAME.fullmatch(normalized):
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


def _error_pattern(message: str) -> str:
    if "connection pool exhausted" in message.lower():
        return "inventory-client connection pool exhausted"
    if "request completed" in message.lower():
        return "request completed"
    return message[:80] or "unknown"
