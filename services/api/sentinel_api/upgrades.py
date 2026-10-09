"""Schema additions made after first deployment.

infra/postgres/init runs only on an empty database, so anything added later is applied
here, idempotently, at every API start. Fresh and existing databases end up the same.
"""
from __future__ import annotations

import asyncpg

UPGRADES = r"""
-- Watchlist near-miss matching by one-character masks. A plate within one substitution of
-- a watchlist plate shares exactly one mask with it ('GJ01AB1_34'), so a 1-edit match is a
-- handful of btree lookups instead of levenshtein() against every entry: about 1 ms against
-- 45-56 ms per plate read at 100k entries, measured by bench/matcher.py (bench/results/matcher.md).
CREATE OR REPLACE FUNCTION plate_masks(p text) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$ SELECT array_agg(overlay(p placing '_' from i for 1) ORDER BY i) FROM generate_series(1, length(p)) AS i $$;

CREATE TABLE IF NOT EXISTS watchlist_masks (
    mask         TEXT NOT NULL,
    watchlist_id UUID NOT NULL REFERENCES watchlist_entries(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS watchlist_masks_mask_idx ON watchlist_masks (mask);
CREATE INDEX IF NOT EXISTS watchlist_masks_entry_idx ON watchlist_masks (watchlist_id);

-- Statement-level, so a bulk watchlist sync (e.g. 100k VAHAN stolen-vehicle records) writes
-- its masks in one pass instead of one trigger call per row.
DROP TRIGGER IF EXISTS watchlist_masks_sync ON watchlist_entries;
DROP FUNCTION IF EXISTS watchlist_masks_sync();
CREATE OR REPLACE FUNCTION watchlist_masks_ins() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    INSERT INTO watchlist_masks (mask, watchlist_id)
    SELECT unnest(plate_masks(n.plate_norm)), n.id FROM new_rows n WHERE n.plate_norm IS NOT NULL;
    RETURN NULL;
END
$fn$;
CREATE OR REPLACE FUNCTION watchlist_masks_upd() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
    DELETE FROM watchlist_masks m USING new_rows n, old_rows o
     WHERE m.watchlist_id = n.id AND o.id = n.id AND o.plate_norm IS DISTINCT FROM n.plate_norm;
    INSERT INTO watchlist_masks (mask, watchlist_id)
    SELECT unnest(plate_masks(n.plate_norm)), n.id
      FROM new_rows n JOIN old_rows o ON o.id = n.id
     WHERE n.plate_norm IS NOT NULL AND o.plate_norm IS DISTINCT FROM n.plate_norm;
    RETURN NULL;
END
$fn$;
DROP TRIGGER IF EXISTS watchlist_masks_ins ON watchlist_entries;
CREATE TRIGGER watchlist_masks_ins AFTER INSERT ON watchlist_entries
    REFERENCING NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION watchlist_masks_ins();
DROP TRIGGER IF EXISTS watchlist_masks_upd ON watchlist_entries;
CREATE TRIGGER watchlist_masks_upd AFTER UPDATE ON watchlist_entries
    REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT
    EXECUTE FUNCTION watchlist_masks_upd();

INSERT INTO watchlist_masks (mask, watchlist_id)
SELECT unnest(plate_masks(w.plate_norm)), w.id
FROM watchlist_entries w
WHERE w.plate_norm IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM watchlist_masks m WHERE m.watchlist_id = w.id);

-- Ingest batches already stored, so a worker's replay of a batch whose reply was lost (the
-- API stored it, the worker timed out and spooled it) is recognised and not stored twice.
CREATE TABLE IF NOT EXISTS ingest_batches (
    batch_id    TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    rows        INT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
DELETE FROM ingest_batches WHERE received_at < now() - interval '14 days';

-- Alerts: a retrospective hit (a plate added to the watchlist had already been seen) is
-- flagged as such; alert_type/detail leave room for alerts that are not watchlist hits.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS retrospective BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_type TEXT NOT NULL DEFAULT 'watchlist';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS detail JSONB NOT NULL DEFAULT '{}'::jsonb;

-- G3 (bench/pipeline_gates.md): how many reads stood behind a sighting and how far the vote agreed (the weakest
-- position's winning share, 0-1), so an operator can tell a one-read 0.6 from a three-read 0.95. The movement
-- view lists its columns, so it is recreated with the two added at the end.
ALTER TABLE vehicle_sightings ADD COLUMN IF NOT EXISTS reads INT;
ALTER TABLE vehicle_sightings ADD COLUMN IF NOT EXISTS agreement REAL;
CREATE OR REPLACE VIEW v_vehicle_movement AS
SELECT s.id, s.plate_norm, s.plate_text, s.event_ts, s.ocr_conf, s.det_conf,
       s.vehicle_type, s.vehicle_color, s.crop_path, s.track_id,
       c.id AS camera_id, c.camera_code, c.name AS camera_name, c.address, c.taluka,
       d.name AS district, dept.name AS department,
       ST_Y(c.location::geometry) AS lat, ST_X(c.location::geometry) AS lon,
       s.reads, s.agreement
FROM vehicle_sightings s
JOIN cameras c ON c.id = s.camera_id
JOIN departments dept ON dept.id = c.department_id
LEFT JOIN districts d ON d.id = c.district_id;

-- Plate review: a person's verdict on a stored read, judged against its evidence crop. The read
-- and its confidence are copied in, so results survive the sighting's retention. Blind (the
-- reviewer typed what they saw before seeing Sentinel's read) and verify are never mixed.
CREATE TABLE IF NOT EXISTS plate_reviews (
    id           BIGSERIAL PRIMARY KEY,
    sighting_id  BIGINT NOT NULL,
    sighting_ts  TIMESTAMPTZ NOT NULL,        -- vehicle_sightings is partitioned: its key is (id, event_ts)
    camera_id    UUID NOT NULL,
    reviewer_id  UUID NOT NULL REFERENCES users(id),
    mode         TEXT NOT NULL CHECK (mode IN ('blind', 'verify')),
    seen         TEXT,                        -- blind: what the reviewer typed; verify: the correction
    verdict      TEXT NOT NULL CHECK (verdict IN ('exact', 'one_off', 'wrong', 'not_a_plate', 'unreadable')),
    stored_plate TEXT NOT NULL,               -- Sentinel's read at review time
    ocr_conf     REAL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sighting_id, reviewer_id, mode)
);
CREATE INDEX IF NOT EXISTS plate_reviews_camera_idx ON plate_reviews (camera_id, mode);
-- A reviewer's later change to their own review (a mistyped plate). In blind mode the page has shown Sentinel's read
-- by then, so the change is not blind: seen and verdict keep the first reading, which blind results use, and the
-- change is kept beside it with its time.
ALTER TABLE plate_reviews ADD COLUMN IF NOT EXISTS corrected_seen TEXT;
ALTER TABLE plate_reviews ADD COLUMN IF NOT EXISTS corrected_verdict TEXT
    CHECK (corrected_verdict IN ('exact', 'one_off', 'wrong', 'not_a_plate', 'unreadable'));
ALTER TABLE plate_reviews ADD COLUMN IF NOT EXISTS corrected_at TIMESTAMPTZ;
-- Sightings whose read a user saw in Results' plate-by-plate list (everyone's reviews) before checking them: as after a
-- quick verify, the blind queue leaves them out for that user and a blind review of them is refused.
CREATE TABLE IF NOT EXISTS plate_review_shown (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sighting_id BIGINT NOT NULL,
    shown_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, sighting_id)
);

-- Capture quality: each stored evidence crop measured and graded good / marginal / poor with its reasons
-- (capture_quality.py), so a camera is judged by what it captures. Metrics only, no plate text; keyed like
-- the partitioned vehicle_sightings, (id, event_ts). Written after ingest and by scripts/quality_backfill.py.
CREATE TABLE IF NOT EXISTS sighting_quality (
    sighting_id BIGINT NOT NULL,
    sighting_ts TIMESTAMPTZ NOT NULL,
    camera_id   UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    plate_w     INT,                    -- plate box, stream pixels
    plate_h     INT,
    char_h      INT,                    -- estimated character height
    layout      TEXT,                   -- one-line | two-line
    sharpness   REAL,
    brightness  REAL,
    contrast    REAL,
    clipped     REAL,                   -- share of plate pixels at <= 5 or >= 250
    oblique     BOOLEAN,
    quality     TEXT NOT NULL CHECK (quality IN ('good', 'marginal', 'poor')),
    reasons     TEXT[] NOT NULL DEFAULT '{}',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (sighting_id, sighting_ts)
);
CREATE INDEX IF NOT EXISTS sighting_quality_camera_idx ON sighting_quality (camera_id, sighting_ts);

-- Model 1 names "camera health and maintenance-status monitoring" and a gap analysis of "ageing infrastructure":
-- each camera's maintenance state, the year it was installed and when its AMC or warranty ends.
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS maintenance TEXT NOT NULL DEFAULT 'in_service'
    CHECK (maintenance IN ('in_service', 'under_maintenance', 'faulty', 'decommissioned'));
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS maintenance_note TEXT;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS install_year SMALLINT CHECK (install_year BETWEEN 1990 AND 2100);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS amc_expiry DATE;

-- Model 2 names "event tagging": operators tag alerts (a case number, "vehicle intercepted") and filter by tag.
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS tags TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS alerts_tags_gin ON alerts USING GIN (tags);
"""


async def apply_upgrades(conn: asyncpg.Connection) -> None:
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(724501)")   # one replica at a time
        await conn.execute(UPGRADES)


def plate_masks(plate: str) -> list[str]:
    """Same as the SQL function: one mask per position."""
    return [plate[:i] + "_" + plate[i + 1:] for i in range(len(plate))]
