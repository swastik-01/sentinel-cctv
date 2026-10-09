import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, CHECK_CROP, fmtTs, Movement, Sighting, vehicleLabel, Visit } from "../api";
import CameraMap, { MapStop } from "../components/CameraMap";
import CropImg from "../components/CropImg";
import QualityBadge from "../components/QualityBadge";

const dur = (s: number) => s < 60 ? `${s} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
const km = (m: number) => m < 1000 ? `${m} m` : `${(m / 1000).toFixed(1)} km`;
const hhmm = (ts: string) => new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

const isoLocal = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

export default function SearchPage() {
  const [params] = useSearchParams();
  const [plate, setPlate] = useState(params.get("plate") || "");
  const [camera] = useState(params.get("camera") || "");
  // A window can come in the URL (?since=&until=, local time), e.g. from an alert or a report.
  const [since, setSince] = useState(params.get("since") || isoLocal(new Date(Date.now() - 7 * 86400e3)));
  const [until, setUntil] = useState(params.get("until") || isoLocal(new Date(Date.now() + 3600e3)));
  const [fuzzy, setFuzzy] = useState(true);
  const [purpose, setPurpose] = useState("");
  const [result, setResult] = useState<Movement | null>(null);
  const [rows, setRows] = useState<Sighting[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [showReads, setShowReads] = useState(false);

  const run = async (e?: FormEvent) => {
    e?.preventDefault(); setBusy(true); setErr(""); setResult(null); setRows(null);
    try {
      const q = new URLSearchParams({ since: new Date(since).toISOString(), until: new Date(until).toISOString() });
      if (plate.trim()) {
        q.set("fuzzy", String(fuzzy)); if (purpose) q.set("purpose", purpose);
        setResult(await api(`/sightings/movement/${encodeURIComponent(plate.trim())}?${q}`));
      } else {
        if (camera) q.set("camera", camera);
        setRows(await api(`/sightings?${q}&limit=500`));
      }
    } catch (ex: any) { setErr(ex.message); } finally { setBusy(false); }
  };
  useEffect(() => { if (plate || camera) run(); }, []); // eslint-disable-line

  const timeline = result?.timeline ?? rows ?? [];
  const mapCams = Object.values(Object.fromEntries(timeline.map((s) => [s.camera_code, {
    camera_code: s.camera_code, name: s.camera_name, lat: s.lat, lon: s.lon, health: "online",
  }])));
  const visits: Visit[] = result?.visits ?? [];
  const stops: MapStop[] = visits.filter((v) => v.lat != null && v.lon != null).map((v) => ({
    key: `${v.n}`, n: v.n, lat: v.lat!, lon: v.lon!, warn: v.possible_misread || !!v.hop?.implausible,
    label: `${v.n}. ${hhmm(v.first_ts)} ${v.camera_code}${v.possible_misread ? " (possible misread)" : ""}`,
  }));
  const flagged = visits.filter((v) => v.hop?.implausible).length;

  const exportCsv = () => {
    const head = "event_ts,plate,vehicle_type,vehicle_color,camera_code,camera_name,district,lat,lon,ocr_conf";
    const body = timeline.map((s) => [s.event_ts, s.plate_norm, s.vehicle_type ?? "", s.vehicle_color ?? "", s.camera_code, `"${s.camera_name}"`, s.district, s.lat, s.lon, s.ocr_conf].join(","));
    const blob = new Blob([[head, ...body].join("\n")], { type: "text/csv" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `movement_${result?.plate_norm || "sightings"}.csv` });
    a.click();
  };

  return (
    <div className="page">
      <header className="page-head"><h1>Vehicle search</h1><span className="muted">Registration number → timestamped, location-wise movement history</span></header>
      <form className="card search-form" onSubmit={run}>
        <label>Registration number<input className="mono" value={plate} onChange={(e) => setPlate(e.target.value.toUpperCase())} placeholder="GJ 01 AB 1234" /></label>
        <label>From<input type="datetime-local" value={since} onChange={(e) => setSince(e.target.value)} /></label>
        <label>To<input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
        <label>Purpose (audited)<input value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="FIR / case reference" /></label>
        <label className="check"><input type="checkbox" checked={fuzzy} onChange={(e) => setFuzzy(e.target.checked)} /> tolerate 1 OCR error</label>
        <button className="btn btn-primary" disabled={busy}>{busy ? "Searching…" : "Search"}</button>
        {camera && !plate && <span className="muted">camera: {camera}</span>}
      </form>
      {err && <div className="error">{err}</div>}

      {result && (
        <div className="stat-grid" style={{ marginTop: 16 }}>
          <div className="stat"><div className="stat-label">Plate</div><div className="stat-value mono">{result.plate_norm}</div>
            {result.matched_plates.length > 1 && <div className="stat-sub">also read as {result.matched_plates.filter((p) => p !== result.plate_norm).join(", ")}</div>}</div>
          <div className="stat"><div className="stat-label">Sightings</div><div className="stat-value">{result.total_sightings}</div></div>
          <div className="stat"><div className="stat-label">Distinct cameras</div><div className="stat-value">{result.distinct_cameras}</div></div>
          <div className="stat"><div className="stat-label">First seen</div><div className="stat-value small">{fmtTs(result.first_seen)}</div></div>
          <div className="stat"><div className="stat-label">Last seen</div><div className="stat-value small">{fmtTs(result.last_seen)}</div></div>
        </div>
      )}

      {(result || rows) && (
        <div className="two-col" style={{ marginTop: 16 }}>
          <section className="card">
          {result && visits.length > 0 && (
            <>
              <div className="row space">
                <h2>Journey: {visits.length} stop{visits.length === 1 ? "" : "s"} at {result.distinct_cameras} camera{result.distinct_cameras === 1 ? "" : "s"}</h2>
                <button className="btn btn-ghost" onClick={() => setShowReads(!showReads)}>{showReads ? "Hide" : "Show"} all {timeline.length} reads</button>
              </div>
              {flagged > 0 && <div className="error small">{flagged} leg(s) faster than any road vehicle: two vehicles may carry this plate (cloned plate), or a read is wrong. Check the crops.</div>}
              <div className="scroll">
                <table>
                  <thead><tr><th>#</th><th>Time</th><th>Camera · location</th><th>Reads</th><th>From previous stop</th><th>Evidence</th></tr></thead>
                  <tbody>{visits.map((v) => (
                    <tr key={v.n} className={v.possible_misread ? "muted" : ""}>
                      <td><span className={`stop-num${v.possible_misread || v.hop?.implausible ? " warn" : ""}`}>{v.n}</span></td>
                      <td className="small">{fmtTs(v.first_ts)}{v.dwell_s > 0 && <div className="muted">for {dur(v.dwell_s)}</div>}</td>
                      <td><b>{v.camera_code}</b> {v.camera_name}<div className="muted small">{v.district} · {v.department}</div>
                        {v.possible_misread && <span className="tag tag-warn">possible misread: {v.best_read}</span>}
                        {v.needs_review && <span className="tag tag-warn" title={CHECK_CROP}>check the crop</span>}</td>
                      <td>{v.reads}<div className="muted small">{[v.vehicle_color, v.vehicle_type].filter(Boolean).join(" ")}</div></td>
                      <td className="small">{v.hop ? <>
                        {km(v.hop.distance_m)} in {dur(v.hop.travel_s)}{v.hop.speed_kmh != null && <> · ~{Math.round(v.hop.speed_kmh)} km/h</>}
                        {v.hop.implausible && <div><span className="tag tag-alert">implausible</span></div>}
                      </> : <span className="muted">{v.hop_note ?? "—"}</span>}</td>
                      <td>{v.crop_path && <CropImg className="crop" path={v.crop_path} />}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              <div className="muted small">Distances are straight lines between cameras; speeds are averages over the leg, not measured speed.</div>
            </>
          )}
          {(!result || showReads || visits.length === 0) && (<>
            <div className="row space"><h2>Timeline ({timeline.length})</h2><button className="btn btn-ghost" onClick={exportCsv} disabled={!timeline.length}>Export CSV</button></div>
            <div className="scroll">
              <table>
                <thead><tr><th>#</th><th>Time</th><th>Plate read</th><th>Vehicle</th><th>Camera</th><th>Location</th><th>Conf</th><th>Crop</th></tr></thead>
                <tbody>
                  {timeline.map((s, i) => (
                    <tr key={s.id}>
                      <td>{i + 1}</td><td>{fmtTs(s.event_ts)}</td>
                      <td className="mono">{s.plate_text}{s.plate_norm !== result?.plate_norm && result && <span className="muted"> ≈</span>}</td>
                      <td className="small">{vehicleLabel(s)}</td>
                      <td>{s.camera_code}</td>
                      <td>{s.camera_name}<div className="muted small">{s.district} · {s.department}</div></td>
                      <td>{Math.round(s.ocr_conf * 100)}%
                        {s.reads != null && <div className="muted small">{s.reads} read{s.reads === 1 ? "" : "s"}</div>}
                        {s.needs_review && <div><span className="tag tag-warn" title={CHECK_CROP}>check the crop</span></div>}</td>
                      {/* The grade is the crop's own (size, sharpness, light, angle); ungraded crops show no badge. */}
                      <td>{s.crop_path && <CropImg className="crop" path={s.crop_path} />}
                        {s.quality && <div><QualityBadge q={s.quality} /></div>}</td>
                    </tr>
                  ))}
                  {timeline.length === 0 && <tr><td colSpan={8} className="muted">No sightings in this window.</td></tr>}
                </tbody>
              </table>
            </div>
          </>)}
          {result && visits.length > 0 && !showReads && <button className="btn btn-ghost" onClick={exportCsv}>Export all reads (CSV)</button>}
          </section>
          <section className="card map-card">
            <h2>Route</h2>
            <div style={{ height: 420 }}>
              <CameraMap cameras={mapCams} route={result?.route} stops={stops} />
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
