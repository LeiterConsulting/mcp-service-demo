from __future__ import annotations

import os
import stat

import pytest

from mcp_service_demo.config import get_environment_settings, get_settings
from mcp_service_demo.connection_settings import MASK, SplunkConnectionStore
from mcp_service_demo.storage import DemoStore


def base_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))
    monkeypatch.setenv("AGENT_MODE", "guided")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
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


def test_demo_reset_preserves_saved_splunk_profile(monkeypatch, tmp_path):
    base = base_settings(monkeypatch, tmp_path)
    connection_store = SplunkConnectionStore.for_settings(base)
    connection_store.save(
        base,
        {
            "data_mode": "live",
            "mcp_token": "saved-mcp-secret",
            "hec_token": "saved-hec-secret",
            "openai_api_key": "saved-llm-secret",
            "demo_audience": "security",
        },
    )
    encrypted_before = connection_store.config_path.read_bytes()
    key_before = connection_store.key_path.read_bytes()

    DemoStore(base.database_path).reset()

    assert connection_store.config_path.read_bytes() == encrypted_before
    assert connection_store.key_path.read_bytes() == key_before
    assert connection_store.apply(base).splunk_mcp_token == "saved-mcp-secret"
    assert connection_store.apply(base).splunk_hec_token == "saved-hec-secret"
    assert connection_store.apply(base).openai_api_key == "saved-llm-secret"
    assert connection_store.safe_export_demo()["audience"] == "security"


def test_demo_audience_defaults_to_executive_and_persists(monkeypatch, tmp_path):
    base = base_settings(monkeypatch, tmp_path)
    connection_store = SplunkConnectionStore.for_settings(base)

    assert connection_store.safe_export_demo() == {
        "audience": "executive",
        "source": "default",
    }

    connection_store.save(base, {"demo_audience": "finance"})

    assert connection_store.safe_export_demo() == {
        "audience": "finance",
        "source": "saved profile",
    }


def test_legacy_profile_migrates_to_dedicated_settings_directory(monkeypatch, tmp_path):
    base = base_settings(monkeypatch, tmp_path)
    legacy_store = SplunkConnectionStore.for_settings(base)
    legacy_store.save(
        base,
        {
            "data_mode": "live",
            "mcp_token": "saved-mcp-secret",
            "hec_token": "saved-hec-secret",
        },
    )

    config_directory = tmp_path / "config"
    monkeypatch.setenv("DEMO_SPLUNK_CONFIG_PATH", str(config_directory / "splunk-connection.enc"))
    monkeypatch.setenv(
        "DEMO_SPLUNK_CONFIG_KEY_PATH", str(config_directory / ".splunk-connection.key")
    )
    migrated_store = SplunkConnectionStore.for_settings(base)
    effective = migrated_store.apply(base)

    assert effective.splunk_mcp_token == "saved-mcp-secret"
    assert effective.splunk_hec_token == "saved-hec-secret"
    assert migrated_store.config_path.is_file()
    assert migrated_store.key_path.is_file()
    assert legacy_store.config_path.is_file()
    assert legacy_store.key_path.is_file()


def test_saved_llm_connection_is_encrypted_masked_and_applied(monkeypatch, tmp_path):
    base = base_settings(monkeypatch, tmp_path)
    connection_store = SplunkConnectionStore.for_settings(base)

    effective = connection_store.save(
        base,
        {
            "agent_mode": "openai",
            "openai_base_url": "https://llm.example/v1/",
            "openai_api_key": "saved-llm-secret",
            "openai_model": "demo-model",
        },
    )
    exported = connection_store.safe_export_llm(base)

    assert effective.agent_mode == "openai"
    assert effective.openai_base_url == "https://llm.example/v1"
    assert effective.openai_api_key == "saved-llm-secret"
    assert effective.openai_model == "demo-model"
    assert exported["api_key"] == MASK
    assert exported["api_key_configured"] is True
    assert exported["active_mode"] == "openai"
    assert b"saved-llm-secret" not in connection_store.config_path.read_bytes()


def test_blank_llm_api_key_preserves_existing_value(monkeypatch, tmp_path):
    base = base_settings(monkeypatch, tmp_path)
    connection_store = SplunkConnectionStore.for_settings(base)
    connection_store.save(base, {"openai_api_key": "first-key"})

    effective = connection_store.save(
        base,
        {
            "agent_mode": "guided",
            "openai_api_key": "",
            "openai_model": "next-model",
        },
    )

    assert effective.openai_api_key == "first-key"
    assert effective.openai_model == "next-model"
    assert effective.agent_mode == "guided"
