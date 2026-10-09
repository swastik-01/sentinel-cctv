-- Upstream stream sources for cameras onboarded by URL and relayed through MediaMTX.
--
-- The registry's rtsp_url/whep_url/hls_url point at the relay, never at the camera:
-- viewers and analytics workers never open extra sessions against department equipment,
-- and camera credentials never leave this table. MediaMTX's own path config is
-- in-memory, so the API re-registers these relays on start and whenever one goes missing.
--
-- Dev note: credentials live inline in source_url here. Production stores them in the
-- secret store and keeps only cameras.credentials_ref.

CREATE TABLE IF NOT EXISTS camera_sources (
    camera_id     UUID PRIMARY KEY REFERENCES cameras(id) ON DELETE CASCADE,
    source_url    TEXT NOT NULL,
    on_demand     BOOLEAN NOT NULL DEFAULT false,   -- connect upstream only while someone reads
    probed_codec  TEXT,
    probed_width  INT,
    probed_height INT,
    probed_at     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
