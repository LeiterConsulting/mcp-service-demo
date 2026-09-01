from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _default_database_path() -> Path:
    return Path.cwd() / "data" / "demo.db"


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _tls_verify(prefix: str) -> bool | str:
    ca_bundle = os.getenv(f"{prefix}_CA_BUNDLE")
    return ca_bundle if ca_bundle else _env_bool(f"{prefix}_VERIFY_SSL", True)


@dataclass(frozen=True)
class Settings:
    database_path: Path
    web_host: str
    web_port: int
    splunk_mcp_host: str
    splunk_mcp_port: int
    ticket_mcp_host: str
    ticket_mcp_port: int
    splunk_mcp_url: str
    splunk_mcp_token: str | None
    splunk_mcp_verify: bool | str
    ticket_mcp_url: str
    splunk_data_mode: str
    splunk_rest_url: str
    splunk_rest_token: str | None
    splunk_rest_token_scheme: str
    splunk_username: str | None
    splunk_password: str | None
    splunk_rest_verify: bool | str
    splunk_search_timeout_seconds: float
    splunk_index_wait_seconds: float
    splunk_app: str
    splunk_owner: str
    splunk_index: str
    splunk_sourcetype: str
    splunk_scenario_id: str
    splunk_hec_url: str | None
    splunk_hec_token: str | None
    splunk_hec_verify: bool | str
    splunk_hec_batch_size: int
    openai_api_key: str | None
    openai_model: str

    @property
    def agent_mode(self) -> str:
        return "openai" if self.openai_api_key else "guided"

    @property
    def splunk_rest_configured(self) -> bool:
        return bool(
            self.splunk_rest_url
            and (
                self.splunk_rest_token
                or (self.splunk_username and self.splunk_password)
            )
        )

    @property
    def splunk_hec_configured(self) -> bool:
        return bool(self.splunk_hec_url and self.splunk_hec_token)


def get_environment_settings() -> Settings:
    splunk_port = int(os.getenv("SPLUNK_MCP_PORT", "8101"))
    ticket_port = int(os.getenv("TICKET_MCP_PORT", "8102"))
    splunk_data_mode = os.getenv("SPLUNK_DATA_MODE", "fixture").strip().lower()
    if splunk_data_mode not in {"fixture", "live"}:
        raise ValueError("SPLUNK_DATA_MODE must be 'fixture' or 'live'")
    token_scheme = os.getenv("SPLUNK_REST_TOKEN_SCHEME", "Bearer").strip().title()
    if token_scheme not in {"Bearer", "Splunk"}:
        raise ValueError("SPLUNK_REST_TOKEN_SCHEME must be 'Bearer' or 'Splunk'")

    return Settings(
        database_path=Path(os.getenv("DEMO_DATABASE_PATH", _default_database_path())),
        web_host=os.getenv("DEMO_WEB_HOST", "127.0.0.1"),
        web_port=int(os.getenv("DEMO_WEB_PORT", "8100")),
        splunk_mcp_host=os.getenv("SPLUNK_MCP_HOST", "127.0.0.1"),
        splunk_mcp_port=splunk_port,
        ticket_mcp_host=os.getenv("TICKET_MCP_HOST", "127.0.0.1"),
        ticket_mcp_port=ticket_port,
        splunk_mcp_url=os.getenv("SPLUNK_MCP_URL", f"http://127.0.0.1:{splunk_port}/mcp"),
        splunk_mcp_token=os.getenv("SPLUNK_MCP_TOKEN") or None,
        splunk_mcp_verify=_tls_verify("SPLUNK_MCP"),
        ticket_mcp_url=os.getenv("TICKET_MCP_URL", f"http://127.0.0.1:{ticket_port}/mcp"),
        splunk_data_mode=splunk_data_mode,
        splunk_rest_url=os.getenv("SPLUNK_REST_URL", "https://127.0.0.1:8089").rstrip("/"),
        splunk_rest_token=os.getenv("SPLUNK_REST_TOKEN") or None,
        splunk_rest_token_scheme=token_scheme,
        splunk_username=os.getenv("SPLUNK_USERNAME") or None,
        splunk_password=os.getenv("SPLUNK_PASSWORD") or None,
        splunk_rest_verify=_tls_verify("SPLUNK_REST"),
        splunk_search_timeout_seconds=float(
            os.getenv("SPLUNK_SEARCH_TIMEOUT_SECONDS", "60")
        ),
        splunk_index_wait_seconds=float(os.getenv("SPLUNK_INDEX_WAIT_SECONDS", "30")),
        splunk_app=os.getenv("SPLUNK_APP", "mcp_service_demo"),
        splunk_owner=os.getenv("SPLUNK_OWNER", "nobody"),
        splunk_index=os.getenv("SPLUNK_INDEX", "mcp_demo"),
        splunk_sourcetype=os.getenv("SPLUNK_SOURCETYPE", "mcp:demo:event"),
        splunk_scenario_id=os.getenv(
            "SPLUNK_SCENARIO_ID", "checkout-degradation-v1"
        ),
        splunk_hec_url=(os.getenv("SPLUNK_HEC_URL") or "").rstrip("/") or None,
        splunk_hec_token=os.getenv("SPLUNK_HEC_TOKEN") or None,
        splunk_hec_verify=_tls_verify("SPLUNK_HEC"),
        splunk_hec_batch_size=max(1, int(os.getenv("SPLUNK_HEC_BATCH_SIZE", "200"))),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    )


def get_settings() -> Settings:
    """Return environment defaults with any saved UI connection profile applied."""
    base = get_environment_settings()
    from .connection_settings import SplunkConnectionStore

    return SplunkConnectionStore.for_settings(base).apply(base)
