"""Tolerant reader for someone else's camera catalogue.

The sandbox rule is "always query the camera list from the catalogue API, never hard-code
endpoints" — but every catalogue names its fields differently, and on the day we get one
attempt. So this module accepts what it is given:

  * envelope: a bare list, or {items|cameras|data|results|feeds|records|features|...: [...]}
  * ids, names, departments, coordinates and stream URLs under any of the usual aliases,
    flat or nested ({"urls": {...}}, {"streams": {...}}, {"endpoints": {...}})
  * departments by code, by the words of a seeded department name, or by a hint
    ("Police" -> HOME, "AMC" -> MUNI); an unknown one falls back to the default with a warning
  * coordinates as lat/lon fields, a GeoJSON Point, a [lon, lat] or [lat, lon] list or a
    "lat,lon" string, flat or nested under location/geo/gps/...; checked against a Gujarat box
  * districts by name or common spelling variant (Kachchh, Mahesana, Dangs...), else inferred
    from the coordinates (nearest seeded district centroid)
  * resolution as "1280x720" or separate width/height

Anything it cannot map is reported per row rather than failing the batch, every guess is
listed in `cameras.tags.catalogue_warnings`, and the original record is kept in
`cameras.tags.catalogue_raw` so nothing is silently lost.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterator, Mapping
from typing import Any
from urllib.parse import urljoin

import httpx

ENVELOPE_KEYS = ("items", "cameras", "data", "results", "feeds", "records", "list", "features",
                 "devices")

# Paths tried when the operator gives only a host. The sandbox documents /api/ingest.
CANDIDATE_PATHS = ("", "/api/ingest", "/api/cameras", "/cameras", "/api/v1/cameras", "/api/feeds")

ALIASES: dict[str, tuple[str, ...]] = {
    "code": ("camera_code", "code", "camera_id", "cameraid", "id", "cam_id", "device_id", "deviceid", "uid"),
    "name": ("name", "camera_name", "title", "label", "location_name", "description"),
    "department": ("department", "department_code", "department_name", "dept", "dept_code",
                   "dept_name", "owner", "agency", "organisation", "organization"),
    "district": ("district", "district_name", "city", "town", "zone", "region"),
    "lat": ("lat", "latitude", "y"),
    "lon": ("lon", "lng", "long", "longitude", "x"),
    "address": ("address", "location", "place", "landmark", "area"),
    "rtsp_url": ("rtsp_url", "rtsp", "rtspurl", "stream_url", "streamurl", "url", "uri", "stream", "rtsp_uri"),
    "whep_url": ("whep_url", "whep", "webrtc", "webrtc_url", "whepurl"),
    "hls_url": ("hls_url", "hls", "m3u8", "hls_uri", "hlsurl"),
    "codec": ("codec", "video_codec", "encoding", "format"),
    "resolution": ("resolution", "res", "size"),
    "width": ("width", "w", "frame_width"),
    "height": ("height", "h", "frame_height"),
    "fps": ("fps", "frame_rate", "framerate", "frames_per_second"),
    "vendor": ("vendor", "make", "manufacturer", "brand"),
    "retention_days": ("retention_days", "retention", "storage_days"),
    "anpr": ("anpr_viable", "anpr", "is_anpr", "anpr_enabled", "plate_capable"),
    "analytics": ("analytics_enabled", "analytics", "run_analytics", "analytics_on"),
    "status": ("status", "state", "health", "online"),
    "camera_class": ("camera_class", "class", "camera_type", "type"),
    "mode": ("mode", "integration_mode", "integration", "protocol"),
    "storage": ("storage", "storage_mode", "recording", "storage_type"),
}

NESTED = ("urls", "url", "streams", "stream", "endpoints", "links", "media", "properties", "props", "meta", "attributes")

# Keys that may hold a position: a dict (GeoJSON or lat/lon fields), a pair, or "lat,lon" text.
GEO_KEYS = ("geometry", "location", "geo", "gps", "coordinates", "coords", "coordinate", "latlng",
            "lat_lng", "latlon", "lat_lon", "lnglat", "lng_lat", "lonlat", "lon_lat", "position",
            "point", "geolocation", "geo_location", "gps_location", "gps_coordinates", "geopoint",
            "geo_point", "loc")

# Fields that may come as an object with a name, and what a location block may fill in.
NAMED = frozenset(ALIASES["department"] + ALIASES["district"] + ALIASES["address"]
                  + ALIASES["vendor"] + GEO_KEYS)
LOCATION_FIELDS = ALIASES["district"] + ALIASES["address"]

# Approximate Gujarat bounding box. The latitude and longitude ranges don't overlap, so an
# unlabelled pair can be oriented and a reversed one detected.
GUJARAT_LAT = (20.0, 24.8)
GUJARAT_LON = (68.0, 74.6)

_COORD_TEXT = re.compile(
    r"\s*(?:point\s*)?[(\[]?\s*([-+]?\d+(?:\.\d+)?)\s*°?\s*[NE]?\s*[,;\s]\s*"
    r"([-+]?\d+(?:\.\d+)?)\s*°?\s*[NE]?\s*[)\]]?\s*", re.I)

# Words that say nothing about which department owns a camera.
DEPT_STOPWORDS = frozenset({"department", "dept", "deptt", "the", "of", "and", "for", "gujarat",
                            "government", "govt", "gog", "state", "district", "office", "ltd",
                            "limited"})

# Names and abbreviations seen in the wild -> seeded codes. Tried after the seeded names, phrases
# before single words, then in this order (so "Police Training College" is HOME, not EDU).
DEPT_HINTS = (
    ("police", "HOME"), ("home", "HOME"), ("scrb", "HOME"), ("traffic", "HOME"), ("crime", "HOME"),
    ("cctns", "HOME"), ("netram", "HOME"), ("viswas", "HOME"), ("safe city", "HOME"),
    ("home guard", "HOME"), ("civil defence", "HOME"),
    ("municipal", "MUNI"), ("municipality", "MUNI"), ("nagar palika", "MUNI"),
    ("nagarpalika", "MUNI"), ("amc", "MUNI"), ("smc", "MUNI"), ("vmc", "MUNI"), ("rmc", "MUNI"),
    ("urban", "MUNI"),
    ("smart city", "MUNI"), ("brts", "MUNI"), ("janmarg", "MUNI"), ("amts", "MUNI"),
    ("city bus", "MUNI"),
    ("gsrtc", "GSRTC"), ("road transport", "GSRTC"), ("st bus", "GSRTC"), ("bus", "GSRTC"),
    ("health", "HEALTH"), ("hospital", "HEALTH"), ("medical", "HEALTH"), ("phc", "HEALTH"),
    ("chc", "HEALTH"), ("family welfare", "HEALTH"),
    ("panchayat", "PNCHT"), ("rural", "PNCHT"), ("gram", "PNCHT"),
    ("rto", "RTO"), ("arto", "RTO"), ("regional transport", "RTO"), ("transport", "RTO"),
    ("food", "FCS"), ("civil supplies", "FCS"), ("pds", "FCS"), ("ration", "FCS"),
    ("fair price", "FCS"), ("godown", "FCS"), ("gscsc", "FCS"),
    ("forest", "FOREST"), ("wildlife", "FOREST"), ("zoo", "FOREST"), ("sanctuary", "FOREST"),
    ("pollution", "FOREST"), ("gpcb", "FOREST"),
    ("education", "EDU"), ("school", "EDU"), ("college", "EDU"), ("university", "EDU"),
    ("gmb", "GMB"), ("port", "GMB"), ("maritime", "GMB"), ("harbour", "GMB"), ("jetty", "GMB"),
    ("narmada", "NWR"), ("irrigation", "NWR"), ("water resources", "NWR"), ("dam", "NWR"),
    ("canal", "NWR"), ("sardar sarovar", "NWR"), ("ssnnl", "NWR"), ("water supply", "NWR"),
    ("gwssb", "NWR"), ("kalpsar", "NWR"),
    ("revenue", "REV"), ("collector", "REV"), ("collectorate", "REV"), ("mamlatdar", "REV"),
    ("tourism", "TOUR"), ("tourist", "TOUR"), ("tcgl", "TOUR"),
    ("energy", "ENERGY"), ("power", "ENERGY"), ("electricity", "ENERGY"), ("guvnl", "ENERGY"),
    ("getco", "ENERGY"), ("ugvcl", "ENERGY"), ("mgvcl", "ENERGY"), ("pgvcl", "ENERGY"),
    ("dgvcl", "ENERGY"), ("substation", "ENERGY"),
    ("industries", "IND"), ("industrial development", "IND"), ("gidc", "IND"), ("mines", "IND"),
    ("mining", "IND"),
    ("roads and buildings", "RNB"), ("r&b", "RNB"), ("rnb", "RNB"), ("public works", "RNB"),
    ("pwd", "RNB"), ("highway", "RNB"),
    ("women", "WCD"), ("child", "WCD"), ("anganwadi", "WCD"), ("icds", "WCD"),
    ("tribal", "TRIBAL"), ("adivasi", "TRIBAL"),
    ("labour", "LABOUR"), ("labor", "LABOUR"), ("employment", "LABOUR"), ("skill", "LABOUR"),
    ("agriculture", "AGRI"), ("farmer", "AGRI"), ("apmc", "AGRI"), ("krishi", "AGRI"),
    ("fisheries", "FISH"), ("fish", "FISH"),
    ("cooperation", "COOP"), ("cooperative", "COOP"), ("co-operative", "COOP"),
    ("court", "LEGAL"), ("judiciary", "LEGAL"), ("judicial", "LEGAL"), ("legal", "LEGAL"),
    ("prison", "JAILS"), ("jail", "JAILS"), ("correctional", "JAILS"),
    ("sports", "SPORTS"), ("stadium", "SPORTS"), ("youth", "SPORTS"),
    ("science", "SCITECH"), ("technology", "SCITECH"),
)

# Spelling variants, old names and headquarters towns -> seeded district names. Spacing,
# hyphens, a plural "s" and words like "district" or "city" are ignored anyway.
DISTRICT_ALIASES = {
    "Ahmedabad": ("ahmadabad", "amdavad", "amdabad"),
    "Aravalli": ("arvalli", "aravali", "arvali", "modasa"),
    "Banaskantha": ("banaskanth", "palanpur"),
    "Bharuch": ("broach", "ankleshwar"),
    "Bhavnagar": ("bhavanagar",),
    "Chhota Udaipur": ("chhota udepur", "chhotaudepur", "chota udaipur", "chota udepur"),
    "Dahod": ("dohad",),
    "Dang": ("ahwa",),
    "Devbhumi Dwarka": ("devbhoomi dwarka", "dwarka", "khambhalia", "jam khambhalia"),
    "Gir Somnath": ("somnath", "veraval"),
    "Junagadh": ("junagarh",),
    "Kheda": ("kaira", "nadiad"),
    "Kutch": ("kachchh", "kachh", "kutchh", "kachchha", "bhuj", "gandhidham"),
    "Mahisagar": ("lunawada", "lunavada"),
    "Mehsana": ("mahesana", "mehesana", "mahsana"),
    "Morbi": ("morvi",),
    "Narmada": ("rajpipla",),
    "Panchmahal": ("godhra",),
    "Sabarkantha": ("sabarkanth", "himmatnagar"),
    "Tapi": ("vyara",),
    "Vadodara": ("baroda",),
    "Valsad": ("bulsar", "vapi"),
}
_DISTRICT_NOISE = frozenset({"district", "dist", "city", "rural", "urban", "the", "zilla", "jilla"})


def _key(k) -> str:
    return str(k).strip().lower().replace(" ", "_").replace("-", "_")


def _flatten(item: dict) -> dict:
    """One flat dict of lower-cased keys, with nested url/property blocks merged in. A named
    object ({"department": {"id": 4, "name": ...}}) collapses to its name, and a location
    block fills in a district or address. Nothing else is lifted out of a location block:
    its id or url must never pass for the camera's."""
    flat: dict[str, Any] = {}
    geo_blocks: list[dict] = []
    for k, v in item.items():
        lk = _key(k)
        if isinstance(v, dict) and lk in NESTED:
            for k2, v2 in v.items():
                lk2 = str(k2).strip().lower()
                flat.setdefault(f"{lk}_{lk2}", v2)
                flat.setdefault(lk2, v2)          # urls.rtsp -> rtsp
                flat.setdefault(f"{lk2}_url", v2)  # urls.rtsp -> rtsp_url
        elif isinstance(v, dict):
            inner = {_key(k2): v2 for k2, v2 in v.items()}
            label = inner.get("name") or (None if lk in GEO_KEYS else inner.get("code"))
            if lk in NAMED and isinstance(label, (str, int)) and not isinstance(label, bool):
                flat[lk] = label
            if lk in GEO_KEYS:
                geo_blocks.append(inner)
        elif not isinstance(v, list):
            flat[lk] = v
    for block in geo_blocks:
        for k2 in LOCATION_FIELDS:
            if block.get(k2) not in (None, "") and not isinstance(block[k2], (dict, list)):
                flat.setdefault(k2, block[k2])
    return flat


# Registry enums (01_schema.sql). A value outside them is ignored, not an error: a catalogue's
# "type" may well be GeoJSON's "Feature".
ENUMS = {"camera_class": {"fixed", "ptz", "dome", "bullet", "anpr", "thermal"},
         "mode": {"analog_dvr", "ip_onvif", "ip_rtsp", "vms_api", "cloud_api"},
         "storage": {"local", "cloud", "hybrid", "unknown"}}


def _enum(flat: dict, field: str, default: str) -> str:
    v = _pick(flat, field)
    v = str(v).strip().lower().replace("-", "_").replace(" ", "_") if v is not None else ""
    return v if v in ENUMS[field] else default


def _pick(flat: dict, field: str):
    for alias in ALIASES[field]:
        if alias in flat and flat[alias] not in (None, ""):
            return flat[alias]
    return None


def _as_int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _as_bool(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "t", "viable", "anpr"}


def _stem(word: str) -> str:
    """Just enough singular/plural folding for names: supplies/supply, ports/port, dangs/dang."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(text, stop: frozenset[str] = frozenset()) -> list[str]:
    s = str(text).lower().replace("&", " and ")
    return [w for w in (_stem(t) for t in re.findall(r"[a-z0-9]+", s)) if w not in stop]


_HINTS = sorted(((" ".join(_words(h, DEPT_STOPWORDS)), code) for h, code in DEPT_HINTS),
                key=lambda hc: -len(hc[0].split()))


def _by_name(words: set[str], names: Mapping[str, str], loose: bool = False) -> str | None:
    """The seeded department whose name (or code) shares the most words with the value. A word
    in several names (transport, development) counts for less. Strict mode also wants the
    value's words all covered, or two words' worth of overlap; a tie is never a match."""
    if not words or not names:
        return None
    vocab = {code: set(_words(f"{code} {name}", DEPT_STOPWORDS)) for code, name in names.items()}
    df = Counter(w for v in vocab.values() for w in v)
    scored = sorted(((round(sum(1 / df[w] for w in words & v), 6), words <= v, code)
                     for code, v in vocab.items()), reverse=True)
    best, covers, code = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0
    if best <= 0 or best == second:
        return None
    return code if loose or covers or best >= 2 else None


def _by_hint(text: str, known) -> str | None:
    padded = f" {' '.join(_words(text, DEPT_STOPWORDS))} "
    for hint, code in _HINTS:
        if hint and code in known and f" {hint} " in padded:
            return code
    return None


def match_department(value, known: Mapping[str, str] | set[str],
                     default: str) -> tuple[str, str | None]:
    """(code, warning). `known` maps seeded codes to names (a bare set of codes still works, but
    then only codes and hints can match). An unrecognised department falls back to `default`
    and the warning names the value, so it is never folded into HOME silently."""
    if value in (None, ""):
        return default, f"no department in record; assigned {default}"
    s = str(value).strip()
    if s.upper() in known:
        return s.upper(), None
    words = set(_words(s, DEPT_STOPWORDS))
    names = known if isinstance(known, Mapping) else {}
    code = _by_name(words, names) or _by_hint(s, known)
    if code:
        return code, None
    code = _by_name(words, names, loose=True)
    if code:
        return code, f"department {s!r} matched loosely to {code}"
    return default, f"department {s!r} not recognised; assigned {default}"


def department_code(value, known: Mapping[str, str] | set[str], default: str) -> str:
    """Accept a code we already know, otherwise map a department name onto one."""
    return match_department(value, known, default)[0]


def _department(flat: dict, known, default: str) -> tuple[str, str | None]:
    """Try every department-ish field (department, dept_name, owner...) until one matches
    cleanly: a catalogue's own department code may sit next to a name we can read."""
    values = [flat[a] for a in ALIASES["department"] if flat.get(a) not in (None, "")]
    results = [match_department(v, known, default) for v in values] or [
        match_department(None, known, default)]
    return next((r for r in results if r[1] is None), results[0])


def _number(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(str(v).strip().rstrip("NnEe° "))       # "23.02° N"
    except ValueError:
        return None
    return f if math.isfinite(f) else None


def _pair(v) -> tuple[float, float, str] | None:
    """Two numbers in the order given, from a list (GeoJSON may add altitude) or text."""
    if isinstance(v, (list, tuple)) and len(v) in (2, 3):
        a, b = _number(v[0]), _number(v[1])
        return (a, b, "list") if a is not None and b is not None else None
    if isinstance(v, str) and (m := _COORD_TEXT.fullmatch(v)):
        return float(m[1]), float(m[2]), "text"
    return None


def _coord_candidates(d: dict, path: str = "",
                      depth: int = 0) -> Iterator[tuple[str, str, float, float]]:
    """(where, kind, a, b) for each coordinate pair in a record, most explicit first. kind is
    'fields' (a=lat, b=lon), 'geojson' (a=lon, b=lat), or 'list'/'text' (order unknown)."""
    keys = {_key(k): v for k, v in d.items()}
    a = _number(next((keys[k] for k in ALIASES["lat"] if keys.get(k) not in (None, "")), None))
    b = _number(next((keys[k] for k in ALIASES["lon"] if keys.get(k) not in (None, "")), None))
    if a is not None and b is not None:
        yield path, "fields", a, b
    geojson = str(keys.get("type", "")).lower() == "point"
    for k in GEO_KEYS:
        v = keys.get(k)
        if isinstance(v, dict):
            if depth < 3:
                yield from _coord_candidates(v, f"{path}{k}.", depth + 1)
        elif (p := _pair(v)) is not None:
            kind = "geojson" if geojson and k == "coordinates" else p[2]
            yield f"{path}{k}", kind, p[0], p[1]
    if depth < 3:
        for k in NESTED:
            if isinstance(keys.get(k), dict):
                yield from _coord_candidates(keys[k], f"{path}{k}.", depth + 1)


def in_gujarat(lat: float, lon: float) -> bool:
    return GUJARAT_LAT[0] <= lat <= GUJARAT_LAT[1] and GUJARAT_LON[0] <= lon <= GUJARAT_LON[1]


def find_coordinates(item: dict) -> tuple[float | None, float | None, str | None, list[str]]:
    """(lat, lon, source, warnings): the first pair in the record that lies inside Gujarat.
    A labelled pair (lat/lon fields, GeoJSON) found reversed is swapped with a warning; a
    pair outside the box is rejected with a warning rather than put on the map."""
    rejected: list[str] = []
    for where, kind, a, b in _coord_candidates(item):
        if kind == "fields":
            where = f"{where}lat/lon"
        stated = (b, a) if kind == "geojson" else (a, b)            # as (lat, lon)
        for lat, lon in (stated, stated[::-1]):
            if not in_gujarat(lat, lon):
                continue
            flipped = (lat, lon) != stated
            if kind == "fields":
                source = where
            elif kind == "geojson":
                source = f"{where} (GeoJSON Point)"
            else:
                order = "lon, lat" if flipped else "lat, lon"
                source = f"{where} [{order}] list" if kind == "list" else f"{where} '{order}' text"
            warnings = []
            if flipped and kind in ("fields", "geojson"):
                warnings.append(f"{source}: latitude and longitude were reversed; swapped")
            return lat, lon, source, warnings
        rejected.append(f"coordinates {a}, {b} in {where} are outside Gujarat; ignored")
    missing = ["no coordinates in record; camera will not be on the map"]
    return None, None, None, rejected[:2] or missing


def _district_key(text) -> str:
    """'The Dangs' -> 'dang', 'Banas Kantha' -> 'banaskantha': spacing and a plural ignored."""
    words = re.findall(r"[a-z]+", str(text).lower())
    return _stem("".join(w for w in words if w not in _DISTRICT_NOISE))


def match_district(value, known: Mapping[str, str]) -> str | None:
    """Seeded district name for a name or spelling variant; `known` maps lower-case names to
    seeded names (the shape sync_catalogue builds)."""
    if value in (None, ""):
        return None
    names = set(known.values())
    table = {_district_key(n): n for n in names}
    for name, variants in DISTRICT_ALIASES.items():
        if name in names:
            for v in variants:
                table.setdefault(_district_key(v), name)
    return known.get(str(value).strip().lower()) or table.get(_district_key(value))


def nearest_district(lat: float, lon: float,
                     centroids: Mapping[str, tuple[float, float]]) -> tuple[str, float] | None:
    """(district, km) whose seeded headquarters centroid is closest. Only centroids are seeded,
    so near a district border this can pick the neighbour; callers say it was inferred."""
    best = None
    for name, (clat, clon) in centroids.items():
        p1, p2 = math.radians(lat), math.radians(clat)
        h = (math.sin((p2 - p1) / 2) ** 2
             + math.cos(p1) * math.cos(p2) * math.sin(math.radians(clon - lon) / 2) ** 2)
        km = 2 * 6371.0 * math.asin(math.sqrt(h))
        if best is None or km < best[1]:
            best = (name, km)
    return best


def extract_items(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ENVELOPE_KEYS:
            v = payload.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):                     # {"cameras": {"CAM1": {...}}}
                return [{"id": k, **x} for k, x in v.items() if isinstance(x, dict)]
        if any(k in payload for k in ("rtsp", "rtsp_url", "urls", "url")):
            return [payload]                            # a single camera
    return []


async def fetch_catalogue(base: str, timeout: float = 15.0) -> tuple[list[dict], str]:
    """Return (items, url actually used). Tries the documented paths when given a host."""
    base = base.strip().rstrip("/")
    tried: list[str] = []
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for path in CANDIDATE_PATHS:
            url = base + path if path else base
            if url in tried:
                continue
            tried.append(url)
            try:
                r = await client.get(url, headers={"Accept": "application/json"})
                if r.status_code >= 400:
                    continue
                items = extract_items(r.json())
            except (httpx.HTTPError, ValueError):
                continue
            if items:
                return items, url
    raise httpx.HTTPError(f"no camera list found at any of: {', '.join(tried)}")


def map_item(item: dict, *, known_departments: Mapping[str, str] | set[str],
             known_districts: dict[str, str], default_department: str,
             relay_host: str | None = None,
             district_centroids: Mapping[str, tuple[float, float]] | None = None,
             ) -> tuple[dict | None, str | None]:
    """(row for upsert_camera, error). Never raises: a bad record is reported, not fatal.
    What had to be guessed is in row["tags"]["catalogue_warnings"], where the position came
    from in row["tags"]["coord_source"]."""
    flat = _flatten(item)
    raw_code = _pick(flat, "code")
    if raw_code in (None, ""):
        return None, "no id/code field"
    code = re.sub(r"[^A-Za-z0-9_-]", "-", str(raw_code)).strip("-").upper()[:64]
    if len(code) < 3:
        code = f"CAM-{code}" if code else None
        if not code:
            return None, f"unusable id {raw_code!r}"

    rtsp = _pick(flat, "rtsp_url")
    whep = _pick(flat, "whep_url")
    hls = _pick(flat, "hls_url")
    if rtsp and relay_host and str(rtsp).startswith("/"):
        rtsp = urljoin(relay_host, str(rtsp))
    if not rtsp and not whep and not hls:
        return None, "no stream URL (rtsp/whep/hls) in record"

    resolution = _pick(flat, "resolution")
    if not resolution:
        w, h = _as_int(_pick(flat, "width")), _as_int(_pick(flat, "height"))
        resolution = f"{w}x{h}" if w and h else None
    codec = _pick(flat, "codec")
    if codec:
        codec = {"H264": "H.264", "H265": "H.265", "HEVC": "H.265", "AVC": "H.264"}.get(
            str(codec).upper().replace(".", "").replace("-", ""), str(codec))

    warnings: list[str] = []
    department, warning = _department(flat, known_departments, default_department)
    if warning:
        warnings.append(warning)
    lat, lon, coord_source, coord_warnings = find_coordinates(item)
    warnings += coord_warnings

    district_raw = _pick(flat, "district")
    district = matched_district = match_district(district_raw, known_districts)
    if not district and lat is not None and district_centroids:
        near = nearest_district(lat, lon, district_centroids)
        if near:
            district = near[0]
            why = f"district {district_raw!r} not recognised; " if district_raw else ""
            warnings.append(f"{why}district inferred from location: {district} "
                            f"(nearest district centroid, {near[1]:.0f} km)")
    elif district_raw and not district:
        warnings.append(f"district {district_raw!r} not recognised; left blank")

    # "location" is an address alias, but not when it holds the coordinates themselves.
    address = next((flat[a] for a in ALIASES["address"] if flat.get(a) not in (None, "")
                    and not _COORD_TEXT.fullmatch(str(flat[a]))), None)
    name = _pick(flat, "name") or code

    row = {
        "camera_code": code,
        "name": str(name)[:200],
        "department_code": department,
        "district": district,
        "lat": lat,
        "lon": lon,
        "address": str(address)[:300] if address else None,
        "vendor": (str(_pick(flat, "vendor"))[:100] if _pick(flat, "vendor") else None),
        "codec": codec,
        "resolution": str(resolution) if resolution else None,
        "fps": _as_int(_pick(flat, "fps")),
        "retention_days": _as_int(_pick(flat, "retention_days")),
        "mode": _enum(flat, "mode", "ip_rtsp"),
        "camera_class": _enum(flat, "camera_class", "fixed"),
        "storage": _enum(flat, "storage", "unknown"),
        "rtsp_url": str(rtsp) if rtsp else None,
        "whep_url": str(whep) if whep else None,
        "hls_url": str(hls) if hls else None,
        "anpr_viable": _as_bool(_pick(flat, "anpr")),
        "analytics_requested": _as_bool(_pick(flat, "analytics")),
        # Always written, so a re-sync that resolves a warning clears the old one (tags merge).
        "tags": {"source": "catalogue", "catalogue_raw": {k: v for k, v in list(item.items())[:25]},
                 "coord_source": coord_source, "catalogue_warnings": warnings},
    }
    if district_raw and not matched_district:
        row["tags"]["district_unmatched"] = str(district_raw)
    return row, None
