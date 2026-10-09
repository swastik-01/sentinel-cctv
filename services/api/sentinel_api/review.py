"""Plate review: a person checks a stored read against its evidence crop.

Blind mode: the reviewer types the plate they see without being shown Sentinel's read, and the
verdict comes from comparing the two here, so no one grades their own agreement by eye.
"""
from __future__ import annotations

from sentinel_common import normalise_plate

UNREADABLE, NOT_A_PLATE = "?", "-"


def edits(a: str, b: str) -> int:
    """Levenshtein distance: substitutions, missing and extra characters each count one."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def reading(seen: str) -> str:
    """What the reviewer typed: '?' and '-' kept; otherwise letters and digits only, upper case (spaces,
    punctuation and case do not count as differences). Never the reads' digit-to-letter repair: a person's
    reading is the ground truth being collected, so a 2 they typed stays a 2."""
    s = seen.strip()
    return s if s in (UNREADABLE, NOT_A_PLATE) else "".join(ch for ch in s.upper() if ch.isascii() and ch.isalnum())


def verdict(seen: str, stored: str) -> str:
    s = reading(seen)
    if s == UNREADABLE:
        return "unreadable"
    if s == NOT_A_PLATE or not any(ch.isalpha() for ch in s):
        return "not_a_plate"      # every Indian registration has letters: digits alone are a phone number or a sign
    d = edits(s, normalise_plate(stored))
    return "exact" if d == 0 else "one_off" if d == 1 else "wrong"


def correction(first_seen: str | None, first_verdict: str, seen: str, stored: str) -> tuple[str, str] | None:
    """A reviewer's later change to their own review: the new (reading, verdict), or None when it says what the review
    already says (which takes an earlier change back). A verify review that confirmed the read has no reading, so
    there the verdict decides."""
    new = (reading(seen), verdict(seen, stored))
    if new[0] == first_seen or (first_seen is None and new[1] == first_verdict):
        return None
    return new
