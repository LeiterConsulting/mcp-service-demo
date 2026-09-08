from __future__ import annotations

import ssl

import httpx2
from openai import DefaultAsyncHttpx2Client


def openai_http_client(
    verify: bool | str,
    *,
    timeout: float,
) -> httpx2.AsyncClient:
    """Build the OpenAI transport with the demo's explicit TLS policy."""
    tls_verify: bool | ssl.SSLContext = verify
    if isinstance(verify, str):
        tls_verify = ssl.create_default_context(cafile=verify)
    return DefaultAsyncHttpx2Client(
        verify=tls_verify,
        timeout=timeout,
    )
