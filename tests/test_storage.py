from __future__ import annotations

from datetime import UTC, datetime

from mcp_service_demo.storage import DemoStore


def test_seeded_scenario_has_a_measurable_checkout_incident(tmp_path):
    store = DemoStore(tmp_path / "demo.db")
    store.reset(now=datetime(2026, 9, 1, 16, 0, tzinfo=UTC))

    health = store.get_service_health("checkout-api", minutes=30)

    assert health["state"] == "degraded"
    assert health["metrics"]["error_rate_pct"] > 15
    assert health["metrics"]["p95_ms"] > 3000
    assert health["baseline"]["error_rate_pct"] == 0
    assert health["recent_changes"][0]["version"] == "4.18.2"


def test_log_search_and_trace_are_derived_from_seeded_events(tmp_path):
    store = DemoStore(tmp_path / "demo.db")
    store.reset(now=datetime(2026, 9, 1, 16, 0, tzinfo=UTC))

    logs = store.search_logs("checkout-api", "ERROR 503", minutes=30, limit=5)
    trace = store.trace_request(logs["events"][0]["trace_id"])

    assert logs["match_count_returned"] == 5
    assert logs["top_patterns"][0]["pattern"] == "inventory-client connection pool exhausted"
    assert trace["found"] is True
    assert trace["events"]


def test_work_note_is_a_real_ticket_write(tmp_path):
    store = DemoStore(tmp_path / "demo.db")
    store.reset(now=datetime(2026, 9, 1, 16, 0, tzinfo=UTC))

    note = store.add_work_note(
        "inc-1042",
        "Evidence supports a checkout degradation.",
        ["splunk://search?service=checkout-api&earliest=-30m"],
    )
    ticket = store.get_ticket("INC-1042")

    assert note["kind"] == "work_note"
    assert ticket is not None
    assert ticket["status"] == "Investigating"
    assert ticket["notes"][-1]["evidence_refs"] == [
        "splunk://search?service=checkout-api&earliest=-30m"
    ]
