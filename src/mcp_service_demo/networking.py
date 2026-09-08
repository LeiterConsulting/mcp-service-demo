from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

CONTAINER_HOST_ALIAS = "host.docker.internal"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def is_containerized() -> bool:
    """Return whether external loopback URLs need Docker host routing."""
    return os.getenv("DEMO_CONTAINERIZED", "").strip().lower() in {"1", "true", "yes", "on"}


def external_runtime_url(configured_url: str) -> str:
    """Route host-local service URLs out of the demo container while preserving saved input."""
    if not is_containerized():
        return configured_url
    parsed = urlsplit(configured_url)
    if (parsed.hostname or "").lower() not in _LOOPBACK_HOSTS:
        return configured_url

    userinfo = parsed.netloc.rsplit("@", 1)[0] + "@" if "@" in parsed.netloc else ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    return urlunsplit(
        (
            parsed.scheme,
            f"{userinfo}{CONTAINER_HOST_ALIAS}{port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def is_bundled_mcp_url(configured_url: str, bundled_port: int) -> bool:
    """Identify the MCP endpoint served inside the all-in-one demo container."""
    parsed = urlsplit(configured_url)
    return (
        (parsed.hostname or "").lower() in _LOOPBACK_HOSTS
        and parsed.port == bundled_port
        and parsed.path.rstrip("/") == "/mcp"
    )
