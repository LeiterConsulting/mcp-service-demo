from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from .config import Settings
from .mcp_client import MCPBroker
from .splunk_backend import LiveSplunkBackend, SplunkConnectionError, SplunkRestClient
from .splunk_mcp_adapter import SplunkMCPAdapter
from .storage import DemoStore


class SplunkHECError(RuntimeError):
    """Raised when the scenario cannot be published through Splunk HEC."""


@dataclass
class SplunkHECClient:
    settings: Settings
    transport: httpx.BaseTransport | None = None

    def __post_init__(self) -> None:
        if not self.settings.splunk_hec_configured:
            raise ValueError("Scenario publication requires SPLUNK_HEC_URL and SPLUNK_HEC_TOKEN")

    @property
    def endpoint(self) -> str:
        base = (self.settings.splunk_hec_url or "").rstrip("/")
        if base.endswith("/services/collector/event"):
            return base
        if base.endswith("/services/collector"):
            return f"{base}/event"
        return f"{base}/services/collector/event"

    def publish(self, events: list[dict[str, Any]], run_id: str) -> int:
        published = 0
        batch_size = self.settings.splunk_hec_batch_size
        with httpx.Client(
            headers={
                "Authorization": f"Splunk {self.settings.splunk_hec_token}",
                "Content-Type": "application/json",
            },
            verify=self.settings.splunk_hec_verify,
            timeout=self.settings.splunk_search_timeout_seconds,
            transport=self.transport,
        ) as client:
            for start in range(0, len(events), batch_size):
                batch = events[start : start + batch_size]
                body = "".join(json.dumps(self._payload(event, run_id)) for event in batch)
                response = client.post(self.endpoint, content=body)
                self._validate_response(response)
                published += len(batch)
        return published

    def _payload(self, event: dict[str, Any], run_id: str) -> dict[str, Any]:
        event_time = datetime.fromisoformat(str(event["timestamp"]))
        fields = {key: value for key, value in event.items() if key != "timestamp"}
        fields.update(
            {
                "scenario_id": self.settings.splunk_scenario_id,
                "demo_run_id": run_id,
            }
        )
        return {
            "time": event_time.timestamp(),
            "host": event["host"],
            "source": "mcp-service-demo",
            "sourcetype": self.settings.splunk_sourcetype,
            "index": self.settings.splunk_index,
            "event": fields,
        }

    @staticmethod
    def _validate_response(response: httpx.Response) -> None:
        if not response.is_success:
            detail = response.text.strip().replace("\n", " ")[:400]
            raise SplunkHECError(
                f"Splunk HEC returned HTTP {response.status_code}. {detail}"
            )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise SplunkHECError("Splunk HEC returned an unreadable response") from exc
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise SplunkHECError(
                "Splunk HEC rejected the event batch: "
                f"{payload.get('text', 'unknown error') if isinstance(payload, dict) else payload}"
            )


def new_run_id() -> str:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return f"demo-{stamp}-{uuid.uuid4().hex[:8]}"


def seed_splunk_scenario(
    settings: Settings,
    store: DemoStore | None = None,
    *,
    hec_client: SplunkHECClient | None = None,
    rest_client: SplunkRestClient | None = None,
    wait_for_index: bool = True,
) -> dict[str, Any]:
    if settings.splunk_data_mode != "live":
        raise ValueError("Set SPLUNK_DATA_MODE=live before publishing a scenario to Splunk")

    publisher = hec_client or SplunkHECClient(settings)
    client = rest_client or SplunkRestClient(settings) if wait_for_index else rest_client
    scenario_store = store or DemoStore(settings.database_path)
    reset = scenario_store.reset()
    run_id = new_run_id()
    events = scenario_store.export_events()
    published = publisher.publish(events, run_id)

    indexed = False
    if wait_for_index:
        assert client is not None
        backend = LiveSplunkBackend(settings, client=client)
        deadline = time.monotonic() + settings.splunk_index_wait_seconds
        while time.monotonic() <= deadline:
            latest = backend._latest_run(required=False)
            if latest and latest.get("demo_run_id") == run_id:
                indexed = True
                break
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
        if not indexed:
            raise SplunkConnectionError(
                f"Published {published} events, but run {run_id} was not searchable within "
                f"{settings.splunk_index_wait_seconds:g} seconds."
            )

    return {
        **reset,
        "status": "published",
        "demo_run_id": run_id,
        "events_published": published,
        "indexed": indexed,
        "index": settings.splunk_index,
        "sourcetype": settings.splunk_sourcetype,
    }


async def seed_splunk_scenario_via_mcp(
    settings: Settings,
    broker: MCPBroker,
    store: DemoStore | None = None,
) -> dict[str, Any]:
    """Publish through HEC, then confirm indexing through the configured MCP search tool."""
    published = await asyncio.to_thread(
        seed_splunk_scenario,
        settings,
        store,
        wait_for_index=False,
    )
    indexed = await SplunkMCPAdapter(settings, broker).wait_for_run(published["demo_run_id"])
    if not indexed:
        raise SplunkConnectionError(
            f"Published {published['events_published']} events, but run "
            f"{published['demo_run_id']} was not searchable through MCP within "
            f"{settings.splunk_index_wait_seconds:g} seconds."
        )
    return {**published, "indexed": True}
