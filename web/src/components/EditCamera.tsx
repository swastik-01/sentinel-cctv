// Edit a registered camera's metadata (Model 1: maintaining the registry), its maintenance state, installation
// year and AMC or warranty expiry included. Only changed fields are sent; the API's own message is shown on refusal.
import { FormEvent, useEffect, useRef, useState } from "react";
import { api, Camera, CAMERA_CLASSES, Maintenance, MAINTENANCE_LABEL } from "../api";

type Form = {
  name: string; district: string; lat: string; lon: string; camera_class: string; vendor: string; model: string;
  retention_days: string; storage: string; maintenance: Maintenance; maintenance_note: string;
  install_year: string; amc_expiry: string; anpr_viable: boolean;
};

const s = (v: unknown) => (v == null ? "" : String(v));
const formOf = (c: Camera): Form => ({
  name: c.name, district: s(c.district), lat: s(c.lat), lon: s(c.lon), camera_class: c.camera_class,
  vendor: s(c.vendor), model: s(c.model), retention_days: s(c.retention_days), storage: c.storage,
  maintenance: c.maintenance ?? "in_service", maintenance_note: s(c.maintenance_note),
  install_year: s(c.install_year), amc_expiry: s(c.amc_expiry), anpr_viable: c.anpr_viable,
});

/** The fields that changed, typed for the API; a message instead when a value cannot be sent. */
function changes(before: Form, f: Form): Record<string, any> | string {
  const out: Record<string, any> = {};
  const num = (k: keyof Form, lo: number, hi: number, label: string): string | null => {
    if (f[k] === before[k]) return null;
    const v = String(f[k]).trim();
    if (v === "") { out[k] = null; return null; }
    const n = Number(v);
    if (!Number.isFinite(n) || n < lo || n > hi) return `${label} must be a number from ${lo} to ${hi}`;
    out[k] = k === "lat" || k === "lon" ? n : Math.round(n);
    return null;
  };
  if (!f.name.trim()) return "Name is required";
  const err = num("lat", -90, 90, "Latitude") ?? num("lon", -180, 180, "Longitude")
    ?? num("retention_days", 0, 3650, "Retention (days)") ?? num("install_year", 1990, 2100, "Installation year");
  if (err) return err;
  if ((f.lat.trim() === "") !== (f.lon.trim() === "")) return "Give both latitude and longitude, or neither";
  for (const k of ["name", "district", "camera_class", "vendor", "model", "storage", "maintenance",
    "maintenance_note", "amc_expiry", "anpr_viable"] as (keyof Form)[]) {
    if (f[k] !== before[k]) out[k] = typeof f[k] === "string" ? (String(f[k]).trim() || null) : f[k];
  }
  if (out.name === null) delete out.name;
  return out;
}

export default function EditCamera({ camera, onClose, onSaved }: {
  camera: Camera; onClose: () => void; onSaved: (c: Camera) => void;
}) {
  const before = useRef(formOf(camera)).current;
  const [f, setF] = useState<Form>(before);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [districts, setDistricts] = useState<string[]>([]);
  const first = useRef<HTMLInputElement>(null);

  useEffect(() => {
    first.current?.focus();
    api("/gis/districts").then((d) => setDistricts(d.map((x: any) => x.district))).catch(() => {});
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  const set = (k: keyof Form) => (e: any) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const save = async (e: FormEvent) => {
    e.preventDefault();
    const body = changes(before, f);
    if (typeof body === "string") { setErr(body); return; }
    if (Object.keys(body).length === 0) { onClose(); return; }
    setBusy(true); setErr("");
    try { onSaved(await api(`/cameras/${encodeURIComponent(camera.camera_code)}`, { method: "PATCH", body })); }
    catch (ex: any) { setErr(ex.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="modal" onSubmit={save} role="dialog" aria-modal="true" aria-labelledby="edit-cam-title">
        <div className="row space">
          <h2 id="edit-cam-title" style={{ margin: 0 }}>Edit camera <span className="mono">{camera.camera_code}</span></h2>
          <button type="button" className="btn btn-ghost" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="modal-grid">
          <label className="span3">Name<input ref={first} value={f.name} onChange={set("name")} maxLength={200} required /></label>
          <label>District<input list="edit-districts" value={f.district} onChange={set("district")} maxLength={100} />
            <datalist id="edit-districts">{districts.map((d) => <option key={d} value={d} />)}</datalist></label>
          <label>Latitude<input value={f.lat} onChange={set("lat")} inputMode="decimal" placeholder="23.2156" /></label>
          <label>Longitude<input value={f.lon} onChange={set("lon")} inputMode="decimal" placeholder="72.6369" /></label>
          <label>Camera type<select value={f.camera_class} onChange={set("camera_class")}>
            {CAMERA_CLASSES.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
          <label>Vendor<input value={f.vendor} onChange={set("vendor")} maxLength={100} /></label>
          <label>Model<input value={f.model} onChange={set("model")} maxLength={100} /></label>
          <label>Recorder retention (days)<input value={f.retention_days} onChange={set("retention_days")} inputMode="numeric" /></label>
          <label>Storage<select value={f.storage} onChange={set("storage")}>
            {["local", "cloud", "hybrid", "unknown"].map((x) => <option key={x}>{x}</option>)}</select></label>
          <label className="check" style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <input type="checkbox" checked={f.anpr_viable} onChange={set("anpr_viable")} /> ANPR-viable</label>
          <label>Maintenance<select value={f.maintenance} onChange={set("maintenance")}>
            {(Object.keys(MAINTENANCE_LABEL) as Maintenance[]).map((m) => <option key={m} value={m}>{MAINTENANCE_LABEL[m]}</option>)}</select></label>
          <label>Installation year<input value={f.install_year} onChange={set("install_year")} inputMode="numeric" placeholder="2019" /></label>
          <label>AMC / warranty expiry<input type="date" value={f.amc_expiry} onChange={set("amc_expiry")} /></label>
          <label className="span3">Maintenance note<input value={f.maintenance_note} onChange={set("maintenance_note")} maxLength={500} placeholder="e.g. lens replaced 12 Sep; vendor ticket 4471" /></label>
        </div>
        <div className="row">
          <button className="btn btn-primary" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
          {err && <span className="error" role="alert">{err}</span>}
        </div>
      </form>
    </div>
  );
}
