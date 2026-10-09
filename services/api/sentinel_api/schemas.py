from __future__ import annotations

import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

CameraClass = Literal["fixed", "ptz", "dome", "bullet", "anpr", "thermal"]
IntegrationMode = Literal["analog_dvr", "ip_onvif", "ip_rtsp", "vms_api", "cloud_api"]
StorageMode = Literal["local", "cloud", "hybrid", "unknown"]
Ownership = Literal["government", "private_shared"]
HealthState = Literal["online", "degraded", "offline", "unknown"]
Maintenance = Literal["in_service", "under_maintenance", "faulty", "decommissioned"]
WatchKind = Literal["stolen_vehicle", "wanted_person", "missing_person", "blacklisted_vehicle", "bolo"]
Severity = Literal["low", "medium", "high", "critical"]
AlertStatus = Literal["new", "acknowledged", "closed", "false_positive"]


# ----------------------------------------------------------------- auth
class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=128)   # argon2 costs ~0.1 s per try: a long body must not multiply it


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: UUID
    username: str
    full_name: str
    role: str
    permissions: list[str]
    department_id: int | None = None
    district_id: int | None = None


# ----------------------------------------------------------------- cameras
class CameraIn(BaseModel):
    camera_code: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    department_code: str = Field(min_length=1, max_length=16)
    district: str | None = Field(None, max_length=100)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    address: str | None = Field(None, max_length=300)
    taluka: str | None = Field(None, max_length=100)
    landmark: str | None = Field(None, max_length=200)
    bearing_deg: int | None = Field(None, ge=0, le=359)
    camera_class: CameraClass = "fixed"
    mode: IntegrationMode = "ip_rtsp"
    ownership: Ownership = "government"
    vendor: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)
    codec: str | None = Field(None, max_length=32)
    resolution: str | None = Field(None, max_length=32)
    fps: int | None = Field(None, ge=0, le=240)
    retention_days: int | None = Field(None, ge=0, le=3650)
    storage: StorageMode = "unknown"
    rtsp_url: str | None = None
    whep_url: str | None = None
    hls_url: str | None = None
    onvif_url: str | None = None
    anpr_viable: bool = False
    analytics_enabled: bool | None = None
    maintenance: Maintenance | None = None   # None: in_service for a new camera, unchanged for one that exists
    maintenance_note: str | None = Field(None, max_length=500)
    install_year: int | None = Field(None, ge=1990, le=2100)
    amc_expiry: date | None = None
    tags: dict[str, Any] = Field(default_factory=dict)


class CameraPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    district: str | None = Field(None, max_length=100)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    address: str | None = Field(None, max_length=300)
    taluka: str | None = Field(None, max_length=100)
    landmark: str | None = Field(None, max_length=200)
    bearing_deg: int | None = Field(None, ge=0, le=359)
    camera_class: CameraClass | None = None
    mode: IntegrationMode | None = None
    vendor: str | None = Field(None, max_length=100)
    model: str | None = Field(None, max_length=100)
    codec: str | None = Field(None, max_length=32)
    resolution: str | None = Field(None, max_length=32)
    fps: int | None = Field(None, ge=0, le=240)
    retention_days: int | None = Field(None, ge=0, le=3650)
    storage: StorageMode | None = None
    rtsp_url: str | None = None
    whep_url: str | None = None
    hls_url: str | None = None
    onvif_url: str | None = None
    anpr_viable: bool | None = None
    analytics_enabled: bool | None = None
    maintenance: Maintenance | None = None
    maintenance_note: str | None = Field(None, max_length=500)
    install_year: int | None = Field(None, ge=1990, le=2100)
    amc_expiry: date | None = None
    tags: dict[str, Any] | None = None


class CameraOut(BaseModel):
    id: UUID
    camera_code: str
    name: str
    department_code: str
    department: str
    district: str | None
    lat: float | None
    lon: float | None
    address: str | None
    taluka: str | None
    landmark: str | None
    bearing_deg: int | None
    camera_class: str
    mode: str
    ownership: str
    vendor: str | None
    model: str | None
    codec: str | None
    resolution: str | None
    fps: int | None
    retention_days: int | None
    storage: str
    rtsp_url: str | None
    whep_url: str | None
    hls_url: str | None
    onvif_url: str | None
    anpr_viable: bool
    analytics_enabled: bool
    health: str
    last_seen_at: datetime | None
    maintenance: str = "in_service"
    maintenance_note: str | None = None
    install_year: int | None = None
    amc_expiry: date | None = None
    tags: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ImportResult(BaseModel):
    inserted: int = 0
    updated: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)


class HealthCheckOut(BaseModel):
    checked_at: datetime
    reachable: bool
    latency_ms: int | None
    fps_observed: float | None
    state: str
    error: str | None


# ----------------------------------------------------------------- sightings
class SightingIn(BaseModel):
    """What an analytics worker posts. event_ts is the FRAME timestamp."""
    camera_code: str
    event_ts: datetime
    plate_text: str
    ocr_conf: float = Field(ge=0, le=1)
    det_conf: float = Field(ge=0, le=1)
    vehicle_type: str | None = None
    vehicle_color: str | None = None
    bbox: list[int] = Field(min_length=4, max_length=4)
    track_id: str | None = None
    crop_path: str | None = None
    frame_uri: str | None = None
    reads: int | None = Field(None, ge=1, le=100_000)   # reads behind this sighting; 1 = single read on a slow camera
    agreement: float | None = Field(None, ge=0, le=1)   # the vote's weakest position's winning share
    first_read_at: datetime | None = None   # worker wall clock at the track's first valid read (latency)

    @field_validator("event_ts", "first_read_at")
    @classmethod
    def _aware_and_recent(cls, v: datetime | None) -> datetime | None:
        """A naive time or one far from now was a worker clock gone wrong (or a fabricated row): refused as 422,
        which the worker sets aside, instead of a database error that would stall every batch behind it."""
        if v is None:
            return v
        if v.tzinfo is None:
            raise ValueError("timestamp must carry a timezone")
        if abs(datetime.now(timezone.utc) - v) > timedelta(days=14):
            raise ValueError("timestamp more than 14 days from now")
        return v

    @field_validator("bbox")
    @classmethod
    def _bbox_fits(cls, v: list[int]) -> list[int]:
        if any(abs(x) > 2**31 - 1 for x in v):
            raise ValueError("bbox values must fit a 32-bit integer")
        return v


class DetectionEventIn(BaseModel):
    camera_code: str
    event_ts: datetime
    event_type: str
    label: str | None = None
    confidence: float | None = None
    value: float | None = None
    bbox: list[int] | None = Field(None, min_length=4, max_length=4)
    track_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)

    @field_validator("bbox")
    @classmethod
    def _bbox_fits(cls, v: list[int] | None) -> list[int] | None:
        if v is not None and any(abs(x) > 2**31 - 1 for x in v):
            raise ValueError("bbox values must fit a 32-bit integer")
        return v


class CaptureGrade(BaseModel):
    quality: Literal["good", "marginal", "poor"]
    reasons: list[str]


class SightingOut(BaseModel):
    id: int
    plate_norm: str
    plate_text: str
    event_ts: datetime
    ocr_conf: float
    det_conf: float
    vehicle_type: str | None
    vehicle_color: str | None
    crop_path: str | None
    track_id: str | None
    camera_id: UUID
    camera_code: str
    camera_name: str
    address: str | None
    taluka: str | None
    district: str | None
    department: str
    lat: float | None
    lon: float | None
    quality: CaptureGrade | None = None     # capture_quality.py; None until the crop is graded
    reads: int | None = None                # how many reads stood behind the stored plate (G3)
    agreement: float | None = None          # the vote's weakest position's winning share, 0-1 (G3)
    needs_review: bool | None = None        # "check the crop": below 0.9 (marking.py); None = marking off


class MovementOut(BaseModel):
    plate: str
    plate_norm: str
    fuzzy: bool
    matched_plates: list[str]
    first_seen: datetime | None
    last_seen: datetime | None
    distinct_cameras: int
    total_sightings: int
    timeline: list[SightingOut]
    route: dict[str, Any]  # GeoJSON Feature (LineString)
    visits: list[dict[str, Any]] = Field(default_factory=list)   # journey.py: stops and the hops between them


# ----------------------------------------------------------------- watchlist / alerts
class WatchlistIn(BaseModel):
    kind: WatchKind
    plate: str | None = None
    subject_name: str | None = None
    severity: Severity = "medium"
    source: str = "manual"
    source_ref: str | None = None
    reason: str | None = None
    valid_until: datetime | None = None


class WatchlistOut(BaseModel):
    id: UUID
    kind: str
    plate_norm: str | None
    subject_name: str | None
    severity: str
    source: str
    source_ref: str | None
    reason: str | None
    active: bool
    valid_from: datetime
    valid_until: datetime | None
    created_at: datetime


class WatchlistCreated(WatchlistOut):
    retro: dict[str, Any] | None = None      # what the last 24 h already show for this plate


class AlertOut(BaseModel):
    id: UUID
    watchlist_id: UUID | None
    kind: str | None
    subject_name: str | None
    reason: str | None
    camera_id: UUID
    camera_code: str
    camera_name: str
    lat: float | None
    lon: float | None
    sighting_id: int | None
    sighting_ts: datetime | None
    plate_norm: str | None
    match_score: float
    exact_match: bool
    severity: str
    status: str
    triggered_at: datetime
    acknowledged_at: datetime | None
    closed_at: datetime | None
    disposition: str | None
    crop_path: str | None = None
    needs_review: bool | None = None        # "check the crop": read below 0.9 or a one-character match (G3)
    watch_plate: str | None = None           # the watchlist plate matched (differs from plate_norm when fuzzy)
    acknowledged_by_name: str | None = None
    retrospective: bool = False              # raised when the plate was added, for a sighting already made
    alert_type: str = "watchlist"
    detail: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)  # the operators' event tags (Model 2: event tagging)




def _tag_char(c: str) -> bool:
    """Letters and their vowel signs in any script (Gujarati included), digits, spaces and . : / # - _"""
    return unicodedata.category(c)[0] in "LMN" or c in " .:/#-_"


class AlertTags(BaseModel):
    """An alert's whole set of tags (a case number, "intercepted"): trimmed, de-duplicated ignoring case."""
    tags: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            tag = " ".join(str(raw).split())
            if not tag:
                continue
            if len(tag) > 32 or not all(_tag_char(c) for c in tag):
                raise ValueError(f"tag {tag[:40]!r}: 1-32 letters, digits, spaces or . : / # -")
            if tag.lower() not in (x.lower() for x in out):
                out.append(tag)
        return out


class AlertClose(BaseModel):
    status: Literal["closed", "false_positive"] = "closed"
    disposition: str | None = Field(None, max_length=500)


TokenOut.model_rebuild()
