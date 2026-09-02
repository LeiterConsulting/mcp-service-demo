from __future__ import annotations

import argparse
import asyncio
import multiprocessing
import signal
import socket
import sys
import tarfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import uvicorn

from .config import Settings, get_settings
from .mcp_client import MCPBroker, MCPRemoteTarget
from .scenario import seed_splunk_scenario, seed_splunk_scenario_via_mcp
from .servers.catalog import run_catalog_server
from .servers.splunk import run_splunk_server
from .servers.tickets import run_ticket_server
from .splunk_backend import create_splunk_backend
from .splunk_mcp_adapter import SplunkMCPAdapter
from .storage import DemoStore


def _run_web() -> None:
    settings = get_settings()
    uvicorn.run(
        "mcp_service_demo.api:app",
        host=settings.web_host,
        port=settings.web_port,
        log_level="warning",
    )


def _process(target: Callable[[], Any], name: str) -> multiprocessing.Process:
    process = multiprocessing.Process(target=target, name=name, daemon=False)
    process.start()
    return process


def _wait_for_port(host: str, port: int, timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.25)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.1)
    raise RuntimeError(f"Service did not become ready on {host}:{port}")


def run_all() -> None:
    settings = get_settings()
    DemoStore(settings.database_path).ensure_seeded()
    processes = [
        _process(run_splunk_server, "splunk-mcp"),
        _process(run_ticket_server, "ticket-mcp"),
        _process(run_catalog_server, "catalog-mcp"),
        _process(_run_web, "demo-web"),
    ]
    shutdown_requested = False

    def stop_all(_signum: int | None = None, _frame: object | None = None) -> None:
        nonlocal shutdown_requested
        shutdown_requested = True
        for process in processes:
            if process.is_alive():
                process.terminate()
        for process in processes:
            process.join(timeout=5)

    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)
    try:
        _wait_for_port(settings.splunk_mcp_host, settings.splunk_mcp_port)
        _wait_for_port(settings.ticket_mcp_host, settings.ticket_mcp_port)
        _wait_for_port(settings.catalog_mcp_host, settings.catalog_mcp_port)
        _wait_for_port(settings.web_host, settings.web_port)
        print("\nMCP Service Demo is ready")
        print(f"  Demo:       http://{settings.web_host}:{settings.web_port}")
        print(f"  Splunk MCP: {settings.splunk_mcp_url}")
        print(f"  Ticket MCP: {settings.ticket_mcp_url}")
        print(f"  Catalog MCP: {settings.catalog_mcp_url}")
        print(f"  Splunk data: {settings.splunk_data_mode}")
        print(f"  Agent mode: {settings.agent_mode}\n")
        while all(process.is_alive() for process in processes):
            time.sleep(0.5)
        failed = [process.name for process in processes if process.exitcode not in (None, 0)]
        if failed and not shutdown_requested:
            raise RuntimeError(f"Demo service stopped unexpectedly: {', '.join(failed)}")
    finally:
        stop_all()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the MCP Service Demo")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="start the web app and all MCP servers")
    subparsers.add_parser("web", help="start only the web app")
    subparsers.add_parser("splunk-mcp", help="start only the Splunk MCP server")
    subparsers.add_parser("ticket-mcp", help="start only the ticket MCP server")
    subparsers.add_parser("catalog-mcp", help="start only the service catalog MCP server")
    subparsers.add_parser("reset", help="restore the seeded demo scenario")
    subparsers.add_parser("test-splunk", help="test the configured Splunk REST connection")
    subparsers.add_parser("seed-splunk", help="publish a fresh scenario to Splunk through HEC")
    package_parser = subparsers.add_parser(
        "package-splunk-app", help="build the companion Splunk app archive"
    )
    package_parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/mcp_service_demo-0.3.0.tar.gz"),
        help="archive path (default: dist/mcp_service_demo-0.3.0.tar.gz)",
    )
    return parser


def package_splunk_app(output: Path) -> Path:
    source = Path.cwd() / "splunk_app" / "mcp_service_demo"
    if not (source / "default" / "app.conf").is_file():
        raise FileNotFoundError(
            "Run this command from the repository root; splunk_app/mcp_service_demo was not found."
        )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.name not in {".DS_Store"}:
                archive.add(path, arcname=Path(source.name) / path.relative_to(source))
    return output


def _remote_splunk_broker(settings: Settings) -> MCPBroker:
    return MCPBroker(
        {
            "splunk": MCPRemoteTarget(
                url=settings.splunk_mcp_url,
                token=settings.splunk_mcp_token,
                verify=settings.splunk_mcp_verify,
            )
        }
    )


def _live_seed(settings: Settings, store: DemoStore) -> dict[str, Any]:
    if settings.splunk_rest_configured:
        return seed_splunk_scenario(settings, store)
    return asyncio.run(
        seed_splunk_scenario_via_mcp(settings, _remote_splunk_broker(settings), store)
    )


def _splunk_status(settings: Settings) -> dict[str, Any]:
    if settings.splunk_data_mode != "live" or settings.splunk_rest_configured:
        return create_splunk_backend(settings).status()
    return asyncio.run(SplunkMCPAdapter(settings, _remote_splunk_broker(settings)).status())


def main() -> None:
    args = build_parser().parse_args()
    command = args.command or "run"
    if command == "run":
        run_all()
    elif command == "web":
        _run_web()
    elif command == "splunk-mcp":
        run_splunk_server()
    elif command == "ticket-mcp":
        run_ticket_server()
    elif command == "catalog-mcp":
        run_catalog_server()
    elif command == "reset":
        settings = get_settings()
        store = DemoStore(settings.database_path)
        result = (
            _live_seed(settings, store)
            if settings.splunk_data_mode == "live"
            else store.reset()
        )
        suffix = (
            f" and published {result['events_published']} events as {result['demo_run_id']}"
            if result.get("events_published")
            else ""
        )
        print(f"Reset {result['scenario']} with ticket {result['ticket']}{suffix}")
    elif command == "test-splunk":
        status = _splunk_status(get_settings())
        print(f"Splunk mode: {status['mode']}")
        print(f"Ready: {status['ready']}")
        print(f"Source: {status['source']}")
        if status.get("active_run_id"):
            print(f"Active demo run: {status['active_run_id']}")
    elif command == "seed-splunk":
        settings = get_settings()
        result = _live_seed(settings, DemoStore(settings.database_path))
        print(
            f"Published {result['events_published']} events to {result['index']} "
            f"as {result['demo_run_id']}"
        )
    elif command == "package-splunk-app":
        output = package_splunk_app(args.output)
        print(f"Built {output}")
    else:
        sys.exit(f"Unknown command: {command}")
