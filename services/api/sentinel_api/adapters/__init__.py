"""Government database adapters.

Each adapter exposes the same tiny contract — fetch() -> list[WatchlistIn] — so the
platform does not care whether entries come from VAHAN, eGujCop, NAFIS or a CSV.
VAHAN and eGujCop read local fixtures shaped like the real feeds; SARTHI, AFIS and
NAFIS are declared and return nothing until authorised access exists. At deployment
the base URL and credentials are swapped in and nothing else changes.
"""
from __future__ import annotations

from .base import WatchlistAdapter
from .egujcop_mock import EGujCopMock
from .pending import AfisPending, NafisPending, SarathiPending
from .vahan_mock import VahanMock

_ADAPTERS: dict[str, WatchlistAdapter] = {
    a.name: a for a in (VahanMock(), EGujCopMock(), SarathiPending(), AfisPending(), NafisPending())
}


def get_adapter(name: str) -> WatchlistAdapter | None:
    return _ADAPTERS.get(name.lower())


def list_adapters() -> list[dict]:
    return [a.describe() for a in _ADAPTERS.values()]
