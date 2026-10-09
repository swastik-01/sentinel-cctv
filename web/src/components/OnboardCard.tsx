// Onboard a camera from its stream URL: probe → relay → register, with the result shown
// inline. This is the flow for an unfamiliar feed handed over on the day.
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

type Probe = { ready: boolean; seconds: number; codec: string | null; width: number | null; height: number | null; error?: string };

const EMPTY = {
  camera_code: "", name: "", department_code: "HOME", district: "", lat: "", lon: "",
  source_url: "rtsp://", anpr_viable: false, on_demand: "auto", metadata_only: false,
};

export default function OnboardCard({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState(EMPTY);
  const [depts, setDepts] = useState<{ code: string; name: string }[]>([]);
  const [districts, setDistricts] = useState<string[]>([]);
  const [busy, setBusy] = useState<"" | "probe" | "onboard">("");
  const [probe, setProbe] = useState<Probe | null>(null);
  const [done, setDone] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api("/reports/departments").then((d) => setDepts(d.map((x: any) => ({ code: x.code, name: x.name })))).catch(() => {});
    api("/gis/districts").then((d) => setDistricts(d.map((x: any) => x.district))).catch(() => {});
  }, []);
  const set = (k: keyof typeof EMPTY) => (e: any) =>
    setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const doProbe = async () => {
    setBusy("probe"); setErr(""); setProbe(null); setDone(null);
    try { setProbe(await api("/onboard/probe", { method: "POST", body: { source_url: f.source_url } })); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy("onboard"); setErr(""); setDone(null);
    const t0 = performance.now();
    try {
      if (f.metadata_only) {
        // Model 1 manual entry: register the camera's metadata now, attach a stream later.
        const cam = await api("/cameras", { method: "POST", body: {
          camera_code: f.camera_code, name: f.name, department_code: f.department_code,
          district: f.district || null, anpr_viable: f.anpr_viable,
          lat: f.lat ? Number(f.lat) : null, lon: f.lon ? Number(f.lon) : null,
        } });
        setDone({ camera: cam, outcome: "registered (metadata only)", on_demand: false,
                  wall: ((performance.now() - t0) / 1000).toFixed(1) });
        onDone();
        return;
      }
      const body: any = {
        camera_code: f.camera_code, name: f.name, department_code: f.department_code,
        district: f.district || null, source_url: f.source_url, anpr_viable: f.anpr_viable,
        lat: f.lat ? Number(f.lat) : null, lon: f.lon ? Number(f.lon) : null,
      };
      if (f.on_demand !== "auto") body.on_demand = f.on_demand === "yes";
      const r = await api("/onboard/stream", { method: "POST", body });
      setDone({ ...r, wall: ((performance.now() - t0) / 1000).toFixed(1) });
      setProbe(r.probe);
      onDone();
    } catch (ex: any) {
      setErr(ex.message);
    } finally { setBusy(""); }
  };

  // The stream URL usually carries the camera's password: hidden by default, so pasting it on a projected
  // screen shows nothing; "show" reveals it to check a typo.
  const [showUrl, setShowUrl] = useState(false);
  return (
    <form className="card onboard" onSubmit={submit}>
      <div className="row space">
        <h2>Add camera by stream URL</h2>
        <span className="muted small">bulk CSV · manual entry · API — probe → relay → register, credentials never leave the server</span>
      </div>
      <div className="onboard-grid">
        <label className="span2">Stream URL{f.metadata_only
          ? <input className="mono" value="" placeholder="not needed — registering metadata only" disabled />
          : <span className="row"><input className="mono" type={showUrl ? "text" : "password"} autoComplete="off" value={f.source_url} onChange={set("source_url")} placeholder="rtsp://user:pass@10.0.0.5:554/Streaming/Channels/101" required style={{ flex: 1 }} />
              <button type="button" className="btn btn-ghost small" onClick={() => setShowUrl(!showUrl)} title="The URL carries the camera's password; it is hidden while a screen is projected">{showUrl ? "hide" : "show"}</button></span>}</label>
        <label>Camera code<input className="mono" value={f.camera_code} onChange={(e) => setF({ ...f, camera_code: e.target.value.toUpperCase() })} placeholder="GNR-POL-120" required /></label>
        <label>Name<input value={f.name} onChange={set("name")} placeholder="Sector 11 junction, north arm" required /></label>
        <label>Department<select value={f.department_code} onChange={set("department_code")}>{depts.map((d) => <option key={d.code} value={d.code}>{d.code} · {d.name}</option>)}</select></label>
        <label>District<input list="districts" value={f.district} onChange={set("district")} /><datalist id="districts">{districts.map((d) => <option key={d} value={d} />)}</datalist></label>
        <label>Latitude<input value={f.lat} onChange={set("lat")} placeholder="23.2156" /></label>
        <label>Longitude<input value={f.lon} onChange={set("lon")} placeholder="72.6369" /></label>
        <label>Upstream connection<select value={f.on_demand} onChange={set("on_demand")}>
          <option value="auto">auto (always-on if ANPR)</option><option value="no">always on</option><option value="yes">only while watched</option>
        </select></label>
        <label className="check"><input type="checkbox" checked={f.anpr_viable} onChange={set("anpr_viable")} /> ANPR-viable (plates legible) — enables analytics</label>
        <label className="check"><input type="checkbox" checked={f.metadata_only} onChange={set("metadata_only")} /> manual entry: register metadata only, no stream yet</label>
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button type="button" className="btn" onClick={doProbe} disabled={!!busy || f.metadata_only || f.source_url.length < 10}>{busy === "probe" ? "Probing…" : "Probe only"}</button>
        <button className="btn btn-primary" disabled={!!busy}>{busy === "onboard" ? "Saving…" : f.metadata_only ? "Register camera" : "Probe & onboard"}</button>
        {probe && (probe.ready
          ? <span className="ok">● reachable · {probe.codec} {probe.width ? `${probe.width}×${probe.height}` : ""} · {probe.seconds}s</span>
          : <span className="error">{probe.error}</span>)}
        {err && <span className="error">{err}</span>}
      </div>
      {done && (
        <div className="row" style={{ marginTop: 8 }}>
          <span className="ok">✓ {done.camera.camera_code} {done.outcome} in {done.wall}s{done.probe ? ` · ${done.on_demand ? "on-demand relay" : "always-on relay"}` : ""}{done.camera.analytics_enabled ? " · analytics on" : ""}</span>
          <Link className="btn" to={`/wall?cams=${done.camera.camera_code}`}>View live</Link>
          <Link className="btn btn-ghost" to="/map">On map</Link>
          <button type="button" className="btn btn-ghost" onClick={() => { setF(EMPTY); setDone(null); setProbe(null); }}>Add another</button>
        </div>
      )}
    </form>
  );
}
