import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api, ApiHealth, can, currentUser, logout, onApiHealth, PAGE_NEEDS, refreshUser } from "../api";
import { startEvents, useEvents, useLiveStatus } from "../events";
import AlertToast from "./AlertToast";

const NAV = [
  ["/", "Overview", "◈"],
  ["/map", "Map", "◎"],
  ["/wall", "Video Wall", "▦"],
  ["/search", "Vehicle Search", "⌕"],
  ["/alerts", "Alerts", "⚑"],
  ["/health", "Health & Reports", "♥"],
  ["/registry", "Registry", "☰"],
  ["/watchlist", "Watchlist", "◉"],
  ["/review", "Plate review", "✓"],
  ["/audit", "Audit trail", "✎"],
] as const;

export default function Layout() {
  const [user, setUser] = useState(currentUser());
  const live = useLiveStatus();
  const [openAlerts, setOpenAlerts] = useState<number>(0);
  const [health, setHealth] = useState<ApiHealth>({ ok: true });
  const alerts = can("alerts.read");      // the event socket and the alert count are for roles that read alerts

  useEffect(() => onApiHealth(setHealth), []);
  useEffect(() => { if (alerts) startEvents(); refreshUser().then(setUser).catch(() => {}); }, [alerts]);
  useEffect(() => {
    if (alerts) api("/alerts/summary").then((s) => setOpenAlerts(s.new)).catch(() => {});
  }, [alerts]);
  useEvents((e) => {
    if (e.type === "alert.new") setOpenAlerts((n) => n + 1);
    if (e.type === "alert.updated" && e.alert?.status !== "new") setOpenAlerts((n) => Math.max(0, n - 1));
  });

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">S</div>
          <div>
            <div className="brand-name">Sentinel</div>
            <div className="brand-sub">Gujarat Police · Unified CCTV</div>
          </div>
        </div>
        <nav>
          {NAV.filter(([to]) => !PAGE_NEEDS[to] || can(PAGE_NEEDS[to])).map(([to, label, icon]) => (
            <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
              <span className="nav-icon">{icon}</span>
              {label}
              {to === "/alerts" && openAlerts > 0 && <span className="pill pill-red">{openAlerts}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          {alerts && (
            <div className={`live ${live ? "on" : ""}`}>
              <span className="dot" /> {live ? "live events" : "reconnecting…"}
            </div>
          )}
          <div className="user">
            <div className="user-name">{user?.full_name}</div>
            <div className="user-role">{user?.role}</div>
          </div>
          <button className="btn btn-ghost" onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main className="main">
        {!health.ok && <div className="banner-error" role="alert">{health.detail}</div>}
        <Outlet />
      </main>
      {alerts && <AlertToast />}
    </div>
  );
}
