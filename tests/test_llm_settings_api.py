from __future__ import annotations

from fastapi.testclient import TestClient

import mcp_service_demo.api as api_module


def test_llm_connection_test_reports_root_cause_and_runtime_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_DATABASE_PATH", str(tmp_path / "demo.db"))
    monkeypatch.setenv("DEMO_SPLUNK_CONFIG_PATH", str(tmp_path / "config" / "profile.enc"))
    monkeypatch.setenv("DEMO_SPLUNK_CONFIG_KEY_PATH", str(tmp_path / "config" / ".profile.key"))
    monkeypatch.setenv("DEMO_CONTAINERIZED", "true")

    class FailingOpenAI:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            root = OSError("certificate verify failed")
            wrapped = RuntimeError("Connection error.")
            wrapped.__cause__ = root
            raise wrapped

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(api_module, "AsyncOpenAI", FailingOpenAI)
    response = TestClient(api_module.app).post(
        "/api/settings/llm/test",
        json={
            "agent_mode": "openai",
            "base_url": "https://localhost:11434/v1",
            "api_key": "test-secret-key",
            "model": "local-model",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert "OSError: certificate verify failed" in payload["message"]
    assert "https://host.docker.internal:11434/v1" in payload["message"]
    assert "Connection error." not in payload["message"]
    assert "test-secret-key" not in payload["message"]
