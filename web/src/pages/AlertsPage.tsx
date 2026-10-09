import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ago, Alert, api, can, CHECK_CROP, fmtTs, SEV_COLOR } from "../api";
import CropImg from "../components/CropImg";
import { useEvents } from "../events";

const STATUSES = ["new", "acknowledged", "closed", "false_positive", "all"];
const SUGGESTED_TAGS = ["intercepted", "patrol sent", "follow-up", "stolen vehicle", "VIP route", "shift handover"];
const MAX_TAGS = 10;
const MAX_TAG_LEN = 32;
const DISPOSITIONS: Record<string, string[]> = {
  closed: ["Vehicle intercepted", "Patrol dispatched, not found", "Owner verified, no action", "Referred to police station"],
  false_positive: ["OCR misread", "Plate not on the vehicle described", "Watchlist entry out of date"],
};

/** Tags compare ignoring case, as the API de-duplicates them. */
const hasTag = (a: Alert, tag: string) => (a.tags ?? []).some((t) => t.toLowerCase() === tag.toLowerCase());

export default function AlertsPage() {
  const [params] = useSearchParams();
  const [status, setStatus] = useState(STATUSES.includes(params.get("status") ?? "") ? params.get("status")! : "new");
  const [tagFilter, setTagFilter] = useState(params.get("tag") ?? "");
  const [tagQuery, setTagQuery] = useState(tagFilter);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  const [closing, setClosing] = useState<{ id: string; status: string; choice: string; note: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);        // the alert an action is running on
  const [adding, setAdding] = useState<Record<string, string>>({});
  const flashTimer = useRef<number>();

  // The tag filter applies once the operator pauses typing.
  useEffect(() => { const t = window.setTimeout(() => setTagFilter(tagQuery.trim()), 300); return () => window.clearTimeout(t); }, [tagQuery]);

  /** keepErr: a refresh after a refused action keeps the refusal on screen. */
  const load = (keepErr = false) => {
    const p = new URLSearchParams({ status, limit: "200" });
    if (tagFilter) p.set("tag", tagFilter);
    return api<Alert[]>(`/alerts?${p}`).then((xs) => { setAlerts(xs); if (!keepErr) setErr(""); })
      .catch((e) => setErr(`Could not load alerts: ${e.message}`))
      .finally(() => setLoaded(true));
  };
  useEffect(() => { load(); }, [status, tagFilter]); // eslint-disable-line
  useEffect(() => () => window.clearTimeout(flashTimer.current), []);

  const shown = (a: Alert) => (status === "all" || a.status === status) && (!tagFilter || hasTag(a, tagFilter));
  useEvents((e) => {
    if (e.type === "alert.new" && shown(e.alert)) {
      setAlerts((xs) => xs.some((x) => x.id === e.alert.id) ? xs : [e.alert, ...xs]);
      setFlash(e.alert.id);
      window.clearTimeout(flashTimer.current);
      flashTimer.current = window.setTimeout(() => setFlash(null), 4000);
    }
    // Another operator's acknowledge, close or tag edit: the alert is replaced, and leaves a list it no longer fits.
    if (e.type === "alert.updated") {
      setAlerts((xs) => xs.map((x) => x.id === e.alert.id ? e.alert : x).filter((x) => x.id !== e.alert.id || shown(e.alert)));
    }
  }, [status, tagFilter]);

  /** Runs an action on one alert; a refusal (409: someone else got there first) is shown and the list re-read. */
  const act = async (id: string, f: () => Promise<Alert>) => {
    setBusy(id); setErr("");
    try {
      const a = await f();
      setAlerts((xs) => xs.map((x) => x.id === a.id ? a : x).filter((x) => x.id !== a.id || shown(a)));
      return true;
    } catch (e: any) {
      setErr(e.status === 409 ? `${e.message}: another operator has already acted on it. The list is refreshed.` : e.message);
      load(true);
      return false;
    } finally { setBusy(null); }
  };
  const ack = (id: string) => act(id, () => api(`/alerts/${id}/ack`, { method: "POST" }));
  const close = async () => {
    if (!closing) return;
    const disposition = [closing.choice, closing.note.trim()].filter(Boolean).join(": ").slice(0, 500) || null;
    if (await act(closing.id, () => api(`/alerts/${closing.id}/close`, { method: "POST", body: { status: closing.status, disposition } }))) {
      setClosing(null);
    }
  };
  const setTags = (a: Alert, tags: string[]) => act(a.id, () => api(`/alerts/${a.id}/tags`, { method: "PUT", body: { tags } }));
  const addTag = async (a: Alert) => {
    const tag = (adding[a.id] ?? "").split(/\s+/).filter(Boolean).join(" ");
    if (!tag) return;
    if (tag.length > MAX_TAG_LEN) { setErr(`A tag is at most ${MAX_TAG_LEN} characters.`); return; }
    if (hasTag(a, tag)) { setAdding({ ...adding, [a.id]: "" }); return; }
    if ((a.tags ?? []).length >= MAX_TAGS) { setErr(`An alert carries at most ${MAX_TAGS} tags.`); return; }
    if (await setTags(a, [...(a.tags ?? []), tag])) setAdding({ ...adding, [a.id]: "" });
  };

  const knownTags = useMemo(() => {
    const seen = new Map<string, string>();
    [...SUGGESTED_TAGS, ...alerts.flatMap((a) => a.tags ?? [])].forEach((t) => { if (!seen.has(t.toLowerCase())) seen.set(t.toLowerCase(), t); });
    return [...seen.values()];
  }, [alerts]);
  const writer = can("alerts.ack");

  return (
    <div className="page">
      <header className="page-head">
        <h1>Alerts</h1>
        <div className="filters">
          {STATUSES.map((s) => (
            <button key={s} className={`btn ${status === s ? "btn-primary" : ""}`} aria-pressed={status === s} onClick={() => setStatus(s)}>{s.replace("_", " ")}</button>
          ))}
          <input className="tag-input" list="alert-tags" placeholder="filter by tag" value={tagQuery} maxLength={MAX_TAG_LEN}
            onChange={(e) => setTagQuery(e.target.value)} aria-label="Filter by tag" />
          {tagQuery && <button className="btn btn-ghost small" onClick={() => setTagQuery("")} aria-label="Clear the tag filter">×</button>}
          <span className="muted">{alerts.length}</span>
        </div>
      </header>
      <datalist id="alert-tags">{knownTags.map((t) => <option key={t} value={t} />)}</datalist>
      {err && <div className="error" role="alert" style={{ marginBottom: 12 }}>{err}</div>}
      <div className="alerts">
        {loaded && alerts.length === 0 && !err && <div className="card muted">
          No {status === "all" ? "" : status.replace("_", " ")} alerts{tagFilter ? ` tagged “${tagFilter}”` : ""}.</div>}
        {alerts.map((a) => (
          <div key={a.id} className={`card alert ${flash === a.id ? "flash" : ""}`} style={{ borderLeftColor: SEV_COLOR[a.severity] }}>
            <div className="alert-main">
              <div className="row">
                <span className="badge" style={{ background: SEV_COLOR[a.severity] }}>{a.severity}</span>
                {a.alert_type === "intrusion"
                  ? <><span className="tag tag-alert">intrusion</span><span className="big">{a.detail?.zone_name}</span></>
                  : <><span className="tag">{a.kind?.replace("_", " ")}</span><span className="mono big">{a.plate_norm}</span></>}
                {!a.exact_match && <span className="tag tag-warn" title={`match score ${Math.round(a.match_score * 100)}%`}>
                  read ≈ watchlist {a.watch_plate ?? ""} (one character off)</span>}
                {a.retrospective && <span className="tag tag-warn" title="Raised when the plate was added: the vehicle had already been seen">retrospective</span>}
                {a.needs_review && <span className="tag tag-warn" title={CHECK_CROP}>check the crop</span>}
                <span className="muted">{ago(a.triggered_at)}</span>
              </div>
              <div className="alert-body">
                <div><b>{a.camera_code}</b> {a.camera_name}</div>
                {a.alert_type === "intrusion" && <div>{Object.entries(a.detail?.classes ?? {}).map(([k, n]) => `${n} ${k}${Number(n) > 1 ? "s" : ""}`).join(", ")} in the zone
                  for {a.detail?.dwell_s} s or more <span className="muted small">(count only: no image of the person is kept; open the live view)</span></div>}
                {a.subject_name && <div>Subject: {a.subject_name}</div>}
                {a.reason && <div className="muted">{a.reason}</div>}
                <div className="muted small">seen {fmtTs(a.sighting_ts)} · status {a.status.replace("_", " ")}
                  {a.acknowledged_by_name ? ` · acknowledged by ${a.acknowledged_by_name} ${ago(a.acknowledged_at ?? null)}` : ""}
                  {a.disposition ? ` · ${a.disposition}` : ""}</div>
                <div className="tags" aria-label="Tags">
                  {(a.tags ?? []).map((t) => (
                    <span key={t} className="tag-chip">{t}
                      {writer && <button onClick={() => setTags(a, (a.tags ?? []).filter((x) => x !== t))} disabled={busy === a.id}
                        aria-label={`Remove the tag ${t}`} title="Remove">×</button>}
                    </span>
                  ))}
                  {writer && (a.tags ?? []).length < MAX_TAGS && (
                    <input className="tag-input" list="alert-tags" placeholder="+ tag (Enter)" value={adding[a.id] ?? ""} maxLength={MAX_TAG_LEN}
                      disabled={busy === a.id} aria-label={`Add a tag to the alert on ${a.plate_norm ?? a.camera_code}`}
                      onChange={(e) => setAdding({ ...adding, [a.id]: e.target.value })}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTag(a); } }} />
                  )}
                </div>
              </div>
              <div className="row">
                {a.alert_type !== "intrusion" && a.plate_norm && <Link className="btn" to={`/search?plate=${encodeURIComponent(a.plate_norm)}`}>Movement history</Link>}
                <Link className="btn" to={`/wall?cams=${encodeURIComponent(a.camera_code)}`}>Live view</Link>
                {writer && a.status === "new" && <button className="btn btn-primary" disabled={busy === a.id} onClick={() => ack(a.id)}>Acknowledge</button>}
                {writer && (a.status === "new" || a.status === "acknowledged") && closing?.id !== a.id && (
                  <>
                    <button className="btn" onClick={() => setClosing({ id: a.id, status: "closed", choice: "", note: "" })}>Close</button>
                    <button className="btn btn-ghost" onClick={() => setClosing({ id: a.id, status: "false_positive", choice: "", note: "" })}>False positive</button>
                  </>
                )}
              </div>
              {closing?.id === a.id && (
                <div className="row">
                  <select value={closing.choice} onChange={(e) => setClosing({ ...closing, choice: e.target.value })} aria-label="Disposition">
                    <option value="">Disposition…</option>
                    {DISPOSITIONS[closing.status].map((d) => <option key={d}>{d}</option>)}
                  </select>
                  <input placeholder="note (optional)" value={closing.note} maxLength={400} aria-label="Note"
                    onChange={(e) => setClosing({ ...closing, note: e.target.value })}
                    onKeyDown={(e) => { if (e.key === "Enter") close(); if (e.key === "Escape") setClosing(null); }} />
                  <button className="btn btn-primary" disabled={busy === a.id} onClick={close}>{closing.status === "closed" ? "Close alert" : "Mark false positive"}</button>
                  <button className="btn btn-ghost" onClick={() => setClosing(null)}>Cancel</button>
                </div>
              )}
            </div>
            {a.crop_path && <CropImg className="alert-crop" path={a.crop_path} alt="plate crop" />}
          </div>
        ))}
      </div>
    </div>
  );
}
