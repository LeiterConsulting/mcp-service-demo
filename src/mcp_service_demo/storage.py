from __future__ import annotations

import json
import math
import random
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SERVICES = ("checkout-api", "inventory-api", "payment-api")
INCIDENT_TICKET = "INC-1042"


class DemoStore:
    """SQLite-backed demo state shared by the UI and both MCP servers."""

    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS demo_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    service TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    assignee TEXT NOT NULL,
                    requester TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    urgency TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ticket_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    author TEXT NOT NULL,
                    body TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    service TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    status_code INTEGER,
                    duration_ms INTEGER,
                    host TEXT NOT NULL,
                    trace_id TEXT NOT NULL,
                    version TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS events_service_timestamp
                    ON events(service, timestamp);
                CREATE INDEX IF NOT EXISTS events_trace_id
                    ON events(trace_id);
                """
            )

    def ensure_seeded(self) -> None:
        self.initialize()
        with self.connect() as connection:
            ticket_count = connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
            event_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if ticket_count == 0 or event_count == 0:
            self.reset()

    def reset(self, now: datetime | None = None) -> dict[str, Any]:
        self.initialize()
        anchor = (now or datetime.now(UTC)).replace(microsecond=0)
        with self.connect() as connection:
            connection.execute("DELETE FROM ticket_notes")
            connection.execute("DELETE FROM tickets")
            connection.execute("DELETE FROM events")
            connection.execute("DELETE FROM demo_state")
            connection.execute(
                "INSERT INTO demo_state(key, value) VALUES (?, ?)",
                ("scenario_anchor", anchor.isoformat()),
            )
            self._seed_tickets(connection, anchor)
            self._seed_events(connection, anchor)
        return {
            "status": "reset",
            "scenario": "checkout-degradation",
            "ticket": INCIDENT_TICKET,
            "anchor": anchor.isoformat(),
        }

    def _seed_tickets(self, connection: sqlite3.Connection, anchor: datetime) -> None:
        tickets = [
            (
                INCIDENT_TICKET,
                "Checkout intermittently failing for online orders",
                (
                    "Store Operations reports that customers are seeing slow checkout responses "
                    "and occasional failures. The issue began within the last 30 minutes. Please "
                    "determine scope, likely cause, and whether a recent change is involved."
                ),
                "checkout-api",
                "P1",
                "New",
                "Maya Chen",
                "Store Operations",
                "High — online revenue path",
                "High",
                (anchor - timedelta(minutes=16)).isoformat(),
                (anchor - timedelta(minutes=11)).isoformat(),
            ),
            (
                "INC-1039",
                "Inventory export delayed",
                "The nightly inventory export completed twelve minutes later than its target.",
                "inventory-api",
                "P3",
                "Monitoring",
                "Maya Chen",
                "Merchandising",
                "Low — batch process only",
                "Low",
                (anchor - timedelta(hours=3, minutes=8)).isoformat(),
                (anchor - timedelta(minutes=48)).isoformat(),
            ),
            (
                "INC-1037",
                "Payment reconciliation warning",
                "A reconciliation job emitted a warning but completed successfully.",
                "payment-api",
                "P4",
                "Resolved",
                "Maya Chen",
                "Finance Systems",
                "None — informational",
                "Low",
                (anchor - timedelta(hours=7, minutes=24)).isoformat(),
                (anchor - timedelta(hours=2, minutes=17)).isoformat(),
            ),
        ]
        connection.executemany(
            """
            INSERT INTO tickets(
                id, title, description, service, priority, status, assignee, requester,
                impact, urgency, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tickets,
        )
        connection.executemany(
            """
            INSERT INTO ticket_notes(ticket_id, kind, author, body, evidence_refs, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    INCIDENT_TICKET,
                    "customer",
                    "Nina Patel · Store Operations",
                    (
                        "Three stores and the web support team report spinning checkouts. A retry "
                        "usually works, but order completion is noticeably slower."
                    ),
                    "[]",
                    (anchor - timedelta(minutes=15)).isoformat(),
                ),
                (
                    INCIDENT_TICKET,
                    "system",
                    "Northstar Service Desk",
                    (
                        "Priority raised to P1 because the affected service is on the online "
                        "revenue path."
                    ),
                    "[]",
                    (anchor - timedelta(minutes=11)).isoformat(),
                ),
            ],
        )

    def _seed_events(self, connection: sqlite3.Connection, anchor: datetime) -> None:
        rng = random.Random(1042)
        rows: list[tuple[Any, ...]] = []
        host_counts = {"checkout-api": 3, "inventory-api": 2, "payment-api": 2}

        for minute_ago in range(90, -1, -1):
            timestamp = anchor - timedelta(minutes=minute_ago)
            for service in SERVICES:
                samples = 12 if service == "checkout-api" else 8
                incident = service == "checkout-api" and minute_ago <= 22
                for sample in range(samples):
                    trace_id = f"tr-{minute_ago:02d}-{service[:3]}-{sample:02d}"
                    version = (
                        "4.18.2"
                        if service == "checkout-api" and minute_ago <= 26
                        else ("4.18.1" if service == "checkout-api" else "2.9.7")
                    )
                    host = f"{service}-{sample % host_counts[service] + 1}"
                    if incident and sample in {1, 5, 9}:
                        status_code = 503
                        duration = rng.randint(2600, 4800)
                        level = "ERROR"
                        message = (
                            "checkout request failed: inventory-client connection pool exhausted; "
                            f"status=503 duration_ms={duration}"
                        )
                    else:
                        status_code = 200
                        base = 210 if service == "checkout-api" else 135
                        duration = max(35, int(rng.gauss(base, base * 0.22)))
                        if incident:
                            duration += rng.randint(700, 1900)
                        level = "INFO"
                        message = (
                            f"request completed status={status_code} duration_ms={duration} "
                            f"route=/{'checkout' if service == 'checkout-api' else 'v1/items'}"
                        )
                    rows.append(
                        (
                            (timestamp + timedelta(seconds=sample * 4)).isoformat(),
                            service,
                            level,
                            "request",
                            message,
                            status_code,
                            duration,
                            host,
                            trace_id,
                            version,
                        )
                    )

        deployment_time = anchor - timedelta(minutes=26)
        rows.append(
            (
                deployment_time.isoformat(),
                "checkout-api",
                "INFO",
                "deployment",
                "deployment completed version=4.18.2 change=CHG-8821 strategy=rolling",
                None,
                None,
                "deploy-controller-1",
                "deploy-4.18.2",
                "4.18.2",
            )
        )

        for index in range(4):
            trace_id = f"tr-hot-{index + 1}"
            event_time = anchor - timedelta(minutes=12 - index * 2)
            rows.extend(
                [
                    (
                        event_time.isoformat(),
                        "checkout-api",
                        "ERROR",
                        "request",
                        (
                            "POST /checkout failed while reserving inventory "
                            "status=503 duration_ms=4210"
                        ),
                        503,
                        4210,
                        f"checkout-api-{index % 3 + 1}",
                        trace_id,
                        "4.18.2",
                    ),
                    (
                        (event_time + timedelta(milliseconds=38)).isoformat(),
                        "inventory-api",
                        "WARN",
                        "dependency",
                        "client disconnected before inventory reservation completed",
                        499,
                        3980,
                        f"inventory-api-{index % 2 + 1}",
                        trace_id,
                        "2.9.7",
                    ),
                ]
            )

        connection.executemany(
            """
            INSERT INTO events(
                timestamp, service, level, event_type, message, status_code, duration_ms,
                host, trace_id, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    def _anchor(self) -> datetime:
        self.ensure_seeded()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM demo_state WHERE key = 'scenario_anchor'"
            ).fetchone()
        return datetime.fromisoformat(row["value"])

    def list_tickets(self, assignee: str | None = None) -> list[dict[str, Any]]:
        self.ensure_seeded()
        query = "SELECT * FROM tickets"
        parameters: list[Any] = []
        if assignee:
            query += " WHERE lower(assignee) = lower(?)"
            parameters.append(assignee)
        query += (
            " ORDER BY CASE priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 "
            "WHEN 'P3' THEN 3 ELSE 4 END, updated_at DESC"
        )
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        self.ensure_seeded()
        normalized = ticket_id.strip().upper()
        with self.connect() as connection:
            ticket = connection.execute(
                "SELECT * FROM tickets WHERE upper(id) = ?", (normalized,)
            ).fetchone()
            if ticket is None:
                return None
            notes = connection.execute(
                "SELECT * FROM ticket_notes WHERE ticket_id = ? ORDER BY created_at, id",
                (ticket["id"],),
            ).fetchall()
        result = dict(ticket)
        result["notes"] = [self._note_dict(row) for row in notes]
        return result

    @staticmethod
    def _note_dict(row: sqlite3.Row) -> dict[str, Any]:
        note = dict(row)
        note["evidence_refs"] = json.loads(note["evidence_refs"])
        return note

    def add_work_note(
        self,
        ticket_id: str,
        body: str,
        evidence_refs: list[str] | None = None,
        author: str = "Splunk Investigation Agent",
    ) -> dict[str, Any]:
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            raise KeyError(f"Ticket {ticket_id!r} was not found")
        now = datetime.now(UTC).replace(microsecond=0).isoformat()
        refs = evidence_refs or []
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO ticket_notes(ticket_id, kind, author, body, evidence_refs, created_at)
                VALUES (?, 'work_note', ?, ?, ?, ?)
                """,
                (ticket["id"], author, body.strip(), json.dumps(refs), now),
            )
            connection.execute(
                "UPDATE tickets SET status = 'Investigating', updated_at = ? WHERE id = ?",
                (now, ticket["id"]),
            )
            note_id = cursor.lastrowid
            row = connection.execute(
                "SELECT * FROM ticket_notes WHERE id = ?", (note_id,)
            ).fetchone()
        return self._note_dict(row)

    def update_ticket_status(self, ticket_id: str, status: str) -> dict[str, Any]:
        allowed = {"New", "Investigating", "Monitoring", "Resolved"}
        if status not in allowed:
            raise ValueError(f"Status must be one of: {', '.join(sorted(allowed))}")
        if self.get_ticket(ticket_id) is None:
            raise KeyError(f"Ticket {ticket_id!r} was not found")
        now = datetime.now(UTC).replace(microsecond=0).isoformat()
        with self.connect() as connection:
            connection.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE upper(id) = upper(?)",
                (status, now, ticket_id),
            )
        return self.get_ticket(ticket_id) or {}

    def list_services(self) -> list[str]:
        self.ensure_seeded()
        return list(SERVICES)

    def export_events(self) -> list[dict[str, Any]]:
        """Return the current synthetic event stream for HEC publication."""
        self.ensure_seeded()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, service, level, event_type, message, status_code,
                       duration_ms, host, trace_id, version
                FROM events ORDER BY timestamp, id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_service_health(self, service: str, minutes: int = 30) -> dict[str, Any]:
        normalized = self._validate_service(service)
        window = min(max(minutes, 5), 90)
        anchor = self._anchor()
        start = anchor - timedelta(minutes=window)
        rows = self._request_rows(normalized, start, anchor)
        baseline_start = start - timedelta(minutes=window)
        baseline = self._request_rows(normalized, baseline_start, start)
        metrics = self._calculate_metrics(rows)
        baseline_metrics = self._calculate_metrics(baseline)
        deployments = self._event_rows(
            normalized,
            start - timedelta(minutes=10),
            anchor,
            event_type="deployment",
            limit=10,
        )
        buckets = self._health_buckets(rows, anchor, window)
        state = (
            "degraded" if metrics["error_rate_pct"] >= 5 or metrics["p95_ms"] >= 1500 else "healthy"
        )
        return {
            "service": normalized,
            "window_minutes": window,
            "state": state,
            "metrics": metrics,
            "baseline": baseline_metrics,
            "change": {
                "error_rate_points": round(
                    metrics["error_rate_pct"] - baseline_metrics["error_rate_pct"], 1
                ),
                "p95_ms": metrics["p95_ms"] - baseline_metrics["p95_ms"],
            },
            "timeline": buckets,
            "recent_changes": deployments,
            "evidence_ref": f"splunk://search?service={normalized}&earliest=-{window}m",
        }

    def compare_service_baseline(self, service: str, minutes: int = 30) -> dict[str, Any]:
        health = self.get_service_health(service, minutes)
        current = health["metrics"]
        baseline = health["baseline"]
        return {
            "service": health["service"],
            "window_minutes": health["window_minutes"],
            "current": current,
            "baseline": baseline,
            "assessment": (
                f"Error rate is {current['error_rate_pct']:.1f}% versus "
                f"{baseline['error_rate_pct']:.1f}% in the preceding window; p95 latency is "
                f"{current['p95_ms']} ms versus {baseline['p95_ms']} ms."
            ),
            "evidence_ref": health["evidence_ref"],
        }

    def search_logs(
        self,
        service: str,
        keywords: str = "",
        minutes: int = 30,
        limit: int = 20,
    ) -> dict[str, Any]:
        normalized = self._validate_service(service)
        window = min(max(minutes, 5), 90)
        result_limit = min(max(limit, 1), 50)
        anchor = self._anchor()
        start = anchor - timedelta(minutes=window)
        words = [word.lower() for word in keywords.split() if word.strip()]
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, service, level, event_type, message, status_code, duration_ms,
                       host, trace_id, version
                FROM events
                WHERE service = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp DESC
                """,
                (normalized, start.isoformat(), anchor.isoformat()),
            ).fetchall()
        matches = []
        for row in rows:
            haystack = " ".join(str(value) for value in row).lower()
            if not words or all(word in haystack for word in words):
                matches.append(dict(row))
            if len(matches) >= result_limit:
                break
        patterns = Counter(
            "inventory-client connection pool exhausted"
            if "connection pool exhausted" in row["message"]
            else "request completed"
            if row["status_code"] == 200
            else row["message"][:80]
            for row in matches
        )
        return {
            "service": normalized,
            "keywords": keywords,
            "window_minutes": window,
            "match_count_returned": len(matches),
            "top_patterns": [
                {"pattern": pattern, "count": count} for pattern, count in patterns.most_common(3)
            ],
            "events": matches,
            "evidence_ref": (
                f"splunk://search?service={normalized}&q={keywords or '*'}&earliest=-{window}m"
            ),
        }

    def trace_request(self, trace_id: str) -> dict[str, Any]:
        self.ensure_seeded()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, service, level, event_type, message, status_code, duration_ms,
                       host, trace_id, version
                FROM events WHERE trace_id = ? ORDER BY timestamp
                """,
                (trace_id,),
            ).fetchall()
        return {
            "trace_id": trace_id,
            "found": bool(rows),
            "events": [dict(row) for row in rows],
            "evidence_ref": f"splunk://trace/{trace_id}",
        }

    def _validate_service(self, service: str) -> str:
        normalized = service.strip().lower()
        if normalized not in SERVICES:
            raise ValueError(
                f"Unknown service {service!r}. Available services: {', '.join(SERVICES)}"
            )
        return normalized

    def _request_rows(self, service: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, status_code, duration_ms, version
                FROM events
                WHERE service = ? AND event_type = 'request' AND timestamp >= ? AND timestamp < ?
                ORDER BY timestamp
                """,
                (service, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [dict(row) for row in rows]

    def _event_rows(
        self,
        service: str,
        start: datetime,
        end: datetime,
        event_type: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, message, version, host
                FROM events
                WHERE service = ? AND event_type = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (service, event_type, start.isoformat(), end.isoformat(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _calculate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"requests": 0, "errors": 0, "error_rate_pct": 0.0, "p50_ms": 0, "p95_ms": 0}
        durations = sorted(row["duration_ms"] for row in rows if row["duration_ms"] is not None)
        errors = sum(1 for row in rows if (row["status_code"] or 0) >= 500)
        return {
            "requests": len(rows),
            "errors": errors,
            "error_rate_pct": round(errors / len(rows) * 100, 1),
            "p50_ms": DemoStore._percentile(durations, 0.50),
            "p95_ms": DemoStore._percentile(durations, 0.95),
        }

    @staticmethod
    def _percentile(values: list[int], percentile: float) -> int:
        if not values:
            return 0
        index = min(len(values) - 1, max(0, math.ceil(len(values) * percentile) - 1))
        return int(values[index])

    def _health_buckets(
        self, rows: list[dict[str, Any]], anchor: datetime, window: int
    ) -> list[dict[str, Any]]:
        bucket_size = 5
        buckets: list[dict[str, Any]] = []
        for offset in range(window, 0, -bucket_size):
            start = anchor - timedelta(minutes=offset)
            end = anchor - timedelta(minutes=max(0, offset - bucket_size))
            selected = [
                row for row in rows if start <= datetime.fromisoformat(row["timestamp"]) < end
            ]
            metrics = self._calculate_metrics(selected)
            buckets.append(
                {
                    "label": f"-{offset}m",
                    "error_rate_pct": metrics["error_rate_pct"],
                    "p95_ms": metrics["p95_ms"],
                }
            )
        return buckets
