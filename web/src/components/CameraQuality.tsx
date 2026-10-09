import { useEffect, useMemo, useRef, useState } from "react";
import { api, CameraQuality, can, reasonLabel } from "../api";

// Plate-reading quality per camera: how its captures grade, what holds them back, and what to change.
// The grades, tiers and recommendations all come from the API; this only lays them out.

// Published size guidance the grades use (docs/commercial-anpr.md: characters at least 10 px, best 20-60;
// plate 100-150 px across, 75 px at least). Here it only colours the medians.
const PLATE_MIN = 75, PLATE_OK = 100, CHAR_MIN = 10, CHAR_OK = 16;

const TIER: Record<string, { label: string; title: string }> = {
  A: { label: "reads plates", title: "Tier A: most captures are good and plates are big enough to read" },
  B: { label: "marginal", title: "Tier B: some captures read well, but size, blur, light or angle hold many back" },
  C: { label: "counts only", title: "Tier C: too few good captures or plates too small; use it for counts and viewing" },
};
const KIND_CLASS: Record<string, string> = { camera: "tag-camera", model: "tag-model", config: "tag-config" };

type SortKey = "tier" | "camera" | "captures" | "good" | "plate_w" | "blind";
const TEXT_KEYS: SortKey[] = ["tier", "camera"];

// Nothing graded in the window (not analysed, or reads with no crop): the API still says C, but that is no finding.
const notGraded = (c: CameraQuality) => c.graded === false;
const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : "—");
const rate = (n: number) => (n >= 10 || n === 0 ? String(Math.round(n)) : n.toFixed(1));
const level = (v: number | null, bad: number, ok: number) => (v == null ? "" : v < bad ? "lvl-bad" : v < ok ? "lvl-warn" : "");
// Unknown sorts last in either direction's natural reading: -1 is below every real share or size.
const sortVal = (c: CameraQuality, k: SortKey): string | number => {
  switch (k) {
    case "tier": return notGraded(c) ? "D" : c.tier;
    case "camera": return c.camera_code;
    case "captures": return c.captures;
    case "good": return c.captures ? c.good / c.captures : -1;
    case "plate_w": return c.median_plate_w ?? -1;
    case "blind": return c.reviewed_blind ? (c.blind_exact ?? 0) / c.reviewed_blind : -1;
  }
};

export default function CameraQualityTable({ hours }: { hours: number }) {
  const [rows, setRows] = useState<CameraQuality[] | null>(null);
  const [err, setErr] = useState("");
  const [prefix, setPrefix] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "tier", desc: false });
  const [showEmpty, setShowEmpty] = useState(false);
  const seq = useRef(0);

  const load = () => {
    const n = ++seq.current;
    const q = new URLSearchParams({ since: new Date(Date.now() - hours * 3600e3).toISOString() });
    if (prefix.trim()) q.set("prefix", prefix.trim());
    api<any>(`/reports/camera-quality?${q}`)
      .then((r) => { if (n === seq.current) { setRows(Array.isArray(r) ? r : r?.items ?? []); setErr(""); } })
      .catch((e) => { if (n === seq.current) { setRows([]); setErr(e.message); } });
  };
  // A typed prefix waits for a pause, so every keystroke is not a query.
  useEffect(() => {
    const t = setTimeout(load, prefix ? 300 : 0);
    return () => clearTimeout(t);
  }, [hours, prefix]); // eslint-disable-line

  const sorted = useMemo(() => [...(rows ?? [])].sort((a, b) => {
    const x = sortVal(a, sort.key), y = sortVal(b, sort.key);
    const d = typeof x === "string" ? x.localeCompare(String(y)) : x - (y as number);
    return (sort.desc ? -d : d) || a.camera_code.localeCompare(b.camera_code);
  }), [rows, sort]);

  if (!can("reports.read")) return null;

  // Tier and camera read best A→C and A→Z; the numbers read best largest first.
  const by = (key: SortKey) => setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: !TEXT_KEYS.includes(key) }));
  const th = (key: SortKey, label: string, title?: string) => (
    <th className="sortable" title={title ?? `Sort by ${label.toLowerCase()}`} onClick={() => by(key)}>
      {label}{sort.key === key ? (sort.desc ? " ▼" : " ▲") : ""}
    </th>
  );
  const tiers = { A: 0, B: 0, C: 0 } as Record<string, number>;
  (rows ?? []).forEach((c) => { if (!notGraded(c)) tiers[c.tier] = (tiers[c.tier] ?? 0) + 1; });
  const idle = (rows ?? []).filter(notGraded).length;
  const cols = 9;
  // Cameras with no capture say one thing each (why, and what to use them for): folded away under the ones
  // with captures, one line each when opened, so thirty sandbox cameras with no plate do not bury the rest.
  const seen = sorted.filter((c) => c.captures > 0), empty = sorted.filter((c) => c.captures === 0);
  const openEmpty = showEmpty || seen.length === 0;
  const why: Record<string, number> = {};
  empty.forEach((c) => { const k = c.tier_reason || "no plate read"; why[k] = (why[k] ?? 0) + 1; });

  const recList = (c: CameraQuality) => (
    <ul className="recs">{c.recommendations.map((r, i) => (
      <li key={i}><span className={`tag ${KIND_CLASS[r.kind] ?? ""}`}>{r.kind}</span>{r.text}</li>
    ))}</ul>
  );
  const tierCell = (c: CameraQuality) => (
    <td className="nowrap">{notGraded(c)
      ? <><span className="tier tier-none" title={`No tier: ${c.tier_reason ?? "nothing graded"}`}>–</span>{" "}
        <span className="muted small">not graded</span></>
      : <><span className={`tier tier-${c.tier}`} title={TIER[c.tier]?.title}>{c.tier}</span>{" "}
        <span className="muted small">{TIER[c.tier]?.label}</span></>}</td>
  );
  const cameraCell = (c: CameraQuality) => (
    <td><span className="mono">{c.camera_code}</span> <span className="muted small">{c.camera_name}</span>
      {c.department && <div className="muted small">{c.department}</div>}</td>
  );
  const rateCell = (c: CameraQuality) => (
    <td>{c.plates_per_1000_frames != null && c.frames_analysed
      ? <span title={`${Math.max(0, (c.sightings ?? c.captures) - (c.not_plates ?? 0)).toLocaleString()} plate reads over `
          + `${c.frames_analysed.toLocaleString()} analysed frames`}>{rate(c.plates_per_1000_frames)}</span>
      : <span className="muted" title="No object-detection frames recorded for this camera in the window">—</span>}</td>
  );

  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="row space">
        <h2>Plate-reading quality by camera — last {hours === 168 ? "7 days" : `${hours} h`}</h2>
        <div className="row">
          <label className="inline" title="Every camera whose code starts with this, e.g. CAM for the sandbox cameras">Code starts with
            <input className="prefix" value={prefix} placeholder="e.g. CAM" maxLength={20}
              onChange={(e) => setPrefix(e.target.value.toUpperCase())} />
          </label>
          <button className="btn btn-ghost small" onClick={load}>Refresh</button>
        </div>
      </div>
      <div className="muted small" style={{ marginBottom: 8 }}>
        Each plate capture is graded good, marginal or poor from its crop: size against published ANPR guidance (characters
        10 px or taller, best 20–60 px; plate 100–150 px across, 75 px at least), and sharpness, light and contrast against how
        far crops from our own stock-footage test feeds could be blurred, darkened or flattened before our reader's reads
        changed; a two-line plate or a low-confidence read makes it marginal. Captures reviewed as not a plate are left out.
        Tier A reads plates, B is marginal, C is for counts and viewing only. Blind exact is the share of blind-checked
        vehicle plates whose stored read matched what the reviewer typed. The grade measures the picture: it cannot see
        plates the reader missed.
      </div>
      {err && <div className="error small" style={{ marginBottom: 8 }}>Quality report unavailable: {err}</div>}
      {rows && rows.length > 0 && (
        <div className="row small" style={{ marginBottom: 8 }}>
          {(["A", "B", "C"] as const).map((t) => (
            <span key={t} title={TIER[t].title}><span className={`tier tier-${t}`}>{t}</span> {tiers[t]} {TIER[t].label}</span>
          ))}
          {idle > 0 && <span className="muted" title="Not analysed in the window, or reads with no crop to grade: no tier">
            {idle} not graded</span>}
        </div>
      )}
      <table className="quality">
        <thead><tr>
          {th("camera", "Camera")}
          {th("tier", "Tier")}
          {th("captures", "Captures", "Plate captures in the window; sort by count")}
          {th("good", "Good · marginal · poor", "Poor: too small to read, or two or more image problems. Marginal: one problem, "
            + "a two-line plate or a low-confidence read. Sort by share of good captures")}
          {th("plate_w", "Plate width", "Median plate width in the frame, in pixels (100–150 px reads well); sort by it")}
          <th title="Median character height, in pixels (10 px at least, 20–60 px best)">Char height</th>
          <th>Main issues</th>
          {th("blind", "Blind exact", "Exact blind-checked reads, of those reviewed; sort by share")}
          <th title="Plate captures per 1,000 frames the object detector analysed on this camera">Plates / 1k frames</th>
        </tr></thead>
        {rows === null && !err && <tbody><tr><td colSpan={cols} className="muted">Loading…</td></tr></tbody>}
        {rows?.length === 0 && !err && <tbody><tr><td colSpan={cols} className="muted">
          {prefix ? `No camera code starts with ${prefix}.` : "No cameras in scope."}</td></tr></tbody>}
        {seen.map((c) => {
          const graded = c.good + c.marginal + c.poor;
          const issues = Object.entries(c.reasons ?? {}).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]).slice(0, 3);
          return (
            <tbody className="qcam" key={c.camera_code}>
              <tr>
                {cameraCell(c)}
                {tierCell(c)}
                <td>{c.captures.toLocaleString()}
                  {!!c.not_plates && <div className="muted small nowrap" title="Captures a reviewer marked as not a plate (a hoarding, a sign): left out of the grades and the tier">
                    +{c.not_plates} not plates</div>}</td>
                <td className="nowrap">{c.captures ? <>
                  <span className="qbar" title={`${c.good} good, ${c.marginal} marginal, ${c.poor} poor`
                    + (c.captures > graded ? `, ${c.captures - graded} not graded yet` : "")}>
                    <span style={{ width: `${(100 * c.good) / c.captures}%`, background: "var(--ok)" }} />
                    <span style={{ width: `${(100 * c.marginal) / c.captures}%`, background: "var(--warn)" }} />
                    <span style={{ width: `${(100 * c.poor) / c.captures}%`, background: "var(--danger)" }} />
                  </span>
                  <span className="small">{c.good} · {c.marginal} · {c.poor}</span>
                </> : <span className="muted">—</span>}</td>
                <td className={level(c.median_plate_w, PLATE_MIN, PLATE_OK)}>
                  {c.median_plate_w != null ? `${Math.round(c.median_plate_w)} px` : "—"}</td>
                <td className={level(c.median_char_h, CHAR_MIN, CHAR_OK)}>
                  {c.median_char_h != null ? `${Math.round(c.median_char_h)} px` : "—"}</td>
                <td>{issues.length ? <div className="issues">{issues.map(([r, n]) => (
                    <span className="tag" key={r} title={`${n} of ${c.captures} captures`}>{reasonLabel(r)} {pct(n, c.captures)}</span>
                  ))}</div> : <span className="muted">none</span>}</td>
                <td className="nowrap">{c.reviewed_blind ? <>{pct(c.blind_exact ?? 0, c.reviewed_blind)} <span className="muted small">of {c.reviewed_blind}</span></>
                  : <span className="muted" title="No blind-checked captures from this camera in the window">—</span>}</td>
                {rateCell(c)}
              </tr>
              {c.recommendations?.length > 0 && <tr className="qrecs"><td colSpan={cols}>{recList(c)}</td></tr>}
            </tbody>
          );
        })}
        {empty.length > 0 && (
          <tbody className="qempty">
            <tr><td colSpan={cols} className="small">
              {seen.length > 0 && <button className="btn btn-ghost small" onClick={() => setShowEmpty((v) => !v)}>
                {openEmpty ? "Hide" : "Show"}</button>}{" "}
              <b>{empty.length}</b> camera{empty.length === 1 ? "" : "s"} with no graded capture in the window
              <span className="muted"> — {Object.entries(why).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${k}: ${n}`).join("; ")}</span>
            </td></tr>
            {openEmpty && empty.map((c) => (
              <tr key={c.camera_code}>
                {cameraCell(c)}
                {tierCell(c)}
                <td>0{!!c.not_plates && <div className="muted small nowrap"
                  title="Captures a reviewer marked as not a plate (a hoarding, a sign): left out of the grades and the tier">
                  +{c.not_plates} not plates</div>}</td>
                <td colSpan={5}><span className="muted">{c.tier_reason || "no plate read"}</span>
                  {c.recommendations?.length > 0 && recList(c)}</td>
                {rateCell(c)}
              </tr>
            ))}
          </tbody>
        )}
      </table>
    </section>
  );
}
