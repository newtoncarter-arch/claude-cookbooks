"""Append-only JSON-lines log of every signal, order, fill, P&L and alert.

One line per event makes it easy to grep and to load into pandas for the
weekly paper-vs-backtest report in Stage 5.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class EventLog:
    def __init__(self, log_dir: str | Path, mode: str):
        self.dir = Path(log_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.mode = mode

    def _path(self) -> Path:
        return self.dir / f"events-{datetime.now(UTC):%Y-%m-%d}.jsonl"

    def log(self, event: str, **fields: Any) -> None:
        record = {"ts": datetime.now(UTC).isoformat(), "mode": self.mode, "event": event}
        record.update(fields)
        with self._path().open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
