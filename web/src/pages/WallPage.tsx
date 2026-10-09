import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, Camera, can, HEALTH_COLOR } from "../api";
import WhepPlayer from "../components/WhepPlayer";
import ZoneEditor, { Zone, ZoneShapes } from "../components/ZoneEditor";
import { useEvents } from "../events";

const KEY = "sentinel.wall";

export default function WallPage() {
  const [params] = useSearchParams();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [grid, setGrid] = useState<number>(() => Number(localStorage.getItem(KEY + ".grid")) || 3);
  const [picked, setPicked] = useState<string[]>(() => {
    const fromUrl = params.get("cams")?.split(",").filter(Boolean);
    if (fromUrl?.length) return fromUrl;
    try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
  });
  const [dept, setDept] = useState("");
  const [showPicker, setShowPicker] = useState(true);
  const [editing, setEditing] = useState<Camera | null>(null);
  const [hot, setHot] = useState<Record<string, boolean>>({});     // cameras with a live intrusion

  useEffect(() => { api("/cameras?limit=2000").then((r) => setCameras(r.items)).catch(() => {}); }, []);
  useEffect(() => { localStorage.setItem(KEY, JSON.stringify(picked)); }, [picked]);
  useEffect(() => { localStorage.setItem(KEY + ".grid", String(grid)); }, [grid]);
  useEvents((e) => {
    if (e.type === "camera.health") setCameras((cs) => cs.map((c) => c.camera_code === e.camera_code ? { ...c, health: e.to } : c));
    if (e.type === "alert.new" && e.alert?.alert_type === "intrusion") {
      const code = e.alert.camera_code;
      setHot((h) => ({ ...h, [code]: true }));
      window.setTimeout(() => setHot((h) => ({ ...h, [code]: false })), 15000);
    }
  });
  const zonesOf = (c: Camera): Zone[] => c.tags?.zones ?? [];

  const max = grid * grid;
  const depts = useMemo(() => [...new Set(cameras.map((c) => c.department_code))].sort(), [cameras]);
  const tiles = picked.slice(0, max).map((code) => cameras.find((c) => c.camera_code === code)).filter(Boolean) as Camera[];
  const toggle = (code: string) => setPicked((p) => p.includes(code) ? p.filter((x) => x !== code) : [...p, code].slice(-max));
  const autoFill = () => setPicked(cameras.filter((c) => c.health === "online" && (!dept || c.department_code === dept)).slice(0, max).map((c) => c.camera_code));

  return (
    <div className="page page-wall">
      <header className="page-head">
        <h1>Video wall</h1>
        <div className="filters">
          <span className="muted">Grid</span>
          {[2, 3, 4].map((g) => <button key={g} className={`btn ${grid === g ? "btn-primary" : ""}`} onClick={() => setGrid(g)}>{g}×{g}</button>)}
          <select value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">All departments</option>
            {depts.map((d) => <option key={d}>{d}</option>)}
          </select>
          <button className="btn" onClick={autoFill}>Fill with online</button>
          <button className="btn btn-ghost" onClick={() => setPicked([])}>Clear</button>
          <button className="btn btn-ghost" onClick={() => setShowPicker((s) => !s)}>{showPicker ? "Hide" : "Show"} picker</button>
          <span className="muted">{tiles.length}/{max}</span>
        </div>
      </header>

      <div className={`wall-layout ${showPicker ? "" : "full"}`}>
        <div className="wall-grid" style={{ gridTemplateColumns: `repeat(${grid}, 1fr)` }}>
          {tiles.map((c) => (
            <div className={`tile${hot[c.camera_code] ? " tile-hot" : ""}`} key={c.camera_code}>
              <div className="tile-head">
                <span className="mono">{c.camera_code}</span>
                <span className="muted small">{c.name}</span>
                <span className="muted small">{c.codec} · {c.resolution}</span>
                {can("cameras.write") && <button className="btn btn-ghost small" onClick={() => setEditing(c)}
                  title="Draw intrusion zones on this camera">zones{zonesOf(c).length ? ` (${zonesOf(c).length})` : ""}</button>}
                <span className="dot" style={{ background: HEALTH_COLOR[c.health] }} />
              </div>
              <WhepPlayer whep={c.whep_url} hls={c.hls_url} codec={c.codec}
                overlay={zonesOf(c).length ? <ZoneShapes zones={zonesOf(c)} hot={hot[c.camera_code]} /> : undefined} />
            </div>
          ))}
          {tiles.length === 0 && <div className="muted" style={{ padding: 24 }}>Pick cameras on the right, or “Fill with online”.</div>}
        </div>
        {showPicker && (
          <aside className="card picker">
            <h2>Cameras</h2>
            <ul>
              {cameras.filter((c) => !dept || c.department_code === dept).map((c) => (
                <li key={c.camera_code} className={picked.includes(c.camera_code) ? "on" : ""} onClick={() => toggle(c.camera_code)}>
                  <span className="dot" style={{ background: HEALTH_COLOR[c.health] }} />
                  <span className="mono">{c.camera_code}</span>
                  <span className="muted small">{c.department_code} · {c.codec}</span>
                </li>
              ))}
            </ul>
          </aside>
        )}
      </div>
      {editing && <ZoneEditor camera={editing} onClose={(saved) => {
        if (saved) setCameras((cs) => cs.map((c) => c.camera_code === editing.camera_code ? { ...c, tags: { ...c.tags, zones: saved } } : c));
        setEditing(null);
      }} />}
    </div>
  );
}
