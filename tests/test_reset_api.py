from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from mcp_service_demo import api as api_module


def test_fixture_reset_reports_authoritative_data_mode(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "get_settings",
        lambda: SimpleNamespace(splunk_data_mode="fixture"),
    )
    monkeypatch.setattr(
        api_module.store,
        "reset",
        lambda: {"status": "reset", "ticket": "INC-1042"},
    )

    response = TestClient(api_module.app).post("/api/demo/reset", json={})

    assert response.status_code == 200
    assert response.json() == {
        "status": "reset",
        "ticket": "INC-1042",
        "data_mode": "fixture",
        "settings_preserved": True,
        "splunk_settings_preserved": True,
    }
