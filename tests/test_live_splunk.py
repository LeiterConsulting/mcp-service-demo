from __future__ import annotations

import json
import tarfile
from datetime import UTC, datetime

import httpx

from mcp_service_demo.cli import package_splunk_app
from mcp_service_demo.config import get_settings
from mcp_service_demo.scenario import SplunkHECClient, seed_splunk_scenario
from mcp_service_demo.splunk_backend import LiveSplunkBackend, SplunkRestClient
from mcp_service_demo.storage import DemoStore


def live_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))
    monkeypatch.setenv("SPLUNK_DATA_MODE", "live")
    monkeypatch.setenv("SPLUNK_REST_URL", "https://splunk.example:8089")
    monkeypatch.setenv("SPLUNK_REST_TOKEN", "rest-secret")
    monkeypatch.setenv("SPLUNK_REST_TOKEN_SCHEME", "Bearer")
    monkeypatch.setenv("SPLUNK_HEC_URL", "https://splunk.example:8088")
    monkeypatch.setenv("SPLUNK_HEC_TOKEN", "hec-secret")
    monkeypatch.setenv("SPLUNK_REST_VERIFY_SSL", "true")
    monkeypatch.setenv("SPLUNK_HEC_VERIFY_SSL", "true")
    return get_settings()


def test_rest_client_uses_v2_export_and_bearer_auth(monkeypatch, tmp_path):
    settings = live_settings(monkeypatch, tmp_path)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text='{"result":{"service":"checkout-api"}}\n'
            '{"result":{"service":"inventory-api"}}\n',
        )

    client = SplunkRestClient(settings, transport=httpx.MockTransport(handler))
    rows = client.search('search index="mcp_demo" | stats count by service')

    assert rows == [
        {"service": "checkout-api"},
        {"service": "inventory-api"},
    ]
    assert requests[0].url.path == "/servicesNS/nobody/mcp_service_demo/search/v2/jobs/export"
    assert requests[0].headers["Authorization"] == "Bearer rest-secret"
    assert b"output_mode=json" in requests[0].content


def test_live_health_queries_are_scoped_to_the_latest_demo_run(monkeypatch, tmp_path):
    settings = live_settings(monkeypatch, tmp_path)

    class FakeRestClient:
        searches: list[str]

        def __init__(self):
            self.searches = []

        def search(self, spl: str):
            self.searches.append(spl)
            if "stats max(_time) as latest" in spl:
                return [{"demo_run_id": "demo-123", "events": "42"}]
            if "stats count as requests" in spl and "by period" in spl:
                return [
                    {
                        "period": "current",
                        "requests": "100",
                        "errors": "12",
                        "error_rate_pct": "12.0",
                        "p50_ms": "850",
                        "p95_ms": "2800",
                    },
                    {
                        "period": "baseline",
                        "requests": "100",
                        "errors": "0",
                        "error_rate_pct": "0",
                        "p50_ms": "210",
                        "p95_ms": "260",
                    },
                ]
            if "bin _time span=5m" in spl:
                return [{"label": "12:30", "error_rate_pct": "12", "p95_ms": "2800"}]
            if "event_type=deployment" in spl:
                return [
                    {
                        "_time": "2026-09-01T12:00:00Z",
                        "message": "deployment completed version=4.18.2",
                        "version": "4.18.2",
                        "host": "deploy-controller-1",
                    }
                ]
            raise AssertionError(f"Unexpected SPL: {spl}")

    fake = FakeRestClient()
    health = LiveSplunkBackend(settings, client=fake).get_service_health(
        "checkout-api", 30
    )

    assert health["state"] == "degraded"
    assert health["metrics"]["error_rate_pct"] == 12.0
    assert health["run_id"] == "demo-123"
    assert all('demo_run_id="demo-123"' in spl for spl in fake.searches[1:])
    assert all('scenario_id="checkout-degradation-v1"' in spl for spl in fake.searches)


def test_hec_payload_includes_scenario_and_run_metadata(monkeypatch, tmp_path):
    settings = live_settings(monkeypatch, tmp_path)
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"text": "Success", "code": 0})

    publisher = SplunkHECClient(settings, transport=httpx.MockTransport(handler))
    published = publisher.publish(
        [
            {
                "timestamp": datetime(2026, 9, 1, 12, tzinfo=UTC).isoformat(),
                "service": "checkout-api",
                "level": "ERROR",
                "event_type": "request",
                "message": "connection pool exhausted",
                "status_code": 503,
                "duration_ms": 4200,
                "host": "checkout-api-1",
                "trace_id": "tr-hot-1",
                "version": "4.18.2",
            }
        ],
        "demo-123",
    )

    body = json.loads(captured[0].content)
    assert published == 1
    assert captured[0].url.path == "/services/collector/event"
    assert captured[0].headers["Authorization"] == "Splunk hec-secret"
    assert body["index"] == "mcp_demo"
    assert body["sourcetype"] == "mcp:demo:event"
    assert body["event"]["scenario_id"] == "checkout-degradation-v1"
    assert body["event"]["demo_run_id"] == "demo-123"


def test_seed_resets_ticket_data_and_publishes_full_event_stream(monkeypatch, tmp_path):
    settings = live_settings(monkeypatch, tmp_path)
    store = DemoStore(settings.database_path)

    class FakePublisher:
        def __init__(self):
            self.events = []
            self.run_id = ""

        def publish(self, events, run_id):
            self.events = events
            self.run_id = run_id
            return len(events)

    publisher = FakePublisher()
    result = seed_splunk_scenario(
        settings,
        store,
        hec_client=publisher,
        wait_for_index=False,
    )

    assert result["ticket"] == "INC-1042"
    assert result["events_published"] == len(publisher.events)
    assert result["events_published"] > 2_000
    assert publisher.run_id == result["demo_run_id"]
    assert store.get_ticket("INC-1042")["status"] == "New"


def test_companion_app_packages_with_required_configuration(tmp_path, monkeypatch):
    repository_root = __import__("pathlib").Path(__file__).parents[1]
    monkeypatch.chdir(repository_root)
    output = package_splunk_app(tmp_path / "mcp_service_demo.tar.gz")

    with tarfile.open(output) as archive:
        names = set(archive.getnames())

    assert "mcp_service_demo/default/app.conf" in names
    assert "mcp_service_demo/default/indexes.conf" in names
    assert "mcp_service_demo/default/savedsearches.conf" in names
    assert "mcp_service_demo/default/data/ui/views/mcp_demo.xml" in names
