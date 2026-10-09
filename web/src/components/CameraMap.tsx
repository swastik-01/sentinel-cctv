import L from "leaflet";
import { useEffect } from "react";
import { CircleMarker, GeoJSON, MapContainer, Marker, Popup, TileLayer, Tooltip, useMap, useMapEvents } from "react-leaflet";
import { HEALTH_COLOR } from "../api";

export type MapCamera = {
  camera_code: string; name: string; lat: number | null; lon: number | null; health: string;
  department_code?: string; codec?: string | null; anpr_viable?: boolean; district?: string | null;
};

const GUJARAT: [number, number] = [22.6, 71.8];

export type MapStop = { key: string; n: number; lat: number; lon: number; label: string; warn?: boolean };
export type MapCluster = { lat: number; lon: number; cameras: number; online: number; offline: number; anpr: number };
export type MapView = { zoom: number; bbox: string };   // bbox: minLon,minLat,maxLon,maxLat

function ViewWatch({ onView }: { onView: (v: MapView) => void }) {
  const report = (m: L.Map) => {
    const b = m.getBounds();
    onView({ zoom: m.getZoom(), bbox: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((x) => x.toFixed(4)).join(",") });
  };
  const map = useMapEvents({ moveend: () => report(map) });
  useEffect(() => { report(map); }, []); // eslint-disable-line
  return null;
}

// A statewide fleet is drawn as counts per grid cell until zoomed in (routers/gis.py /clusters).
const clusterIcon = (c: MapCluster) => L.divIcon({
  className: "", iconSize: [0, 0],
  html: `<div class="cluster-pin${c.offline / c.cameras > 0.1 ? " warn" : ""}">${c.cameras >= 1000 ? `${(c.cameras / 1000).toFixed(1)}k` : c.cameras}</div>`,
});

// Numbered journey stops: several stops at one camera share a marker, numbers joined ("1·4").
const stopIcon = (text: string, warn?: boolean) => L.divIcon({
  className: "", iconSize: [0, 0],
  html: `<div class="stop-pin${warn ? " warn" : ""}">${text}</div>`,
});

function FitTo({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    if (points.length === 1) { map.setView(points[0], 13); return; }
    map.fitBounds(L.latLngBounds(points), { padding: [30, 30], maxZoom: 14 });
  }, [points.map((p) => p.join(",")).join("|")]); // eslint-disable-line
  return null;
}

export default function CameraMap({ cameras, selected, onSelect, route, districts, stops, clusters, onView, fit = true, height = "100%" }: {
  cameras: MapCamera[];
  selected?: string | null;
  onSelect?: (c: MapCamera) => void;
  route?: any;                       // GeoJSON Feature (LineString / MultiPoint)
  districts?: { district: string; lat: number | null; lon: number | null; total_cameras: number;
                online_cameras: number; anpr_cameras: number }[];
  stops?: MapStop[];
  clusters?: MapCluster[];
  onView?: (v: MapView) => void;
  fit?: boolean;
  height?: string;
}) {
  const byPlace = new Map<string, MapStop[]>();
  stops?.forEach((s) => byPlace.set(`${s.lat},${s.lon}`, [...(byPlace.get(`${s.lat},${s.lon}`) ?? []), s]));
  const pts = cameras.filter((c) => c.lat != null && c.lon != null).map((c) => [c.lat!, c.lon!] as [number, number]);
  return (
    <MapContainer center={GUJARAT} zoom={7} style={{ height, width: "100%" }} preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        className="dark-tiles"
      />
      {fit && <FitTo points={pts} />}
      {onView && <ViewWatch onView={onView} />}
      {clusters?.map((c, i) => (
        <Marker key={`c${i}-${c.lat}`} position={[c.lat, c.lon]} icon={clusterIcon(c)}>
          <Tooltip direction="top">{c.cameras} cameras · {c.online} online · {c.offline} offline · {c.anpr} ANPR<br />zoom in for cameras</Tooltip>
        </Marker>
      ))}
      {districts?.map((d) => d.lat != null && (
        <CircleMarker key={d.district} center={[d.lat, d.lon!]}
          radius={Math.max(8, Math.min(40, 6 + Math.sqrt(d.total_cameras) * 6))}
          pathOptions={{ color: d.total_cameras ? "#38bdf8" : "#ef4444", fillOpacity: 0.12, weight: 1 }}>
          <Tooltip direction="top">
            <b>{d.district}</b><br />
            {d.total_cameras} cameras · {d.online_cameras} online · {d.anpr_cameras} ANPR
          </Tooltip>
        </CircleMarker>
      ))}
      {route?.geometry?.coordinates?.length > 0 && (
        <GeoJSON key={JSON.stringify(route.geometry).slice(0, 80)} data={route}
          style={{ color: "#f97316", weight: 4, opacity: 0.9, dashArray: "8 6" }} />
      )}
      {[...byPlace.values()].map((ss) => (
        <Marker key={ss[0].key} position={[ss[0].lat, ss[0].lon]} zIndexOffset={1000}
          icon={stopIcon(ss.length > 4 ? `${ss[0].n}·${ss[1].n}·…·${ss[ss.length - 1].n} (${ss.length})` : ss.map((s) => s.n).join("·"),
                         ss.some((s) => s.warn))}>
          <Tooltip direction="top" offset={[0, -14]}>{ss.slice(0, 8).map((s) => <div key={s.key}>{s.label}</div>)}
            {ss.length > 8 && <div>… {ss.length - 8} more stops here</div>}</Tooltip>
        </Marker>
      ))}
      {cameras.map((c) => c.lat != null && c.lon != null && (
        <CircleMarker key={c.camera_code} center={[c.lat, c.lon]}
          radius={selected === c.camera_code ? 11 : 7}
          pathOptions={{
            color: selected === c.camera_code ? "#fff" : HEALTH_COLOR[c.health] || "#64748b",
            fillColor: HEALTH_COLOR[c.health] || "#64748b", fillOpacity: 0.9,
            weight: selected === c.camera_code ? 3 : 1.5,
          }}
          eventHandlers={{ click: () => onSelect?.(c) }}>
          <Popup>
            <div className="popup">
              <b>{c.camera_code}</b><br />{c.name}<br />
              <span className="muted">{c.department_code} · {c.codec || "?"} · {c.anpr_viable ? "ANPR" : "no ANPR"}</span><br />
              <span style={{ color: HEALTH_COLOR[c.health] }}>● {c.health}</span>
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
