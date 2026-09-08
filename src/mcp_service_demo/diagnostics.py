from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit, urlunsplit

_GENERIC_WRAPPERS = {
    "Connection error.",
    "unhandled errors in a TaskGroup",
}
_URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+@")


def exception_details(error: BaseException, *, secrets: Iterable[str] = ()) -> list[str]:
    """Return useful, deduplicated leaf errors from exception groups and cause chains."""
    redactions = tuple(secret for secret in secrets if secret)
    visited: set[int] = set()
    seen_messages: set[str] = set()
    details: list[str] = []

    def visit(current: BaseException) -> None:
        if id(current) in visited:
            return
        visited.add(id(current))

        if isinstance(current, BaseExceptionGroup):
            for nested in current.exceptions:
                visit(nested)
        else:
            message = " ".join(str(current).split()).strip()
            for secret in redactions:
                message = message.replace(secret, "***")
            message = _URL_CREDENTIALS.sub(r"\1***@", message)
            if message and message not in _GENERIC_WRAPPERS and message not in seen_messages:
                seen_messages.add(message)
                details.append(f"{current.__class__.__name__}: {message}"[:600])

        cause = current.__cause__
        if cause is not None:
            visit(cause)
        elif current.__context__ is not None and not current.__suppress_context__:
            visit(current.__context__)

    visit(error)
    return details or [error.__class__.__name__]


def safe_endpoint(url: str) -> str:
    """Return an endpoint suitable for diagnostics without credentials, query, or fragment."""
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname or "configured-host"
        host = f"[{hostname}]" if ":" in hostname else hostname
        netloc = f"{host}:{parsed.port}" if parsed.port is not None else host
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except ValueError:
        return "the configured URL"
