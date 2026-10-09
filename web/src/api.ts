// Thin API client. Token lives in localStorage; a 401 anywhere sends us back to /login.

/** "localhost" in a configured or stored address means the machine that serves this page. Opened from another machine
 *  on the LAN (the operator laptop, a judge's tablet), the API and the relay are reached at the page's own host. */
export function pageHost(url: string): string {
  const local = (h: string) => h === "localhost" || h === "127.0.0.1";
  try {
    const u = new URL(url);
    if (!local(u.hostname) || local(window.location.hostname)) return url;
    u.hostname = window.location.hostname;
    const out = u.toString();
    return url.endsWith("/") ? out : out.replace(/\/$/, "");
  } catch {
    return url;
  }
}

export const API = pageHost((import.meta.env.VITE_API_URL as string) || "http://localhost:8000");
export const CATALOGUE = pageHost((import.meta.env.VITE_CATALOGUE_URL as string) || "http://localhost:8010");

export type User = {
  id: string; username: string; full_name: string; role: string; permissions: string[];
  department_id: number | null; district_id: number | null;
};

export type Camera = {
  id: string; camera_code: string; name: string; department_code: string; department: string;
  district: string | null; lat: number | null; lon: number | null; address: string | null;
  camera_class: string; mode: string; vendor: string | null; model?: string | null; codec: string | null;
  resolution: string | null; fps: number | null; retention_days: number | null; storage: string;
  rtsp_url: string | null; whep_url: string | null; hls_url: string | null;
  anpr_viable: boolean; analytics_enabled: boolean; health: string; last_seen_at: string | null;
  maintenance: Maintenance; maintenance_note: string | null; install_year: number | null; amc_expiry: string | null;
  tags?: Record<string, any>;
};

/** A camera's maintenance state (Model 1: maintenance-status monitoring). */
export type Maintenance = "in_service" | "under_maintenance" | "faulty" | "decommissioned";
export const MAINTENANCE_LABEL: Record<Maintenance, string> = {
  in_service: "in service", under_maintenance: "under maintenance", faulty: "faulty", decommissioned: "decommissioned",
};
export const CAMERA_CLASSES = ["fixed", "ptz", "dome", "bullet", "anpr", "thermal"] as const;

/** An AMC or warranty date as the registry shows it: past (red), within 90 days (amber), or neither. */
export function dueClass(date: string | null | undefined): string {
  if (!date) return "";
  const days = (Date.parse(date) - Date.now()) / 864e5;
  return days < 0 ? "due-past" : days < 90 ? "due-soon" : "";
}

export type Sighting = {
  id: number; plate_norm: string; plate_text: string; event_ts: string; ocr_conf: number;
  det_conf: number; vehicle_type: string | null; vehicle_color: string | null; crop_path: string | null;
  camera_code: string; camera_name: string; district: string | null; department: string;
  lat: number | null; lon: number | null;
  quality?: CaptureQuality | null;   // null until the crop has been graded (or when there is no crop)
  reads?: number | null;             // reads behind the stored plate; agreement: the vote's weakest share (0-1)
  agreement?: number | null;
  needs_review?: boolean | null;     // "check the crop": read below 0.9; null when marking is off
};

/** A capture's grade, from the crop's own pixels (size, sharpness, light, angle) and the read confidence. */
export type Grade = "good" | "marginal" | "poor";
export type CaptureQuality = { quality: Grade; reasons: string[] };
export type Recommendation = { kind: "camera" | "model" | "config"; text: string };
/** One row of /reports/camera-quality. `blind_exact` counts exact blind verdicts out of `reviewed_blind`. */
export type CameraQuality = {
  camera_code: string; camera_name: string; department: string | null;
  captures: number; good: number; marginal: number; poor: number;
  median_plate_w: number | null; median_char_h: number | null;
  reasons: Record<string, number>;
  frames_analysed: number | null; plates_per_1000_frames: number | null;
  sightings?: number; not_plates?: number;   // not_plates: captures a reviewer marked as not a plate, left out of the grades
  reviewed_blind: number; blind_exact: number | null;
  tier: "A" | "B" | "C"; tier_reason?: string | null;
  graded?: boolean;   // false: C only by default (not analysed in the window, or reads with no crop to grade)
  recommendations: Recommendation[];
};
export const REASON_LABEL: Record<string, string> = {
  too_small: "too small", small: "small", blurred: "blurred", dark: "dark", glare: "glare",
  low_contrast: "low contrast", oblique: "at an angle", two_line: "two-line plate", low_confidence: "low read confidence",
};
export const reasonLabel = (r: string) => REASON_LABEL[r] ?? r.replace(/_/g, " ");

export type Visit = {
  n: number; camera_code: string; camera_name: string; district: string | null; department: string | null;
  lat: number | null; lon: number | null; first_ts: string; last_ts: string; dwell_s: number; reads: number;
  plates: string[]; exact: boolean; possible_misread: boolean; best_read: string; crop_path: string | null;
  vehicle_type: string | null; vehicle_color: string | null;
  hop: { from_n: number; distance_m: number; travel_s: number; speed_kmh: number | null; implausible: boolean } | null;
  hop_note: string | null;   // why a stop has no leg: first read, same camera, possible misread
  needs_review?: boolean | null;   // a read in this stop is marked "check the crop"
};

export type Movement = {
  plate: string; plate_norm: string; fuzzy: boolean; matched_plates: string[];
  first_seen: string | null; last_seen: string | null; distinct_cameras: number;
  total_sightings: number; timeline: Sighting[]; route: any; visits: Visit[];
};

export type Alert = {
  id: string; kind: string | null; subject_name: string | null; reason: string | null;
  camera_code: string; camera_name: string; lat: number | null; lon: number | null;
  sighting_ts: string | null; plate_norm: string | null; match_score: number; exact_match: boolean;
  severity: string; status: string; triggered_at: string; crop_path: string | null;
  disposition: string | null; watch_plate?: string | null; acknowledged_by_name?: string | null;
  acknowledged_at?: string | null; retrospective?: boolean; alert_type?: string; detail?: Record<string, any>;
  needs_review?: boolean | null;   // "check the crop": read below 0.9 or a one-character match
  tags?: string[];                 // operators' event tags (Model 2)
};

/** Why an alert or sighting is marked "check the crop", for the badge's tooltip. */
export const CHECK_CROP = "Open the evidence crop before acting: the read is below 0.9 confidence or one character off the watchlist plate. Nothing is suppressed.";

export type ReviewMode = "blind" | "verify";
export type Verdict = "exact" | "one_off" | "wrong" | "not_a_plate" | "unreadable";
/** A blind queue item carries no plate text and no confidence: the reviewer reads the crop cold. */
export type ReviewItem = { sighting_id: number; event_ts: string; camera_code: string; camera_name: string; crop_path: string };
export type VerifyItem = ReviewItem & { plate_norm: string; ocr_conf: number | null };
export type ReviewResult = {
  sighting_id: number; mode: ReviewMode; verdict: Verdict; seen: string | null;
  stored_plate: string; ocr_conf: number | null;
  // A change the reviewer made after saving. Blind results keep the first reading (seen, verdict).
  corrected_seen?: string | null; corrected_verdict?: Verdict | null; corrected_at?: string | null;
};
/** One of the signed-in reviewer's own saved reviews (/reviews/mine). */
export type MyReview = ReviewResult & {
  event_ts: string; camera_code: string; camera_name: string; crop_path: string; created_at: string;
};
/** A row of Results' plate-by-plate list (/reviews/plates): one review, Sentinel's read beside the reviewer's. */
export type PlateRow = MyReview & { reviewer: string; reviewer_name: string; mine: boolean };
export type ReviewSummary = {
  reviewers: { username: string; full_name: string; blind: number; verify: number; corrected?: number }[];
  cameras: {
    camera_code: string; camera_name: string; mode: ReviewMode; n: number;
    exact: number; one_off: number; wrong: number; not_a_plate: number; unreadable: number;
  }[];
  bands: { mode: ReviewMode; band: string; n_plates: number; exact: number; one_off?: number }[];
  agreement: { sightings_with_2plus_blind: number; same_verdict: number; same_reading: number };
};

// Cameras published by the local feed simulator. Its test controls (e.g. "simulate outage")
// are offered only for these, never for a real department's camera.
let simCams: Promise<Set<string>> | null = null;
// The feed simulator is looked for only where one is expected: on the dev server (the demo) or in a build told where
// it is. A production build otherwise never calls a port on the operator's own machine.
const SIMULATOR = import.meta.env.DEV || !!import.meta.env.VITE_CATALOGUE_URL;
export const simulatorCameras = (): Promise<Set<string>> => simCams ??= !SIMULATOR ? Promise.resolve(new Set<string>())
  : fetch(`${CATALOGUE}/cameras`)
    .then((r) => (r.ok ? r.json() : { items: [] }))
    .then((j: any) => new Set<string>((j?.items ?? []).map((c: any) => String(c.code))))
    .catch(() => new Set<string>());

export const token = () => localStorage.getItem("sentinel.token");

/** The permission each page needs: the sidebar shows a page, and the router opens it, only for users who hold it. */
export const PAGE_NEEDS: Record<string, string> = {
  "/map": "cameras.read", "/wall": "streams.view", "/search": "sightings.search", "/alerts": "alerts.read",
  "/health": "reports.read", "/registry": "cameras.read", "/watchlist": "watchlist.read",
  "/review": "reviews.read", "/audit": "audit.read",
};

// Whether the API answered: the shell (Layout) shows a banner while it does not, so an operator never reads an
// empty table as "nothing happened".
export type ApiHealth = { ok: boolean; detail?: string };
const healthListeners = new Set<(h: ApiHealth) => void>();
export function onApiHealth(f: (h: ApiHealth) => void) { healthListeners.add(f); return () => { healthListeners.delete(f); }; }
const reportHealth = (h: ApiHealth) => healthListeners.forEach((f) => f(h));

// Evidence crops are fetched with the Authorization header and shown from memory (components/CropImg.tsx): a token
// in an <img> URL ends up in browser history, proxy logs and screenshots. A crop never changes, so each is fetched
// once per sign-in; the cache is dropped when the token changes and keeps at most CROP_CACHE images.
const crops = new Map<string, Promise<string>>();
let cropsToken: string | null = null;
const CROP_CACHE = 400;
const revoke = (p: Promise<string>) => p.then((u) => URL.revokeObjectURL(u), () => undefined);

export function cropUrl(path: string): Promise<string> {
  const t = token();
  if (t !== cropsToken) {
    crops.forEach(revoke);
    crops.clear();
    cropsToken = t;
  }
  let p = crops.get(path);
  if (!p) {
    p = fetch(API + path, { headers: t ? { Authorization: `Bearer ${t}` } : {} })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(`crop ${r.status}`))))
      .then((b) => URL.createObjectURL(b));
    p.catch(() => crops.delete(path));   // a failed fetch is tried again next time
    crops.set(path, p);
    if (crops.size > CROP_CACHE) {
      const oldest = crops.keys().next().value as string;
      revoke(crops.get(oldest)!);
      crops.delete(oldest);
    }
  }
  return p;
}
export const currentUser = (): User | null => {
  try { return JSON.parse(localStorage.getItem("sentinel.user") || "null"); } catch { return null; }
};
export const can = (perm: string) => {
  const u = currentUser();
  return !!u && (u.permissions.includes("*") || u.permissions.includes(perm));
};

type ApiInit = Omit<RequestInit, "body"> & { body?: any };

/** A validation refusal (FastAPI's list of {loc, msg}) as one readable line: "install_year: Input should be ...". */
function detailText(d: any): string {
  if (!Array.isArray(d)) return JSON.stringify(d);
  return d.map((e: any) => {
    const field = Array.isArray(e?.loc) ? e.loc.filter((x: any) => x !== "body" && x !== "query").join(".") : "";
    return field ? `${field}: ${e?.msg ?? "invalid"}` : String(e?.msg ?? "invalid");
  }).join("; ");
}

export async function api<T = any>(path: string, init: ApiInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const t = token();
  if (t) headers.Authorization = `Bearer ${t}`;
  let body: any = init.body;
  if (body && !(body instanceof FormData) && typeof body !== "string") {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  let r: Response;
  try {
    r = await fetch(API + path, { ...init, headers, body });
  } catch {
    reportHealth({ ok: false, detail: "The Sentinel API is not answering. Check the server; this page retries on its next refresh." });
    throw new Error("Cannot reach the Sentinel API");
  }
  reportHealth(r.status >= 500 ? { ok: false, detail: `The API failed (${r.status}) on ${path.split("?")[0]}.` } : { ok: true });
  if (r.status === 401) {
    localStorage.removeItem("sentinel.token");
    if (!location.pathname.startsWith("/login")) location.href = "/login";
    throw new Error("not authenticated");
  }
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (j.detail) msg = typeof j.detail === "string" ? j.detail : detailText(j.detail);
    } catch { /* keep status text */ }
    throw Object.assign(new Error(msg), { status: r.status });
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}

export async function login(username: string, password: string): Promise<User> {
  const r = await fetch(`${API}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!r.ok) throw new Error(r.status === 401 ? "Invalid credentials" : `Login failed (${r.status})`);
  const j = await r.json();
  localStorage.setItem("sentinel.token", j.access_token);
  localStorage.setItem("sentinel.user", JSON.stringify(j.user));
  return j.user;
}

/** Re-reads the signed-in user, so a permission granted after sign-in (role grants are applied
 *  at API start) reaches an open session without signing out. */
export const refreshUser = () => api<User>("/auth/me").then((u) => {
  localStorage.setItem("sentinel.user", JSON.stringify(u));
  return u;
});

export function logout() {
  localStorage.removeItem("sentinel.token");
  localStorage.removeItem("sentinel.user");
  location.href = "/login";
}

export const fmtTs = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleString("en-IN", { hour12: false }) : "—";
export const ago = (s: string | null | undefined) => {
  if (!s) return "never";
  const d = (Date.now() - new Date(s).getTime()) / 1000;
  if (d < 60) return `${Math.round(d)}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
};
/** "white car", "car", or "—". Type and colour come from the object detector; either may be
 *  absent (no vehicle box around the plate, IR frame, two-wheeler), and absent is shown as absent. */
export const vehicleLabel = (s: { vehicle_type?: string | null; vehicle_color?: string | null }) =>
  s.vehicle_type ? [s.vehicle_color, s.vehicle_type].filter(Boolean).join(" ") : "—";
export const HEALTH_COLOR: Record<string, string> = {
  online: "#22c55e", degraded: "#f59e0b", offline: "#ef4444", unknown: "#64748b",
};
export const SEV_COLOR: Record<string, string> = {
  low: "#64748b", medium: "#3b82f6", high: "#f59e0b", critical: "#ef4444",
};
