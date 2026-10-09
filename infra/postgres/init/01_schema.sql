-- Sentinel :: Gujarat Police CCTV Integration Platform
-- Model 1 (registry + GIS) and Model 2 (unified viewing + metadata analytics) schema.
-- Vendor-neutral by design: no column assumes a particular VMS or camera make.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- trigram index: cheap prefilter for near-miss plates
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch; -- levenshtein(): the actual OCR-error tolerance
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------- enums

CREATE TYPE camera_class     AS ENUM ('fixed', 'ptz', 'dome', 'bullet', 'anpr', 'thermal');
CREATE TYPE integration_mode AS ENUM ('analog_dvr', 'ip_onvif', 'ip_rtsp', 'vms_api', 'cloud_api');
CREATE TYPE storage_mode     AS ENUM ('local', 'cloud', 'hybrid', 'unknown');
CREATE TYPE ownership        AS ENUM ('government', 'private_shared');
CREATE TYPE health_state     AS ENUM ('online', 'degraded', 'offline', 'unknown');
CREATE TYPE watch_kind       AS ENUM ('stolen_vehicle', 'wanted_person', 'missing_person', 'blacklisted_vehicle', 'bolo');
CREATE TYPE alert_status     AS ENUM ('new', 'acknowledged', 'closed', 'false_positive');
CREATE TYPE severity_level   AS ENUM ('low', 'medium', 'high', 'critical');

-- ---------------------------------------------------------------- org units

-- The 26 government departments, each historically running its own CCTV island.
CREATE TABLE departments (
    id            SERIAL PRIMARY KEY,
    code          TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    contact_name  TEXT,
    contact_email TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE districts (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    range_name TEXT,
    centroid   GEOGRAPHY(POINT, 4326),
    boundary   GEOGRAPHY(MULTIPOLYGON, 4326)
);

-- A source system is one department's VMS/NVR/DVR head-end. Model 3 federation
-- attaches adapters here; Model 2 connects straight through without middleware.
CREATE TABLE source_systems (
    id                  SERIAL PRIMARY KEY,
    department_id       INT NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    name                TEXT NOT NULL,
    vendor              TEXT,
    product             TEXT,
    version             TEXT,
    mode                integration_mode NOT NULL,
    base_url            TEXT,
    adapter             TEXT,                 -- python entrypoint of the vendor adapter
    credentials_ref     TEXT,                 -- pointer into the secret store, never the secret
    notes               TEXT,
    remains_independent BOOLEAN NOT NULL DEFAULT true,  -- we never replace dept infrastructure
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (department_id, name)
);

-- ---------------------------------------------------------------- registry

CREATE TABLE cameras (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    camera_code       TEXT NOT NULL UNIQUE,          -- stable statewide identifier
    name              TEXT NOT NULL,
    department_id     INT NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    source_system_id  INT REFERENCES source_systems(id) ON DELETE SET NULL,
    district_id       INT REFERENCES districts(id) ON DELETE SET NULL,

    location          GEOGRAPHY(POINT, 4326),
    address           TEXT,
    taluka            TEXT,
    landmark          TEXT,
    bearing_deg       SMALLINT CHECK (bearing_deg BETWEEN 0 AND 359),
    field_of_view_deg SMALLINT,
    view_range_m      INT,

    camera_class      camera_class NOT NULL DEFAULT 'fixed',
    mode              integration_mode NOT NULL,
    ownership         ownership NOT NULL DEFAULT 'government',
    vendor            TEXT,
    model             TEXT,
    codec             TEXT,                          -- H.264 / H.265 / MJPEG
    resolution        TEXT,
    fps               SMALLINT,
    retention_days    SMALLINT,                      -- observed 7 to 15+ across depts
    storage           storage_mode NOT NULL DEFAULT 'unknown',

    -- Stream endpoints. Mirrors the sandbox contract: RTSP for inference,
    -- WHEP for browser preview, HLS for dashboards and mobile.
    rtsp_url          TEXT,
    whep_url          TEXT,
    hls_url           TEXT,
    onvif_url         TEXT,
    credentials_ref   TEXT,

    -- Is this camera positioned such that plate OCR is viable? Most wide-angle
    -- cameras are not, and pretending otherwise is how ANPR demos fail.
    anpr_viable       BOOLEAN NOT NULL DEFAULT false,

    health            health_state NOT NULL DEFAULT 'unknown',
    last_seen_at      TIMESTAMPTZ,
    analytics_enabled BOOLEAN NOT NULL DEFAULT false,
    tags              JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX cameras_location_gix   ON cameras USING GIST (location);
CREATE INDEX cameras_department_idx ON cameras (department_id);
CREATE INDEX cameras_health_idx     ON cameras (health);
CREATE INDEX cameras_district_idx   ON cameras (district_id);
CREATE INDEX cameras_anpr_idx       ON cameras (anpr_viable) WHERE anpr_viable;
CREATE INDEX cameras_tags_gin       ON cameras USING GIN (tags);

CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $fn$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END
$fn$ LANGUAGE plpgsql;

CREATE TRIGGER cameras_touch BEFORE UPDATE ON cameras
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- Rolling health history, used by the uptime and gap-analysis reports.
CREATE TABLE camera_health_checks (
    id           BIGSERIAL PRIMARY KEY,
    camera_id    UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    reachable    BOOLEAN NOT NULL,
    latency_ms   INT,
    fps_observed REAL,
    state        health_state NOT NULL,
    error        TEXT
);
CREATE INDEX health_camera_time_idx ON camera_health_checks (camera_id, checked_at DESC);

-- ---------------------------------------------------------------- sightings

-- One row per plate read. Partitioned monthly: at 80k cameras this table is the
-- hot path, and dropping an old partition beats deleting a billion rows.
CREATE TABLE vehicle_sightings (
    id            BIGSERIAL,
    camera_id     UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    event_ts      TIMESTAMPTZ NOT NULL,     -- FRAME timestamp, never arrival time
    ingest_ts     TIMESTAMPTZ NOT NULL DEFAULT now(),
    plate_text    TEXT NOT NULL,            -- as read by OCR
    plate_norm    TEXT NOT NULL,            -- normalised for matching
    ocr_conf      REAL NOT NULL,
    det_conf      REAL NOT NULL,
    vehicle_type  TEXT,
    vehicle_color TEXT,
    bbox          INT[] NOT NULL,           -- [x, y, w, h] in source pixels
    track_id      TEXT,                     -- per-camera tracker identity
    crop_path     TEXT,
    frame_uri     TEXT,
    PRIMARY KEY (id, event_ts)
) PARTITION BY RANGE (event_ts);

CREATE INDEX sightings_plate_time_idx  ON vehicle_sightings (plate_norm, event_ts DESC);
CREATE INDEX sightings_camera_time_idx ON vehicle_sightings (camera_id, event_ts DESC);
CREATE INDEX sightings_plate_trgm      ON vehicle_sightings USING GIN (plate_norm gin_trgm_ops);

-- Non-plate detections (vehicle counts, crowd density, anomalies). Kept apart so
-- the plate hot path stays narrow.
CREATE TABLE detection_events (
    id          BIGSERIAL,
    camera_id   UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    event_ts    TIMESTAMPTZ NOT NULL,
    ingest_ts   TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type  TEXT NOT NULL,              -- vehicle_count, crowd_density, loitering, ...
    label       TEXT,
    confidence  REAL,
    value       DOUBLE PRECISION,
    bbox        INT[],
    track_id    TEXT,
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (id, event_ts)
) PARTITION BY RANGE (event_ts);

CREATE INDEX detection_camera_time_idx ON detection_events (camera_id, event_ts DESC);
CREATE INDEX detection_type_time_idx   ON detection_events (event_type, event_ts DESC);

-- Partitions for the demo window plus headroom. A cron job extends this in production.
DO $init$
DECLARE
    m DATE := date_trunc('month', now() - interval '2 months')::date;
BEGIN
    FOR i IN 0..11 LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS vehicle_sightings_%s PARTITION OF vehicle_sightings
               FOR VALUES FROM (%L) TO (%L)',
            to_char(m, 'YYYYMM'), m, (m + interval '1 month')::date);
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS detection_events_%s PARTITION OF detection_events
               FOR VALUES FROM (%L) TO (%L)',
            to_char(m, 'YYYYMM'), m, (m + interval '1 month')::date);
        m := (m + interval '1 month')::date;
    END LOOP;
END
$init$;

-- ---------------------------------------------------------------- watchlist

CREATE TABLE watchlist_entries (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kind         watch_kind NOT NULL,
    plate_norm   TEXT,                     -- for vehicle kinds
    subject_name TEXT,
    severity     severity_level NOT NULL DEFAULT 'medium',
    source       TEXT NOT NULL,            -- VAHAN, SARTHI, eGujCop, AFIS, NAFIS, manual
    source_ref   TEXT,                     -- FIR number or upstream record id
    reason       TEXT,
    active       BOOLEAN NOT NULL DEFAULT true,
    valid_from   TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_until  TIMESTAMPTZ,
    created_by   UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (kind IN ('wanted_person','missing_person') OR plate_norm IS NOT NULL)
);
CREATE INDEX watchlist_plate_idx  ON watchlist_entries (plate_norm) WHERE active;
CREATE INDEX watchlist_plate_trgm ON watchlist_entries USING GIN (plate_norm gin_trgm_ops);

CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    watchlist_id    UUID REFERENCES watchlist_entries(id) ON DELETE SET NULL,
    camera_id       UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    sighting_id     BIGINT,
    sighting_ts     TIMESTAMPTZ,
    plate_norm      TEXT,
    match_score     REAL NOT NULL DEFAULT 1.0,   -- <1.0 means fuzzy OCR match
    exact_match     BOOLEAN NOT NULL DEFAULT true,
    severity        severity_level NOT NULL DEFAULT 'medium',
    status          alert_status NOT NULL DEFAULT 'new',
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    acknowledged_by UUID,
    acknowledged_at TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    disposition     TEXT
);
CREATE INDEX alerts_status_time_idx ON alerts (status, triggered_at DESC);
CREATE INDEX alerts_camera_idx      ON alerts (camera_id, triggered_at DESC);

-- ---------------------------------------------------------------- access control

CREATE TABLE roles (
    id          SERIAL PRIMARY KEY,
    code        TEXT NOT NULL UNIQUE,   -- admin, supervisor, operator, auditor, dept_nodal
    name        TEXT NOT NULL,
    permissions JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role_id       INT NOT NULL REFERENCES roles(id),
    department_id INT REFERENCES departments(id),  -- NULL = statewide scope
    district_id   INT REFERENCES districts(id),
    badge_no      TEXT,
    active        BOOLEAN NOT NULL DEFAULT true,
    last_login_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only audit trail. Every footage view and every plate search is recorded;
-- this is what makes the platform defensible under the DPDP Act.
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_id    UUID,
    actor_name  TEXT,
    action      TEXT NOT NULL,          -- camera.view, plate.search, alert.ack, watchlist.create
    object_type TEXT,
    object_id   TEXT,
    purpose     TEXT,                   -- stated investigative purpose, where required
    ip          INET,
    user_agent  TEXT,
    detail      JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX audit_at_idx     ON audit_log (at DESC);
CREATE INDEX audit_actor_idx  ON audit_log (actor_id, at DESC);
CREATE INDEX audit_action_idx ON audit_log (action, at DESC);

CREATE RULE audit_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE audit_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING;

-- ---------------------------------------------------------------- views

-- Movement history for a plate: the core live-test-case query.
CREATE VIEW v_vehicle_movement AS
SELECT s.id, s.plate_norm, s.plate_text, s.event_ts, s.ocr_conf, s.det_conf,
       s.vehicle_type, s.vehicle_color, s.crop_path, s.track_id,
       c.id AS camera_id, c.camera_code, c.name AS camera_name, c.address, c.taluka,
       d.name AS district, dept.name AS department,
       ST_Y(c.location::geometry) AS lat, ST_X(c.location::geometry) AS lon
FROM vehicle_sightings s
JOIN cameras c ON c.id = s.camera_id
JOIN departments dept ON dept.id = c.department_id
LEFT JOIN districts d ON d.id = c.district_id;

-- Coverage gap analysis per district. Drives the Model 1 gap-analysis report.
CREATE VIEW v_coverage_gaps AS
SELECT d.id AS district_id, d.name AS district,
       count(c.id)                                        AS total_cameras,
       count(c.id) FILTER (WHERE c.health = 'online')     AS online_cameras,
       count(c.id) FILTER (WHERE c.health = 'offline')    AS offline_cameras,
       count(c.id) FILTER (WHERE c.anpr_viable)           AS anpr_cameras,
       count(c.id) FILTER (WHERE c.analytics_enabled)     AS analytics_cameras,
       count(DISTINCT c.department_id)                    AS departments_present,
       round(100.0 * count(c.id) FILTER (WHERE c.health = 'online')
             / NULLIF(count(c.id), 0), 1)                 AS uptime_pct,
       ST_Y(d.centroid::geometry) AS lat, ST_X(d.centroid::geometry) AS lon
FROM districts d
LEFT JOIN cameras c ON c.district_id = d.id
GROUP BY d.id, d.name, d.centroid;

CREATE VIEW v_fleet_summary AS
SELECT count(*)                                    AS cameras,
       count(*) FILTER (WHERE health = 'online')   AS online,
       count(*) FILTER (WHERE health = 'degraded') AS degraded,
       count(*) FILTER (WHERE health = 'offline')  AS offline,
       count(*) FILTER (WHERE health = 'unknown')  AS unknown,
       count(*) FILTER (WHERE anpr_viable)         AS anpr_viable,
       count(*) FILTER (WHERE analytics_enabled)   AS analytics_on,
       count(DISTINCT department_id)               AS departments,
       count(DISTINCT source_system_id)            AS source_systems
FROM cameras;
