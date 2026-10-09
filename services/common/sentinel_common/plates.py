"""Indian number-plate normalisation and OCR-confusion handling.

Standard format:  SS RR L{1,3} NNNN   e.g. GJ 01 AB 1234, GJ 05 EF 9012, MH 12 A 4567
BH series:        YY BH NNNN LL        e.g. 22 BH 1234 AA

OCR routinely confuses O/0, I/1, Z/2, S/5, B/8, G/6, Q/0, D/0. Which way to resolve
depends on *position*: a state code is always letters, an RTO code always digits,
the running number always digits. We use that structure to repair reads before
matching, and also generate the plausible variants so a watchlist lookup can
succeed even when the read is slightly off.
"""
from __future__ import annotations

import re

_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2",
                           "S": "5", "B": "8", "G": "6", "T": "7", "A": "4"})
_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G",
                           "4": "A", "7": "T"})

_STD = re.compile(r"^([A-Z]{2})(\d{2})([A-Z]{1,3})(\d{4})$")
_BH = re.compile(r"^(\d{2})(BH)(\d{4})([A-Z]{1,2})$")

# Common OCR junk: "IND", plate-holder text, dashes, dots, spaces.
_JUNK = re.compile(r"[^A-Z0-9]")
_PREFIX_JUNK = re.compile(r"^(IND|INDIA)")

STATE_CODES = {
    "AN", "AP", "AR", "AS", "BR", "CG", "CH", "DD", "DL", "DN", "GA", "GJ", "HP", "HR",
    "JH", "JK", "KA", "KL", "LA", "LD", "MH", "ML", "MN", "MP", "MZ", "NL", "OD", "OR",
    "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK", "UP", "WB",
}


def _clean(raw: str) -> str:
    s = _JUNK.sub("", raw.upper())
    s = _PREFIX_JUNK.sub("", s)
    return s


def _repair_standard(s: str) -> str | None:
    """Apply positional confusion repair for the standard layout and validate."""
    if not 8 <= len(s) <= 11:
        return None
    # last 4 must be digits, first 2 letters, positions 2-3 digits.
    head, num = s[:-4], s[-4:]
    num = num.translate(_TO_DIGIT)
    if not num.isdigit() or len(head) < 4:
        return None
    state = head[:2].translate(_TO_ALPHA)
    rto = head[2:4].translate(_TO_DIGIT)
    series = head[4:].translate(_TO_ALPHA)
    cand = f"{state}{rto}{series}{num}"
    return cand if _STD.match(cand) else None


def _repair_bh(s: str) -> str | None:
    if len(s) not in (9, 10):
        return None
    yy = s[:2].translate(_TO_DIGIT)
    bh = s[2:4].translate(_TO_ALPHA)
    num = s[4:8].translate(_TO_DIGIT)
    tail = s[8:].translate(_TO_ALPHA)
    cand = f"{yy}{bh}{num}{tail}"
    return cand if _BH.match(cand) else None


# Letters OCR engines mistake for each other on plate typefaces.
_LOOKALIKES = {
    "I": "JL1", "J": "IU", "L": "I", "U": "JV", "V": "UW", "W": "V", "O": "QD", "Q": "O", "D": "O",
    "B": "R8", "R": "BP", "P": "R", "G": "C6", "C": "G", "E": "F", "F": "E", "M": "N", "N": "M",
    "K": "X", "X": "K", "T": "7", "S": "5", "Z": "2", "A": "4", "Y": "V",
}
PREFERRED_STATE = "GJ"   # deployment state: wins ties when a repair is ambiguous


def _fix_state(code: str) -> str:
    """Repair an invalid 2-letter state code by single look-alike substitution."""
    if code in STATE_CODES:
        return code
    found: list[str] = []
    for i, ch in enumerate(code):
        for alt in _LOOKALIKES.get(ch, ""):
            cand = code[:i] + alt + code[i + 1:]
            if cand in STATE_CODES and cand not in found:
                found.append(cand)
    if not found:
        return code
    return PREFERRED_STATE if PREFERRED_STATE in found else found[0]


def normalise_plate(raw: str) -> str:
    """Return the canonical form (no spaces, uppercase, confusions repaired).

    Falls back to the cleaned string when the read does not fit a known layout,
    so nothing is silently dropped — it just will not match a watchlist exactly.
    """
    s = _clean(raw)
    if not s:
        return ""
    if _BH.match(s):
        return s
    if not _STD.match(s):
        s = _repair_standard(s) or _repair_bh(s) or s
    m = _STD.match(s)
    if m and m.group(1) not in STATE_CODES:
        s = _fix_state(m.group(1)) + s[2:]
    return s


def letters_from_digits(raw: str) -> int:
    """How many digits normalise_plate turned into letters to fit a plate layout (state code, series letters and BH
    letters together). One is a common misread; two or more usually means other text, such as a phone number on a
    hoarding that fits the layout only after the repair. The look-alike state fix swaps letters, so it never counts."""
    s = _clean(raw)
    if not s or _BH.match(s) or _STD.match(s):
        return 0
    rep = _repair_standard(s) or _repair_bh(s)
    return sum(a.isdigit() and b.isalpha() for a, b in zip(s, rep)) if rep else 0


def looks_like_indian_plate(norm: str) -> bool:
    m = _STD.match(norm)
    if m:
        return m.group(1) in STATE_CODES
    return bool(_BH.match(norm))


def plate_variants(norm: str, max_variants: int = 12) -> list[str]:
    """Plausible alternative reads for fuzzy watchlist lookup.

    Generates single-character substitutions within the confusion classes at
    each position where the character class is ambiguous. Kept small on purpose:
    trigram similarity in Postgres handles the long tail.
    """
    if not norm:
        return []
    classes = [("O", "0", "Q", "D"), ("I", "1", "L"), ("Z", "2"), ("S", "5"), ("B", "8"),
               ("G", "6"), ("A", "4"), ("T", "7")]
    lookup = {ch: cls for cls in classes for ch in cls}
    out: list[str] = []
    for i, ch in enumerate(norm):
        for alt in lookup.get(ch, ()):
            if alt == ch:
                continue
            cand = norm[:i] + alt + norm[i + 1:]
            if cand not in out:
                out.append(cand)
            if len(out) >= max_variants:
                return out
    return out


def mask_plate(norm: str) -> str:
    """A plate for a log line: the state code and the last two characters, the rest starred. Logs leave the
    database's scoping, audit and retention, so they never carry a whole registration."""
    s = str(norm or "")
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]
