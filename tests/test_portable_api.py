from __future__ import annotations

from fastapi.testclient import TestClient

from mcp_service_demo.api import app


def test_portable_profile_api_exports_previews_and_imports(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))
    monkeypatch.setenv("DEMO_SPLUNK_CONFIG_PATH", str(tmp_path / "config" / "profile.enc"))
    monkeypatch.setenv("DEMO_SPLUNK_CONFIG_KEY_PATH", str(tmp_path / "config" / ".profile.key"))
    monkeypatch.setenv("SPLUNK_DATA_MODE", "fixture")
    monkeypatch.setenv("SPLUNK_MCP_URL", "http://127.0.0.1:8101/mcp")
    monkeypatch.setenv("AGENT_MODE", "guided")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = TestClient(app)
    passphrase = "portable-api-passphrase"

    exported = client.post(
        "/api/settings/portable/export",
        json={"passphrase": passphrase},
    )
    assert exported.status_code == 200
    assert exported.headers["cache-control"] == "no-store"
    bundle = exported.json()["bundle"]

    preview = client.post(
        "/api/settings/portable/preview",
        json={"passphrase": passphrase, "bundle": bundle},
    )
    assert preview.status_code == 200
    assert preview.json()["summary"]["splunk"]["data_mode"] == "fixture"
    assert preview.json()["summary"]["llm"]["agent_mode"] == "guided"

    imported = client.post(
        "/api/settings/portable/import",
        json={"passphrase": passphrase, "bundle": bundle},
    )
    assert imported.status_code == 200
    assert imported.json()["settings"]["demo"]["audience"] == "executive"

    rejected = client.post(
        "/api/settings/portable/preview",
        json={"passphrase": "wrong-passphrase", "bundle": bundle},
    )
    assert rejected.status_code == 400
    assert "passphrase" in rejected.json()["detail"]
