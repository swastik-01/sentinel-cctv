"""eGujCop (Gujarat Police CCTNS) — wanted/missing persons and BOLO vehicles, mocked."""
from __future__ import annotations

from ..schemas import WatchlistIn
from .base import WatchlistAdapter

_KIND = {"WANTED": "wanted_person", "MISSING": "missing_person", "BOLO": "bolo"}
_SEV = {"WANTED": "critical", "MISSING": "high", "BOLO": "medium"}


class EGujCopMock(WatchlistAdapter):
    name = "egujcop"
    system = "eGujCop (CCTNS Gujarat)"
    description = "Wanted persons, missing persons and BOLO (be-on-lookout) vehicles"

    async def fetch(self) -> list[WatchlistIn]:
        out = []
        for rec in self._load_fixture("egujcop_watch.json"):
            out.append(WatchlistIn(
                kind=_KIND[rec["category"]],
                plate=rec.get("vehicle_regn"),
                subject_name=rec.get("subject"),
                severity=_SEV[rec["category"]],
                source="eGujCop", source_ref=rec.get("fir_no"),
                reason=rec.get("details"),
            ))
        return out
