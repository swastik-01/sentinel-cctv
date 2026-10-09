"""Store-and-forward for a district edge that loses its backhaul.

A batch the API cannot take (network down, API down, 5xx) is written to local disk, one
JSON file per batch, named so that sorting the names gives arrival order. Once the API
answers again the files are replayed oldest first and deleted as each one is accepted.
A replayed sighting still carries its frame timestamp, so a watchlist hit raises its alert
on replay with the time the vehicle was actually seen, not the time the link came back.

Bounded: past `max_mb` the oldest files are dropped, and the log says how many rows.
A batch the API rejects as malformed (4xx other than auth/throttling) can never succeed,
so it is moved to `rejected/` for inspection instead of blocking the queue.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("sentinel.spool")


class Spool:
    def __init__(self, root: str | Path, max_mb: float) -> None:
        self.root = Path(root)
        self.max_bytes = int(max_mb * 1024 * 1024)
        self._seq = 0
        self.dropped_rows = 0

    def put(self, kind: str, batch: list[dict], batch_id: str | None = None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._seq += 1
        name = f"{time.time_ns():020d}-{self._seq:06d}-{kind}.json"
        tmp = self.root / f"{name}.tmp"
        tmp.write_text(json.dumps({"batch_id": batch_id, "rows": batch}), encoding="utf-8")
        tmp.replace(self.root / name)          # a crash mid-write never leaves a half file to replay
        self._trim()

    def pending(self) -> list[Path]:
        return sorted(self.root.glob("*.json")) if self.root.is_dir() else []

    @staticmethod
    def read(path: Path) -> tuple[str, str | None, list[dict]]:
        """(kind, batch id, rows). The batch id travels with a replay so the API can tell a
        batch it already stored (the reply was lost) from a new one."""
        kind = path.stem.rsplit("-", 1)[-1]
        body = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(body, list):          # written before batch ids existed
            return kind, None, body
        return kind, body.get("batch_id"), body["rows"]

    def done(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def reject(self, path: Path) -> None:
        bad = self.root / "rejected"
        bad.mkdir(exist_ok=True)
        try:
            path.replace(bad / path.name)
        except FileNotFoundError:          # already taken by another process reading the same folder
            pass

    def _trim(self) -> None:
        files = self.pending()
        total = sum(f.stat().st_size for f in files)
        while files and total > self.max_bytes:
            f = files.pop(0)
            total -= f.stat().st_size
            try:
                self.dropped_rows += len(self.read(f)[2])
            except (OSError, ValueError, KeyError):
                pass
            f.unlink(missing_ok=True)
            log.warning("spool over %d MB: dropped oldest batch %s", self.max_bytes >> 20, f.name)
