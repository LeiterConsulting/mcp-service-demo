from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _default_database_path() -> Path:
    return Path.cwd() / "data" / "demo.db"


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
    ticket_mcp_url: str
    openai_api_key: str | None
    openai_model: str

    @property
    def agent_mode(self) -> str:
        return "openai" if self.openai_api_key else "guided"


def get_settings() -> Settings:
    splunk_port = int(os.getenv("SPLUNK_MCP_PORT", "8101"))
    ticket_port = int(os.getenv("TICKET_MCP_PORT", "8102"))
    return Settings(
        database_path=Path(os.getenv("DEMO_DATABASE_PATH", _default_database_path())),
        web_host=os.getenv("DEMO_WEB_HOST", "127.0.0.1"),
        web_port=int(os.getenv("DEMO_WEB_PORT", "8100")),
        splunk_mcp_host=os.getenv("SPLUNK_MCP_HOST", "127.0.0.1"),
        splunk_mcp_port=splunk_port,
        ticket_mcp_host=os.getenv("TICKET_MCP_HOST", "127.0.0.1"),
        ticket_mcp_port=ticket_port,
        splunk_mcp_url=os.getenv("SPLUNK_MCP_URL", f"http://127.0.0.1:{splunk_port}/mcp"),
        ticket_mcp_url=os.getenv("TICKET_MCP_URL", f"http://127.0.0.1:{ticket_port}/mcp"),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    )
