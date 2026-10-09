import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ago, api, fmtTs, HEALTH_COLOR, Sighting, vehicleLabel } from "../api";
import { LiveEvent, useEvents } from "../events";

const IN_VIEW_HELP = "Average number visible per analysed frame, summed over reporting cameras. " +
  "A detection is a box in one frame, not a unique vehicle or person: nothing is tracked or identified. " +
  "People include riders and passengers.";
const VEHICLES = ["bicycle", "car", "motorcycle", "bus", "truck"];

function inViewText(c: { camera_code: string; frames: number; detections: Record<string, number> }) {
  if (!c.frames) return `${c.camera_code}: no frames`;
  const v = VEHICLES.reduce((n, k) => n + (c.detections[k] ?? 0), 0) / c.frames;
  const p = (c.detections.person ?? 0) / c.frames;
  return `${c.camera_code}: ${v.toFixed(1)} vehicles, ${p.toFixed(1)} people in view`;
}

function Stat({ label, value, color, sub, title }: { label: string; value: any; color?: string; sub?: string; title?: string }) {
  return (
    <div className="stat" title={title}>
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ color }}>{value ?? "—"}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export default function Overview() {
  const [fleet, setFleet] = useState<any>();
  const [alerts, setAlerts] = useState<any>();
  const [stats, setStats] = useState<any>();
  const [objects, setObjects] = useState<any>();
  const [recent, setRecent] = useState<Sighting[]>([]);
  const [ticker, setTicker] = useState<LiveEvent[]>([]);

  const load = () => {
    api("/reports/fleet").then(setFleet).catch(() => {});
    api("/alerts/summary").then(setAlerts).catch(() => {});
    api("/sightings/stats?hours=24").then(setStats).catch(() => {});
    api("/sightings/recent?limit=12").then(setRecent).catch(() => {});
    api("/reports/objects?hours=24").then(setObjects).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, []);
  useEvents((e) => {
    setTicker((t) => [e, ...t].slice(0, 25));
    if (e.type === "sighting.new") setRecent((r) => [e.sighting, ...r].slice(0, 12));
    if (e.type === "camera.health" || e.type === "alert.new") load();
  });

  return (
    <div className="page">
      <header className="page-head">
        <h1>Control room overview</h1>
        <span className="muted">Statewide · auto-refresh 30 s</span>
      </header>

      <div className="stat-grid">
        <Stat label="Cameras registered" value={fleet?.cameras} sub={`${fleet?.departments ?? "—"} departments · ${fleet?.districts ?? "—"} districts`} />
        <Stat label="Online" value={fleet?.online} color={HEALTH_COLOR.online} />
        <Stat label="Degraded" value={fleet?.degraded} color={HEALTH_COLOR.degraded} />
        <Stat label="Offline" value={fleet?.offline} color={HEALTH_COLOR.offline} />
        <Stat label="ANPR-viable" value={fleet?.anpr_viable} sub={`${fleet?.analytics_on ?? "—"} with analytics on`} />
        <Stat label="Open alerts" value={alerts?.new} color={alerts?.open_high ? "#ef4444" : undefined} sub={`${alerts?.open_high ?? 0} high/critical · ${alerts?.last_24h ?? 0} in 24 h`} />
        <Stat label="Plate reads (24 h)" value={stats?.sightings} sub={`${stats?.distinct_plates ?? 0} distinct plates · ${stats?.cameras_reporting ?? 0} cameras`} />
        <Stat label="Avg OCR confidence" value={stats?.avg_ocr_conf != null ? `${Math.round(stats.avg_ocr_conf * 100)}%` : "—"} />
        <Stat label="Vehicles in view" value={objects?.frames ? objects.vehicles.in_view : "—"}
              title={IN_VIEW_HELP}
              sub={objects?.frames ? `average, 24 h · peak ${objects.vehicles.peak} in one frame · ${objects.cameras_reporting} cameras` : "no object analytics in 24 h"} />
        <Stat label="People in view" value={objects?.frames ? objects.people.in_view : "—"}
              title={IN_VIEW_HELP}
              sub={objects?.frames ? `average, 24 h · peak ${objects.people.peak} · counted, never identified` : "counted, never identified"} />
      </div>

      <div className="two-col">
        <section className="card">
          <h2>Recent plate reads</h2>
          <table>
            <thead><tr><th>Time</th><th>Plate</th><th>Vehicle</th><th>Camera</th><th>Conf</th></tr></thead>
            <tbody>
              {recent.length === 0 && <tr><td colSpan={5} className="muted">No sightings yet — the analytics worker writes here.</td></tr>}
              {recent.map((s) => (
                <tr key={s.id}>
                  <td>{fmtTs(s.event_ts)}</td>
                  <td><Link to={`/search?plate=${s.plate_norm}`} className="mono">{s.plate_norm}</Link></td>
                  <td className="small">{vehicleLabel(s)}</td>
                  <td>{s.camera_code} <span className="muted">{s.camera_name}</span></td>
                  <td>{Math.round(s.ocr_conf * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="card">
          <h2>Live events</h2>
          <ul className="ticker">
            {ticker.length === 0 && <li className="muted">Waiting for events…</li>}
            {ticker.map((e, i) => (
              <li key={i}>
                <span className={`tag tag-${e.type.split(".")[0]}`}>{e.type}</span>
                {e.type === "alert.new" && <> <b>{e.alert.plate_norm}</b> on {e.alert.camera_code} · {e.alert.kind} · <span style={{ color: "#f97316" }}>{e.alert.severity}</span></>}
                {e.type === "alert.updated" && <> {e.alert.plate_norm} → {e.alert.status}</>}
                {e.type === "sighting.new" && <> {e.sighting.plate_norm} @ {e.sighting.camera_code}</>}
                {e.type === "camera.health" && <> {e.camera_code}: {e.from} → <span style={{ color: HEALTH_COLOR[e.to] }}>{e.to}</span></>}
                {e.type === "worker.heartbeat" && <> {e.worker_id}: {e.cameras.length} cameras</>}
                {e.type === "detection.counts" && <> {e.cameras.slice(0, 3).map(inViewText).join(" · ")}{e.cameras.length > 3 ? ` +${e.cameras.length - 3}` : ""}</>}
                <span className="muted small"> {ago(e.at)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
