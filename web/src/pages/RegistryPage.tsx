import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ago, API, api, Camera, CAMERA_CLASSES, can, dueClass, HEALTH_COLOR, Maintenance, MAINTENANCE_LABEL, token } from "../api";
import EditCamera from "../components/EditCamera";
import OnboardCard from "../components/OnboardCard";

export default function RegistryPage() {
  const [items, setItems] = useState<Camera[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [dept, setDept] = useState("");
  const [health, setHealth] = useState("");
  const [cls, setCls] = useState("");
  const [maint, setMaint] = useState("");
  const [loadErr, setLoadErr] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState<Camera | null>(null);
  const [msg, setMsg] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [catUrl, setCatUrl] = useState("");
  const [analytics, setAnalytics] = useState("anpr");
  const [preview, setPreview] = useState<any>(null);

  // Typing searches once the operator pauses, not on every key.
  useEffect(() => { const t = window.setTimeout(() => setQDebounced(q.trim()), 300); return () => window.clearTimeout(t); }, [q]);

  const load = () => {
    const p = new URLSearchParams({ limit: "500" });
    if (qDebounced) p.set("q", qDebounced); if (dept) p.set("department", dept); if (health) p.set("health", health);
    if (cls) p.set("camera_class", cls); if (maint) p.set("maintenance", maint);
    api(`/cameras?${p}`).then((r) => { setItems(r.items); setTotal(r.total); setLoadErr(""); })
      .catch((e) => setLoadErr(`Could not load the registry: ${e.message}`))
      .finally(() => setLoaded(true));
  };
  useEffect(load, [qDebounced, dept, health, cls, maint]);

  const importCsv = async (f: File) => {
    setBusy(true); setMsg(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      setMsg(await api("/cameras/import", { method: "POST", body: fd })); load();
    } catch (e: any) { setMsg({ error: e.message }); } finally { setBusy(false); }
  };
  const syncQuery = (dry: boolean) => {
    const p = new URLSearchParams({ analytics, dry_run: String(dry) });
    if (catUrl.trim()) p.set("url", catUrl.trim());
    return `/cameras/sync-catalogue?${p}`;
  };
  const dryRun = async () => {
    setBusy(true); setMsg(null); setPreview(null);
    try { setPreview(await api(syncQuery(true), { method: "POST" })); }
    catch (e: any) { setMsg({ error: e.message }); } finally { setBusy(false); }
  };
  const sync = async () => {
    setBusy(true); setMsg(null); setPreview(null);
    try { setMsg(await api(syncQuery(false), { method: "POST" })); load(); }
    catch (e: any) { setMsg({ error: e.message }); } finally { setBusy(false); }
  };
  const toggleAnalytics = async (c: Camera) => {
    try {
      await api(`/cameras/${encodeURIComponent(c.camera_code)}`, { method: "PATCH", body: { analytics_enabled: !c.analytics_enabled } });
      setItems((xs) => xs.map((x) => x.camera_code === c.camera_code ? { ...x, analytics_enabled: !c.analytics_enabled } : x));
    } catch (e: any) { setMsg({ error: e.message }); }
  };
  const download = async (path: string, name: string) => {
    try {
      const r = await fetch(API + path, { headers: { Authorization: `Bearer ${token()}` } });
      if (!r.ok) throw new Error(`download failed (${r.status})`);
      const url = URL.createObjectURL(await r.blob());
      Object.assign(document.createElement("a"), { href: url, download: name }).click();
      window.setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (e: any) {
      setMsg({ error: e instanceof TypeError ? "download failed: the API is not answering" : e.message });
    }
  };
  const remove = async (c: Camera) => {
    if (!window.confirm(`Delete ${c.camera_code} (${c.name}) from the registry? `
      + "Its sightings, counts and alerts go with it. This cannot be undone.")) return;
    try {
      await api(`/cameras/${encodeURIComponent(c.camera_code)}`, { method: "DELETE" });
      setMsg({ info: `${c.camera_code} deleted` }); load();
    } catch (e: any) { setMsg({ error: e.message }); }
  };
  const depts = [...new Set(items.map((c) => c.department_code))].sort();
  const filtered = !!(qDebounced || dept || health || cls || maint);
  const writer = can("cameras.write");

  return (
    <div className="page">
      <header className="page-head">
        <h1>Camera registry</h1>
        <div className="filters">
          <input placeholder="search code / name / address" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search" maxLength={100} />
          <select value={dept} onChange={(e) => setDept(e.target.value)} aria-label="Department"><option value="">All departments</option>{depts.map((d) => <option key={d}>{d}</option>)}</select>
          <select value={health} onChange={(e) => setHealth(e.target.value)} aria-label="Health"><option value="">Any health</option>{Object.keys(HEALTH_COLOR).map((h) => <option key={h}>{h}</option>)}</select>
          <select value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Camera type"><option value="">Any type</option>{CAMERA_CLASSES.map((c) => <option key={c}>{c}</option>)}</select>
          <select value={maint} onChange={(e) => setMaint(e.target.value)} aria-label="Maintenance"><option value="">Any maintenance</option>
            {(Object.keys(MAINTENANCE_LABEL) as Maintenance[]).map((m) => <option key={m} value={m}>{MAINTENANCE_LABEL[m]}</option>)}</select>
          <span className="muted">{total} cameras</span>
        </div>
      </header>

      {writer && (
        <div className="card row wrap" style={{ marginBottom: 16 }}>
          <b>Onboarding</b>
          <label className="btn">Bulk import CSV<input type="file" accept=".csv,text/csv" hidden
            onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) importCsv(f); }} /></label>
          <button className="btn" onClick={() => download("/cameras/template.csv", "cameras_template.csv")}>Template</button>
          <input style={{ minWidth: 260 }} placeholder="catalogue URL (blank = configured)" value={catUrl} onChange={(e) => setCatUrl(e.target.value)} />
          <select value={analytics} onChange={(e) => setAnalytics(e.target.value)} title="Which cameras the analytics worker takes">
            <option value="anpr">analyse: where the catalogue says ANPR</option>
            <option value="all">analyse: all cameras</option>
            <option value="none">analyse: none (view only)</option>
          </select>
          <button className="btn" onClick={dryRun} disabled={busy}>Preview (dry run)</button>
          <button className="btn btn-primary" onClick={sync} disabled={busy}>Sync from catalogue API</button>
          <button className="btn btn-ghost" onClick={() => download("/cameras/export.csv", "cameras.csv")}>Export CSV</button>
          {msg && (
            <span className={msg.error ? "error" : "ok"} role={msg.error ? "alert" : "status"}>
              {msg.error ? msg.error : msg.info ? msg.info : `inserted ${msg.inserted}, updated ${msg.updated}, errors ${msg.errors?.length ?? 0}`}
              {msg.errors?.length > 0 && <details><summary>details</summary><pre>{JSON.stringify(msg.errors, null, 1)}</pre></details>}
            </span>
          )}
        </div>
      )}

      {preview && (
        <div className="card scroll" style={{ marginBottom: 16 }}>
          <div className="row space"><b>Dry run: {preview.rows?.length ?? 0} cameras from {preview.catalogue_url}, nothing written</b>
            <button className="btn btn-ghost" onClick={() => setPreview(null)} aria-label="Close preview">×</button></div>
          <table>
            <thead><tr><th>Code</th><th>Name</th><th>Dept</th><th>District</th><th>Location</th><th>Analyse</th><th>Warnings</th></tr></thead>
            <tbody>{(preview.rows ?? []).map((r: any) => (
              <tr key={r.camera_code}>
                <td className="mono">{r.camera_code}</td><td>{r.name}</td><td>{r.department_code}</td><td>{r.district ?? "—"}</td>
                <td className="small">{r.lat != null ? `${r.lat.toFixed(4)}, ${r.lon.toFixed(4)}` : "—"} <span className="muted">{r.coord_source}</span></td>
                <td>{r.analytics_enabled ? "✓" : "—"}</td>
                <td className="small">{(r.warnings ?? []).map((w: string, i: number) => <div key={i} className="tag tag-warn">{w}</div>)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {writer && <OnboardCard onDone={load} />}

      {editing && <EditCamera camera={editing} onClose={() => setEditing(null)}
        onSaved={(c) => { setEditing(null); setMsg({ info: `${c.camera_code} saved` }); load(); }} />}
      {!writer && msg?.error && <div className="error" role="alert" style={{ marginTop: 16 }}>{msg.error}</div>}
      {loadErr && <div className="error" role="alert" style={{ marginTop: 16 }}>{loadErr}</div>}

      <div className="card scroll" style={{ marginTop: 16 }}>
        <table>
          <thead><tr><th>Code</th><th>Name</th><th>Dept</th><th>District</th><th>Type</th><th>Mode</th><th>Vendor</th><th>Stream</th><th>Retention</th><th>ANPR</th>
            <th title="Analysed by the worker (takes effect when the worker restarts)">Analyse</th><th>Health</th><th>Maintenance</th>
            <th title="Installation year">Installed</th><th title="AMC or warranty expiry: red when past, amber within 90 days">AMC</th><th>Seen</th>
            {writer && <th className="actions"><span className="sr-only">Actions</span></th>}</tr></thead>
          <tbody>{items.map((c) => (
            <tr key={c.camera_code}>
              <td><Link className="mono" to={`/wall?cams=${encodeURIComponent(c.camera_code)}`}>{c.camera_code}</Link></td>
              <td>{c.name}</td><td>{c.department_code}</td><td>{c.district}</td><td>{c.camera_class}</td><td>{c.mode}</td><td>{c.vendor}</td>
              <td>{[c.codec, c.resolution, c.fps ? `${c.fps} fps` : null].filter(Boolean).join(" · ")}</td>
              <td>{c.retention_days ? `${c.retention_days} d / ${c.storage}` : c.storage}</td>
              <td>{c.anpr_viable ? "✓" : "—"}</td>
              <td>{writer
                ? <input type="checkbox" checked={c.analytics_enabled} onChange={() => toggleAnalytics(c)} aria-label={`Analyse ${c.camera_code}`} />
                : c.analytics_enabled ? "✓" : "—"}</td>
              <td><span className="dot" style={{ background: HEALTH_COLOR[c.health] }} /> {c.health}</td>
              <td><span className={`mt mt-${c.maintenance}`} title={c.maintenance_note ?? ""}>{MAINTENANCE_LABEL[c.maintenance] ?? c.maintenance}</span></td>
              <td>{c.install_year ?? <span className="muted">—</span>}</td>
              <td className={dueClass(c.amc_expiry)}>{c.amc_expiry ?? <span className="muted">—</span>}</td>
              <td className="muted small">{ago(c.last_seen_at)}</td>
              {writer && <td className="actions" style={{ whiteSpace: "nowrap" }}>
                <button className="btn btn-ghost small" onClick={() => setEditing(c)}>Edit</button>
                {can("*") && <button className="btn btn-ghost small" onClick={() => remove(c)} title="Delete from the registry (administrator)">Delete</button>}
              </td>}
            </tr>
          ))}
          {loaded && items.length === 0 && !loadErr && (
            <tr><td colSpan={writer ? 17 : 16} className="muted">
              {filtered ? "No cameras match these filters." : "No cameras registered yet. Import a CSV, sync the catalogue or onboard one above."}
            </td></tr>
          )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
