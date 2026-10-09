import { useEffect, useState } from "react";
import { api, CATALOGUE, can, fmtTs, HEALTH_COLOR, simulatorCameras } from "../api";
import { useEvents } from "../events";
import CameraQualityTable from "../components/CameraQuality";

const OBJ_CLASSES = ["car", "motorcycle", "bus", "truck", "bicycle"];
const SEV_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };
const SEV_BG: Record<string, string> = { high: "#ef4444", medium: "#f59e0b", low: "#64748b" };

type Finding = { district: string; severity: string; finding: string };
/** Findings worst first; one that several districts share ("no cameras registered") becomes one line naming them,
 *  so it does not push the rest off the screen. */
function grouped(findings: Finding[]): { severity: string; finding: string; districts: string[] }[] {
  const m = new Map<string, { severity: string; finding: string; districts: string[] }>();
  for (const f of findings) {
    const k = `${f.severity}|${f.finding}`;
    if (!m.has(k)) m.set(k, { severity: f.severity, finding: f.finding, districts: [] });
    m.get(k)!.districts.push(f.district);
  }
  return [...m.values()].sort((a, b) => (SEV_ORDER[a.severity] ?? 9) - (SEV_ORDER[b.severity] ?? 9)
    || b.districts.length - a.districts.length);
}

export default function HealthPage() {
  const [fleet, setFleet] = useState<any>();
  const [uptime, setUptime] = useState<any[]>([]);
  const [gaps, setGaps] = useState<any>({ districts: [], findings: [] });
  const [depts, setDepts] = useState<any[]>([]);
  const [objects, setObjects] = useState<any>();
  const [hours, setHours] = useState(24);
  const [sim, setSim] = useState<Set<string>>(new Set());
  const [loadErr, setLoadErr] = useState("");
  useEffect(() => { simulatorCameras().then(setSim); }, []);

  const load = () => {
    api("/reports/fleet").then((f) => { setFleet(f); setLoadErr(""); })
      .catch((e) => setLoadErr(`Could not load the reports: ${e.message}`));
    api(`/reports/uptime?hours=${hours}`).then(setUptime).catch(() => {});
    api("/reports/gaps").then(setGaps).catch(() => {});
    api("/reports/departments").then(setDepts).catch(() => {});
    api(`/reports/objects?hours=${hours}`).then(setObjects).catch(() => {});
  };
  useEffect(load, [hours]);
  useEvents((e) => { if (e.type === "camera.health") load(); });

  const outage = async (code: string) => {
    try {
      const r = await fetch(`${CATALOGUE}/admin/outage/${encodeURIComponent(code)}?seconds=60`, { method: "POST" });
      if (!r.ok) throw new Error(`the simulator refused (${r.status})`);
    } catch (e: any) {
      setLoadErr(`Simulator outage failed: ${e instanceof TypeError ? "the feed simulator is not answering" : e.message}`);
    }
  };

  return (
    <div className="page">
      <header className="page-head"><h1>Health &amp; reports</h1>
        <div className="filters"><span className="muted">Window</span>
          {[1, 24, 168].map((h) => <button key={h} className={`btn ${hours === h ? "btn-primary" : ""}`} onClick={() => setHours(h)}>{h === 168 ? "7 d" : `${h} h`}</button>)}
        </div>
      </header>

      {loadErr && <div className="error" role="alert" style={{ marginBottom: 12 }}>{loadErr}</div>}
      {fleet && (
        <div className="stat-grid">
          {["online", "degraded", "offline", "unknown"].map((k) => (
            <div className="stat" key={k}><div className="stat-label">{k}</div><div className="stat-value" style={{ color: HEALTH_COLOR[k] }}>{fleet[k]}</div></div>
          ))}
          <div className="stat"><div className="stat-label">Ungeocoded</div><div className="stat-value">{fleet.ungeocoded}</div><div className="stat-sub">cameras without a location</div></div>
          <div className="stat"><div className="stat-label">Integration modes</div><div className="stat-sub">{fleet.by_mode?.map((m: any) => `${m.mode} ${m.count}`).join(" · ")}</div></div>
          <div className="stat"><div className="stat-label">Codecs</div><div className="stat-sub">{fleet.by_codec?.map((m: any) => `${m.codec} ${m.count}`).join(" · ")}</div></div>
          <div className="stat"><div className="stat-label">Maintenance</div>
            <div className="stat-value small">{fleet.under_maintenance ?? 0} under maintenance · {fleet.faulty ?? 0} faulty</div>
            <div className="stat-sub">{fleet.decommissioned ?? 0} decommissioned</div></div>
          <div className="stat"><div className="stat-label">Ageing</div>
            <div className="stat-value small"><span className={fleet.amc_expired ? "due-past" : ""}>{fleet.amc_expired ?? 0} AMC expired</span> · {fleet.ageing ?? 0} past {gaps.ageing_years ?? 7} years</div>
            <div className="stat-sub">{fleet.install_year_unknown ?? 0} without an installation year</div></div>
          <div className="stat"><div className="stat-label">Storage</div><div className="stat-sub">{fleet.by_storage?.map((m: any) => `${m.storage} ${m.count} (avg ${m.avg_retention ?? "?"} d)`).join(" · ")}</div></div>
        </div>
      )}

      <div className="two-col" style={{ marginTop: 16 }}>
        <section className="card">
          <h2>Gap analysis</h2>
          {gaps.findings.length === 0 && <div className="muted">No findings.</div>}
          <ul className="findings">
            {grouped(gaps.findings).map((g) => (
              <li key={`${g.severity}|${g.finding}`}>
                <span className="badge" style={{ background: SEV_BG[g.severity] ?? "#64748b" }}>{g.severity}</span>{" "}
                {g.districts.length > 3
                  ? <><b>{g.districts.length} districts</b> — {g.finding}
                      <details className="small muted"><summary>which</summary>{g.districts.join(", ")}</details></>
                  : <><b>{g.districts.join(", ")}</b> — {g.finding}</>}
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <h2>Departments</h2>
          <table>
            <thead><tr><th>Dept</th><th>Cameras</th><th>Online</th><th>ANPR</th><th>Districts</th><th>Vendors</th><th>Retention</th></tr></thead>
            <tbody>{depts.filter((d) => d.cameras > 0).map((d) => (
              <tr key={d.code}><td>{d.code}</td><td>{d.cameras}</td><td>{d.online}</td><td>{d.anpr_viable}</td><td>{d.districts}</td><td>{d.vendors}</td><td>{d.min_retention ?? "?"}–{d.max_retention ?? "?"} d</td></tr>
            ))}</tbody>
          </table>
        </section>
      </div>

      <CameraQualityTable hours={hours} />

      <section className="card" style={{ marginTop: 16 }}>
        <h2>Vehicle &amp; person detection — last {hours === 168 ? "7 days" : `${hours} h`}</h2>
        <div className="muted small" style={{ marginBottom: 8 }}>
          Average in view per analysed frame, and the most seen in any single frame. A detection is a box in one frame:
          nothing here is a unique vehicle or person, and people (riders included) are counted, never identified.
        </div>
        <table>
          <thead><tr><th>Camera</th><th>Frames</th><th>Vehicles</th><th>People</th>
            {OBJ_CLASSES.map((k) => <th key={k}>{k}</th>)}<th>Last window</th></tr></thead>
          <tbody>
            {(!objects || objects.per_camera.length === 0) && <tr><td colSpan={5 + OBJ_CLASSES.length} className="muted">
              No object analytics in this window: the worker writes a row per camera per minute while it runs.</td></tr>}
            {objects?.per_camera.map((c: any) => (
              <tr key={c.camera_code}>
                <td><span className="mono">{c.camera_code}</span> <span className="muted small">{c.name}</span></td>
                <td>{c.frames.toLocaleString()}</td>
                <td>{c.frames ? <>{c.vehicles_in_view} <span className="muted small">peak {c.vehicle_peak}</span></> : "—"}</td>
                <td>{c.frames ? <>{c.in_view.person ?? 0} <span className="muted small">peak {c.peak.person ?? 0}</span></> : "—"}</td>
                {OBJ_CLASSES.map((k) => <td key={k}>{c.in_view[k] ?? (c.frames ? 0 : "—")}</td>)}
                <td>{fmtTs(c.last_window)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <h2>Uptime — last {hours === 168 ? "7 days" : `${hours} h`}</h2>
        <table>
          <thead><tr><th>Camera</th><th>Dept</th><th>Checks</th><th>Uptime</th><th>Latency</th><th>Last reachable</th>{can("cameras.write") && <th></th>}</tr></thead>
          <tbody>{uptime.map((u) => (
            <tr key={u.camera_code}>
              <td><span className="mono">{u.camera_code}</span> <span className="muted small">{u.name}</span></td>
              <td>{u.department_code}</td><td>{u.checks}</td>
              <td><span className="bar"><span style={{ width: `${u.uptime_pct ?? 0}%`, background: (u.uptime_pct ?? 0) > 95 ? HEALTH_COLOR.online : (u.uptime_pct ?? 0) > 70 ? HEALTH_COLOR.degraded : HEALTH_COLOR.offline }} /></span> {u.uptime_pct ?? "—"}%</td>
              <td>{u.avg_latency_ms != null ? `${u.avg_latency_ms} ms` : "—"}</td>
              <td>{fmtTs(u.last_reachable)}</td>
              {can("cameras.write") && <td>{sim.has(u.camera_code) && <button className="btn btn-ghost small" onClick={() => outage(u.camera_code)} title="Feed simulator: take this camera down for 60 s">simulator: outage</button>}</td>}
            </tr>
          ))}</tbody>
        </table>
      </section>
    </div>
  );
}
