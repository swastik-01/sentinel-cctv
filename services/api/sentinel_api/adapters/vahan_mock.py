"""VAHAN (national vehicle registry) — stolen / blacklisted vehicle feed, mocked.

Real integration: the NIC VAHAN/Sarathi APIs expose vehicle detail lookups and
state-level stolen-vehicle flags to authorised police systems via the
state's SDC/eGujCop gateway. The record shape below mirrors those fields.
"""
from __future__ import annotations

from ..schemas import WatchlistIn
from .base import WatchlistAdapter


class VahanMock(WatchlistAdapter):
    name = "vahan"
    system = "VAHAN (NIC)"
    description = "Stolen and blacklisted vehicle flags keyed by registration number"

    async def fetch(self) -> list[WatchlistIn]:
        out = []
        for rec in self._load_fixture("vahan_stolen.json"):
            out.append(WatchlistIn(
                kind="stolen_vehicle" if rec["flag"] == "STOLEN" else "blacklisted_vehicle",
                plate=rec["regn_no"],
                severity="high" if rec["flag"] == "STOLEN" else "medium",
                source="VAHAN", source_ref=rec.get("fir_no") or rec.get("ref"),
                reason=f"{rec['flag']}: {rec.get('remarks', '')}".strip(),
            ))
        return out
