import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { can, PAGE_NEEDS, token } from "./api";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Overview from "./pages/Overview";

// Pages load on first visit: the map, the wall and the review page carry most of the bundle, and an operator
// who opens only Alerts should not wait for them.
const MapPage = lazy(() => import("./pages/MapPage"));
const WallPage = lazy(() => import("./pages/WallPage"));
const SearchPage = lazy(() => import("./pages/SearchPage"));
const AlertsPage = lazy(() => import("./pages/AlertsPage"));
const HealthPage = lazy(() => import("./pages/HealthPage"));
const RegistryPage = lazy(() => import("./pages/RegistryPage"));
const WatchlistPage = lazy(() => import("./pages/WatchlistPage"));
const AuditPage = lazy(() => import("./pages/AuditPage"));
const ReviewPage = lazy(() => import("./pages/ReviewPage"));

function Protected({ children }: { children: JSX.Element }) {
  return token() ? children : <Navigate to="/login" replace />;
}

/** A page opened by its address without the permission says so, instead of loading into empty tables. */
function Needs({ path, children }: { path: string; children: JSX.Element }) {
  if (!can(PAGE_NEEDS[path])) {
    return <div className="page"><div className="card muted">This page is not available to your role.</div></div>;
  }
  return <Suspense fallback={<div className="page muted">Loading…</div>}>{children}</Suspense>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Layout /></Protected>}>
        <Route index element={<Overview />} />
        <Route path="map" element={<Needs path="/map"><MapPage /></Needs>} />
        <Route path="wall" element={<Needs path="/wall"><WallPage /></Needs>} />
        <Route path="search" element={<Needs path="/search"><SearchPage /></Needs>} />
        <Route path="alerts" element={<Needs path="/alerts"><AlertsPage /></Needs>} />
        <Route path="health" element={<Needs path="/health"><HealthPage /></Needs>} />
        <Route path="registry" element={<Needs path="/registry"><RegistryPage /></Needs>} />
        <Route path="watchlist" element={<Needs path="/watchlist"><WatchlistPage /></Needs>} />
        <Route path="review" element={<Needs path="/review"><ReviewPage /></Needs>} />
        <Route path="audit" element={<Needs path="/audit"><AuditPage /></Needs>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
