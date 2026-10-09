// Title and end cards of the demo video, shared by record.mjs (recording) and retitle.mjs
// (swapping the title frame of an existing recording without re-recording it).
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const W = 1920, H = 1080;

const cardCss = `body{margin:0;width:${W}px;height:${H}px;background:radial-gradient(1400px 800px at 20% 0%,#172554 0%,#0b1220 62%);color:#fff;font-family:"Segoe UI",Arial,sans-serif;display:flex;flex-direction:column;justify-content:center;padding:0 150px;box-sizing:border-box}
.mark{width:84px;height:84px;border-radius:20px;background:linear-gradient(135deg,#38bdf8,#6366f1);display:grid;place-items:center;font-weight:800;font-size:46px;margin-bottom:34px}
h1{font-size:104px;margin:0;line-height:1} .sub{font-size:40px;color:#cbd5e1;margin-top:18px} .meta{font-size:26px;color:#94a3b8;margin-top:54px;line-height:1.6}
.meta b{color:#38bdf8;font-weight:600} .grid{display:grid;grid-template-columns:repeat(4,1fr);gap:26px;margin-top:50px}
.stat{background:rgba(15,23,42,.8);border:1px solid #1e3a5f;border-radius:18px;padding:26px 26px}
.stat .v{font-size:50px;font-weight:700;color:#fff}.stat .l{font-size:22px;color:#94a3b8;margin-top:6px;line-height:1.35}`;

// Cards for the government-feed recording (record_gov.mjs). Every figure here was measured on 25 Sep 2026:
// onboarding times and codecs from scripts/onboard_sandbox.py, plate sizes from data/gov-sandbox/diag_plates.py.
// The end card's figures: cameras from sandbox.json; plates from the 25 Sep evening run the video records, as a team
// member checked them blind on the Plate review page (sandbox_daynight.json "blind.evening"). Before that check existed
// the card used our AI assistant's labels (not blind, "accuracy.evening"); that stays only as the fallback. The 26 Sep
// morning run (the same looping footage) is pooled into the sandbox_eye/sandbox_review totals, so the card must not
// read those.
export function govFacts(root) {
  const read = (f) => JSON.parse(readFileSync(join(root, "bench/results", f), "utf-8"));
  const S = read("sandbox.json"), E = read("sandbox_eye.json"), D = read("sandbox_daynight.json");
  const b = D.blind && D.blind.evening, blind = !!(b && (b.exact || 0) + (b.one_off || 0) + (b.wrong || 0));
  const n = blind ? b : D.accuracy.evening;
  return { analysed: S.cameras_analysed, cameras: S.cameras, exact: n.exact || 0, blind,
    plates: (n.exact || 0) + (n.one_off || 0) + (n.wrong || 0), platecams: E.cameras_with_plates.length };
}

// facts: { analysed, cameras, exact, plates, platecams, blind } from bench/results/sandbox.json and, for the plates,
// the evening run the video records (sandbox_daynight.json: "blind.evening", else "accuracy.evening"), never a pooled total
export function writeGovCards(out, facts) {
  mkdirSync(join(out, "cards"), { recursive: true });
  writeFileSync(join(out, "cards/gov_title.html"), `<!doctype html><meta charset="utf-8"><style>${cardCss}</style><body>
<div class="mark">S</div><h1>Sentinel</h1>
<div class="sub">Live test case on the government-provided CCTV feeds</div>
<div class="meta"><b>Gujarat Police Innovation Challenge 2026</b> · Model 2 on the Model 1 registry foundation<br>
The organisers' sandbox camera grid: 30 cameras, replayed recordings streamed live, onboarded by RTSP and recorded live.<br>
Camera positions and departments are our reading of the camera names: the sandbox catalogue gives only id and name.<br>
Times are Sentinel's clock when each frame arrived; the footage shows its own recording date and time.</div></body>`);
  writeFileSync(join(out, "cards/gov_end.html"), `<!doctype html><meta charset="utf-8"><style>${cardCss}</style><body>
<div class="mark">S</div><h1 style="font-size:84px">30 government feeds, one registry.</h1>
<div class="sub">Onboarded, mapped, viewed and analysed without touching the source system.</div>
<div class="grid">
<div class="stat"><div class="v">1–2 s</div><div class="l">per camera to onboard: probed, relayed on demand, registered</div></div>
<div class="stat"><div class="v">H.264 + H.265</div><div class="l">960×576 to 2560×1440, as the sandbox delivers them</div></div>
<div class="stat"><div class="v">${facts.analysed} / ${facts.cameras}</div><div class="l">cameras analysed for vehicles and people, 4 at a time in rotation on one laptop</div></div>
<div class="stat"><div class="v">${facts.exact} / ${facts.plates}</div><div class="l">real Gujarat plates stored exactly right in this run; ${facts.blind ? "blind-checked by a team member against each crop" : "checked against each crop by our AI assistant, not blind"}; readable on ${facts.platecams} of ${facts.cameras} views</div></div></div>
<div class="meta">Built on open source · recordings stay with the source · no face recognition · every search audited</div></body>`);
}

export function writeCards(out) {
  mkdirSync(join(out, "cards"), { recursive: true });
  // Says what the feeds are, so "recorded live" is never read as "simulated interface".
  writeFileSync(join(out, "cards/title.html"), `<!doctype html><meta charset="utf-8"><style>${cardCss}</style><body>
<div class="mark">S</div><h1>Sentinel</h1>
<div class="sub">Unified CCTV integration and video analytics for Gujarat Police</div>
<div class="meta"><b>Gujarat Police Innovation Challenge 2026</b> · Model 2 on the Model 1 registry foundation<br>
Working software, recorded live: real backend, real analytics, nothing mocked in the interface.<br>
Feeds of our choice: 12 generated clips and 2 stock traffic clips with every plate replaced, replayed as RTSP cameras.</div></body>`);
  writeFileSync(join(out, "cards/end.html"), `<!doctype html><meta charset="utf-8"><style>${cardCss}</style><body>
<div class="mark">S</div><h1 style="font-size:84px">One registry. One map. One viewer.</h1>
<div class="sub">For every department's cameras — without replacing any of them.</div>
<div class="grid">
<div class="stat"><div class="v">~2 s</div><div class="l">to onboard any RTSP feed: probed, relayed, registered</div></div>
<div class="stat"><div class="v">Live</div><div class="l">plate reads matched against watchlists (VAHAN and eGujCop adapters, mock data)</div></div>
<div class="stat"><div class="v">34</div><div class="l">end-to-end checks passing</div></div>
<div class="stat"><div class="v">80,000</div><div class="l">cameras sized: 248 edge GPU nodes across 33 districts</div></div></div>
<div class="meta">Built on open source · recordings stay with departments · no face recognition · every plate search audited</div></body>`);
}
