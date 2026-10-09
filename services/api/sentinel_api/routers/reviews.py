"""Plate review: supervisors and auditors check Sentinel's stored reads against their evidence crops.

Blind: the queue carries no plate text and no confidence, the reviewer types what they see, and the
verdict is computed here from their reading and the stored one. Verify: the reviewer is shown the
read and confirms or corrects it. Results keep the two apart; only blind numbers are independent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field

from ..audit import audit
from ..auth import User, require
from ..cameras_repo import scope_clause
from ..db import get_conn, rows_to_dicts
from ..review import correction, reading, verdict as judge
from .evidence import crop_file, send_crop, token_user

router = APIRouter(prefix="/reviews", tags=["reviews"])

Mode = Literal["blind", "verify"]
VERDICTS = ("exact", "one_off", "wrong", "not_a_plate", "unreadable")
VERIFY_AS = {"correct": "exact", "not_a_plate": "not_a_plate", "unreadable": "unreadable"}
# ocr_conf is REAL: compared with a numeric 0.9 it is widened to 0.8999999761 and drops a band.
BAND = """CASE WHEN r.ocr_conf >= real '0.9' THEN '>=0.9' WHEN r.ocr_conf >= real '0.7' THEN '0.7-0.9'
               WHEN r.ocr_conf >= real '0.5' THEN '0.5-0.7' WHEN r.ocr_conf >= real '0.35' THEN '0.35-0.5'
               ELSE '<0.35' END"""
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class ReviewIn(BaseModel):
    sighting_id: int = Field(ge=1, le=2**63 - 1)
    mode: Mode
    seen: str | None = Field(None, max_length=32)   # the plate as read; '?' unreadable, '-' not a plate
    verdict: str | None = None                      # verify only: correct | wrong | not_a_plate | unreadable


class ReviewEdit(BaseModel):
    mode: Mode
    seen: str = Field(min_length=1, max_length=32)  # the plate as the crop shows it; '?' unreadable, '-' not a plate


class Filters:
    """WHERE clauses with numbered parameters, starting from the user's camera scope."""

    def __init__(self, user: User):
        where, self.params = scope_clause(user, alias="c")
        self.clauses = [where]

    def add(self, cond: str, val) -> None:
        self.params.append(val)
        self.clauses.append(cond.replace("?", f"${len(self.params)}"))

    def window(self, col: str, camera: list[str] | None, since: datetime | None, until: datetime | None,
               prefix: str | None = None):
        if camera:
            self.add("c.camera_code = ANY(?::text[])", [c.strip().upper() for c in camera])
        if prefix:      # a family of cameras, e.g. every "CAM.." of one estate, without listing them
            esc = prefix.strip().upper().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            self.add("c.camera_code LIKE ?", esc + "%")
        if since:
            self.add(f"{col} >= ?", since)
        if until:
            self.add(f"{col} <= ?", until)

    @property
    def sql(self) -> str:
        return " AND ".join(self.clauses)


def _conf(c: float | None) -> float | None:
    return None if c is None else round(c, 3)


def _review(r) -> dict:
    """A saved review as its reviewer sees it: the first reading (what blind results use) and any later change."""
    return {"sighting_id": r["sighting_id"], "mode": r["mode"], "verdict": r["verdict"], "seen": r["seen"],
            "stored_plate": r["stored_plate"], "ocr_conf": _conf(r["ocr_conf"]), "corrected_seen": r["corrected_seen"],
            "corrected_verdict": r["corrected_verdict"], "corrected_at": r["corrected_at"]}


async def _sighting(conn: asyncpg.Connection, user: User, sighting_id: int):
    where, params = scope_clause(user, alias="c", start_idx=2)
    return await conn.fetchrow(
        f"""SELECT s.id, s.event_ts, s.camera_id, c.camera_code, s.plate_norm, s.ocr_conf, s.crop_path
            FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
            WHERE s.id = $1 AND s.crop_path IS NOT NULL AND {where}""", sighting_id, *params)


@router.get("/queue")
async def queue(mode: Mode, camera: list[str] | None = Query(None), prefix: str | None = Query(None, max_length=20),
                since: datetime | None = None, until: datetime | None = None,
                band: Literal["all", "low"] = Query("all", description="low: reads below 0.9 nobody has reviewed"),
                limit: int = Query(50, ge=1, le=200),
                user: User = Depends(require("reviews.read")),
                conn: asyncpg.Connection = Depends(get_conn)):
    """Stored reads with a crop that this user has not reviewed in this mode, oldest first. A blind
    check is blind only on a read the reviewer has not been shown, so the blind queue also leaves
    out whatever they verified. `band=low` (G3, bench/pipeline_gates.md) narrows it to the reads marked
    "check the crop" that no one has reviewed in any mode: the operator's queue after a shift."""
    f = Filters(user)
    f.clauses.append("s.crop_path IS NOT NULL")
    if band == "low":       # the review page's band, compared as the summary does (ocr_conf is REAL)
        f.clauses.append("s.ocr_conf < real '0.9' AND NOT EXISTS (SELECT 1 FROM plate_reviews r WHERE r.sighting_id = s.id)")
    f.add("NOT EXISTS (SELECT 1 FROM plate_reviews r WHERE r.sighting_id = s.id AND r.reviewer_id = ?"
          + ("" if mode == "blind" else " AND r.mode = 'verify'") + ")", user.id)
    if mode == "blind":     # nor a read this user saw in Results' list of everyone's reviews
        f.add("NOT EXISTS (SELECT 1 FROM plate_review_shown x WHERE x.sighting_id = s.id AND x.user_id = ?)", user.id)
    f.window("s.event_ts", camera, since, until, prefix)
    n = len(f.params)
    sql = f"""SELECT s.id AS sighting_id, s.event_ts, c.camera_code, c.name AS camera_name, s.crop_path,
                     s.plate_norm, s.ocr_conf
              FROM vehicle_sightings s JOIN cameras c ON c.id = s.camera_id
              WHERE {f.sql} AND (s.event_ts, s.id) > (${n + 1}, ${n + 2})
              ORDER BY s.event_ts, s.id LIMIT ${n + 3}"""
    # A crop missing from disk would be judged "unreadable" from a broken image: skip it, and page on.
    rows, after = [], (EPOCH, 0)
    for _ in range(10):
        page = await conn.fetch(sql, *f.params, *after, limit)
        rows += [r for r in page if crop_file(r["crop_path"])]
        if len(page) < limit or len(rows) >= limit:
            break
        after = (page[-1]["event_ts"], page[-1]["sighting_id"])

    items = []
    for r in rows[:limit]:
        # The stored crop's file name carries the plate, so the crop goes out under the sighting id.
        item = {"sighting_id": r["sighting_id"], "event_ts": r["event_ts"], "camera_code": r["camera_code"],
                "camera_name": r["camera_name"], "crop_path": f"/reviews/crop/{r['sighting_id']}"}
        if mode == "verify":
            item |= {"plate_norm": r["plate_norm"], "ocr_conf": _conf(r["ocr_conf"])}
        items.append(item)
    return items


@router.get("/crop/{sighting_id}", include_in_schema=False)
async def crop(request: Request, sighting_id: int = Path(ge=1, le=2**63 - 1),
               conn: asyncpg.Connection = Depends(get_conn)):
    """A queue item's crop, for the Authorization header's user (evidence.token_user: never a token in the URL)."""
    user = await token_user(request, conn)
    if not user.can("reviews.read"):
        raise HTTPException(403, "missing permission: reviews.read")
    s = await _sighting(conn, user, sighting_id)
    path = crop_file(s["crop_path"]) if s else None
    if path is None:
        raise HTTPException(404, "no such crop")
    return send_crop(path)


@router.post("", status_code=201)
async def create(body: ReviewIn, request: Request,
                 user: User = Depends(require("reviews.write")),
                 conn: asyncpg.Connection = Depends(get_conn)):
    """Record a verdict and reveal Sentinel's read. In blind mode any client verdict is ignored."""
    seen = (body.seen or "").strip()
    if body.mode == "blind" and not seen:
        raise HTTPException(422, "a blind review needs seen: the plate as read, '?' if unreadable, '-' if not a plate")
    if body.mode == "verify":
        if body.verdict not in (*VERIFY_AS, "wrong"):
            raise HTTPException(422, "verdict must be correct, wrong, not_a_plate or unreadable")
        if body.verdict == "wrong" and not seen:
            raise HTTPException(422, "a 'wrong' verdict needs seen: the plate as it should read")
    compare = body.mode == "blind" or body.verdict == "wrong"
    if compare and not reading(seen):
        raise HTTPException(422, "seen holds no letters or digits")

    s = await _sighting(conn, user, body.sighting_id)
    if s is None:
        raise HTTPException(404, "no such sighting with a crop")
    # A "wrong" that matches the stored read after all is recorded as exact: the server compares.
    verdict = judge(seen, s["plate_norm"]) if compare else VERIFY_AS[body.verdict]
    async with conn.transaction():
        if body.mode == "blind" and await conn.fetchval(
                """SELECT 1 FROM plate_reviews WHERE sighting_id = $1 AND reviewer_id = $2 AND mode = 'verify'
                   UNION ALL SELECT 1 FROM plate_review_shown WHERE sighting_id = $1 AND user_id = $2 LIMIT 1""",
                s["id"], user.id):
            raise HTTPException(409, "you have already been shown this read: a blind check of it would not be blind")
        rid = await conn.fetchval(
            """INSERT INTO plate_reviews (sighting_id, sighting_ts, camera_id, reviewer_id, mode, seen, verdict,
                                          stored_plate, ocr_conf)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
               ON CONFLICT (sighting_id, reviewer_id, mode) DO NOTHING RETURNING id""",
            s["id"], s["event_ts"], s["camera_id"], user.id, body.mode, reading(seen) if compare else None,
            verdict, s["plate_norm"], s["ocr_conf"])
        if rid is None:
            raise HTTPException(409, f"already reviewed by you in {body.mode} mode")
        # No plate text in the audit trail: the review is traceable by sighting id.
        await audit(conn, request, user, "plate.review", "sighting", s["id"], mode=body.mode, verdict=verdict,
                    camera=s["camera_code"])
    return {"sighting_id": s["id"], "mode": body.mode, "verdict": verdict,
            "seen": reading(seen) if compare else None, "stored_plate": s["plate_norm"],
            "ocr_conf": _conf(s["ocr_conf"])}


@router.get("/mine")
async def mine(mode: Mode, camera: list[str] | None = Query(None), prefix: str | None = Query(None, max_length=20),
               since: datetime | None = None, until: datetime | None = None, limit: int = Query(50, ge=1, le=200),
               user: User = Depends(require("reviews.write")),
               conn: asyncpg.Connection = Depends(get_conn)):
    """The reviews this user saved in one mode, newest first, to look at a crop again and correct a reading. Each
    carries Sentinel's read: the page showed it to them when they saved the review."""
    f = Filters(user)
    f.add("r.reviewer_id = ?", user.id)
    f.add("r.mode = ?", mode)
    f.window("r.sighting_ts", camera, since, until, prefix)
    rows = await conn.fetch(
        f"""SELECT r.sighting_id, r.sighting_ts, r.mode, r.seen, r.verdict, r.stored_plate, r.ocr_conf, r.corrected_seen,
                   r.corrected_verdict, r.corrected_at, r.created_at, c.camera_code, c.name AS camera_name
            FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id
            WHERE {f.sql} ORDER BY r.created_at DESC, r.id DESC LIMIT ${len(f.params) + 1}""", *f.params, limit)
    return [_review(r) | {"event_ts": r["sighting_ts"], "camera_code": r["camera_code"], "camera_name": r["camera_name"],
                          "crop_path": f"/reviews/crop/{r['sighting_id']}", "created_at": r["created_at"]} for r in rows]


@router.patch("/{sighting_id}")
async def edit(body: ReviewEdit, request: Request, sighting_id: int = Path(ge=1, le=2**63 - 1),
               user: User = Depends(require("reviews.write")),
               conn: asyncpg.Connection = Depends(get_conn)):
    """Change your own saved review, e.g. a mistyped plate. The first reading is never overwritten: in blind mode the
    page had shown Sentinel's read before any change, so only the first reading is blind. The change is kept beside
    it with its time, and the server grades it as it graded the first; sending the first reading again takes it back."""
    if not reading(body.seen):
        raise HTTPException(422, "seen holds no letters or digits")
    where, params = scope_clause(user, alias="c", start_idx=4)
    async with conn.transaction():
        r = await conn.fetchrow(
            f"""SELECT r.id, r.seen, r.verdict, r.stored_plate, c.camera_code
                FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id
                WHERE r.sighting_id = $1 AND r.reviewer_id = $2 AND r.mode = $3 AND {where} FOR UPDATE OF r""",
            sighting_id, user.id, body.mode, *params)
        if r is None:
            raise HTTPException(404, f"no {body.mode} review of yours for this sighting")
        new = correction(r["seen"], r["verdict"], body.seen, r["stored_plate"])
        row = await conn.fetchrow(
            """UPDATE plate_reviews SET corrected_seen = $2, corrected_verdict = $3,
                      corrected_at = CASE WHEN $3::text IS NULL THEN NULL ELSE now() END
               WHERE id = $1
               RETURNING sighting_id, mode, seen, verdict, stored_plate, ocr_conf, corrected_seen, corrected_verdict,
                         corrected_at""", r["id"], *(new or (None, None)))
        # As for the review itself: no plate text in the audit trail.
        await audit(conn, request, user, "plate.review.edit", "sighting", sighting_id, mode=body.mode,
                    first_verdict=r["verdict"], verdict=new[1] if new else None, camera=r["camera_code"])
    return _review(row)


@router.get("/plates")
async def plates(request: Request, scope: Literal["mine", "all"] = "mine", mode: Mode | None = None,
                 camera: list[str] | None = Query(None), prefix: str | None = Query(None, max_length=20),
                 since: datetime | None = None, until: datetime | None = None,
                 limit: int = Query(500, ge=1, le=2000),
                 user: User = Depends(require("reviews.read")),
                 conn: asyncpg.Connection = Depends(get_conn)):
    """Results plate by plate: each review's reading beside Sentinel's read, in sighting order. `mine` lists this
    user's own reviews, whose reads the page has already shown them. `all` adds everyone else's: a crop this user has
    not checked then counts as shown to them, so it leaves their blind queue and a blind check of it is refused, as
    after a quick verify. The listing is audited, without plate text."""
    f = Filters(user)
    if scope == "mine":
        f.add("r.reviewer_id = ?", user.id)
    if mode:
        f.add("r.mode = ?", mode)
    f.window("r.sighting_ts", camera, since, until, prefix)
    n = len(f.params)
    rows = await conn.fetch(
        f"""SELECT r.sighting_id, r.sighting_ts, r.mode, r.seen, r.verdict, r.stored_plate, r.ocr_conf, r.corrected_seen,
                   r.corrected_verdict, r.corrected_at, r.created_at, r.reviewer_id = ${n + 1} AS mine,
                   c.camera_code, c.name AS camera_name, u.username, u.full_name
            FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id
            WHERE {f.sql} ORDER BY r.sighting_ts, r.sighting_id, r.created_at LIMIT ${n + 2}""", *f.params, user.id, limit)
    async with conn.transaction():
        if scope == "all" and rows:
            ids = sorted({r["sighting_id"] for r in rows})
            await conn.execute(
                """INSERT INTO plate_review_shown (user_id, sighting_id)
                   SELECT $1, i FROM unnest($2::bigint[]) AS i
                   WHERE NOT EXISTS (SELECT 1 FROM plate_reviews r WHERE r.sighting_id = i AND r.reviewer_id = $1)
                   ON CONFLICT DO NOTHING""", user.id, ids)
        await audit(conn, request, user, "plate.review.list", "reviews", scope, rows=len(rows), mode=mode)
    return [_review(r) | {"event_ts": r["sighting_ts"], "camera_code": r["camera_code"], "camera_name": r["camera_name"],
                          "crop_path": f"/reviews/crop/{r['sighting_id']}", "created_at": r["created_at"],
                          "reviewer": r["username"], "reviewer_name": r["full_name"], "mine": r["mine"]} for r in rows]


@router.get("/summary")
async def summary(camera: list[str] | None = Query(None), prefix: str | None = Query(None, max_length=20),
                  since: datetime | None = None, until: datetime | None = None,
                  user: User = Depends(require("reviews.read")),
                  conn: asyncpg.Connection = Depends(get_conn)):
    """Counts only, no plate text. The window is on the sighting's time, as in the queue. Verdicts are the first
    readings; `corrected` counts the reviews their reviewer changed afterwards."""
    f = Filters(user)
    f.window("r.sighting_ts", camera, since, until, prefix)
    base = f"""FROM plate_reviews r JOIN cameras c ON c.id = r.camera_id JOIN users u ON u.id = r.reviewer_id
               WHERE {f.sql}"""
    counts = ", ".join(f"count(*) FILTER (WHERE r.verdict = '{v}') AS {v}" for v in VERDICTS)
    reviewers = await conn.fetch(
        f"""SELECT u.username, u.full_name, count(*) FILTER (WHERE r.mode = 'blind') AS blind,
                   count(*) FILTER (WHERE r.mode = 'verify') AS verify,
                   count(*) FILTER (WHERE r.corrected_at IS NOT NULL) AS corrected
            {base} GROUP BY u.username, u.full_name ORDER BY u.username""", *f.params)
    cameras = await conn.fetch(
        f"""SELECT c.camera_code, c.name AS camera_name, r.mode, count(*) AS n, {counts}
            {base} GROUP BY c.camera_code, c.name, r.mode ORDER BY c.camera_code, r.mode""", *f.params)
    # How often a read is right at each confidence: vehicle plates only, a crop with no plate or
    # none a person can read says nothing about the read.
    bands = await conn.fetch(
        f"""SELECT r.mode, {BAND} AS band, count(*) AS n_plates,
                   count(*) FILTER (WHERE r.verdict = 'exact') AS exact,
                   count(*) FILTER (WHERE r.verdict = 'one_off') AS one_off
            {base} AND r.ocr_conf IS NOT NULL AND r.verdict NOT IN ('not_a_plate', 'unreadable')
            GROUP BY 1, 2 ORDER BY 1, min(r.ocr_conf)""", *f.params)
    agreement = await conn.fetchrow(
        f"""SELECT count(*) AS sightings_with_2plus_blind,
                   count(*) FILTER (WHERE verdicts = 1) AS same_verdict,
                   count(*) FILTER (WHERE readings = 1) AS same_reading
            FROM (SELECT r.sighting_id, count(DISTINCT r.verdict) AS verdicts, count(DISTINCT r.seen) AS readings
                  {base} AND r.mode = 'blind' GROUP BY r.sighting_id HAVING count(*) >= 2) g""", *f.params)
    return {"reviewers": rows_to_dicts(reviewers), "cameras": rows_to_dicts(cameras),
            "bands": rows_to_dicts(bands), "agreement": dict(agreement)}
