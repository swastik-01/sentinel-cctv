from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from ..schemas import WatchlistIn

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


class WatchlistAdapter(ABC):
    name: str = "base"
    system: str = ""
    description: str = ""
    mode: str = "mock"          # mock | awaiting-access | live
    requires: str = ""          # what is needed before this adapter can return records

    @abstractmethod
    async def fetch(self) -> list[WatchlistIn]: ...

    def describe(self) -> dict:
        return {"name": self.name, "system": self.system, "description": self.description,
                "mode": self.mode}

    @staticmethod
    def _load_fixture(filename: str) -> list[dict]:
        return json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
