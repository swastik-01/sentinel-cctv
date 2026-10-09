import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ago, api, CAMERA_CLASSES, CATALOGUE, can, dueClass, HEALTH_COLOR, Maintenance, MAINTENANCE_LABEL, simulatorCameras } from "../api";
import CameraMap, { MapCamera, MapCluster, MapView } from "../components/CameraMap";

// Above this many cameras the map stops loading the whole registry: clusters until zoomed in,
// then only the cameras in view (at 80,000 cameras a single GeoJSON is 45 MB: bench/results/core_scale.md).
const LARGE_FLEET = 2000;
const CAMERA_ZOOM = 12;
import WhepPlayer from "../components/WhepPlayer";
import { useEvents } from "../events";

type Feature = { properties: MapCamera & { whep_url: string | null; hls_url: string | null; resolution: string | null;
  vendor: string | null; mode: string; last_seen_at: string | null; department: string; retention_days: number | null;
  camera_class: string; maintenance: Maintenance; install_year: number | null; amc_expiry: string | null };
  geometry: { coordinates: [number, number] } };

export default function MapPage() {
  const [features, setFeatures] = useState<Feature[]>([]);
  const [districts, setDistricts] = useState<any[]>([]);
  const [showDistricts, setShowDistricts] = useState(false);
  const [dept, setDept] = useState("");
  const [health, setHealth] = useState("");
  const [anpr, setAnpr] = useState("");
  const [cls, setCls] = useState("");
  const [maint, setMaint] = useState("");
  const [loadErr, setLoadErr] = useState("");
  const [sim, setSim] = useState<Set<string>>(new Set());
  useEffect(() => { simulatorCameras().then(setSim); }, []);
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("camera"));
  const [large, setLarge] = useState<boolean | null>(null);     // null until the fleet size is known
  const [clusters, setClusters] = useState<MapCluster[]>([]);
  const [total, setTotal] = useState(0);
  const [view, setView] = useState<MapView | null>(null);

  const load = () => {
    api("/gis/clusters?zoom=5").then((c) => {
      setTotal(c.total);
      const big = c.total > LARGE_FLEET;
      setLarge(big);
      if (!big) api("/gis/cameras.geojson").then((g) => { setFeatures(g.features); setLoadErr(""); })
        .catch((e) => setLoadErr(`Could not load the cameras: ${e.message}`));
    }).catch((e) => { setLarge(false); setLoadErr(`Could not load the cameras: ${e.message}`); });
    api("/gis/districts").then(setDistricts).catch(() => {});
  };
  useEffect(load, []);
  useEvents((e) => { if (e.type === "camera.health" && large === false) load(); });

  // Large fleet: what is drawn follows the view.
  useEffect(() => {
    if (!large || !view) return;
    const f = new URLSearchParams({ bbox: view.bbox });
    if (dept) f.set("department", dept);
    if (health) f.set("health", health);
    if (anpr) f.set("anpr", anpr);
    if (cls) f.set("camera_class", cls);
    if (maint) f.set("maintenance", maint);
    if (view.zoom < CAMERA_ZOOM) {
      api(`/gis/clusters?zoom=${view.zoom}&${f}`).then((c) => { setClusters(c.clusters); setFeatures([]); }).catch(() => {});
    } else {
      api(`/gis/cameras.geojson?limit=3000&${f}`).then((g) => { setFeatures(g.features); setClusters([]); }).catch(() => {});
    }
  }, [large, view, dept, health, anpr, cls, maint]);

  const cameras: MapCamera[] = useMemo(() => features
    .filter((f) => (!dept || f.properties.department_code === dept)
      && (!health || f.properties.health === health)
      && (!anpr || String(f.properties.anpr_viable) === anpr)
      && (!cls || f.properties.camera_class === cls)
      && (!maint || f.properties.maintenance === maint))
    .map((f) => ({ ...f.properties, lat: f.geometry.coordinates[1], lon: f.geometry.coordinates[0] })),
    [features, dept, health, anpr, cls, maint]);
  const [allDepts, setAllDepts] = useState<string[]>([]);
  useEffect(() => { if (large) api("/reports/departments").then((ds) => setAllDepts(ds.filter((d: any) => d.cameras > 0).map((d: any) => d.code))).catch(() => {}); }, [large]);
  const depts = useMemo(() => large ? allDepts : [...new Set(features.map((f) => f.properties.department_code))].sort(), [features, large, allDepts]);
  const sel = features.find((f) => f.properties.camera_code === selected)?.properties;

  const simulateOutage = async (code: string) => {
    try {
      const r = await fetch(`${CATALOGUE}/admin/outage/${encodeURIComponent(code)}?seconds=60`, { method: "POST" });
      if (!r.ok) throw new Error(`the simulator refused (${r.status})`);
    } catch (e: any) {
      setLoadErr(`Simulator outage failed: ${e instanceof TypeError ? "the feed simulator is not answering" : e.message}`);
    }
  };

  return (
    <div className="page page-map">
      <header className="page-head">
        <h1>Camera map</h1>
        <div className="filters">
          <select value={dept} onChange={(e) => setDept(e.target.value)}>
            <option value="">All departments</option>
            {depts.map((d) => <option key={d}>{d}</option>)}
          </select>
          <select value={health} onChange={(e) => setHealth(e.target.value)}>
            <option value="">Any health</option>
            {Object.keys(HEALTH_COLOR).map((h) => <option key={h}>{h}</option>)}
          </select>
          <select value={anpr} onChange={(e) => setAnpr(e.target.value)}>
            <option value="">ANPR: any</option><option value="true">ANPR-viable</option><option value="false">Not viable</option>
          </select>
          <select value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Camera type">
            <option value="">Any type</option>{CAMERA_CLASSES.map((c) => <option key={c}>{c}</option>)}
          </select>
          <select value={maint} onChange={(e) => setMaint(e.target.value)} aria-label="Maintenance">
            <option value="">Any maintenance</option>
            {(Object.keys(MAINTENANCE_LABEL) as Maintenance[]).map((m) => <option key={m} value={m}>{MAINTENANCE_LABEL[m]}</option>)}
          </select>
          <label className="check"><input type="checkbox" checked={showDistricts} onChange={(e) => setShowDistricts(e.target.checked)} /> district coverage</label>
          <span className="muted">{large ? `${total.toLocaleString()} registered · ${view && view.zoom >= CAMERA_ZOOM ? `${cameras.length} in view` : "clustered: zoom in for cameras"}` : `${cameras.length} shown`}</span>
        </div>
      </header>

      {loadErr && <div className="error" role="alert" style={{ marginBottom: 8 }}>{loadErr}</div>}
      <div className="map-layout">
        <div className="map-box">
          <CameraMap cameras={cameras} selected={selected} onSelect={(c) => setSelected(c.camera_code)}
            districts={showDistricts ? districts : undefined} fit={large === false}
            clusters={large ? clusters : undefined} onView={large ? setView : undefined} />
        </div>
        <aside className="card side">
          {!sel ? (
            <div className="muted">Click a camera. Colour = health: {Object.entries(HEALTH_COLOR).map(([k, v]) => (
              <span key={k} style={{ color: v, marginLeft: 8 }}>● {k}</span>))}</div>
          ) : (
            <>
              <div className="side-head">
                <div>
                  <div className="mono big">{sel.camera_code}</div>
                  <div>{sel.name}</div>
                  <div className="muted small">{sel.department} · {sel.district}</div>
                </div>
                <span className="badge" style={{ background: HEALTH_COLOR[sel.health] }}>{sel.health}</span>
              </div>
              <WhepPlayer whep={sel.whep_url} hls={sel.hls_url} codec={sel.codec} />
              <dl className="kv">
                <dt>Type</dt><dd>{sel.camera_class}</dd>
                <dt>Stream</dt><dd>{sel.codec || "?"} · {sel.resolution || "?"} · {sel.mode}</dd>
                <dt>Vendor</dt><dd>{sel.vendor || "—"}</dd>
                <dt>Retention</dt><dd>{sel.retention_days ? `${sel.retention_days} days` : "—"}</dd>
                <dt>ANPR</dt><dd>{sel.anpr_viable ? "viable" : "not viable (wide angle)"}</dd>
                <dt>Maintenance</dt><dd><span className={`mt mt-${sel.maintenance}`}>{MAINTENANCE_LABEL[sel.maintenance] ?? sel.maintenance}</span></dd>
                <dt>Installed</dt><dd>{sel.install_year ?? "—"}</dd>
                <dt>AMC expiry</dt><dd className={dueClass(sel.amc_expiry)}>{sel.amc_expiry ?? "—"}</dd>
                <dt>Last seen</dt><dd>{ago(sel.last_seen_at)}</dd>
              </dl>
              <div className="row">
                <Link className="btn" to={`/wall?cams=${sel.camera_code}`}>Open in wall</Link>
                <Link className="btn" to={`/search?camera=${sel.camera_code}`}>Sightings</Link>
                {can("cameras.write") && sim.has(sel.camera_code) && <button className="btn btn-ghost" onClick={() => simulateOutage(sel.camera_code)} title="Feed simulator: take this camera down for 60 s">Simulator: outage</button>}
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
