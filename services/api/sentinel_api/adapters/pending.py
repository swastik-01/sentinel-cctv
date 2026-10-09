"""Government systems we are ready for but cannot reach yet.

The problem statement asks for integration readiness with VAHAN, SARTHI, eGujCop, AFIS
and NAFIS. VAHAN and eGujCop have working adapters against mock services that use the
real record shapes. The three below are declared through the same contract and return
nothing until authorised access exists. Enabling one means writing its client (endpoint,
credentials, field mapping) behind this contract; nothing else in the platform changes.
They are listed in the UI as `mode: awaiting-access`
so nobody mistakes an empty sync for a working integration.
"""
from __future__ import annotations

import logging

from ..schemas import WatchlistIn
from .base import WatchlistAdapter

log = logging.getLogger("sentinel.adapters")


class PendingAdapter(WatchlistAdapter):
    mode = "awaiting-access"

    async def fetch(self) -> list[WatchlistIn]:
        log.info("%s: no authorised endpoint configured; returning no entries", self.name)
        return []

    def describe(self) -> dict:
        return {**super().describe(), "requires": self.requires}


class SarathiPending(PendingAdapter):
    name = "sarathi"
    system = "SARTHI (NIC)"
    description = "Driving licence records — licence status and holder details for a traced vehicle"
    requires = "State Transport Department authorisation and an SDC/NIC gateway endpoint"


class AfisPending(PendingAdapter):
    name = "afis"
    system = "AFIS (State)"
    description = "Fingerprint identification — identity confirmation for a person of interest"
    requires = "SCRB authorisation; no watchlist entries are created from biometrics by this platform"


class NafisPending(PendingAdapter):
    name = "nafis"
    system = "NAFIS (NCRB)"
    description = "National fingerprint database — arrested-person records supporting an investigation"
    requires = "NCRB authorisation; identity matching stays in NAFIS, not in Sentinel"
