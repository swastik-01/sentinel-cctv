# Watchlist matching cost per plate read

Measured 2026-09-24 00:33 India Standard Time on DESKTOP-R2I8CQL (Intel64 Family 6 Model 165 Stepping 2, GenuineIntel), PostgreSQL in Docker Desktop, by `bench/matcher.py`.
Watchlist: 100,011 active entries (100,000 synthetic, inserted in 34.0 s with the mask trigger, then rolled back). Times are one query per plate read, round trip from Python, single connection.

| Matcher | Probes | Matched | Median ms | p95 ms |
|---|---|---|---|---|
| masks (current), one character off | 1000 | 1000 | 0.79 | 1.40 |
| masks (current), plate not listed | 1000 | 0 | 1.14 | 11.67 |
| levenshtein scan (before), one character off | 100 | 100 | 55.58 | 107.10 |
| levenshtein scan (before), plate not listed | 100 | 0 | 44.83 | 53.86 |

One character off = a real watchlist plate with one character replaced, i.e. a single OCR slip.
Every one of them must match; a plate not on the list must not.
