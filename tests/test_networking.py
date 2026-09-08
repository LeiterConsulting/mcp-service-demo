from __future__ import annotations

from mcp_service_demo.networking import external_runtime_url, is_bundled_mcp_url


def test_external_loopback_urls_route_through_docker_host(monkeypatch):
    monkeypatch.setenv("DEMO_CONTAINERIZED", "true")

    assert external_runtime_url("https://localhost:8089/services/mcp") == (
        "https://host.docker.internal:8089/services/mcp"
    )
    assert external_runtime_url("https://127.0.0.1:8088/services/collector") == (
        "https://host.docker.internal:8088/services/collector"
    )
    assert external_runtime_url("https://splunk.example:8089/services/mcp") == (
        "https://splunk.example:8089/services/mcp"
    )


def test_native_runtime_preserves_loopback_urls(monkeypatch):
    monkeypatch.delenv("DEMO_CONTAINERIZED", raising=False)

    assert external_runtime_url("https://localhost:8089/services/mcp") == (
        "https://localhost:8089/services/mcp"
    )


def test_bundled_mcp_endpoint_is_distinguished_from_external_splunk():
    assert is_bundled_mcp_url("http://127.0.0.1:8101/mcp", 8101) is True
    assert is_bundled_mcp_url("http://localhost:8101/mcp/", 8101) is True
    assert is_bundled_mcp_url("https://localhost:8089/services/mcp", 8101) is False
