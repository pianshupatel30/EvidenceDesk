import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import numpy as np


class Telemetry:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, result: dict):
        # Store request measurements, never document content, prompts, or API keys.
        measured = {key: result[key] for key in ["id", "created", "status", "provider", "retrieval_mode",
                    "index_version", "retrieval_ms", "generation_ms", "total_ms", "usage", "cost_usd"]}
        with self.connect() as connection:
            connection.execute("INSERT INTO requests VALUES (?, ?, ?)",
                               (result["id"], result["created"], json.dumps(measured)))

    def summary(self):
        with self.connect() as connection:
            rows = connection.execute("SELECT payload FROM requests ORDER BY created DESC LIMIT 1000").fetchall()
        requests = [json.loads(row[0]) for row in rows]
        latencies = [row["total_ms"] for row in requests]
        costs = [row["cost_usd"] for row in requests if row["cost_usd"] is not None]
        return {"window": "Latest 1,000 requests", "requests": len(requests),
                "p50_ms": float(np.percentile(latencies, 50)) if latencies else 0,
                "p95_ms": float(np.percentile(latencies, 95)) if latencies else 0,
                "error_rate": sum(row["status"] == "error" for row in requests) / max(len(requests), 1),
                "abstention_rate": sum(row["status"] == "abstained" for row in requests) / max(len(requests), 1),
                "known_cost_usd": sum(costs), "unknown_cost_requests": len(requests) - len(costs),
                "recent": requests[:30]}
