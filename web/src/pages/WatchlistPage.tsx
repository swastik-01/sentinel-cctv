import { FormEvent, useEffect, useState } from "react";
import { api, can, fmtTs, SEV_COLOR } from "../api";

const KINDS = ["stolen_vehicle", "blacklisted_vehicle", "bolo", "wanted_person", "missing_person"];

export default function WatchlistPage() {
  const [items, setItems] = useState<any[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [form, setForm] = useState({ kind: "stolen_vehicle", plate: "", subject_name: "", severity: "high", source: "manual", source_ref: "", reason: "" });
  const [check, setCheck] = useState<any>(null);
  const [msg, setMsg] = useState("");

  const load = () => api(`/watchlist?active=true${q ? `&q=${encodeURIComponent(q)}` : ""}`).then(setItems).catch(() => {});
  useEffect(() => { load(); }, [q]); // eslint-disable-line
  useEffect(() => { api("/watchlist/sources").then(setSources).catch(() => {}); }, []);

  const add = async (e: FormEvent) => {
    e.preventDefault(); setMsg("");
    try {
      const w = await api("/watchlist", { method: "POST", body: { ...form, plate: form.plate || null, subject_name: form.subject_name || null } });
      setForm({ ...form, plate: "", subject_name: "", reason: "" }); load();
      const r = w.retro;
      if (r?.seen) setMsg(`${w.plate_norm} was already seen ${r.seen} time(s) in the last ${r.hours} h on ${r.cameras} camera(s); ` +
        `last at ${r.last.camera_code} (${r.last.camera_name}) ${fmtTs(r.last.event_ts)}${r.last.exact ? "" : `, read as ${r.last.plate_norm}`}` +
        `${r.alert_id ? " — alert raised" : ""}. Open Vehicle Search for the full route.`);
      else if (r) setMsg(`${w.plate_norm} added. Not seen in the last ${r.hours} h; every camera now checks for it.`);
    }
    catch (ex: any) { setMsg(ex.message); }
  };
  const remove = async (id: string) => { await api(`/watchlist/${id}`, { method: "DELETE" }); load(); };
  const sync = async (name: string) => { setMsg(""); try { const r = await api(`/watchlist/sync/${name}`, { method: "POST" }); setMsg(`${r.adapter.system}: ${r.synced} entries synced${r.already_seen ? `; ${r.already_seen} already seen in the last 24 h (alerts raised)` : ""}`); load(); } catch (ex: any) { setMsg(ex.message); } };
  const doCheck = async (plate: string) => { if (plate.length >= 6) setCheck(await api(`/watchlist/check/${encodeURIComponent(plate)}`)); else setCheck(null); };

  return (
    <div className="page">
      <header className="page-head"><h1>Watchlist</h1>
        <div className="filters">
          <input placeholder="filter plate / name" value={q} onChange={(e) => setQ(e.target.value)} />
          {can("watchlist.write") && sources.map((s) => (s.mode === "awaiting-access" ? (
            <span key={s.name} className="btn btn-ghost" style={{ opacity: 0.75, cursor: "default" }}
                  title={`${s.description}. Needs: ${s.requires}`}>{s.system} <span className="tag">awaiting access</span></span>
          ) : (
            <button key={s.name} className="btn" onClick={() => sync(s.name)} title={s.description}>Sync {s.system} <span className="tag">{s.mode}</span></button>
          )))}
          <span className="muted">{items.length} active</span>
        </div>
      </header>
      {msg && <div className="ok">{msg}</div>}

      <div className="two-col">
        <section className="card">
          <h2>Active entries</h2>
          <div className="scroll">
            <table>
              <thead><tr><th>Kind</th><th>Plate</th><th>Subject</th><th>Sev</th><th>Source</th><th>Reason</th><th>Since</th><th></th></tr></thead>
              <tbody>{items.map((w) => (
                <tr key={w.id}>
                  <td>{w.kind.replace("_", " ")}</td><td className="mono">{w.plate_norm || "—"}</td><td>{w.subject_name || "—"}</td>
                  <td><span className="badge" style={{ background: SEV_COLOR[w.severity] }}>{w.severity}</span></td>
                  <td>{w.source}<div className="muted small">{w.source_ref}</div></td>
                  <td className="muted small">{w.reason}</td><td className="muted small">{fmtTs(w.created_at)}</td>
                  <td>{can("watchlist.write") && <button className="btn btn-ghost small" onClick={() => remove(w.id)}>deactivate</button>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </section>
        <div>
          {can("watchlist.write") && (
            <form className="card form" onSubmit={add}>
              <h2>Add entry</h2>
              <label>Kind<select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{KINDS.map((k) => <option key={k} value={k}>{k.replace("_", " ")}</option>)}</select></label>
              <label>Plate<input className="mono" value={form.plate} onChange={(e) => setForm({ ...form, plate: e.target.value.toUpperCase() })} placeholder="GJ01AB1234" /></label>
              <label>Subject name<input value={form.subject_name} onChange={(e) => setForm({ ...form, subject_name: e.target.value })} /></label>
              <label>Severity<select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>{Object.keys(SEV_COLOR).map((s) => <option key={s}>{s}</option>)}</select></label>
              <label>Source ref (FIR)<input value={form.source_ref} onChange={(e) => setForm({ ...form, source_ref: e.target.value })} /></label>
              <label>Reason<input value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} /></label>
              <button className="btn btn-primary">Add to watchlist</button>
            </form>
          )}
          <div className="card" style={{ marginTop: 16 }}>
            <h2>Check a plate</h2>
            <input className="mono" placeholder="type a plate…" onChange={(e) => doCheck(e.target.value.toUpperCase())} />
            {check && (
              <div style={{ marginTop: 8 }}>
                <div className="muted small">normalised: <span className="mono">{check.plate_norm}</span></div>
                {check.matches.length === 0 ? <div className="ok">No match</div> : check.matches.map((m: any) => (
                  <div key={m.id} className="row"><span className="badge" style={{ background: SEV_COLOR[m.severity] }}>{m.severity}</span> {m.kind} <span className="mono">{m.plate_norm}</span> <span className="muted">{Math.round(m.score * 100)}%</span></div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
