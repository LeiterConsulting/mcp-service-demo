from __future__ import annotations

import argparse
import multiprocessing
import signal
import socket
import sys
import time
from collections.abc import Callable
from typing import Any

import uvicorn

from .config import get_settings
from .servers.splunk import run_splunk_server
from .servers.tickets import run_ticket_server
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
        _wait_for_port(settings.web_host, settings.web_port)
        print("\nMCP Service Demo is ready")
        print(f"  Demo:       http://{settings.web_host}:{settings.web_port}")
        print(f"  Splunk MCP: {settings.splunk_mcp_url}")
        print(f"  Ticket MCP: {settings.ticket_mcp_url}")
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
    subparsers.add_parser("run", help="start the web app and both MCP servers")
    subparsers.add_parser("web", help="start only the web app")
    subparsers.add_parser("splunk-mcp", help="start only the Splunk MCP server")
    subparsers.add_parser("ticket-mcp", help="start only the ticket MCP server")
    subparsers.add_parser("reset", help="restore the seeded demo scenario")
    return parser


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
    elif command == "reset":
        result = DemoStore(get_settings().database_path).reset()
        print(f"Reset {result['scenario']} with ticket {result['ticket']}")
    else:
        sys.exit(f"Unknown command: {command}")
