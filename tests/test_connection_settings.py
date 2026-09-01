from __future__ import annotations

import os
import stat

import pytest

from mcp_service_demo.config import get_environment_settings, get_settings
from mcp_service_demo.connection_settings import MASK, SplunkConnectionStore


def base_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))
    monkeypatch.setenv("SPLUNK_DATA_MODE", "fixture")
    monkeypatch.setenv("SPLUNK_MCP_URL", "https://environment-mcp.example/mcp")
    monkeypatch.setenv("SPLUNK_MCP_TOKEN", "environment-mcp-token")
    monkeypatch.setenv("SPLUNK_REST_URL", "https://environment.example:8089")
    monkeypatch.setenv("SPLUNK_REST_TOKEN", "environment-token")
    monkeypatch.setenv("SPLUNK_HEC_URL", "https://environment.example:8088")
    monkeypatch.setenv("SPLUNK_HEC_TOKEN", "environment-hec")
    return get_environment_settings()


def test_saved_connection_is_encrypted_masked_and_applied(monkeypatch, tmp_path):
    base = base_settings(monkeypatch, tmp_path)
    connection_store = SplunkConnectionStore.for_settings(base)

    saved = connection_store.save(
        base,
        {
            "mcp_url": "https://saved-mcp.example/mcp/",
            "mcp_token": "saved-mcp-secret",
            "mcp_verify_ssl": False,
            "data_mode": "live",
            "rest_url": "https://saved.example:8089/",
            "rest_token": "saved-rest-secret",
            "rest_token_scheme": "Splunk",
            "rest_verify_ssl": True,
            "rest_ca_bundle_path": "/certs/customer-ca.pem",
            "hec_url": "https://saved.example:8088/",
            "hec_token": "saved-hec-secret",
            "hec_verify_ssl": False,
        },
    )
    exported = connection_store.safe_export(base)

    assert saved.splunk_mcp_url == "https://saved-mcp.example/mcp"
    assert saved.splunk_mcp_token == "saved-mcp-secret"
    assert saved.splunk_mcp_verify is False
    assert saved.splunk_data_mode == "live"
    assert saved.splunk_rest_url == "https://saved.example:8089"
    assert saved.splunk_rest_token == "saved-rest-secret"
    assert saved.splunk_rest_token_scheme == "Splunk"
    assert saved.splunk_rest_verify == "/certs/customer-ca.pem"
    assert saved.splunk_hec_url == "https://saved.example:8088"
    assert saved.splunk_hec_token == "saved-hec-secret"
    assert saved.splunk_hec_verify is False
    assert exported["rest_token"] == MASK
    assert exported["hec_token"] == MASK
    assert exported["mcp_token"] == MASK
    assert b"saved-mcp-secret" not in connection_store.config_path.read_bytes()
    assert b"saved-rest-secret" not in connection_store.config_path.read_bytes()
    assert b"saved-hec-secret" not in connection_store.config_path.read_bytes()
    if os.name != "nt":
        assert stat.S_IMODE(connection_store.config_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(connection_store.key_path.stat().st_mode) == 0o600

    runtime = get_settings()
    assert runtime.splunk_mcp_url == "https://saved-mcp.example/mcp"
    assert runtime.splunk_mcp_token == "saved-mcp-secret"
    assert runtime.splunk_rest_token == "saved-rest-secret"
    assert runtime.splunk_hec_token == "saved-hec-secret"


def test_blank_secret_fields_preserve_existing_values(monkeypatch, tmp_path):
    base = base_settings(monkeypatch, tmp_path)
    connection_store = SplunkConnectionStore.for_settings(base)
    connection_store.save(
        base,
        {
            "data_mode": "live",
            "mcp_token": "first-mcp",
            "rest_token": "first-token",
            "hec_token": "first-hec",
        },
    )

    updated = connection_store.save(
        base,
        {
            "mcp_token": "",
            "rest_token": "",
            "hec_token": "",
            "rest_url": "https://next.example:8089",
        },
    )

    assert updated.splunk_mcp_token == "first-mcp"
    assert updated.splunk_rest_token == "first-token"
    assert updated.splunk_hec_token == "first-hec"
    assert updated.splunk_rest_url == "https://next.example:8089"


def test_invalid_connection_url_is_rejected_before_write(monkeypatch, tmp_path):
    base = base_settings(monkeypatch, tmp_path)
    connection_store = SplunkConnectionStore.for_settings(base)

    with pytest.raises(ValueError, match="complete http"):
        connection_store.save(base, {"rest_url": "splunk.example:8089"})

    assert not connection_store.config_path.exists()
