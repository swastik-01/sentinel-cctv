import { useEffect, useState } from "react";
import { api, fmtTs } from "../api";

const ACTIONS = ["", "plate.", "camera.", "alert.", "watchlist.", "auth."];

export default function AuditPage() {
  const [rows, setRows] = useState<any[]>([]);
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    const q = new URLSearchParams({ limit: "300" });
    if (action) q.set("action", action);
    if (actor) q.set("actor", actor);
    api(`/audit?${q}`).then((r) => { setRows(r); setErr(""); }).catch((e) => setErr(e.message));
  }, [action, actor]);

  return (
    <div className="page">
      <header className="page-head">
        <h1>Audit trail</h1>
        <span className="muted">Append-only · every plate search, footage view, onboarding and alert action</span>
        <div className="filters">
          <select value={action} onChange={(e) => setAction(e.target.value)}>
            {ACTIONS.map((a) => <option key={a} value={a}>{a ? a.replace(".", "") : "All actions"}</option>)}
          </select>
          <input placeholder="actor" value={actor} onChange={(e) => setActor(e.target.value)} />
          <span className="muted">{rows.length}</span>
        </div>
      </header>
      {err && <div className="error">{err}</div>}
      <div className="card scroll" style={{ maxHeight: "none" }}>
        <table>
          <thead><tr><th>When</th><th>Actor</th><th>Action</th><th>Object</th><th>Purpose</th><th>Detail</th><th>IP</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="small">{fmtTs(r.at)}</td>
                <td>{r.actor_name}</td>
                <td><span className={`tag tag-${r.action.split(".")[0] === "plate" ? "alert" : r.action.split(".")[0] === "camera" ? "camera" : "sighting"}`}>{r.action}</span></td>
                <td className="mono small">{r.object_id}</td>
                <td className="small">{r.purpose || <span className="muted">—</span>}</td>
                <td className="muted small mono">{Object.entries(r.detail || {}).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join("  ")}</td>
                <td className="muted small">{r.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
