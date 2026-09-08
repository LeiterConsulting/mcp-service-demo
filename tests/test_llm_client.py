from __future__ import annotations

import mcp_service_demo.llm_client as llm_client_module


def test_openai_transport_can_disable_tls_verification(monkeypatch):
    captured = {}
    transport = object()

    def fake_default_client(**kwargs):
        captured.update(kwargs)
        return transport

    monkeypatch.setattr(llm_client_module, "DefaultAsyncHttpx2Client", fake_default_client)

    assert llm_client_module.openai_http_client(False, timeout=20.0) is transport
    assert captured == {"verify": False, "timeout": 20.0}


def test_openai_transport_loads_a_custom_ca_bundle(monkeypatch):
    captured = {}
    tls_context = object()
    transport = object()

    def fake_create_default_context(*, cafile):
        captured["cafile"] = cafile
        return tls_context

    def fake_default_client(**kwargs):
        captured.update(kwargs)
        return transport

    monkeypatch.setattr(
        llm_client_module.ssl,
        "create_default_context",
        fake_create_default_context,
    )
    monkeypatch.setattr(llm_client_module, "DefaultAsyncHttpx2Client", fake_default_client)

    result = llm_client_module.openai_http_client(
        "/app/certs/company-root.pem",
        timeout=45.0,
    )

    assert result is transport
    assert captured == {
        "cafile": "/app/certs/company-root.pem",
        "verify": tls_context,
        "timeout": 45.0,
    }
