// Draw intrusion zones on a camera's live picture: click to place corners, name the zone,
// choose what triggers it and when it is armed. Points are stored as fractions of the frame.
import { MouseEvent, useEffect, useState } from "react";
import { api, Camera } from "../api";
import WhepPlayer from "./WhepPlayer";

export type Zone = {
  id: string; name: string; polygon: [number, number][]; classes: string[];
  min_dwell_s: number; armed?: { from: string; to: string }; severity: string;
};

const CLASSES = ["person", "car", "motorcycle", "bicycle", "bus", "truck"];
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 32) || "zone";

export function ZoneShapes({ zones, draft, hot }: { zones: Zone[]; draft?: [number, number][]; hot?: boolean }) {
  return (
    <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="zone-svg">
      {zones.map((z) => (
        <g key={z.id}>
          <polygon points={z.polygon.map((p) => p.join(",")).join(" ")} className={`zone-poly${hot ? " hot" : ""}`} />
          <text x={z.polygon[0][0]} y={z.polygon[0][1]} className="zone-label">{z.name}</text>
        </g>
      ))}
      {draft && draft.length > 0 && <polyline points={draft.map((p) => p.join(",")).join(" ")} className="zone-draft" />}
      {draft?.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={0.008} className="zone-dot" />)}
    </svg>
  );
}

export default function ZoneEditor({ camera, onClose }: { camera: Camera; onClose: (saved?: Zone[]) => void }) {
  const [zones, setZones] = useState<Zone[]>([]);
  const [draft, setDraft] = useState<[number, number][]>([]);
  const [form, setForm] = useState({ name: "", classes: ["person"], min_dwell_s: 3, from: "", to: "", severity: "high" });
  const [msg, setMsg] = useState("");

  useEffect(() => { api(`/cameras/${camera.camera_code}/zones`).then(setZones).catch((e) => setMsg(e.message)); }, [camera.camera_code]);

  const click = (e: MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const p: [number, number] = [+((e.clientX - r.left) / r.width).toFixed(4), +((e.clientY - r.top) / r.height).toFixed(4)];
    setDraft((d) => [...d, p]);
  };
  const finish = () => {
    if (draft.length < 3 || !form.name.trim()) { setMsg("A zone needs a name and at least 3 corners."); return; }
    let id = slug(form.name); while (zones.some((z) => z.id === id)) id = `${id}-2`;
    setZones([...zones, {
      id, name: form.name.trim(), polygon: draft, classes: form.classes, min_dwell_s: form.min_dwell_s,
      severity: form.severity, ...(form.from && form.to ? { armed: { from: form.from, to: form.to } } : {}),
    }]);
    setDraft([]); setForm({ ...form, name: "" }); setMsg("");
  };
  const save = async () => {
    try { const saved = await api(`/cameras/${camera.camera_code}/zones`, { method: "PUT", body: zones }); onClose(saved); }
    catch (e: any) { setMsg(e.message); }
  };

  return (
    <div className="modal-back" onClick={() => onClose()}>
      <div className="modal card" onClick={(e) => e.stopPropagation()}>
        <div className="row space"><h2>Intrusion zones · <span className="mono">{camera.camera_code}</span> {camera.name}</h2>
          <button className="btn btn-ghost" onClick={() => onClose()}>×</button></div>
        <p className="muted small">Click on the picture to place the corners of an area. A person (or vehicle) whose feet
          (wheels) stay inside it for the dwell time, while it is armed, raises an alert. The alert records the zone, how many
          and for how long; no image of the person is stored.</p>
        <WhepPlayer whep={camera.whep_url} hls={camera.hls_url} codec={camera.codec}
          overlay={<div className="zone-click" onClick={click}><ZoneShapes zones={zones} draft={draft} /></div>} />
        <div className="row wrap" style={{ marginTop: 10 }}>
          <input placeholder="zone name, e.g. Depot gate" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          {CLASSES.map((c) => (
            <label key={c} className="check"><input type="checkbox" checked={form.classes.includes(c)}
              onChange={(e) => setForm({ ...form, classes: e.target.checked ? [...form.classes, c] : form.classes.filter((x) => x !== c) })} /> {c}</label>
          ))}
          <label className="inline">dwell <input type="number" min={1} max={600} style={{ width: 60 }} value={form.min_dwell_s}
            onChange={(e) => setForm({ ...form, min_dwell_s: Number(e.target.value) })} /> s</label>
          <label className="inline">armed <input type="time" value={form.from} onChange={(e) => setForm({ ...form, from: e.target.value })} />
            – <input type="time" value={form.to} onChange={(e) => setForm({ ...form, to: e.target.value })} /> IST</label>
          <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
            {["low", "medium", "high", "critical"].map((s) => <option key={s}>{s}</option>)}</select>
          <button className="btn" onClick={() => setDraft(draft.slice(0, -1))} disabled={!draft.length}>Undo corner</button>
          <button className="btn btn-primary" onClick={finish} disabled={draft.length < 3}>Add zone</button>
        </div>
        <ul className="zone-list">
          {zones.map((z) => (
            <li key={z.id}><b>{z.name}</b> <span className="muted small">{z.classes.join(", ")} · ≥{z.min_dwell_s}s ·
              {z.armed ? ` armed ${z.armed.from}–${z.armed.to}` : " always armed"} · {z.severity}</span>
              <button className="btn btn-ghost small" onClick={() => setZones(zones.filter((x) => x.id !== z.id))}>remove</button></li>
          ))}
          {!zones.length && <li className="muted small">No zones on this camera.</li>}
        </ul>
        {msg && <div className="error">{msg}</div>}
        <div className="row"><button className="btn btn-primary" onClick={save}>Save zones</button>
          <span className="muted small">The analytics worker picks up zone changes when it restarts.</span></div>
      </div>
    </div>
  );
}
