import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  api, Camera, can, cropUrl, fmtTs, MyReview, PlateRow, ReviewItem, ReviewMode, ReviewResult, ReviewSummary, Verdict,
  VerifyItem,
} from "../api";
import CropImg from "../components/CropImg";

// People check Sentinel's stored plate reads against the evidence crop. Blind check is the one the
// accuracy figures quote: the reviewer types the plate before Sentinel's reading is on screen.

type Tab = ReviewMode | "results";

const VERDICT: Record<Verdict, { label: string; cls: string }> = {
  exact: { label: "exact", cls: "v-exact" },
  one_off: { label: "one character off", cls: "v-off" },
  wrong: { label: "wrong", cls: "v-wrong" },
  not_a_plate: { label: "not a plate", cls: "v-none" },
  unreadable: { label: "unreadable", cls: "v-none" },
};
const verdictOf = (v: string) => VERDICT[v as Verdict] ?? { label: v.replace(/_/g, " "), cls: "v-none" };
// Bands in confidence order; below 0.35 appears only when something stored that low (single reads on slow cameras).
const BANDS: [string, string][] = [["<0.35", "below 0.35"], ["0.35-0.5", "0.35 – 0.5"], ["0.5-0.7", "0.5 – 0.7"],
                                   ["0.7-0.9", "0.7 – 0.9"], [">=0.9", "0.9 and above"]];
const BATCH = 100;

const conf = (c: number | null | undefined) => (c == null ? "—" : c.toFixed(2));
const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : "—");

// Page keys stay quiet while the reviewer is typing elsewhere (camera filter, dates, a correction).
const isTextField = (t: EventTarget | null) =>
  t instanceof HTMLElement && (["INPUT", "SELECT", "TEXTAREA"].includes(t.tagName) || t.isContentEditable);
// Enter on a focused button already clicks it; handling it again would skip a crop.
const ownsEnter = (t: EventTarget | null) =>
  isTextField(t) || (t instanceof HTMLElement && ["BUTTON", "A"].includes(t.tagName));

function useKeys(handler: (e: KeyboardEvent) => void) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    // A held key must not label a run of crops.
    const h = (e: KeyboardEvent) => { if (!e.repeat && !e.ctrlKey && !e.metaKey && !e.altKey) ref.current(e); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);
}

export default function ReviewPage() {
  const writer = can("reviews.write");
  const [tab, setTab] = useState<Tab>(writer ? "blind" : "results");
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [camera, setCamera] = useState("");
  const [prefix, setPrefix] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [lowOnly, setLowOnly] = useState(false);   // G3: reads marked "check the crop" that nobody has reviewed

  useEffect(() => {
    api("/cameras?limit=2000")
      .then((r) => setCameras([...r.items].sort((a: Camera, b: Camera) => a.camera_code.localeCompare(b.camera_code))))
      .catch(() => {});
  }, []);

  const query = useMemo(() => {
    const q = new URLSearchParams();
    if (camera) q.set("camera", camera);
    if (prefix.trim()) q.set("prefix", prefix.trim());
    if (since) q.set("since", new Date(since).toISOString());
    if (until) q.set("until", new Date(until).toISOString());
    if (lowOnly) q.set("band", "low");
    return q.toString();
  }, [camera, prefix, since, until, lowOnly]);

  if (!can("reviews.read")) {
    return <div className="page"><div className="card muted">Plate review needs the reviews.read permission, which supervisors, auditors and administrators hold.</div></div>;
  }

  const tabs: [Tab, string][] = [
    ...(writer ? [["blind", "Blind check"], ["verify", "Quick verify"]] as [Tab, string][] : []),
    ["results", "Results"],
  ];

  return (
    <div className="page">
      <header className="page-head">
        <h1>Plate review</h1>
        <span className="muted">Blind check: you type what the crop shows before Sentinel's reading appears, so its answer cannot steer yours.</span>
      </header>
      <div className="row space review-bar">
        <div className="row">
          {tabs.map(([t, label]) => (
            <button key={t} className={`btn ${tab === t ? "btn-primary" : ""}`} onClick={() => setTab(t)}>{label}</button>
          ))}
        </div>
        <div className="row">
          <label className="inline">Camera
            {/* Blur after choosing, so the review keys work again straight away. */}
            <select value={camera} onChange={(e) => { setCamera(e.target.value); e.target.blur(); }}>
              <option value="">All cameras</option>
              {cameras.map((c) => <option key={c.camera_code} value={c.camera_code}>{c.camera_code} · {c.name}</option>)}
            </select>
          </label>
          <label className="inline" title="Every camera whose code starts with this, e.g. CAM for the sandbox cameras">Code starts with
            <input className="prefix" value={prefix} placeholder="e.g. CAM" maxLength={20}
              onChange={(e) => setPrefix(e.target.value.toUpperCase())}
              onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          </label>
          <label className="inline" title="Time of the sighting">From<input type="datetime-local" value={since} onChange={(e) => setSince(e.target.value)} /></label>
          <label className="inline" title="Time of the sighting">To<input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
          {(since || until) && <button className="btn btn-ghost small" onClick={() => { setSince(""); setUntil(""); }}>Any time</button>}
          {tab !== "results" && <label className="inline" title="Only reads below 0.9 confidence that no one has reviewed yet: the ones marked 'check the crop'">
            <input type="checkbox" checked={lowOnly} onChange={(e) => setLowOnly(e.target.checked)} /> Below 0.9, unchecked</label>}
        </div>
      </div>
      {/* key: a fresh queue per mode, so a verify item (which carries the reading) never lingers into blind. */}
      {tab === "results" ? <Results query={query} /> : <Queue key={tab} mode={tab} query={query} />}
    </div>
  );
}

function Queue({ mode, query }: { mode: ReviewMode; query: string }) {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [more, setMore] = useState(false);
  const [pos, setPos] = useState(0);
  const [done, setDone] = useState(0);
  const [last, setLast] = useState<ReviewResult | null>(null);
  const [err, setErr] = useState("");
  const skipped = useRef(new Set<number>());
  const seq = useRef(0);

  const load = () => {
    const n = ++seq.current;
    setItems(null);
    const q = new URLSearchParams(query);
    q.set("mode", mode);
    q.set("limit", String(BATCH));
    api<any>(`/reviews/queue?${q}`).then((r) => {
      if (n !== seq.current) return;
      const rows: any[] = Array.isArray(r) ? r : r?.items ?? [];
      // Keep only what this mode may show: a blind item holds no reading, even if one were sent.
      setItems(rows.filter((x) => !skipped.current.has(x.sighting_id)).map((x) => {
        const base: ReviewItem = { sighting_id: x.sighting_id, event_ts: x.event_ts, camera_code: x.camera_code,
                                   camera_name: x.camera_name, crop_path: x.crop_path };
        return mode === "verify" ? { ...base, plate_norm: x.plate_norm, ocr_conf: x.ocr_conf } as VerifyItem : base;
      }));
      setMore(rows.length >= BATCH);
      setPos(0);
      setErr("");
    }).catch((e) => { if (n === seq.current) { setErr(e.message); setItems([]); } });
  };
  useEffect(() => { load(); }, [query]); // eslint-disable-line

  // Reviewed crops leave the server's queue; skipped ones would come back first, so they are held back here.
  const next = (reviewed: boolean) => {
    const cur = items?.[pos];
    if (reviewed) setDone((d) => d + 1);
    else if (cur) skipped.current.add(cur.sighting_id);
    if (items && pos + 1 >= items.length && more) load();
    else setPos((p) => p + 1);
  };

  const item = items?.[pos];
  useEffect(() => {
    const after = items?.[pos + 1];
    if (after) cropUrl(after.crop_path).catch(() => undefined);   // fetched ahead; a failure shows on its own card
  }, [items, pos]);

  const left = items ? Math.max(0, items.length - pos) : 0;
  return (
    <>
    <section className="card review-card">
      <div className="row space" style={{ width: "100%" }}>
        <span className="muted small">
          {item ? <><b>{item.camera_code}</b> {item.camera_name} · {fmtTs(item.event_ts)}</> : null}
        </span>
        <span className="muted small">{done} reviewed · {left}{more ? "+" : ""} left in this queue</span>
      </div>
      {err && <div className="error">{err}</div>}
      {items === null && <div className="muted">Loading…</div>}
      {items !== null && !item && !err && (
        <div className="muted">Nothing left to review here: only sightings with a stored crop that you have not yet reviewed in this mode are listed.</div>
      )}
      {item && (mode === "blind"
        ? <BlindCard key={item.sighting_id} item={item} onNext={() => next(true)} onSkip={() => next(false)} />
        : <VerifyCard key={item.sighting_id} item={item as VerifyItem} onSaved={(r) => { setLast(r); next(true); }} onSkip={() => next(false)} />)}
      {mode === "verify" && last && (
        <div className="small muted">Last saved: <span className="mono">{last.stored_plate}</span>{" "}
          <b className={`verdict ${verdictOf(last.verdict).cls}`}>{verdictOf(last.verdict).label}</b>
          {last.seen && last.verdict !== "exact" ? <> · corrected to <span className="mono">{last.seen}</span></> : null}
        </div>
      )}
      <div className="muted small">Every review is recorded in the audit trail under your name.</div>
    </section>
    <MyReviews mode={mode} query={query} saved={done} />
    </>
  );
}

function Crop({ path, onBroken }: { path: string; onBroken: () => void }) {
  const [broken, setBroken] = useState(false);
  if (broken) {
    return <div className="review-crop missing">The crop could not be loaded (removed by retention, or not available to you). Skip it: it stays unreviewed.</div>;
  }
  return <CropImg className="review-crop" path={path} alt="plate crop" onError={() => { setBroken(true); onBroken(); }} />;
}

function BlindCard({ item, onNext, onSkip }: { item: ReviewItem; onNext: () => void; onSkip: () => void }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<ReviewResult | null>(null);
  const [gone, setGone] = useState("");   // the server's reason this crop can no longer be reviewed blind
  const [busy, setBusy] = useState(false);
  const [broken, setBroken] = useState(false);
  const [err, setErr] = useState("");
  const [editing, setEditing] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const advance = () => (result ? onNext() : onSkip());
  const submit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (result || gone) return advance();
    const seen = text.trim();
    if (!seen || busy || broken) return;
    setBusy(true); setErr("");
    try {
      setResult(await api<ReviewResult>("/reviews", { method: "POST", body: { sighting_id: item.sighting_id, mode: "blind", seen } }));
    } catch (ex: any) {
      if (ex.status === 409) setGone(ex.message); else setErr(ex.message);
    } finally { setBusy(false); }
  };

  useKeys((e) => {
    if (e.key === "Enter" && (result || gone) && !ownsEnter(e.target)) { e.preventDefault(); advance(); return; }
    // Typing with nothing focused goes to the plate box.
    if (!result && !gone && e.key.length === 1 && !isTextField(e.target)) input.current?.focus();
  });

  const v = result ? verdictOf(result.verdict) : null;
  return (
    <form className="review-card" onSubmit={submit}>
      <Crop path={item.crop_path} onBroken={() => setBroken(true)} />
      <input ref={input} className="review-input" autoFocus readOnly={busy || !!result || !!gone} value={text} maxLength={16}
             placeholder="type the plate you read" spellCheck={false} autoComplete="off"
             onChange={(e) => setText(e.target.value.toUpperCase())}
             onKeyDown={(e) => {
               if (e.key !== "Enter") return;
               // A held Enter must not submit and then skip past the reveal.
               if (e.repeat) e.preventDefault();
               else if (result || gone) { e.preventDefault(); advance(); }
             }} />
      {!result && !gone && (
        <div className="muted small">
          Type the plate as you read it and press <kbd>Enter</kbd>. <kbd>?</kbd> <kbd>Enter</kbd> unreadable ·{" "}
          <kbd>-</kbd> <kbd>Enter</kbd> not a plate. Spaces and punctuation do not matter.
        </div>
      )}
      {result && v && (
        <div className={`reveal ${v.cls}`}>
          {result.verdict === "unreadable" ? "You marked it unreadable"
            : result.verdict === "not_a_plate" ? "You marked it not a plate"
            : <>You read <span className="mono">{result.seen ?? text}</span></>}
          {" · "}Sentinel read <span className="mono">{result.stored_plate}</span> (confidence {conf(result.ocr_conf)})
          {" · "}<b className="verdict">{v.label}</b>
          <Changed r={result} />
          {!editing && <div className="muted small">Press <kbd>Enter</kbd> for the next crop.</div>}
        </div>
      )}
      {result && editing && <EditReading review={result} onSaved={setResult} onClose={() => setEditing(false)} />}
      {gone && <div className="muted">Not recorded: {gone}. Press <kbd>Enter</kbd> for the next crop.</div>}
      {err && <div className="error">{err}</div>}
      <div className="row">
        <button className="btn btn-primary" disabled={busy || (!result && !gone && (!text.trim() || broken))}>
          {result || gone ? "Next" : busy ? "Saving…" : "Check"} <kbd>Enter</kbd>
        </button>
        {!result && !gone && <button type="button" className="btn btn-ghost" onClick={onSkip} title="Leave this crop unreviewed and move on">Skip</button>}
        {result && !editing && (
          <button type="button" className="btn" onClick={() => setEditing(true)}
                  title="Mistyped? Your first reading stays on record as the blind one; the change is saved beside it">Edit my reading</button>
        )}
      </div>
    </form>
  );
}

// A change to a saved review. Sentinel's read was on screen before it, so the server keeps it beside the first
// reading, which blind results go on using.
function EditReading({ review, onSaved, onClose }: {
  review: ReviewResult; onSaved: (r: ReviewResult) => void; onClose: () => void;
}) {
  const [text, setText] = useState(review.corrected_seen ?? review.seen ?? "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const save = async () => {
    const seen = text.trim();
    if (!seen || busy) return;
    setBusy(true); setErr("");
    try {
      onSaved(await api<ReviewResult>(`/reviews/${review.sighting_id}`, { method: "PATCH", body: { mode: review.mode, seen } }));
      onClose();
    } catch (ex: any) { setErr(ex.message); setBusy(false); }
  };

  return (
    <div className="review-edit">
      <input className="review-input" autoFocus value={text} maxLength={16} placeholder="the plate as the crop shows it"
             spellCheck={false} autoComplete="off" onChange={(e) => setText(e.target.value.toUpperCase())}
             onKeyDown={(e) => {
               // Inside the blind card, Enter would also submit the card and move on to the next crop.
               if (e.key === "Enter") { e.preventDefault(); if (!e.repeat) save(); }
               else if (e.key === "Escape") { e.preventDefault(); onClose(); }
             }} />
      <div className="row">
        <button type="button" className="btn btn-primary" disabled={busy || !text.trim()} onClick={save}>
          {busy ? "Saving…" : "Save change"} <kbd>Enter</kbd></button>
        <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel <kbd>Esc</kbd></button>
      </div>
      <div className="muted small">
        <kbd>?</kbd> unreadable · <kbd>-</kbd> not a plate. Sentinel's read was on screen before this change, so it is
        saved beside your first reading, with the time, and blind results keep the first. Type your first reading again to
        take a change back.
      </div>
      {err && <div className="error">{err}</div>}
    </div>
  );
}

function Changed({ r }: { r: ReviewResult }) {
  if (!r.corrected_verdict) return null;
  const c = verdictOf(r.corrected_verdict);
  const as = r.corrected_seen === "?" ? "unreadable" : r.corrected_seen === "-" ? "not a plate" : null;
  return (
    <div className="small">
      Changed after the reveal{r.corrected_at ? ` (${fmtTs(r.corrected_at)})` : ""}
      {as ? <>: marked {as}</> : <> to <span className="mono">{r.corrected_seen}</span>: <b className={`verdict ${c.cls}`}>{c.label}</b></>}
      <span className="muted"> · blind results keep the first reading</span>
    </div>
  );
}

function firstSaid(r: ReviewResult) {
  if (r.seen === "?" || (r.seen == null && r.verdict === "unreadable")) return <>You marked it unreadable</>;
  if (r.seen === "-" || (r.seen == null && r.verdict === "not_a_plate")) return <>You marked it not a plate</>;
  if (r.seen == null) return <>You confirmed it</>;
  return <>You read <span className="mono">{r.seen}</span></>;
}

// The reviewer's own saved reviews, newest first, to look at a crop again and correct a reading. Closed by default:
// it shows Sentinel's reads, which a reviewer should not have in view while reading the next crop blind.
function MyReviews({ mode, query, saved }: { mode: ReviewMode; query: string; saved: number }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<MyReview[] | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const seq = useRef(0);

  useEffect(() => {
    if (!open) return;
    const n = ++seq.current;
    const q = new URLSearchParams(query);
    q.delete("band");
    q.set("mode", mode);
    q.set("limit", "200");
    api<MyReview[]>(`/reviews/mine?${q}`)
      .then((r) => { if (n === seq.current) { setRows(r); setErr(""); } })
      .catch((e) => { if (n === seq.current) setErr(e.message); });
  }, [open, mode, query, saved]);

  const update = (r: ReviewResult) =>
    setRows((rs) => rs && rs.map((x) => (x.sighting_id === r.sighting_id ? { ...x, ...r } : x)));

  return (
    <section className="card my-reviews">
      <div className="row space">
        <h2>Your saved {mode === "blind" ? "blind checks" : "quick verifies"}</h2>
        <button type="button" className="btn btn-ghost small" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide" : "Show, to correct one"}</button>
      </div>
      {open && <div className="muted small">Newest first, with Sentinel's read as the page showed it when you saved. Hide this list before you read the next crop.</div>}
      {open && err && <div className="error">{err}</div>}
      {open && rows && rows.length === 0 && <div className="muted">Nothing saved yet for this filter.</div>}
      {open && rows && rows.map((r) => {
        const v = verdictOf(r.verdict);
        return (
          <div key={r.sighting_id} className="my-review">
            <CropImg className="review-thumb" path={r.crop_path} alt="plate crop" />
            <div className="my-review-body">
              <div className="muted small"><b>{r.camera_code}</b> {r.camera_name} · {fmtTs(r.event_ts)}</div>
              <div>{firstSaid(r)} · Sentinel read <span className="mono">{r.stored_plate}</span> ·{" "}
                <b className={`verdict ${v.cls}`}>{v.label}</b></div>
              <Changed r={r} />
              {editing === r.sighting_id
                ? <EditReading review={r} onSaved={update} onClose={() => setEditing(null)} />
                : <button type="button" className="btn small" onClick={() => setEditing(r.sighting_id)}>Edit</button>}
            </div>
          </div>
        );
      })}
    </section>
  );
}

type VerifyChoice = "correct" | "wrong" | "not_a_plate" | "unreadable";

function VerifyCard({ item, onSaved, onSkip }: { item: VerifyItem; onSaved: (r: ReviewResult) => void; onSkip: () => void }) {
  const [fixing, setFixing] = useState(false);
  const [fix, setFix] = useState("");
  const [busy, setBusy] = useState(false);
  const [broken, setBroken] = useState(false);
  const [err, setErr] = useState("");

  const save = async (verdict: VerifyChoice, seen?: string) => {
    if (busy || broken) return;
    setBusy(true); setErr("");
    try {
      onSaved(await api<ReviewResult>("/reviews", { method: "POST", body: {
        sighting_id: item.sighting_id, mode: "verify", verdict, ...(seen ? { seen } : {}) } }));
    } catch (ex: any) {
      if (ex.status === 409) onSkip(); else { setErr(ex.message); setBusy(false); }
    }
  };
  const cancelFix = () => { setFixing(false); setFix(""); };

  useKeys((e) => {
    if (isTextField(e.target) || fixing) return;
    const k = e.key.toLowerCase();
    if (!["y", "n", "x", "u"].includes(k)) return;
    e.preventDefault();   // the N that opens the correction box must not be typed into it
    if (k === "y") save("correct");
    else if (k === "n") { if (!busy && !broken) setFixing(true); }
    else if (k === "x") save("not_a_plate");
    else save("unreadable");
  });

  return (
    <div className="review-card">
      <Crop path={item.crop_path} onBroken={() => setBroken(true)} />
      <div className="row">
        <span className="muted">Sentinel read</span>
        <span className="mono big">{item.plate_norm}</span>
        <span className="muted">confidence {conf(item.ocr_conf)}</span>
      </div>
      {!fixing ? (
        <div className="row">
          <button className="btn" disabled={busy || broken} onClick={() => save("correct")}><kbd>Y</kbd> Correct</button>
          <button className="btn" disabled={busy || broken} onClick={() => setFixing(true)}><kbd>N</kbd> Wrong</button>
          <button className="btn" disabled={busy || broken} onClick={() => save("not_a_plate")}><kbd>X</kbd> Not a plate</button>
          <button className="btn" disabled={busy || broken} onClick={() => save("unreadable")}><kbd>U</kbd> Unreadable</button>
          <button className="btn btn-ghost" onClick={onSkip} title="Leave this crop unreviewed and move on">Skip</button>
        </div>
      ) : (
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (fix.trim()) save("wrong", fix.trim()); }}>
          <input className="review-input" autoFocus value={fix} maxLength={16} placeholder="the plate as the crop shows it"
                 spellCheck={false} autoComplete="off" onChange={(e) => setFix(e.target.value.toUpperCase())}
                 onKeyDown={(e) => { if (e.key === "Escape") cancelFix(); }} />
          <button className="btn btn-primary" disabled={busy || !fix.trim()}>Save <kbd>Enter</kbd></button>
          <button type="button" className="btn btn-ghost" onClick={cancelFix}>Cancel <kbd>Esc</kbd></button>
        </form>
      )}
      <div className="muted small">
        <kbd>Y</kbd> correct · <kbd>N</kbd> wrong (type the right plate) · <kbd>X</kbd> not a plate · <kbd>U</kbd> unreadable.
        Keys work while no text box has focus. Quick verify shows Sentinel's reading first, so its results are kept apart from blind checks.
        Do blind checks first: a read you have seen here is no longer blind for you, even if you skip it.
      </div>
      {err && <div className="error">{err}</div>}
    </div>
  );
}

function Results({ query }: { query: string }) {
  const [s, setS] = useState<ReviewSummary | null>(null);
  const [err, setErr] = useState("");
  const seq = useRef(0);

  const load = () => {
    const n = ++seq.current;
    api<ReviewSummary>(`/reviews/summary${query ? `?${query}` : ""}`)
      .then((r) => { if (n === seq.current) { setS(r); setErr(""); } })
      .catch((e) => { if (n === seq.current) setErr(e.message); });
  };
  useEffect(() => { setS(null); load(); }, [query]); // eslint-disable-line

  if (!s) return err ? <div className="error">{err}</div> : <div className="card muted">Loading…</div>;
  const a = s.agreement;
  return (
    <>
      <div className="two-col">
        <ModeResults mode="blind" s={s} footer={
          <div className="small" style={{ marginTop: 10 }}>
            {a.sightings_with_2plus_blind
              ? <>{a.sightings_with_2plus_blind} plate{a.sightings_with_2plus_blind === 1 ? "" : "s"} checked blind by two or more reviewers:{" "}
                  {a.same_verdict} same verdict, {a.same_reading} same reading.</>
              : <span className="muted">No crop has been checked blind by two reviewers yet; agreement shows once two people label the same crops.</span>}
          </div>
        } />
        <ModeResults mode="verify" s={s} />
      </div>
      <section className="card" style={{ marginTop: 16 }}>
        <div className="row space"><h2>Reviewers</h2><button className="btn btn-ghost small" onClick={load}>Refresh</button></div>
        {s.reviewers.length === 0 ? <div className="muted">Nobody has reviewed a plate for this filter yet.</div> : (
          <table>
            <thead><tr><th>Reviewer</th><th>Blind checks</th><th>Quick verifies</th><th>Changed after saving</th></tr></thead>
            <tbody>{s.reviewers.map((r) => (
              <tr key={r.username}><td>{r.full_name} <span className="muted small">{r.username}</span></td><td>{r.blind}</td><td>{r.verify}</td>
                <td>{r.corrected ?? 0}</td></tr>
            ))}</tbody>
          </table>
        )}
        <div className="muted small" style={{ marginTop: 8 }}>
          The results above use each reviewer's first reading. A reading changed after Sentinel's read was shown is not
          blind: it is counted here and kept beside the first one.
        </div>
      </section>
      <PlateByPlate query={query} />
    </>
  );
}

function readingOf(seen: string | null | undefined, verdict: string) {
  if (seen === "?" || (seen == null && verdict === "unreadable")) return <i>unreadable</i>;
  if (seen === "-" || (seen == null && verdict === "not_a_plate")) return <i>not a plate</i>;
  if (seen == null) return <i>confirmed Sentinel's read</i>;
  return <span className="mono">{seen}</span>;
}

// Each review: the crop, Sentinel's read and the reviewer's reading side by side. The reviewer's own by default. Everyone's
// shows reads of crops this user may not have checked, so the server then takes those out of their blind queue.
function PlateByPlate({ query }: { query: string }) {
  const [scope, setScope] = useState<"mine" | "all">("mine");
  const [asking, setAsking] = useState(false);
  const [rows, setRows] = useState<PlateRow[] | null>(null);
  const [err, setErr] = useState("");
  const seq = useRef(0);

  useEffect(() => {
    const n = ++seq.current;
    setRows(null);
    const q = new URLSearchParams(query);
    q.delete("band");
    q.set("scope", scope);
    q.set("limit", "1000");
    api<PlateRow[]>(`/reviews/plates?${q}`)
      .then((r) => { if (n === seq.current) { setRows(r); setErr(""); } })
      .catch((e) => { if (n === seq.current) { setErr(e.message); setRows([]); } });
  }, [query, scope]);

  const v = Object.fromEntries(Object.keys(VERDICT).map((k) => [k, rows?.filter((r) => r.verdict === k).length ?? 0]));
  return (
    <section className="card" style={{ marginTop: 16 }}>
      <div className="row space">
        <h2>Plate by plate: Sentinel's read and the reviewer's</h2>
        <div className="row">
          <button className={`btn small ${scope === "mine" ? "btn-primary" : ""}`}
                  onClick={() => { setScope("mine"); setAsking(false); }}>Your reviews</button>
          <button className={`btn small ${scope === "all" ? "btn-primary" : ""}`}
                  onClick={() => { if (scope !== "all") setAsking(true); }}>Everyone's</button>
        </div>
      </div>
      {asking && (
        <div className="notice">
          Everyone's reviews show Sentinel's read, and other reviewers' readings, of crops you may not have checked yet.
          Those crops then leave your blind queue: you could no longer check them blind.
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn btn-primary small" onClick={() => { setScope("all"); setAsking(false); }}>Show everyone's</button>
            <button className="btn btn-ghost small" onClick={() => setAsking(false)}>Cancel</button>
          </div>
        </div>
      )}
      {err && <div className="error">{err}</div>}
      {rows === null && !err && <div className="muted">Loading…</div>}
      {rows && rows.length === 0 && !err && (
        <div className="muted">{scope === "mine" ? "You have not reviewed a plate for this filter yet." : "Nobody has reviewed a plate for this filter yet."}</div>
      )}
      {rows && rows.length > 0 && (
        <>
          <div className="muted small" style={{ marginBottom: 8 }}>
            {rows.length} review{rows.length === 1 ? "" : "s"}, by first reading: exact {v.exact} · one character off {v.one_off} ·
            wrong {v.wrong} · not a plate {v.not_a_plate} · unreadable {v.unreadable}. A reading changed after the reveal is
            shown under the first; it is not blind.
          </div>
          <div className="table-x">
            <table className="plates">
              <thead><tr><th>Crop</th><th>Camera · seen</th><th>Sentinel read</th><th>Reviewer's reading</th><th>Verdict</th>
                {scope === "all" && <th>Reviewer</th>}</tr></thead>
              <tbody>{rows.map((r) => {
                const first = verdictOf(r.verdict);
                const after = r.corrected_verdict ? verdictOf(r.corrected_verdict) : null;
                return (
                  <tr key={`${r.sighting_id}-${r.reviewer}-${r.mode}`}>
                    <td><CropImg className="plate-thumb" path={r.crop_path} alt="plate crop" /></td>
                    <td><b>{r.camera_code}</b><div className="muted small">{fmtTs(r.event_ts)}</div></td>
                    <td><span className="mono">{r.stored_plate}</span><div className="muted small">confidence {conf(r.ocr_conf)}</div></td>
                    <td>{readingOf(r.seen, r.verdict)}{r.mode === "verify" && <span className="muted small"> (quick verify)</span>}
                      {after && <div className="small">changed after the reveal: {readingOf(r.corrected_seen, r.corrected_verdict!)}</div>}</td>
                    <td><b className={`verdict ${first.cls}`}>{first.label}</b>
                      {after && <div className="small">after the change: <b className={`verdict ${after.cls}`}>{after.label}</b></div>}</td>
                    {scope === "all" && <td>{r.reviewer_name} <span className="muted small">{r.reviewer}</span>
                      <div className="muted small">{r.mode === "blind" ? "blind" : "quick verify"}</div></td>}
                  </tr>
                );
              })}</tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function Share({ a, b }: { a: number; b: number }) {
  if (!b) return <span className="muted">—</span>;
  return <span className="share">{pct(a, b)} <span className="muted small">{a}/{b}</span></span>;
}

function ModeResults({ mode, s, footer }: { mode: ReviewMode; s: ReviewSummary; footer?: JSX.Element }) {
  const rows = s.cameras.filter((c) => c.mode === mode);
  const title = mode === "blind" ? "Blind check" : "Quick verify";
  const plates = (c: { exact: number; one_off: number; wrong: number }) => c.exact + c.one_off + c.wrong;
  const total = rows.reduce((t, c) => ({
    n: t.n + c.n, exact: t.exact + c.exact, one_off: t.one_off + c.one_off, wrong: t.wrong + c.wrong,
    not_a_plate: t.not_a_plate + c.not_a_plate, unreadable: t.unreadable + c.unreadable,
  }), { n: 0, exact: 0, one_off: 0, wrong: 0, not_a_plate: 0, unreadable: 0 });
  const mine = s.bands.filter((x) => x.mode === mode);
  const known = new Set(BANDS.map(([k]) => k));
  const bands = [...BANDS, ...mine.filter((x) => !known.has(x.band)).map((x): [string, string] => [x.band, x.band])]
    .map(([key, label]) => {
      const b = mine.find((x) => x.band === key);
      return { key, label, n: b?.n_plates ?? 0, exact: b?.exact ?? 0, one_off: b?.one_off };
    })
    .filter((b) => b.n > 0 || b.key !== "<0.35");

  return (
    <section className="card">
      <h2>{title}</h2>
      <div className="muted small" style={{ marginBottom: 8 }}>
        {mode === "blind" ? "The reviewer typed the plate before seeing Sentinel's reading."
          : "The reviewer saw Sentinel's reading first, which can lean towards agreeing."}
      </div>
      {rows.length === 0 ? <div className="muted">No {title.toLowerCase()} reviews for this filter yet.</div> : (
        <>
          <table>
            <thead><tr><th>Camera</th><th>Reviewed</th><th>Exact</th><th>Within one</th><th>Not a plate</th><th>Unreadable</th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.camera_code}>
                  <td><b>{c.camera_code}</b><div className="muted small">{c.camera_name}</div></td>
                  <td>{c.n}</td>
                  <td><Share a={c.exact} b={plates(c)} /></td>
                  <td><Share a={c.exact + c.one_off} b={plates(c)} /></td>
                  <td>{c.not_a_plate}</td><td>{c.unreadable}</td>
                </tr>
              ))}
              {rows.length > 1 && (
                <tr>
                  <td><b>All cameras</b></td><td>{total.n}</td>
                  <td><Share a={total.exact} b={plates(total)} /></td>
                  <td><Share a={total.exact + total.one_off} b={plates(total)} /></td>
                  <td>{total.not_a_plate}</td><td>{total.unreadable}</td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="muted small" style={{ margin: "6px 0 14px" }}>
            Exact and within one are shares of crops that show a readable plate; not-a-plate and unreadable crops are counted apart.
          </div>
          <h2>By Sentinel's confidence</h2>
          <table>
            <thead><tr><th>Confidence</th><th>Plates</th><th>Exact</th><th>Within one</th></tr></thead>
            <tbody>{bands.map((b) => (
              <tr key={b.key}><td>{b.label}</td><td>{b.n}</td><td><Share a={b.exact} b={b.n} /></td>
                <td>{b.one_off == null ? <span className="muted">—</span> : <Share a={b.exact + b.one_off} b={b.n} />}</td></tr>
            ))}</tbody>
          </table>
        </>
      )}
      {footer}
    </section>
  );
}
