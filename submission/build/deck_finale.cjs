// Finale presentation: node deck_finale.cjs -> submission/out/Sentinel-Finale.pptx
// Ten slides for a 7-10 minute demo-led slot (grand finale, 12-13 Oct 2026). Same look, helpers and data
// files as deck.cjs (the 23-slide written-pack deck, which stays as the backup). Every caveat sits in the
// speaker notes, not on the slide; every figure comes from a bench/results file or the finale brief.
// The team's name is unknown here: the title slide carries the literal <TEAM NAME> until the team fills it in.
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "../..");
const OUT = path.join(ROOT, "submission/out");
const DIA = (n) => path.join(OUT, "diagrams", `${n}.png`);
const SCR = (n) => path.join(OUT, "screens", `${n}.png`);
const J = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf-8"));
const PCT = (n, d) => `${(100 * n / d).toFixed(1)}%`;

const S = J("bench/results/sandbox.json");                      // the organisers' 30 cameras, 25 Sep
const B = J("bench/results/sandbox_review.json").modes.blind;   // real plates checked blind by one team member, 26 Sep
const CC = J("bench/results/counts_capacity.json").rows;        // counts-only worker, one laptop, 7 Oct
const G3 = J("bench/results/g3_wiring.json");                   // confidence marking: gate verdict, 8 Oct
const HLD_VERSION = (fs.readFileSync(path.join(ROOT, "docs/hld.md"), "utf-8").match(/^version:\s*([\d.]+)/m) || [])[1];
if (!HLD_VERSION) throw new Error("docs/hld.md: no version in the front matter");
if (G3.verdict !== "PASS") throw new Error(`g3_wiring.json verdict is ${G3.verdict}: slide 6 says the gate passed`);
const hi = B.bands[">=0.9"], mid = B.bands["0.7-0.9"], low = B.bands["0.5-0.7"];
const within1 = B.exact + B.one_off;
const [p0, , p1] = S.probe_s;
const c40 = CC.find((r) => r.streams === 40), c50 = CC.find((r) => r.streams === 50);
for (const f of ["d1-architecture"].map(DIA).concat(["wall", "alerts", "gov-wall", "search", "objects-AMD-TRAF-002", "alerts-check-crop", "review-low-band"].map(SCR))) {
  if (!fs.existsSync(f)) throw new Error(`missing asset: ${f}`);
}
// Figures quoted from script-made files that have no JSON twin; the file is named beside each
const FT1 = { base: 88, cand: 89, n: 120, fixed: 8, broken: 7 };      // bench/results/ocr_ft1.md, sandbox-blind-v1
const STOCK = { exact: "96.8%", n: "659 of 681", capture: "91.2%" };   // bench/results/anpr_eval_current.md, AMD-TRAF-002
const LAT = { median: "1.06 s", p95: "1.94 s", alerts: 31 };          // bench/results/latency.md
const SCALE = { nodes: "248", meta: "2.7 Mbps", video: "320 Gbps", tco: "₹100.7 cr", capex: "₹39.7 cr", impl: "₹9.9 cr", opex: "₹51.0 cr", perCam: "₹210", ingest: "706 /s" }; // docs/plan-for-scale.md 6.3, 9.4; bench/results/core_scale.md
// pytest --collect-only -q on 9 Oct (379; 309 on the 8 Oct evening, 286 that morning); security_checks.py as it runs (23 checks: crops 4, quality report 1, write
// scope 4, ingest 3, review 3, secrets 2, LAN 6; a plain count of check( calls in the file gives 19 because its
// control-plane loop covers five ports); smoke.py's count (34) is on the demo video's end card
const TESTS = { unit: 379, security: 23, smoke: 34 };

const C = {
  ink: "0B1220", ink2: "111C33", slate: "334155", muted: "64748B", line: "CBD5E1", soft: "F1F5F9",
  white: "FFFFFF", cyan: "0284C7", cyanL: "38BDF8", red: "DC2626", green: "047857", amber: "B45309",
  paleCyan: "E0F2FE", paleGreen: "ECFDF5", paleRed: "FEE2E2", paleAmber: "FEF3C7",
};
const FONT = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.title = "Sentinel — Grand finale";
pres.company = "Gujarat Police Innovation Challenge 2026";

const W = 13.333, M = 0.6;

function kicker(s, text, dark = false) {
  const w = 0.32 + text.length * 0.105;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 0.42, w, h: 0.34, rectRadius: 0.17,
    fill: { color: dark ? "0F2A44" : C.paleCyan }, line: { color: dark ? C.cyanL : C.cyan, width: 1 } });
  s.addText(text.toUpperCase(), { x: M, y: 0.42, w, h: 0.34, fontFace: FONT, fontSize: 10.5, bold: true,
    color: dark ? C.cyanL : C.cyan, align: "center", valign: "middle", charSpacing: 1.5, margin: 0, isTextBox: true });
}
function title(s, text, dark = false, opts = {}) {
  s.addText(text, { x: M, y: 0.86, w: W - 2 * M, h: 0.9, fontFace: FONT, fontSize: opts.size || 32, bold: true,
    color: dark ? C.white : C.ink, valign: "top", margin: 0, isTextBox: true });
}
function framed(s, img, x, y, w, h, { dark = false } = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.06, y: y - 0.06, w: w + 0.12, h: h + 0.12, rectRadius: 0.08,
    fill: { color: dark ? "1E293B" : C.white }, line: { color: dark ? "334155" : C.line, width: 0.75 },
    shadow: { type: "outer", color: "000000", opacity: dark ? 0.45 : 0.18, blur: 10, offset: 3, angle: 90 } });
  s.addImage({ path: img, x, y, w, h });
}
function stat(s, x, y, w, value, label, { dark = false, color, size = 40, labelSize = 12.5 } = {}) {
  s.addText(value, { x, y, w, h: 0.75, fontFace: FONT, fontSize: size, bold: true, color: color || (dark ? C.white : C.ink), margin: 0, valign: "bottom", isTextBox: true });
  s.addText(label, { x, y: y + 0.78, w, h: 0.62, fontFace: FONT, fontSize: labelSize, color: dark ? "94A3B8" : C.muted, margin: 0, valign: "top", isTextBox: true });
}
function tile(s, x, y, w, h, value, label, { color = C.ink, size = 28, vw = 1.75, labelSize = 11, dark = false } = {}) {
  if (dark) s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: C.ink2 }, line: { color: "1E3A5F", width: 1 } });
  else card(s, x, y, w, h);
  s.addText(value, { x: x + 0.22, y, w: vw, h, fontFace: FONT, fontSize: size, bold: true, color, valign: "middle", margin: 0, isTextBox: true });
  s.addText(label, { x: x + 0.3 + vw, y, w: w - vw - 0.5, h, fontFace: FONT, fontSize: labelSize, color: dark ? "CBD5E1" : C.slate, valign: "middle", margin: 0, isTextBox: true });
}
function bullets(s, items, x, y, w, h, { size = 15, dark = false, gap = 8 } = {}) {
  s.addText(items.map((t, i) => {
    const [head, body] = Array.isArray(t) ? t : [null, t];
    const runs = [];
    if (head) runs.push({ text: head + " ", options: { bold: true, color: dark ? C.white : C.ink } });
    runs.push({ text: body, options: { color: dark ? "CBD5E1" : C.slate, breakLine: i < items.length - 1 } });
    return runs.map((r, j) => ({ text: r.text, options: { ...r.options, bullet: j === 0 ? { indent: 16 } : undefined, paraSpaceAfter: gap } }));
  }).flat(), { x, y, w, h, fontFace: FONT, fontSize: size, valign: "top", margin: 0, isTextBox: true });
}
function caption(s, text, x, y, w, h = 0.5) {
  s.addText(text, { x, y, w, h, fontFace: FONT, fontSize: 11, italic: true, color: C.muted, margin: 0, valign: "top", isTextBox: true });
}
function footer(s, n, dark = false) {
  s.addText("Sentinel · Grand finale · Gujarat Police Innovation Challenge 2026", { x: M, y: 7.08, w: 7, h: 0.28, fontFace: FONT, fontSize: 9, color: dark ? "64748B" : "94A3B8", margin: 0, isTextBox: true });
  s.addText(String(n), { x: W - M - 1, y: 7.08, w: 1, h: 0.28, fontFace: FONT, fontSize: 9, color: dark ? "64748B" : "94A3B8", align: "right", margin: 0, isTextBox: true });
}
function chip(s, x, y, w, text, fill, color) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.3, rectRadius: 0.15, fill: { color: fill }, line: { color: fill, width: 0 } });
  s.addText(text, { x, y, w, h: 0.3, fontFace: FONT, fontSize: 10, bold: true, color, align: "center", valign: "middle", margin: 0, isTextBox: true });
}
function card(s, x, y, w, h, fill = C.soft, line = C.soft) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: fill }, line: { color: line, width: 0.75 } });
}
function numDot(s, x, y, n, color = C.cyan) {
  s.addShape(pres.shapes.OVAL, { x, y, w: 0.42, h: 0.42, fill: { color }, line: { color, width: 0 } });
  s.addText(String(n), { x, y, w: 0.42, h: 0.42, fontFace: FONT, fontSize: 14, bold: true, color: C.white, align: "center", valign: "middle", margin: 0, isTextBox: true });
}
let page = 0;
const slide = (dark = false) => {
  const s = pres.addSlide();
  s.background = { color: dark ? C.ink : C.white };
  page += 1;
  if (page > 1) footer(s, page, dark);
  return s;
};

// 1 ─ Title
{
  const s = slide(true);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 1.0, w: 0.78, h: 0.78, rectRadius: 0.18, fill: { color: C.cyan }, line: { color: C.cyan, width: 0 } });
  s.addText("S", { x: M, y: 1.0, w: 0.78, h: 0.78, fontFace: FONT, fontSize: 36, bold: true, color: C.white, align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText("Sentinel", { x: M, y: 1.95, w: 6.3, h: 1.1, fontFace: FONT, fontSize: 64, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addText("— <TEAM NAME>", { x: M, y: 3.05, w: 6.3, h: 0.6, fontFace: FONT, fontSize: 30, bold: true, color: C.cyanL, margin: 0, isTextBox: true });
  s.addText("Model 2 on the Model 1 foundation · integrate, don't replace · metadata, not video.",
    { x: M, y: 3.8, w: 6.1, h: 0.95, fontFace: FONT, fontSize: 19, color: "CBD5E1", margin: 0, valign: "top", isTextBox: true });
  chip(s, M, 4.95, 4.3, "GRAND FINALE · 12–13 OCT 2026 · i-HUB GANDHINAGAR", "0F2A44", C.cyanL);
  chip(s, M + 4.45, 4.95, 2.6, "LIVE ON THE GOVERNMENT FEEDS", "0F2A44", C.cyanL);
  s.addText("Gujarat Police Innovation Challenge 2026 · Finale presentation", { x: M, y: 6.35, w: 6.5, h: 0.35, fontFace: FONT, fontSize: 13, color: "94A3B8", margin: 0, isTextBox: true });
  framed(s, SCR("wall"), 6.95, 1.3, 5.8, 3.2625, { dark: true });
  framed(s, SCR("alerts"), 7.75, 4.05, 4.4, 2.475, { dark: true });
  s.addNotes("Replace <TEAM NAME> with the team's name before the finale (submission/build/deck_finale.cjs, slide 1; then node deck_finale.cjs and pptx_pdf.ps1). Sentinel joins Gujarat's fragmented CCTV estate (26 departments, many vendors) into one registry, map, viewer and analytics layer without replacing department infrastructure. Model 2 (unified viewing and selective analytics) on the mandatory Model 1 foundation (registry and GIS): never 'hybrid'. Everything in this deck is running software; the screenshots are from the live system on the simulator's feeds. The demo itself is the presentation: this deck frames it, and the 23-slide written-pack deck (Sentinel-Solution.pptx) is the backup for questions.");
}

// 2 ─ The next eight minutes (the runbook's click path, docs/demo-runbook.md section 3)
{
  const s = slide();
  kicker(s, "Live, in this order");
  title(s, "What you will see in the next eight minutes");
  const steps = [
    ["Onboard", "1 min", "One government camera through the card, live: probe → relay → register. The rest go in as a batch from the operator laptop."],
    ["View", "1 min", "Every camera on one map and one wall. Health grades each camera's plate-reading quality and says what would improve it."],
    ["Read", "1 min", "Plate reads with vehicle type and colour. Vehicle and person counts on every camera, at once."],
    ["Trace", "2 min", "The registration you give: a 24-hour look-back, then its journey — stops, legs, near misses marked."],
    ["Alert", "1 min", "The next pass raises a live alert with its evidence crop. Acknowledge, close; every step audited."],
    ["Zone", "1 min", "An intrusion zone drawn on live video. The alert carries counts and dwell, never an image."],
    ["Report", "1 min", "Detected plates with timestamps as PDF and CSV, and the audit trail behind the session."],
  ];
  const colW = (W - 2 * M) / steps.length;
  steps.forEach(([name, t, desc], i) => {
    const x = M + i * colW;
    if (i < steps.length - 1) s.addShape(pres.shapes.LINE, { x: x + 0.5, y: 2.21, w: colW - 0.5, h: 0, line: { color: C.line, width: 2 } });
    numDot(s, x + 0.08, 2.0, i + 1, i === 3 ? C.red : C.cyan);
    s.addText(name, { x, y: 2.62, w: colW - 0.15, h: 0.4, fontFace: FONT, fontSize: 19, bold: true, color: C.ink, margin: 0, isTextBox: true });
    s.addText(t, { x, y: 3.02, w: colW - 0.15, h: 0.3, fontFace: FONT, fontSize: 13, bold: true, color: C.cyan, margin: 0, isTextBox: true });
    s.addText(desc, { x, y: 3.4, w: colW - 0.18, h: 2.1, fontFace: FONT, fontSize: 11.5, color: C.slate, margin: 0, valign: "top", isTextBox: true });
  });
  card(s, M, 5.7, W - 2 * M, 1.2, C.soft, C.soft);
  s.addText([
    { text: "What is real on stage. ", options: { bold: true, color: C.ink } },
    { text: "The cameras are the organisers' live feeds. The watchlist entries you give us are real; VAHAN and eGujCop are mock adapters over fixture files, and we say so. Plates are read where a camera's view allows it; every other camera is counted. The intrusion zone goes on a government camera with people in view, or on stock footage, and we say which.", options: { color: C.slate } },
  ], { x: M + 0.25, y: 5.7, w: W - 2 * M - 0.5, h: 1.2, fontFace: FONT, fontSize: 12.5, valign: "middle", margin: 0, isTextBox: true });
  s.addNotes("The order and the click path are docs/demo-runbook.md section 3; the times are targets for a 7-10 minute slot, and the slot length, format and hardware were not confirmed by the organisers when this deck was made, so the Timekeeper scales them on the day. Onboard: the organisers' feeds are expected to arrive as stream addresses and names, as the sandbox's did; one camera goes in through the onboarding card on the projector (the stream address box hides its credentials), the rest by scripts/onboard_urls.py from laptop B. View: map, video wall (Fill with online), then Health & Reports → Plate-reading quality by camera: it grades what each camera captures and gives advice (zoom, shutter, infrared, re-aim); on the 120 blind-checked plates the grade did not predict which reads were right, so it describes the camera, not the read. Read: Overview → Recent plate reads with the vehicle column; Vehicles and People in view tiles, counted per camera per minute on every camera by the counts-only worker on laptop B (slide 4). Trace: Watchlist → Add entry with the plate as given (the reply says whether it was seen in the last 24 h; one retrospective alert carries the time it was seen), then Vehicle search → the journey view (slide 5). Alert: the next pass raises the live alert; a one-character near miss is shown as 'read ≈ watchlist' and marked 'check the crop'; a single read on a slow camera alerts only on an exact match. Zone: drawn on the tile; the worker that counts that camera reads zones when it starts, so the zone is drawn before laptop B starts; fallback is the demo zone on AMD-TRAF-001 (Pexels stock footage) and we say so. Report: scripts/detection_report.py → HTML, PDF, CSV with a SHA-256 per evidence crop (an integrity check, not a signature). If anything fails under time pressure, the backup videos (Sentinel-Demo.mp4, Sentinel-Gov-Demo.mp4) are narrated and the live system offered again after.");
}

// 3 ─ The government feeds, measured (sandbox.json; the blind check in sandbox_review.json)
{
  const s = slide();
  kicker(s, "The organisers' feeds · measured 25–26 Sep");
  title(s, `The organisers' ${S.cameras} cameras: onboarded, viewed, analysed — and the plates checked blind`, false, { size: 28 });
  framed(s, SCR("gov-wall"), M, 1.95, 7.0, 7.0 * 928 / 1902);        // 1902 x 928 screenshot
  const rows = [
    [`${S.cameras} / ${S.cameras}`, `onboarded by RTSP address, ${p0.toFixed(1)}–${p1.toFixed(1)} s each · ${S.codecs.join(" and ")}, 960×576 to 2560×1440`, undefined],
    [`${B.exact} / ${B.plates}`, `real Gujarat plates stored exactly right (${PCT(B.exact, B.plates)}); ${within1} within one character. Checked blind by one team member against each crop`, C.green],
    [`${hi.exact} / ${hi.plates}`, `exact where Sentinel's own confidence is 0.9 or above (${PCT(hi.exact, hi.plates)}); ${low.exact} of ${low.plates} between 0.5 and 0.7`, undefined],
    [`2 / ${S.cameras}`, "views where plates are readable (CAM06, CAM07). The Health page grades every camera and says why", undefined],
  ];
  rows.forEach(([v, l, col], i) => stat(s, 8.0, 1.8 + i * 1.12, 4.75, v, l, { size: 30, color: col, labelSize: 12 }));
  card(s, M, 5.55, 3.42, 1.0, C.paleAmber, C.paleAmber);
  s.addText([{ text: "Capture on real plates: unmeasured. ", options: { bold: true, color: C.amber } },
    { text: "The blind check judges plates Sentinel stored (precision). A plate it never stored cannot be counted.", options: { color: C.slate } }],
    { x: M + 0.18, y: 5.55, w: 3.1, h: 1.0, fontFace: FONT, fontSize: 10.5, valign: "middle", margin: 0, isTextBox: true });
  card(s, M + 3.58, 5.55, 3.42, 1.0);
  s.addText([{ text: `${STOCK.exact} exact · stock footage, synthetic plates. `, options: { bold: true, color: C.ink } },
    { text: `AMD-TRAF-002 (Pexels traffic, registrations painted on): ${STOCK.n}; capture ${STOCK.capture}. Not Gujarat plates.`, options: { color: C.slate } }],
    { x: M + 3.76, y: 5.55, w: 3.1, h: 1.0, fontFace: FONT, fontSize: 10.5, valign: "middle", margin: 0, isTextBox: true });
  caption(s, `Recorded footage the organisers replay as live streams, looping. Positions are our reading of the camera names (${S.placed} of ${S.cameras} placed). bench/results/sandbox.md, sandbox_review.md, capture_quality.md, anpr_eval_current.md.`, M, 6.62, W - 2 * M, 0.42);
  s.addNotes(`Lead with the real-plate figure. The organisers' sandbox, 25 Sep: ${S.cameras} government cameras replaying recorded footage on a common timeline, looping. Every camera was onboarded by its RTSP address in ${p0.toFixed(1)}–${p1.toFixed(1)} s (median 1.1 s), shown on the wall and analysed for vehicle and person counts, 4 at a time in rotation on one GTX 1650 Ti laptop (${S.frames.toLocaleString("en-US")} frames). Plates were readable on 2 of the 30 views (CAM06, CAM07): the rest are overview or red-light views, several recorded at night, where plates are too small to read; the Health page's plate-reading quality grades say so per camera (CAM06 and CAM07 marginal, median plates 104 and 106 px across; the rest counts-only, including the five the registry had marked ANPR-viable). The grade describes the camera and drives the advice; on the 120 blind-checked plates it did not predict which reads were right (good 80.3%, marginal 65.9%, poor 80.0% exact), and Sentinel's own confidence did, so never call it a readability score (bench/results/capture_quality.md). The blind check, 26 Sep: one team member checked ${B.sightings} real sightings on the Plate review page; the page shows only the crop, the reviewer types the plate, the server grades it against the stored read. ${B.verdicts.not_a_plate} were a hoarding's phone number (not a plate; a rule added on 26 Sep now drops such reads). Of the ${B.plates} vehicle plates: ${B.exact} exact (${PCT(B.exact, B.plates)}), ${within1} within one character (${PCT(within1, B.plates)}), ${B.verdicts.wrong} wrong, none unreadable. By confidence: at 0.9 or above ${hi.exact} of ${hi.plates} exact and ${hi.exact + hi.one_off} within one character; 0.7-0.9: ${mid.exact} of ${mid.plates}; 0.5-0.7: ${low.exact} of ${low.plates}. One reviewer so far: on our own cameras, where the plates are known, the same reviewer was right 222 times in 226 (review_truth.md). An earlier check by our AI coding assistant with the read in view (92 of 107, not blind) was optimistic and is quoted only as that; its later review of the 30 misses (blind_errors.md) corrects nothing: only a second blind reviewer can move 90 of 120, and no estimated corrected figure is ever quoted. By run: 54 of 75 in the 25 Sep evening run and 36 of 45 in the 26 Sep morning run; both replayed the same looping clips, each camera's recorded at one time of day, so that is not day against night (sandbox_daynight.md). Capture on real plates is unmeasured: the check judges stored plates only. The second figure, ${STOCK.exact} exact and ${STOCK.capture} capture, is the pipeline on real traffic with synthetic plates painted onto Pexels stock footage (AMD-TRAF-002, 24 Sep, 4 cameras, bench/results/anpr_eval_current.md): it says nothing about Gujarat plates. The sandbox itself drops every session about every 45 s and has locked the team's login twice after reconnect storms: the worker backs off to 30 s and nothing probes in a loop.`);
}

// 4 ─ Production-scale on stage: the counts-only worker (counts_capacity.json) and the two-laptop topology
{
  const s = slide();
  kicker(s, "New since the submission · measured 7 Oct");
  title(s, "Every camera analysed at once: plates where they can be read, counts and zones everywhere else", false, { size: 28 });
  s.addChart(pres.charts.BAR, [{ name: "CPU cores", labels: CC.map((r) => `${r.streams}`), values: CC.map((r) => r.cpu_cores) }],
    { x: M, y: 1.95, w: 6.2, h: 3.35, barDir: "col", chartColors: [C.cyan],
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 12, dataLabelColor: C.slate, dataLabelFormatCode: "0.00",
      showLegend: false, showTitle: true, title: "CPU cores used by the counts-only worker, by streams counted at once", titleFontSize: 13, titleColor: C.ink, titleFontFace: FONT,
      catAxisTitle: "streams", showCatAxisTitle: true, catAxisTitleFontSize: 11, catAxisTitleColor: C.muted,
      catAxisLabelColor: C.muted, catAxisLabelFontSize: 12, valAxisLabelColor: C.muted, valAxisLabelFontSize: 10,
      valAxisMaxVal: 4, valAxisMinVal: 0, valAxisMajorUnit: 1, valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" } });
  s.addText([
    { text: `Frames counted per stream, median: ${CC.map((r) => r.per_stream_fps_median.toFixed(2)).join(" · ")} a second. `, options: { bold: true, color: C.ink } },
    { text: `${c40.streams} streams hold at ${c40.per_stream_fps_median} with the GPU ${c40.gpu_util_mean.toFixed(0)}% busy; ${c50.streams} saturate (${c50.per_stream_fps_median}). One GTX 1650 Ti laptop, keyframes only, no plate worker running at the same time; the relay's own CPU is not included.`, options: { color: C.slate } },
  ], { x: M, y: 5.4, w: 6.2, h: 1.3, fontFace: FONT, fontSize: 12, valign: "top", margin: 0, isTextBox: true });
  const lap = [
    ["Laptop A · the projector", "Database, API, relay and the control room. The plate worker at full rate on the plate-readable cameras: 4 streams at ~4.5 fps with object detection (8 at 2.9 without)."],
    ["Laptop B · the operator", "The counts-only worker on every other camera (30–40) from keyframes: vehicle and person counts and intrusion zones, about one frame a second each. Also the hot spare: a database backup every 10 minutes."],
  ];
  lap.forEach(([h, b], i) => {
    const y = 1.95 + i * 1.95;
    card(s, 7.1, y, 5.63, 1.8, C.white, C.line);
    s.addText(h, { x: 7.35, y: y + 0.15, w: 5.2, h: 0.4, fontFace: FONT, fontSize: 17, bold: true, color: C.ink, margin: 0, isTextBox: true });
    s.addText(b, { x: 7.35, y: y + 0.58, w: 5.2, h: 1.15, fontFace: FONT, fontSize: 12.5, color: C.slate, margin: 0, valign: "top", isTextBox: true });
  });
  const tiles = [[`${c40.streams}`, "streams counted at once"], [`${c40.cpu_cores.toFixed(1)}`, "CPU cores at 40 streams"], [`${c40.gpu_util_mean.toFixed(0)}%`, "GPU busy at 40 streams"]];
  tiles.forEach(([v, l], i) => {       // value over label: the tile() layout has no room for a label beside a number here
    const x = 7.1 + i * 1.91;
    card(s, x, 5.85, 1.81, 1.0);
    s.addText(v, { x: x + 0.15, y: 5.85, w: 1.55, h: 0.55, fontFace: FONT, fontSize: 24, bold: true, color: C.ink, valign: "bottom", margin: 0, isTextBox: true });
    s.addText(l, { x: x + 0.15, y: 6.42, w: 1.55, h: 0.4, fontFace: FONT, fontSize: 10.5, color: C.slate, valign: "top", margin: 0, isTextBox: true });
  });
  s.addNotes(`This is the Plan for Scale's tier B keyframe profile, which the written pack called 'sized but not yet built': built on 7 Oct, measured on one laptop. The counts-only worker (services/analytics/sentinel_analytics/counts.py, python -m sentinel_analytics.counts) decodes keyframes only (PyAV skip_frame) and runs the stock COCO detector on them in batches, beside the unchanged plate worker; a camera whose keyframes are more than 4 s apart is decoded in full (on the sandbox CAM07, CAM17 and CAM18 keyframe every 10-15 s). Conditions of the chart (bench/results/counts_capacity.md, 7 Oct 21:28 IST): RTSP sessions through the local relay cycling over the 14 simulator cameras (H.264 and H.265, 704x576 to 1920x1080, 12-25 fps, keyframes every 1-2 s), yolo11n on CUDA at 640, batches of up to 16, at most 1 frame/s per stream, 15 s to connect then 45 s measured per row; the relay's CPU is not included and no plate worker ran at the same time. A stream's rate is capped by its keyframe interval, so 0.5-1 frame/s is the most this profile counts; counts are per minute, so that is enough. On the sandbox's own cameras (counts_sandbox.md): 7 cameras counted at 14-34 frames a minute each while the sandbox dropped every session about every 45 s. Unmeasured, and say so if asked: the combined load of a plate worker and the counts worker on one machine; count accuracy (per-frame COCO detections; no auto-rickshaw class; misses at night); the Plan for Scale's 250 streams per node stays an assumption until measured on server hardware. The two-laptop topology: both GTX 1650-class with 4 GB; A runs the core and the plate worker on a fixed plate group that is also listed in B's COUNTS_EXCLUDE so a zone never alerts twice; B reaches A's relay through RELAY_HOST and the control room opens from B through CORS_ORIGIN_REGEX (scripts/lan.ps1 sets both); no rotation during the slot. Hot spare: scripts/db_backup.ps1 every 10 minutes to a USB stick with the crops, scripts/db_restore.ps1 on B, and the relay rebuilds every camera path from the registry within about 20 s. Settings: COUNTS_FPS 1.0, COUNTS_MAX_STREAMS 60, COUNTS_EXCLUDE, COUNTS_BATCH, COUNTS_WORKER_ID; count rows carry detail.profile ('keyframes' or 'every-frame').`);
}

// 5 ─ The designated vehicle
{
  const s = slide();
  kicker(s, "The live test case's core ask");
  title(s, "The registration you give us: its last 24 hours, then its journey", false, { size: 30 });
  framed(s, SCR("search"), M, 1.95, 8.2, 4.6125);
  caption(s, "Journey view on the simulator, which loops the same vehicles past every camera: the 7 km leg is flagged implausible, as a cloned plate would be on real feeds. All plates synthetic.", M, 6.62, 8.2, 0.42);
  bullets(s, [
    ["Retrospective hit:", "adding the plate checks the last 24 hours at once; one alert carries the time it was actually seen."],
    ["A journey, not a list:", "reads grouped into stops with dwell, legs with straight-line distance, time and average speed, numbered on the map."],
    ["Near misses kept, marked:", "a stop made only of one-character reads is a possible misread and never used for a speed; a read below 0.9 says “check the crop”."],
    ["Cloned plate or misread:", "a leg faster than 150 km/h over 1 km or more is flagged implausible."],
    ["Evidence:", "a crop per stop, CSV export; the search carries a stated purpose into the audit trail."],
  ], 9.3, 1.95, 3.45, 4.8, { size: 12.5, gap: 8 });
  s.addNotes("Identify, trace and present the movement of a designated vehicle: the judges give a registration; Watchlist → Add entry (kind bolo, severity high, the case reference as the FIR field) answers at once whether it was seen in the last 24 hours, on how many cameras, and raises one retrospective alert with the original time; Vehicle search with 'tolerate 1 OCR error' ticked and the purpose filled in opens the journey view. Only cameras that were being analysed when the vehicle passed have sightings: on stage that is the plate-readable cameras on laptop A, at full rate, with no rotation. Distances are straight lines between camera positions, not road distances, and the speeds are averages from them; on the organisers' feeds the positions are our reading of the camera names (24 of 30 placed), so they are approximate and the legs are indicative. The implausible-leg flag (over 150 km/h across 1 km or more) is a prompt for a person: a cloned plate, a misread, or two cameras whose positions we placed wrongly. Timestamps are frame times from the stream, not arrival times. The 'check the crop' mark on a read below 0.9 is the G3 confidence marking adopted on 8 Oct (slide 6).");
}

// 6 ─ Honest ANPR, usable ANPR (bands from sandbox_review.json; G3 verdict from g3_wiring.json)
{
  const s = slide();
  kicker(s, "Confidence routing");
  title(s, "75% exact on real plates is usable when every read says how sure it is", false, { size: 30 });
  const bands = [["0.5 – 0.7", low], ["0.7 – 0.9", mid], ["≥ 0.9", hi]];
  s.addChart(pres.charts.BAR, [{ name: "Exact", labels: bands.map(([l]) => l), values: bands.map(([, b]) => +(100 * b.exact / b.plates).toFixed(1)) }],
    { x: M, y: 1.95, w: 4.6, h: 3.3, barDir: "col", chartColors: [C.green],
      showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 13, dataLabelColor: C.ink, dataLabelFormatCode: "0.0\"%\"",
      showLegend: false, showTitle: true, title: "Real plates exact, by Sentinel's confidence (blind check)", titleFontSize: 12.5, titleColor: C.ink, titleFontFace: FONT,
      catAxisTitle: "OCR confidence of the stored read", showCatAxisTitle: true, catAxisTitleFontSize: 11, catAxisTitleColor: C.muted,
      catAxisLabelColor: C.muted, catAxisLabelFontSize: 12, valAxisLabelColor: C.muted, valAxisLabelFontSize: 10,
      valAxisMaxVal: 100, valAxisMinVal: 0, valAxisMajorUnit: 20, valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" } });
  s.addText(`${low.exact} of ${low.plates} · ${mid.exact} of ${mid.plates} · ${hi.exact} of ${hi.plates} plates; one plate at 0.35–0.5 left out. Precision on stored reads; capture unmeasured. bench/results/sandbox_review.md`,
    { x: M, y: 5.3, w: 4.6, h: 0.8, fontFace: FONT, fontSize: 10.5, italic: true, color: C.muted, margin: 0, valign: "top", isTextBox: true });
  // The marks on screen: the live control room on 8 Oct with G3 on (1582 x 904 screenshots; synthetic simulator plates)
  const sw = 3.6, sh = sw * 904 / 1582;
  framed(s, SCR("alerts-check-crop"), 5.5, 1.95, sw, sh);
  caption(s, "Alerts, 8 Oct: a stolen-vehicle hit and a one-character match, both tagged “check the crop”. Synthetic plates.", 5.5, 1.95 + sh + 0.1, sw, 0.42);
  framed(s, SCR("review-low-band"), 5.5, 4.55, sw, sh);
  caption(s, "Plate review: the new “Below 0.9, unchecked” queue.", 5.5, 4.55 + sh + 0.1, sw, 0.3);
  const cards = [
    ["Route by confidence", `Reads at 0.9 or above can pass (${hi.exact} of ${hi.plates} exact); the rest go to a person. How the toll and highway ANPR systems work, and how 75% becomes usable.`],
    ["“Check the crop”: gate passed 8 Oct", "A read below 0.9, or an alert on a one-character match, is marked in alerts, search, the journey and the live toast. Nothing is suppressed; no alert rule changed."],
    ["Plate review: the human check", "Blind: the crop only; the reviewer types the plate; the server grades it, per camera and band. The step the Indian highway and toll ANPR specs build in before anyone acts on a read."],
  ];
  cards.forEach(([h, b], i) => {
    const y = 1.95 + i * 1.6;
    card(s, 9.4, y, 3.33, 1.5, C.white, C.line);
    s.addText(h, { x: 9.58, y: y + 0.1, w: 3.0, h: 0.36, fontFace: FONT, fontSize: 13.5, bold: true, color: i === 1 ? C.green : C.ink, margin: 0, isTextBox: true });
    s.addText(b, { x: 9.58, y: y + 0.48, w: 3.0, h: 1.0, fontFace: FONT, fontSize: 10.5, color: C.slate, margin: 0, valign: "top", isTextBox: true });
  });
  s.addNotes(`The honest way to use a 75%-exact figure is to route by confidence, as the toll and highway systems do: IHMCL's free-flow toll spec has a separate control-centre team validate low-confidence cases, and NHAI's highway spec has an operator check every machine-read plate against the image before an e-challan (docs/commercial-anpr.md, internal research note; those tenders ask for 99% accuracy on purpose-built ANPR cameras, which these government views are not). On the 120 blind-checked plates Sentinel's confidence separated right from wrong: ${hi.exact} of ${hi.plates} exact at 0.9 or above against 21 of 39 below. G3 confidence marking (API setting CONFIDENCE_MARKING, default on since 8 Oct; services/api/sentinel_api/marking.py): a stored read below 0.9 (compared as the review page bands it, rounded to 3 decimals) or a watchlist alert on a one-character match is marked 'check the crop' in alerts, search, the journey view and the live toast; the Plate review page gains a 'Below 0.9, unchecked' filter; each sighting stores reads and agreement (the vote's weakest position's winning share). Nothing is suppressed and no alert rule changes. Gate (bench/pipeline_gates.md G3; verdict ${G3.verdict} in bench/results/g3_wiring.md, 8 Oct): the T block (pytest test_marking.py and the live bench/g3_check.py, marking off and on) and the L wiring pair (B's marked share, 161 of 748 scored sightings, equals anpr_eval's below-0.9 count exactly; median latency 1.68 s against A's 2.25 s; the alert count equal off and on); the F leg (a fresh real-plate set by band) was not run because sandbox-fresh-v1 was never frozen, so no claim that confidence separates right from wrong is made beyond the 120 blind-checked plates: the marking ships as a review aid. The Plate review page (/review; admin, supervisor, auditor): blind mode shows only the crop, the reviewer types the plate (? unreadable, - not a plate) and the server derives the verdict; verify mode shows the read and asks for confirmation; the two are never mixed and only blind numbers are quoted. The auditor role can review crops without being able to search plates or watch video. The reviewer's own reliability: 222 of 226 on our own plates where the truth is known (review_truth.md). One reviewer so far; a second blind reviewer is the next step, not an AI estimate.`);
}

// 7 ─ Beyond ANPR, without identity
{
  const s = slide();
  kicker(s, "Beyond ANPR");
  title(s, "Counts, type and colour, intrusion zones: presence, never identity", false, { size: 30 });
  framed(s, SCR("objects-AMD-TRAF-002"), M, 1.95, 6.9, 6.9 * 1080 / 1920);
  caption(s, "Worker view of AMD-TRAF-002: stock traffic footage replayed by the simulator, every number plate replaced by a synthetic registration.", M, 5.95, 6.9, 0.5);
  bullets(s, [
    ["Counts, not tracks:", "one row per camera per minute: frames analysed, average and peak in view per class. Now on every camera at once, from keyframes. No box, image or track of a person is kept."],
    ["What each plate is on:", "type from the vehicle box the plate sits in, colour from its body panels; unsure means blank, not a guess."],
    ["Intrusion zones:", "drawn on the live picture, with classes, dwell and armed hours. One alert per occupancy, holding the zone, the count and the dwell; the operator opens the live view to see who."],
    ["No face recognition, by design:", "proportionality and the DPDP Act. If it were mandated: one more detector into the same watchlist and alert path, under a lawful order, gallery governance and a bias test (HLD 7.4)."],
  ], 7.8, 1.95, 4.93, 4.9, { size: 12.5, gap: 9 });
  s.addNotes("Evaluation area 5 names vehicle and person detection, object detection and intrusion detection. The second model in the worker is stock COCO weights (yolo11n); on the plate cameras it runs on the frames ANPR already pulls, and since 7 Oct the counts-only worker runs it on keyframes of every other camera (slide 4). Counts are aggregates with a frame denominator: a zero on a synthetic camera is an honest zero. Type is the COCO class of the box the plate sits in, voted across the vehicle's reads; bus and truck are often confused and auto-rickshaws have no class, so they stay blank; colour is a heuristic over body panels that abstains on infrared frames and two-wheelers. Neither type, colour nor the counts are measured on Gujarat footage: say so if asked. Intrusion zones reuse the same boxes: a person is inside when the bottom centre of the box (where they stand) falls in the polygon; an occupancy ends after the zone has looked empty for 2.5 analysis intervals; one event per occupancy and at most one alert per zone per camera every 120 s; the alert stores zone, classes, peak count and dwell, never a crop, box or track, and the smoke test checks that no count row carries a box or track. Measured on one stock clip only (24 Sep, AMD-TRAF-001, bench/zone_check.py: 14 events in 15 minutes, 6 alerts after the cooldown, riders beside the zone did not trigger): it shows the mechanism, not a false-alarm rate, and the detector misses people at night, far away and in crowds. Face recognition is not built, by choice; ENABLE_FACE_RECOGNITION exists only to make the choice visible. Wanted and missing persons are handled through their vehicles.");
}

// 8 ─ Architecture and scale in one slide
{
  const s = slide();
  kicker(s, "Architecture and scale");
  title(s, "Edges analyse, the core keeps metadata: sized for 80,000 cameras, every assumption labelled", false, { size: 28 });
  s.addImage({ path: DIA("d1-architecture"), x: M, y: 1.9, w: 7.4, h: 7.4 * 1360 / 2400 });
  caption(s, "Tiers in the model: A plates 8,000 cameras at 5 fps · B events 16,000 at 1 fps (the keyframe counts profile, now built and measured on one laptop) · C view only 56,000, relayed while watched. Tier shares, streams per node and unit prices are ASSUMPTIONS; bench/capacity.py derives every figure from them.", M, 6.15, 7.4, 0.85);
  const tiles = [
    [SCALE.nodes, "edge GPU nodes, about 7.5 per district; streams per node is an ASSUMPTION until measured on server hardware", C.ink],
    [SCALE.meta, `of metadata across the backbone on average, where carrying every main stream to a central VMS would take ${SCALE.video} (64 Gbps for sub-streams)`, C.cyan],
    [SCALE.tco, `over five years: ${SCALE.capex} hardware + ${SCALE.impl} implementation + ${SCALE.opex} operating; ${SCALE.perCam} per camera per month`, C.ink],
    [SCALE.ingest, "sightings ingested and matched against 100,000 watchlist entries at statewide size on this laptop: a floor for the core, not a sizing", C.green],
  ];
  tiles.forEach(([v, l, col], i) => tile(s, 8.3, 1.9 + i * 1.25, 4.43, 1.13, v, l, { color: col, size: 24, vw: 1.55, labelSize: 10.5 }));
  s.addNotes(`Three zones: departments keep everything they have; each district edge runs a media relay and GPU analytics nodes beside the cameras; the state core holds the registry, sightings, watchlist matcher, audit log and the government DB adapters; control rooms get live video from the district relay and alerts from the core. If the core is unreachable the edge spools sightings to disk and replays them with their original times (tested 24 Sep with an 87 s API outage: 21 of 21 replayed). Every scale figure is the capacity model in docs/plan-for-scale.md (HLD v${HLD_VERSION}; bench/capacity.py), not a statewide measurement: 248 single-GPU edge nodes at ₹15 lakh each (about ₹39.7 crore of hardware), five-year total ₹100.7 crore = hardware 39.7 + one-time implementation 9.9 + operating 51.0, ₹210 per camera per month across all 80,000 cameras (₹699 per analysed camera). Sensitivity: at 30 tier-A streams per node the five-year total is ₹141.7 crore; at 90, ₹86.8 crore; at a 5% tier-A share, ₹79.9 crore. The two levers that dominate, the share of cameras that need plate reading and streams per GPU node, are the pilot's first measurements; the registry replaces the tier-share assumption camera by camera. Bandwidth: about 2.7 Mbps of plate metadata statewide (4.6 Mbps with counts, 40.1 Mbps with crops), against 320 Gbps to carry 80,000 main streams at 4 Mbps centrally. The core at statewide size was measured on one laptop (bench/results/core_scale.md, 24 Sep): 80,000 cameras, 3 million sightings, 100,000 watchlist entries; 706 sightings/s ingested and matched against a modelled average of 556/s; state map 161 ms, a 30-day movement history 337 ms. The tier B profile the counts-only worker implements was measured at 40 streams on one laptop (slide 4); the Plan's 250 streams per node for it stays an assumption.`);
}

// 9 ─ Security and privacy: this week's hardening, one honest line each
{
  const s = slide();
  kicker(s, "Security and privacy");
  title(s, "Hardened this week, said plainly: what the PoC does, what production adds", false, { size: 30 });
  s.addText("DONE SINCE 26 SEP, IN THE CODE", { x: M, y: 1.9, w: 6.3, h: 0.3, fontFace: FONT, fontSize: 11, bold: true, color: C.cyan, charSpacing: 1.5, margin: 0, isTextBox: true });
  bullets(s, [
    ["Secrets:", "the laptop ran on the repo's example values; scripts now replace them, the API warns loudly at start if one is still an example, and a security check fails on it."],
    ["Relay:", "a camera's picture cannot be replaced from the LAN (publishing needs the credential). Viewing is still open on the LAN: the relay's authorisation hook is roadmap."],
    ["Control plane:", "database, cache, relay API and the simulator's outage switch listen on this host only."],
    ["Sign-in:", "password hashing off the event loop; a per-address limit on attempts (429)."],
    ["Ingest:", "key compared in constant time; event times timezone-aware and within 14 days; batches capped at 5,000; a replayed batch is never stored twice."],
    ["Registry:", "camera code and stream address validated on every write path; stream credentials masked in the camera list, the CSV export and the onboarding card."],
    ["Logs and audit:", "the API's access log is off (plate searches, tokens in URLs); plate text masked in worker logs; watchlist checks, recent-sighting reads and the registry export audited; district-only users no longer statewide."],
    ["Evidence:", "a SHA-256 per crop in the detection report: an integrity check, not a signature."],
  ], M, 2.25, 6.3, 4.7, { size: 11, gap: 5 });
  s.addText("STILL OPEN IN THE POC · PRODUCTION ADDS", { x: 7.3, y: 1.9, w: 5.43, h: 0.3, fontFace: FONT, fontSize: 11, bold: true, color: C.amber, charSpacing: 1.5, margin: 0, isTextBox: true });
  bullets(s, [
    ["Open:", "live viewing unauthenticated on the local network; VAHAN and eGujCop are mock adapters; one blind reviewer; no signed evidence."],
    ["Production:", "state SSO with MFA · vault-held credentials · RBAC enforced at the media relay · camera VLANs · mTLS edge ↔ core · signed evidence · CERT-In reporting · STQC audit."],
  ], 7.3, 2.25, 5.43, 2.3, { size: 11.5, gap: 6 });
  tile(s, 7.3, 4.55, 5.43, 0.95, `${TESTS.unit} · ${TESTS.security} · ${TESTS.smoke}`, "unit tests · negative security checks · end-to-end checks, all passing", { color: C.green, size: 20, vw: 2.2, labelSize: 11 });
  card(s, 7.3, 5.65, 5.43, 1.25, C.paleGreen, C.paleGreen);
  s.addText([{ text: "No face recognition, by design. ", options: { bold: true, color: C.green } },
    { text: "Append-only audit of every plate search, movement query and operator action; five roles with department and district scope in SQL; metadata and small crops only, video stays on department recorders.", options: { color: C.slate } }],
    { x: 7.5, y: 5.65, w: 5.05, h: 1.25, fontFace: FONT, fontSize: 11.5, valign: "middle", margin: 0, isTextBox: true });
  s.addNotes(`Each line on the left is in the working tree as of 8 Oct; say what it is and no more. Secrets: the demo laptop had been running on .env.example's values, so anyone on the LAN who read the public repository could have signed in as admin, fabricated sightings with the ingest key or published over a camera; scripts/set_passwords.py and scripts/rotate_secrets.py replace them, main.py logs an error at start for any secret still at its example value, and security_checks.py fails if the live .env matches the example or the admin password is the dev default. Relay: MediaMTX paths carry overridePublisher: no and publishing needs the publisher credential, so a picture cannot be replaced from the LAN; reading remains open to anyone on the LAN (authInternalUsers: any, read), which is the roadmap's relay authorisation hook. Control plane: Postgres, Valkey, the relay's control API and metrics, and the simulator's control port 8010 (whose outage switch had no auth) bind to 127.0.0.1. Sign-in: argon2 verification runs in a thread pool and more than a set number of attempts a minute from one address is refused with 429 before the password is checked. Ingest: secrets.compare_digest on the key; a naive or far-off event_ts is refused as 422 so one bad row does not stall the batches behind it; MAX_BATCH 5000; batch ids stop a replayed batch being stored twice. Registry: cameras_repo.validate_fields on every write path; rtsp_url masked in GET /cameras, the CSV export and the onboarding card (type=password with show/hide); scripts/onboard_urls.py onboards a CSV of credentialed addresses through the relay so credentials never reach the registry. Logs: uvicorn runs with --no-access-log; the worker and sink mask plate text at INFO; the audit now covers watchlist.check, sightings.recent and camera.export; a user scoped to a district alone is no longer statewide; enum query parameters are Literal types (422, not 500). Evidence: detection_report.py writes a SHA-256 per crop, which detects a changed file but does not prove who wrote it; signed evidence is a production item. Test counts: ${TESTS.unit} unit tests (pytest --collect-only, 9 Oct), ${TESTS.security} negative security checks as the script runs (crops 4, quality report 1, write scope 4, ingest 3, review 3, secrets 2, LAN 6; a count of check( calls in the file gives 19 because its control-plane loop covers five ports), ${TESTS.smoke} end-to-end checks. Privacy: no face recognition by design (HLD 7.4 gives the route if mandated); the auditor role can read the audit trail and review crops but cannot search plates or watch video; UPDATE and DELETE on the audit table are no-ops. docs/privacy-dpdp.md holds the DPDP position.`);
}

// 10 ─ Since the submission, and the pilot in 90 days
{
  const s = slide(true);
  kicker(s, "Since the submission · 26 Sep → 10 Oct", true);
  title(s, "What was built, what passed its gate, what was tried and not adopted, what is not built", true, { size: 28 });
  const cols = [
    ["BUILT", C.green, "0F2A44", [
      "Counts-only worker: every camera counted at once, from keyframes; 40 streams on one laptop",
      "Two-laptop topology: RELAY_HOST, LAN scripts, hot spare with a 10-minute backup",
      "Reliability: services restart with Docker, relay image pinned, API waits for the database",
      `Security: the hardening on slide 9; new security checks and unit tests (${TESTS.security} and ${TESTS.unit}, all passing)`,
    ]],
    ["PASSED ITS GATE", C.cyanL, "0F2A44", [
      "G3 confidence marking: “check the crop” on reads below 0.9 and one-character alerts",
      `Verdict ${G3.verdict}, 8 Oct; default on; a setting restores the 26 Sep behaviour`,
      "No claim beyond the 120 blind-checked plates: the fresh-set leg was not run",
    ]],
    ["TRIED, NOT ADOPTED", "FBBF24", "2A2410", [
      `OCR fine-tune ft1: non-inferior on real plates (${FT1.base} → ${FT1.cand} of ${FT1.n} exact; ${FT1.fixed} fixed, ${FT1.broken} broken, p = 1.0), no gain`,
      "The shipped reader stays; every accuracy figure in the pack still describes the build that runs",
    ]],
    ["NOT BUILT", "FCA5A5", "2A1414", [
      "YOLOX licence-clean detectors: not trained; the pilot's plan, with gates written before training",
      "Tracker and detector changes G0, G2, G2b, G4, G5, G6: not built, not adopted",
      "A frozen fresh real-plate set and a second blind reviewer: still to do",
    ]],
  ];
  const cw = (W - 2 * M - 3 * 0.2) / 4;
  cols.forEach(([h, col, fill, items], i) => {
    const x = M + i * (cw + 0.2);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 1.95, w: cw, h: 3.15, rectRadius: 0.12, fill: { color: fill }, line: { color: "1E3A5F", width: 1 } });
    s.addText(h, { x: x + 0.2, y: 2.05, w: cw - 0.4, h: 0.35, fontFace: FONT, fontSize: 12, bold: true, color: col, charSpacing: 1.5, margin: 0, isTextBox: true });
    bullets(s, items, x + 0.2, 2.45, cw - 0.4, 2.6, { size: 11, dark: true, gap: 5 });
  });
  s.addText("THE PILOT IN 90 DAYS", { x: M, y: 5.3, w: 6, h: 0.3, fontFace: FONT, fontSize: 11, bold: true, color: C.cyanL, charSpacing: 1.5, margin: 0, isTextBox: true });
  const pilot = ["One district's edge node on server hardware: streams per node measured, not assumed", "Real VAHAN and eGujCop access behind the adapter contract", "State SSO; authorisation at the relay",
    "A second blind reviewer and a frozen fresh set; count accuracy measured", "YOLOX detectors through their gates; ONVIF discovery"];
  pilot.forEach((t, i) => {
    const x = M + i * ((W - 2 * M - 4 * 0.15) / 5 + 0.15), w = (W - 2 * M - 4 * 0.15) / 5;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.65, w, h: 0.95, rectRadius: 0.1, fill: { color: C.ink2 }, line: { color: "1E3A5F", width: 1 } });
    s.addText(t, { x: x + 0.12, y: 5.65, w: w - 0.24, h: 0.95, fontFace: FONT, fontSize: 10.5, color: "CBD5E1", valign: "middle", margin: 0, isTextBox: true });
  });
  s.addText("One registry. One map. One viewer. Integrate, don't replace.", { x: M, y: 6.65, w: W - 2 * M, h: 0.4, fontFace: FONT, fontSize: 18, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addNotes(`Everything here is in bench/results/pipeline_gates_results.md (the index of the finale gates) or in the working tree. Built: the counts-only worker (counts_capacity.md, counts_sandbox.md); RELAY_HOST, CORS_ORIGIN_REGEX, scripts/lan.ps1, .env.b.example; restart: unless-stopped on Postgres, Valkey and MediaMTX after the core stayed down on the 7 Oct reboot; the MediaMTX image pinned by digest; api.ps1 waits for Postgres and runs python -m uvicorn with --no-access-log; demo_prep.py refuses to delete sightings on cameras onboarded by stream address unless --force; ACCESS_TOKEN_MINUTES 720 for the slot; HEALTH_INTERVAL_S 60 on the organisers' network. Passed: G3 (bench/results/g3_wiring.md, verdict ${G3.verdict}, 8 Oct): T live checks and the L wiring pair passed; the F leg was not run because sandbox-fresh-v1 was never frozen, so the marking ships as a review aid and no claim is made beyond the 120 blind-checked plates. Tried: the OCR fine-tune ft1 (bench/results/ocr_ft1.md) passed Gate 0 and Gate 1 on the four frozen sets but showed no real-plate gain: sandbox-blind-v1 ${FT1.base} to ${FT1.cand} of ${FT1.n} exact, ${FT1.fixed} fixed and ${FT1.broken} broken (McNemar p = 1.0), and 69 to 66 exact among the 81 at or above 0.9; its fresh-set leg lapsed and Gates 2 and 3 were not run: not adopted. Not built: YOLOX detectors (bench/detector_gates.md stays the plan for the pilot, not the finale: Apache-2.0 models on ONNX Runtime, retrained only on images licensed for commercial use, adopted only if gates written before training pass; until then the AGPL Ultralytics models run and every number was measured with them); G0 instrumentation, G2 one-read acceptance, G2b longer hold, G4 evidence-crop agreement, G5 detector at 960 px, G6 analysis rate: not built. So the plate pipeline on stage is the 26 Sep build plus G3's marking, and every accuracy, capture and latency figure in the pack still describes it. The pilot: the two cost levers measured (tier share from the registry, streams per node on server hardware); real government DB access needs authorisation; SSO and the relay authorisation hook close the open items on slide 9; a second blind reviewer is the only thing that can move 90 of 120.`);
}

if (page !== 10) throw new Error(`expected 10 slides, built ${page}`);
pres.writeFile({ fileName: path.join(OUT, "Sentinel-Finale.pptx") }).then((f) => console.log("wrote", f, `(${page} slides)`));
