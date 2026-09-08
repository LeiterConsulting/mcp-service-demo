from __future__ import annotations

from mcp_service_demo.diagnostics import exception_details, safe_endpoint


def test_exception_details_unwraps_generic_connection_error_and_redacts_secret():
    root = OSError(
        "TLS verification failed while using secret-key via https://proxy-user:proxy-pass@proxy.test"
    )
    wrapped = RuntimeError("Connection error.")
    wrapped.__cause__ = root

    assert exception_details(wrapped, secrets=("secret-key",)) == [
        "OSError: TLS verification failed while using *** via https://***@proxy.test"
    ]


def test_safe_endpoint_removes_userinfo_query_and_fragment():
    assert safe_endpoint("https://user:password@example.test:8443/v1?secret=yes#fragment") == (
        "https://example.test:8443/v1"
    )
