// New alerts surface on every page, not only on the Alerts page: a card in the corner, and a
// short chime for high and critical ones. An operator watching the wall still sees the hit.
import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert, CHECK_CROP, fmtTs, SEV_COLOR } from "../api";
import { useEvents } from "../events";

const SHOW_MS = 15000;

function chime() {
  try {
    const ctx = new AudioContext();
    [0, 0.18].forEach((t) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = 880; g.gain.value = 0.08;
      o.connect(g).connect(ctx.destination);
      o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.12);
    });
  } catch { /* audio blocked until the user interacts with the page: the card still shows */ }
}

export default function AlertToast() {
  const [items, setItems] = useState<Alert[]>([]);
  useEvents((e) => {
    if (e.type !== "alert.new") return;
    const a = e.alert as Alert;
    setItems((xs) => [a, ...xs].slice(0, 3));
    if (a.severity === "high" || a.severity === "critical") chime();
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== a.id)), SHOW_MS);
  });
  if (!items.length) return null;
  return (
    <div className="toasts">
      {items.map((a) => (
        <div key={a.id} className="toast" style={{ borderLeftColor: SEV_COLOR[a.severity] }}>
          <div className="row">
            <span className="badge" style={{ background: SEV_COLOR[a.severity] }}>{a.severity}</span>
            {a.alert_type === "intrusion"
              ? <><span className="tag tag-alert">intrusion</span><b>{a.detail?.zone_name}</b></>
              : <span className="mono big">{a.plate_norm}</span>}
            {a.retrospective && <span className="tag tag-warn">already seen</span>}
            {a.needs_review && <span className="tag tag-warn" title={CHECK_CROP}>check the crop</span>}
            <button className="btn btn-ghost small" style={{ marginLeft: "auto" }}
                    onClick={() => setItems((xs) => xs.filter((x) => x.id !== a.id))}>×</button>
          </div>
          <div className="small">{a.alert_type === "intrusion" ? `${a.detail?.count} in zone · ` : `${a.kind?.replace("_", " ")} · `}<b>{a.camera_code}</b> {a.camera_name}</div>
          <div className="muted small">seen {fmtTs(a.sighting_ts)}</div>
          <div className="row">
            <Link className="btn small btn-primary" to="/alerts">Open alerts</Link>
            {a.alert_type === "intrusion"
              ? <Link className="btn small" to={`/wall?cams=${a.camera_code}`}>Live view</Link>
              : <Link className="btn small" to={`/search?plate=${a.plate_norm}`}>Movement</Link>}
          </div>
        </div>
      ))}
    </div>
  );
}
