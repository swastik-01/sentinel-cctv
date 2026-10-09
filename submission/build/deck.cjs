// Solution presentation: node deck.cjs -> submission/out/Sentinel-Solution.pptx
// Diagrams from docs/diagrams (rendered by render.mjs), screenshots from screens.mjs.
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "../..");
const OUT = path.join(ROOT, "submission/out");
const DIA = (n) => path.join(OUT, "diagrams", `${n}.png`);
const SCR = (n) => path.join(OUT, "screens", `${n}.png`);
// Real Gujarat plates on the organisers' sandbox, blind-checked by a team member on the plate review page (26 Sep)
const BLIND = JSON.parse(fs.readFileSync(path.join(ROOT, "bench/results/sandbox_review.json"), "utf-8")).modes.blind;
const PCT = (n, d) => `${(100 * n / d).toFixed(1)}%`;
// The HLD's version from its front matter, so the deck never cites a stale one
const HLD_VERSION = (fs.readFileSync(path.join(ROOT, "docs/hld.md"), "utf-8").match(/^version:\s*([\d.]+)/m) || [])[1];
if (!HLD_VERSION) throw new Error("docs/hld.md: no version in the front matter");
for (const f of ["d1-architecture", "d3-onboarding", "d4-anpr-pipeline", "d5-alert-workflow"].map(DIA)
  .concat(["wall", "alerts", "search", "registry", "map", "health", "overview", "zones", "scale-map", "objects-AMD-TRAF-002", "gov-wall"].map(SCR))) {
  if (!fs.existsSync(f)) throw new Error(`missing asset: ${f}`);
}

const C = {
  ink: "0B1220", ink2: "111C33", slate: "334155", muted: "64748B", line: "CBD5E1", soft: "F1F5F9",
  white: "FFFFFF", cyan: "0284C7", cyanL: "38BDF8", red: "DC2626", green: "047857", amber: "B45309",
  paleCyan: "E0F2FE", paleGreen: "ECFDF5", paleRed: "FEE2E2", paleAmber: "FEF3C7",
};
const FONT = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.title = "Sentinel — Solution Presentation";
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
// crop: [x, y, w, h, sourceW, sourceH] in pixels of the source image; the crop fills w x h on the slide
function framed(s, img, x, y, w, h, { dark = false, crop } = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.06, y: y - 0.06, w: w + 0.12, h: h + 0.12, rectRadius: 0.08,
    fill: { color: dark ? "1E293B" : C.white }, line: { color: dark ? "334155" : C.line, width: 0.75 },
    shadow: { type: "outer", color: "000000", opacity: dark ? 0.45 : 0.18, blur: 10, offset: 3, angle: 90 } });
  if (!crop) return s.addImage({ path: img, x, y, w, h });
  const [cx, cy, cw, , sw, sh] = crop;
  const k = w / cw;
  s.addImage({ path: img, x, y, w: sw * k, h: sh * k, sizing: { type: "crop", x: cx * k, y: cy * k, w, h } });
}
function stat(s, x, y, w, value, label, { dark = false, color, size = 40 } = {}) {
  s.addText(value, { x, y, w, h: 0.75, fontFace: FONT, fontSize: size, bold: true, color: color || (dark ? C.white : C.ink), margin: 0, valign: "bottom", isTextBox: true });
  s.addText(label, { x, y: y + 0.78, w, h: 0.62, fontFace: FONT, fontSize: 12.5, color: dark ? "94A3B8" : C.muted, margin: 0, valign: "top", isTextBox: true });
}
// A number beside its explanation, in one card (for labels too long to sit under the number)
function tile(s, x, y, w, h, value, label, { color = C.ink, size = 28, vw = 1.75, labelSize = 11 } = {}) {
  card(s, x, y, w, h);
  s.addText(value, { x: x + 0.22, y, w: vw, h, fontFace: FONT, fontSize: size, bold: true, color, valign: "middle", margin: 0, isTextBox: true });
  s.addText(label, { x: x + 0.3 + vw, y, w: w - vw - 0.5, h, fontFace: FONT, fontSize: labelSize, color: C.slate, valign: "middle", margin: 0, isTextBox: true });
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
  s.addText(`Sentinel · Gujarat Police Innovation Challenge 2026`, { x: M, y: 7.08, w: 7, h: 0.28, fontFace: FONT, fontSize: 9, color: dark ? "64748B" : "94A3B8", margin: 0, isTextBox: true });
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
const P = {}; // slide numbers by name, for the requirements map
const slide = (name, dark = false) => {
  const s = pres.addSlide();
  s.background = { color: dark ? C.ink : C.white };
  page += 1;
  P[name] = page;
  if (page > 1) footer(s, page, dark);
  return s;
};

// 1 ─ Title
{
  const s = slide("title", true);
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: 1.05, w: 0.78, h: 0.78, rectRadius: 0.18, fill: { color: C.cyan }, line: { color: C.cyan, width: 0 } });
  s.addText("S", { x: M, y: 1.05, w: 0.78, h: 0.78, fontFace: FONT, fontSize: 36, bold: true, color: C.white, align: "center", valign: "middle", margin: 0, isTextBox: true });
  s.addText("Sentinel", { x: M, y: 2.05, w: 6.2, h: 1.25, fontFace: FONT, fontSize: 72, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addText("One registry, one map and one viewer for Gujarat's 80,000 government cameras — without replacing any of them.",
    { x: M, y: 3.35, w: 5.6, h: 1.3, fontFace: FONT, fontSize: 21, color: "CBD5E1", margin: 0, valign: "top", isTextBox: true });
  chip(s, M, 4.95, 3.5, "MODEL 2 ON THE MODEL 1 FOUNDATION", "0F2A44", C.cyanL);
  chip(s, M + 3.65, 4.95, 1.9, "WORKING SOFTWARE", "0F2A44", C.cyanL);
  s.addText("Gujarat Police Innovation Challenge 2026 · Solution presentation", { x: M, y: 6.35, w: 6.5, h: 0.35, fontFace: FONT, fontSize: 13, color: "94A3B8", margin: 0, isTextBox: true });
  framed(s, SCR("wall"), 6.95, 1.3, 5.8, 3.2625, { dark: true });
  framed(s, SCR("alerts"), 7.75, 4.05, 4.4, 2.475, { dark: true });
  s.addNotes("Sentinel joins up Gujarat's fragmented CCTV estate — 26 departments, many vendors — into one registry, map, viewer and analytics layer, without replacing department infrastructure. Everything in this deck is running software; the screenshots are from the live system on the simulator's feeds.");
}

// 2 ─ The problem
{
  const s = slide("problem");
  kicker(s, "The problem");
  title(s, "80,000 cameras, 26 departments — and no way to follow a vehicle between them");
  const stats = [["80,000", "government cameras statewide"], ["26", "departments, each with its own CCTV island"], ["7–15 days", "retention, local or cloud, varying by department"]];
  stats.forEach(([v, l], i) => { card(s, M, 2.1 + i * 1.55, 3.9, 1.35); stat(s, M + 0.3, 2.12 + i * 1.55, 3.4, v, l, { size: 34 }); });
  const rows = [
    ["Different everything.", "Analog and IP cameras, many vendors, NVRs, DVRs and enterprise VMS platforms."],
    ["No shared inventory.", "Nobody can say where every camera is, who owns it, or whether it is working."],
    ["No cross-reference.", "Footage cannot be searched together or checked against VAHAN, eGujCop or AFIS/NAFIS."],
    ["No continuity.", "A vehicle seen by a police camera and again by a municipal camera 5 km away is two unrelated recordings."],
  ];
  rows.forEach(([h, b], i) => {
    numDot(s, 5.05, 2.2 + i * 1.12, i + 1, C.ink);
    s.addText([{ text: h + " ", options: { bold: true, color: C.ink } }, { text: b, options: { color: C.slate } }],
      { x: 5.7, y: 2.12 + i * 1.12, w: 7.0, h: 0.95, fontFace: FONT, fontSize: 16, valign: "top", margin: 0, isTextBox: true });
  });
  s.addNotes("The estate grew department by department. The result is a lot of cameras and very little shared capability: no inventory, no common viewing, no searchable metadata, no link to police databases.");
}

// 3 ─ Objectives and key innovations
{
  const s = slide("objectives");
  kicker(s, "Objectives and key innovations");
  title(s, "What the platform has to achieve, and six things it does differently", false, { size: 30 });
  card(s, M, 1.95, 4.45, 4.93);
  s.addText("OBJECTIVES", { x: M + 0.3, y: 2.12, w: 3.9, h: 0.3, fontFace: FONT, fontSize: 11, bold: true, color: C.cyan, charSpacing: 1.5, margin: 0, isTextBox: true });
  s.addText([
    { text: "“A secure, scalable, interoperable, technically feasible and cost-effective approach that uses existing infrastructure to the maximum practical extent.”", options: { italic: true, color: C.ink, breakLine: true } },
    { text: "The portal's core goal", options: { fontSize: 10.5, color: C.muted } },
  ], { x: M + 0.3, y: 2.47, w: 3.9, h: 1.05, fontFace: FONT, fontSize: 13, valign: "top", margin: 0, isTextBox: true });
  bullets(s, [
    ["Reuse what exists:", "cameras, recorders, VMS and retention stay with the departments."],
    ["Know the estate:", "every camera registered, mapped and health-checked (Model 1)."],
    ["See and search across owners:", "one viewer; plate metadata from every camera that can read plates (Model 2)."],
    ["Act on watchlists:", "every read checked against VAHAN and eGujCop lists (mock adapters today) and manual entries, with real-time alerts."],
    ["Scale at a stated cost:", "80,000 cameras by adding edge nodes, every input labelled measured or assumed."],
  ], M + 0.3, 3.6, 3.9, 3.2, { size: 12.5, gap: 6 });
  const inn = [
    ["Metadata, not video, at the edge", "District edges analyse beside the cameras; only plate reads, counts and alerts cross the backbone: about 2.7 Mbps of plate metadata statewide (4.6 with counts), modelled, where carrying the video would take 320 Gbps."],
    ["Registry first, with gap analysis", "Every camera is a record before it is a stream: owner, location, health, retention, whether plates are legible. Districts with no cameras or no plate-reading camera are flagged."],
    ["Store-and-forward edges", "If the core is unreachable, sightings spool to disk and replay with their original times; watchlist hits are logged at the edge and alerted on replay. 21/21 replayed after a ~87 s API outage."],
    ["Honest optics tiering", "The registry records which cameras can read plates; at scale only those run ANPR and wide cameras count vehicles and people. In the PoC every analysed camera runs the plate path."],
    ["Intrusion and counts without identity", "Zones and counts alert on presence and store numbers only: no box, image or track of a person. No face recognition, by design."],
    ["Measured, with conditions", "Alert latency, matcher cost, decode and plate accuracy each come from a script, with the conditions written beside the number. Assumptions are labelled."],
  ];
  inn.forEach(([h, b], i) => {
    const x = 5.3 + (i % 2) * 3.82, y = 1.95 + Math.floor(i / 2) * 1.67;
    card(s, x, y, 3.62, 1.55, C.white, C.line);
    s.addText(h, { x: x + 0.2, y: y + 0.13, w: 3.25, h: 0.34, fontFace: FONT, fontSize: 14, bold: true, color: C.ink, margin: 0, valign: "top", isTextBox: true });
    s.addText(b, { x: x + 0.2, y: y + 0.5, w: 3.25, h: 1.0, fontFace: FONT, fontSize: 11, color: C.slate, margin: 0, valign: "top", isTextBox: true });
  });
  s.addNotes("The objectives follow the portal's core goal word for word. The innovations list what is built in the proof of concept, except where a card says otherwise: tiering at scale and the bandwidth figures are modelled. Store-and-forward was tested live on 24 Sep on one camera by stopping the API, not by cutting a link: it was down for about 87 s, 21 sightings were spooled at the edge and all 21 replayed with their original frame times once it returned; meanwhile the edge recorded 20 watchlist hits in its log and a local file, and the control-room alerts were raised on replay. The 2.7 Mbps and 320 Gbps figures come from the capacity model (bench/capacity.py), not from a statewide measurement.");
}

// 4 ─ Approach and model choice
{
  const s = slide("approach");
  kicker(s, "Model choice and justification");
  title(s, "Why Model 2, on the Model 1 foundation");
  const models = [
    ["Model 1", "Registry + GIS", "BUILT · FOUNDATION", C.paleGreen, C.green, "Mandatory for every entry. Every camera as a record: location, owner, stream, health, what its position allows."],
    ["Model 2", "Unified viewing + metadata analytics", "BUILT · OUR MODEL", C.paleGreen, C.green, "Direct RTSP connection, one relayed session per camera, plate metadata and live alerts."],
    ["Model 3", "VMS federation", "NOT NEEDED", C.paleAmber, C.amber, "No middleware layer. A VMS that won't re-stream RTSP connects through its SDK, within Model 2 (designed)."],
    ["Model 4", "Central VMS", "NOT NOW", C.paleRed, C.red, "Re-recording 80,000 streams centrally duplicates storage departments already pay for."],
  ];
  models.forEach(([m, name, status, fill, col, desc], i) => {
    const x = M + i * 3.07;
    card(s, x, 2.05, 2.87, 2.95, C.white, C.line);
    s.addText(m, { x: x + 0.25, y: 2.25, w: 2.4, h: 0.35, fontFace: FONT, fontSize: 13, bold: true, color: C.muted, margin: 0, isTextBox: true });
    s.addText(name, { x: x + 0.25, y: 2.6, w: 2.45, h: 0.85, fontFace: FONT, fontSize: 18, bold: true, color: C.ink, margin: 0, valign: "top", isTextBox: true });
    chip(s, x + 0.25, 3.5, 1.9, status, fill, col);
    s.addText(desc, { x: x + 0.25, y: 3.95, w: 2.4, h: 1.35, fontFace: FONT, fontSize: 13, color: C.slate, margin: 0, valign: "top", isTextBox: true });
  });
  s.addText([{ text: "Submitted as Model 2 on the mandatory Model 1 foundation: ", options: { bold: true, color: C.ink } },
    { text: "no middleware, no central recording, nothing replaced.", options: { color: C.slate } }],
    { x: M, y: 5.12, w: W - 2 * M, h: 0.4, fontFace: FONT, fontSize: 14.5, margin: 0, isTextBox: true });
  const principles = [["Video stays local.", "Analytics runs at the edge; only metadata crosses the backbone."], ["Honest optics.", "The registry records which cameras can read plates; at scale only those run ANPR."], ["Accountable.", "Every plate search and operator action audited; no face recognition, by design."]];
  principles.forEach(([h, b], i) => {
    s.addText([{ text: h + " ", options: { bold: true, color: C.ink } }, { text: b, options: { color: C.slate } }],
      { x: M + i * 4.1, y: 5.7, w: 3.9, h: 0.95, fontFace: FONT, fontSize: 14, valign: "top", margin: 0, isTextBox: true });
  });
  s.addNotes("We chose Model 2, on the Model 1 foundation. Model 1 is mandatory for every entry and is our registry and map; the submission form confirms it separately, so Model 1 with Model 2 is Model 2, not a hybrid. Model 2 delivers the live test case without middleware and without touching department systems. Model 3's federation layer is not needed: a VMS that will not re-stream RTSP connects through its vendor's SDK, which Model 2 allows (adapter designed, not built). A central VMS would duplicate storage and, by the capacity model, need about 320 Gbps of sustained backbone to carry every main stream (64 Gbps even for sub-streams only). Counting, intrusion zones and route reconstruction are analytics on Model 2's streams; they do not make the entry a hybrid.");
}

// 5 ─ On the government feeds (numbers from bench/results/sandbox.json, the blind check in sandbox_review.json, its
// split by run in sandbox_daynight.json: the 25 Sep evening and 26 Sep morning runs, the same looping footage, never
// day and night; sandbox_eye.json is the earlier AI check, not blind, quoted only as such)
{
  const S = JSON.parse(fs.readFileSync(path.join(ROOT, "bench/results/sandbox.json"), "utf-8"));
  const E = JSON.parse(fs.readFileSync(path.join(ROOT, "bench/results/sandbox_eye.json"), "utf-8"));
  const D = JSON.parse(fs.readFileSync(path.join(ROOT, "bench/results/sandbox_daynight.json"), "utf-8")).blind;
  const B = BLIND, judged = (v) => (v.exact || 0) + (v.one_off || 0) + (v.wrong || 0);
  // plates are readable on the views the earlier check found them on; the blind check may add a stray one elsewhere
  const views = E.cameras_with_plates, onViews = views.reduce((n, c) => n + judged(B.cameras[c] || {}), 0);
  const hi = B.bands[">=0.9"], mid = B.bands["0.5-0.7"];
  const [p0, , p1] = S.probe_s;
  const s = slide("govfeeds");
  kicker(s, "The government feeds · 25–26 Sep 2026");
  title(s, `The organisers' ${S.cameras} cameras: onboarded, viewed and analysed`, false, { size: 30 });
  framed(s, SCR("gov-wall"), M, 2.05, 7.6, 3.708);           // 1902 x 928 screenshot
  const rows = [
    [`${S.cameras} / ${S.cameras}`, `onboarded by RTSP address, ${p0.toFixed(1)}–${p1.toFixed(1)} s each · ${S.codecs.join(" and ")}, 960×576 to 2560×1440`],
    [`${S.cameras_analysed} / ${S.cameras}`, `analysed for vehicles and people: ${S.frames.toLocaleString("en-US")} frames, 4 cameras at a time in rotation on one laptop`],
    [`${B.exact} / ${B.plates}`, `real Gujarat plates stored exactly right, ${onViews === B.plates ? "" : `all but ${B.plates - onViews} `}on the ${views.length} of ${S.cameras} views where plates are readable; blind-checked by a team member against each crop`],
    [String(S.intrusion_alerts), "intrusion alerts from two demo zones we drew (simulated)"],
  ];
  // the plate row's label runs to three lines: the last row sits a little lower to clear it
  rows.forEach(([v, l], i) => stat(s, 8.6, 1.85 + i * 1.12 + (i === 3 ? 0.1 : 0), 4.15, v, l, { size: 30, color: i === 2 ? C.green : undefined }));
  caption(s, `Recorded footage replayed live by the organisers. The catalogue gives only id and name: departments and map positions are our reading of the names (${S.placed} of ${S.cameras} placed). Video: “2 - Government feed demo”; its report lists every read with its timestamp (both cover the 25 Sep evening run). Plates checked blind by a team member, 26 Sep. bench/results/sandbox.md, sandbox_review.md.`, M, 6.42, W - 2 * M, 0.5);
  s.addNotes(`The live test case on the organisers' sandbox: ${S.cameras} government cameras replaying recorded footage. Every camera was onboarded by its RTSP address in ${p0.toFixed(1)}–${p1.toFixed(1)} s, shown on the wall, and analysed for vehicle and person counts, four at a time on one GTX 1650 Ti laptop. Plates are readable only where the view allows. On 26 Sep a team member checked ${B.sightings} of the ${E.stored} real sightings Sentinel stored, blind, on the plate review page: only the crop is shown, the reviewer types the plate and the server grades it against the stored read. ${B.verdicts.not_a_plate} were a hoarding's phone number, graded not a plate. Of the ${B.plates} vehicle plates, ${B.exact} were exact (${PCT(B.exact, B.plates)}), ${B.exact + B.one_off} within one character (${PCT(B.exact + B.one_off, B.plates)}), ${B.verdicts.wrong} wrong, none unreadable. By Sentinel's own confidence: at 0.9 or above ${hi.exact} of ${hi.plates} exact (${PCT(hi.exact, hi.plates)}) and ${hi.exact + hi.one_off} within one character; between 0.5 and 0.7 only ${mid.exact} of ${mid.plates}. So high-confidence reads can pass and the rest go to a person, which is how commercial systems work. The 25 Sep evening run (all 30 cameras; the government video and report cover it): ${D.evening.exact} of ${judged(D.evening)}; the 26 Sep morning run (8 cameras): ${D.morning.exact} of ${judged(D.morning)}. Both replayed the same footage: the sandbox loops fixed clips, each camera's recorded at one time of day, so this is not day against night. We checked the method on our own cameras, where the true plates are known: the reviewer was right 222 times in 226 (98.2%), and on the stock clip the blind check found Sentinel right on 96.7%, against 96.8% from automated ground truth (bench/results/review_truth.md). An earlier check by our AI assistant, with the stored read in view and so not blind, gave ${E.exact} of ${E.plates} after leaving ${E.verdicts.unreadable} crops out as unreadable. It was optimistic: on the crops it judged readable the blind reviewer found 80 exact against its 92; a second blind reviewer would settle the 12 disagreements. Our AI assistant then reviewed the 30 misses: it puts 13 on Sentinel (mostly a character dropped near the plate's end, or a digit or letter misread by the reader model) and 13 on the reviewer's typing. That is not a person's judgement, so the figure stays until a second team member reads them blind (bench/results/blind_errors.md). 25 reading changes tried without training did not beat the shipped reader (ocr_fix_trials.md); the Indian-format fine-tune is gated for the finale. Most sandbox views are overview or red-light cameras, several recorded at night, where plates are too small to read. A hoarding's phone number was read as a plate until we added a fixed-text filter; since 26 Sep a read that fits a plate only after two or more digits are turned into letters is dropped, which would have stopped all 24 hoarding sightings and lost none of the 92 plates the AI check had labelled exact (bench/results/plate_gate_confirm.md). The video and report were made from the 25 Sep evening run before any review and before that rule, so the report still lists the 24 hoarding sightings.`);
}

// 5 ─ Architecture
{
  const s = slide("arch");
  kicker(s, "Architecture");
  title(s, "Department estates untouched · district edges relay and analyse · only metadata reaches the core");
  s.addImage({ path: DIA("d1-architecture"), x: M, y: 1.95, w: 8.55, h: 4.845 });
  const pts = [
    ["One session per camera.", "The media relay fans a stream out to analytics and every viewer; departments see a single client."],
    ["Metadata, not video.", "Plate reads and events cross the state backbone — about 2.7 Mbps of plate metadata statewide on average (modelled)."],
    ["Government data in.", "One adapter contract: VAHAN and eGujCop as mocks over local fixture files; SARTHI, AFIS, NAFIS awaiting access."],
    ["Resilient edges.", "If the core is unreachable, sightings spool to disk and replay in order with their original times; hits on the edge's watchlist copy are logged locally and alerted on replay. Tested with a ~87 s API outage: 21/21 sightings replayed."],
  ];
  bullets(s, pts, 9.45, 2.0, 3.3, 4.85, { size: 13, gap: 10 });
  s.addNotes("Three zones. Departments keep everything they have. Each district edge runs a media relay and GPU analytics nodes next to the cameras. The state core holds the registry, sightings, watchlist matcher, audit log and government DB adapters. Control rooms get live video from the district relay and alerts from the core. Outage test, 24 Sep: API stopped for about 87 s; 21 sightings spooled and all 21 replayed within half a second of the next attempt; the control-room alerts carried the original sighting times. The edge's watchlist copy holds plate, kind and severity only.");
}

// 6 ─ Model 1: registry, GIS map and gap analysis
{
  const s = slide("registry");
  kicker(s, "Model 1 · Registry and GIS");
  title(s, "Registry, GIS map and gap analysis");
  const shots = [
    ["registry", "Registry: bulk CSV, catalogue sync with a dry-run preview, stream URL or manual entry"],
    ["map", "GIS map: department, health and ANPR layers, district coverage"],
    ["health", "Health and gap analysis: districts without cameras flagged"],
  ];
  shots.forEach(([n, cap], i) => {
    const x = M + i * 4.1, w = 3.93, h = w * 9 / 16;
    framed(s, SCR(n), x, 1.95, w, h);
    caption(s, cap, x, 1.95 + h + 0.13, w, 0.45);
  });
  bullets(s, [
    ["Bulk, manual and API onboarding:", "CSV import with per-row errors, manual entry (metadata now, stream later), a stream URL probed in ~2 s, or catalogue API sync. A dry run shows each camera's department, district, coordinates and their source, and any warnings, before anything is written."],
    ["GIS map:", "PostGIS layers by department, health and ANPR viability, district coverage; GeoJSON and nearby-camera APIs."],
    ["Health:", "reachability and byte flow every 20 s: online, degraded, offline."],
    ["Plate-reading quality:", "every capture graded; each camera tiered (reads plates, marginal, counts only) with advice."],
  ], M, 4.85, 5.95, 2.1, { size: 12, gap: 5 });
  bullets(s, [
    ["Gap analysis:", "districts with no cameras, no ANPR-viable camera, or uptime under 70%, as CSV, HTML and PDF."],
    ["Role-based search, export, audit:", "search and filters, CSV export; onboarding and edits audited; a department nodal officer sees and changes only their own cameras."],
    ["Deliverables:", "registry API reference (OpenAPI), sample camera dataset (CSV), sample gap-analysis report."],
    ["Asked of each department:", "nodal officer, camera inventory with coordinates, stream access, read-only credentials, network path (HLD 13a.3)."],
  ], 6.78, 4.85, 5.95, 2.1, { size: 12, gap: 5 });
  s.addNotes("Model 1 is flagged mandatory on the portal: the common registry and GIS foundation. Of its five features, two are in the product in full (bulk, manual and API onboarding; role-based search, export and audit) and three in part: health is monitored every 20 s, but there is no maintenance-status field; gap analysis covers uncovered districts and uptime but not ageing infrastructure, because installation year and AMC are collected on the department sheet, not yet registry columns; the map has department, health and ANPR layers and district coverage, but no camera-type layer. Its deliverables are in the submission folder: registry-cameras.csv (sample dataset), registry-gap-analysis as CSV, HTML and PDF, and registry-api.md with the OpenAPI file. The catalogue dry run reads the sandbox catalogue and shows how each camera would be mapped (department by name, district, coordinates and where they came from) before anything is written. At about 50 cameras on one laptop, every camera is onboarded and viewable; analytics runs on a few at a time, in rotation. Plate-reading quality (26 Sep, Health page): every stored plate capture is graded good, marginal or poor from its crop (size against published ANPR guidance, blur, light, contrast, layout, reader confidence), and each camera gets a tier and advice: zoom in or move closer, faster shutter, infrared, re-aim, retrain the reader, or use it for counts. On the sandbox CAM06 and CAM07 are marginal (median plates 104 and 106 px across) and the other 28 counts-only, including the five the registry marked ANPR-viable. We checked it against the 120 blind-checked plates: the grade did not predict which reads were right (good 80.3%, marginal 65.9%, poor 80.0% exact), and Sentinel's own confidence did. So it describes the camera and drives the advice; it is not a readability score (bench/results/capture_quality.md).");
}

// 7 ─ Onboarding
{
  const s = slide("onboard");
  kicker(s, "Camera integration");
  title(s, "Any RTSP feed onboarded in seconds — probed, relayed, registered");
  s.addImage({ path: DIA("d3-onboarding"), x: M, y: 2.0, w: 7.3, h: 4.623 });
  stat(s, 8.35, 1.95, 4.4, "1.2–2.0 s", "measured end to end on an idle stack (17 Sep); ~4 s on the same laptop while recording the demo", { color: C.cyan, size: 44 });
  bullets(s, [
    ["Four ways in:", "catalogue sync (sandbox-style), CSV bulk import with per-row errors, a single stream URL, or manual entry."],
    ["Credentials stay server-side;", "browsers and workers only ever see relay endpoints."],
    ["H.265 handled:", "a 640p H.264 preview is transcoded only while someone watches."],
    ["Self-healing:", "relays re-registered automatically after a media-server restart (tested 2/2)."],
  ], 8.35, 3.55, 4.4, 3.3, { size: 13.5, gap: 10 });
  s.addNotes("This is the flow for the government feed handed over on the day. Paste a URL; the relay probes it; codec and resolution come from the stream itself; the camera is registered with RTSP, WebRTC and HLS endpoints. A camera without analytics connects upstream only while someone watches it.");
}

// 8 ─ Unified viewing
{
  const s = slide("viewing");
  kicker(s, "Unified viewing");
  title(s, "One video wall across every department's cameras");
  framed(s, SCR("wall"), M, 1.95, 8.2, 4.6125);
  stat(s, 9.35, 1.95, 3.4, "WebRTC", "live preview with automatic HLS fallback", { size: 34 });
  stat(s, 9.35, 3.45, 3.4, "Mixed estate", "H.264 and H.265 · analog D1 to 1080p · 12–25 fps", { size: 34 });
  stat(s, 9.35, 4.95, 3.4, "130% → 23%", "idle media-server CPU after moving previews to on-demand transcoding (17 Sep)", { size: 34, color: C.green });
  s.addNotes("Same application for the state and district control rooms: map with live health, a 2×2 to 4×4 video wall, health and gap reports. Previews for H.265 cameras are transcoded only while watched, which cut idle media CPU from about 130% to 23% of a core.");
}

// 9 ─ AI approach
{
  const s = slide("ai");
  kicker(s, "AI approach");
  title(s, "From RTSP frame to watchlist alert in seven stages");
  s.addImage({ path: DIA("d4-anpr-pipeline"), x: M, y: 1.85, w: 9.3, h: 3.9525 });
  bullets(s, [
    ["Built for Indian plates:", "standard and BH layouts, position-aware O/0 and I/1 repair, look-alike state codes; text that fits only once two or more digits become letters is dropped as not a plate."],
    ["Robust to single-frame errors:", "per-character, confidence-weighted voting across a vehicle's reads."],
    ["Tiered by optics:", "the registry flags which cameras can read plates; at scale only those run ANPR, and wide cameras still count vehicles and people."],
  ], 10.2, 1.95, 2.55, 4.9, { size: 13, gap: 12 });
  s.addText("Face recognition is deliberately not implemented — see Security and privacy.", { x: M, y: 6.05, w: 9.3, h: 0.45, fontFace: FONT, fontSize: 13, italic: true, color: C.muted, margin: 0, isTextBox: true });
  s.addNotes("YOLOv11n plate detector on the GPU, unioned with a classical text-line finder for footage the model hasn't seen. Batched OCR with a 10-slot model so Indian plates fit. Normalisation repairs OCR confusions by position. A vehicle's reads are voted per character before anything is emitted. Not a plate (26 Sep): a read is dropped when two or more of its letters had to be made from digits to fit a plate layout, which is how a hoarding's phone number on the sandbox became plate-like. Gates written before the build all passed (bench/results/plate_gate_confirm.md): the hoarding caught in 23 of 23 frozen crops and 24 of 24 stored sightings; no real sandbox plate lost (0 of 25 in the frozen set, 0 of the 92 stored plates the AI check labelled exact); on our own feed 4 of 5,307 exact reads and no vehicle; 1 of 1,723 held-out synthetic plates. The real non-plate evidence is one hoarding (3 texts, one camera) and the rule was chosen after seeing it; it stops numeric text, not signage made of letters. A learned plate / not-a-plate classifier is planned for the finale.");
}

// 10 ─ Vehicle and person detection
{
  const s = slide("objects");
  kicker(s, "Beyond ANPR");
  title(s, "Vehicles and people: counted per camera, never identified");
  framed(s, SCR("objects-AMD-TRAF-002"), M, 1.95, 7.4, 4.1625);
  caption(s, "Worker view of AMD-TRAF-002: stock traffic footage replayed by the simulator, every number plate replaced by a synthetic registration.", M, 6.22, 7.4);
  bullets(s, [
    ["Same frames, second detector:", "a stock COCO model finds people, cars, two-wheelers, buses and trucks on the frames the plate path analyses (at most 5 a second per camera and 8 frames per pass)."],
    ["What each plate is on:", "a read is bound to the vehicle box around it; type is voted over the vehicle's reads, colour read from its body panels. Unsure means blank, not a guess."],
    ["Counts, not tracks:", "one row per camera per minute: frames analysed, average and peak in view per class. No box, image or track of a person is kept."],
  ], 8.35, 1.95, 4.4, 3.2, { size: 13, gap: 10 });
  const st = [["13", "vehicles in view on average, peak 21 in one frame, on the wide stock-footage camera"], ["−5%", "plate analysis rate with the second detector on (4-stream A/B)"]];
  st.forEach(([v, l], i) => { card(s, 8.35, 5.2 + i * 0.86, 4.4, 0.76); s.addText([{ text: v + "  ", options: { bold: true, fontSize: 20, color: C.ink } }, { text: l, options: { fontSize: 11.5, color: C.muted } }], { x: 8.5, y: 5.2 + i * 0.86, w: 4.15, h: 0.76, fontFace: FONT, valign: "middle", margin: 0, isTextBox: true }); });
  s.addNotes(`Evaluation area 5 names vehicle and person detection and object detection. This is the second model in the worker: stock COCO weights, run on the frames ANPR already pulls, so it never competes with ANPR for frames. Counts are aggregates with a frame denominator, so a zero on a synthetic camera is an honest zero. Type and colour are attached to plate sightings; colour is a heuristic and abstains on IR frames and two-wheelers. The same boxes feed the intrusion zones on the next slide (${page + 1}).`);
}

// 11 ─ Intrusion zones
{
  const s = slide("intrusion");
  kicker(s, "Intrusion detection");
  title(s, "Intrusion zones: presence, not identity");
  // the AMD-TRAF-001 tile of the video wall, zone drawn dashed on the right
  framed(s, SCR("zones"), M, 1.95, 6.7, 6.7 * 480 / 766, { crop: [384, 100, 766, 480, 2400, 1350] });
  caption(s, "Video-wall tile of AMD-TRAF-001 with its zone drawn (dashed): “kerb strip”, a simulated restricted area on stock footage. The same tile flashes when the zone is entered.", M, 6.3, 6.7, 0.6);
  bullets(s, [
    ["Drawn on live video:", "a supervisor, or the camera's own department, draws the polygon on its tile in the video wall; each change is audited."],
    ["Rules per zone:", "which classes (people by default, or vehicles), minimum dwell (3 s default), armed hours in IST such as 22:00–06:00, and severity."],
    ["Ground point test:", "an object is inside when the bottom centre of its box, where a person stands, falls in the polygon, not when the box merely overlaps it."],
    ["One alert per occupancy:", "a zone occupied for a minute raises one event, not one per frame; then at most one alert per zone per camera every 120 s."],
    ["Nothing about the person is kept:", "the alert stores the zone, classes and counts, and dwell. No box, crop or track; the operator opens the live view."],
  ], 7.6, 1.95, 5.13, 3.55, { size: 12, gap: 5 });
  card(s, 7.6, 5.55, 5.13, 1.35, C.paleAmber, C.paleAmber);
  s.addText([
    { text: "Demo scope. ", options: { bold: true, color: C.amber } },
    { text: "One zone on one stock clip (60 s loop). In 15 min live: 14 events, one per loop, one or two people each time; 6 alerts after the cooldown. Checked on the saved frames of a replayed loop; riders on the road beside the zone did not trigger. It shows the mechanism end to end, not a false-alarm rate.", options: { color: C.slate } },
  ], { x: 7.8, y: 5.55, w: 4.8, h: 1.35, fontFace: FONT, fontSize: 11, valign: "middle", margin: 0, isTextBox: true });
  s.addNotes("Evaluation area 5 names intrusion detection. Zones reuse the person and vehicle boxes the worker already computes for counts, so they cost no extra inference. Polygons are stored in normalised frame coordinates, so they survive a resolution change. Presence tolerates missed frames: an occupancy ends only after the zone has looked empty for at least 2.5 analysis intervals. The alert goes through the same queue, notification and audit as plate alerts, with the zone name, classes, peak count and dwell. The demo figures are from 24 Sep on AMD-TRAF-001 (Pexels stock footage; the location name is simulated) and bench/zone_check.py; nothing here is a false-alarm rate on Gujarat footage.");
}

// 12 ─ Alerts
{
  const s = slide("alerts");
  kicker(s, "Watchlist and alerts");
  title(s, "Every plate read is checked against the watchlist as it happens");
  framed(s, SCR("alerts"), M, 1.95, 7.4, 4.1625);
  caption(s, "The alerts page: intrusion alerts from the stock camera, a stolen-vehicle hit, and a near miss labelled “read ≈ watchlist GJ01AB1234 (one character off)”. All plates are synthetic.", M, 6.25, 7.4, 0.6);
  const steps = [
    ["Sources", "VAHAN stolen and blacklisted; eGujCop wanted, missing and BOLO (mock adapters); manual entries with FIR reference and expiry."],
    ["Match", "Exact plate, else one character off, labelled “read ≈ watchlist”. A single-read sighting alerts only on an exact match. About 1 ms per read at 100,000 entries."],
    ["Look back", "A newly listed plate is checked against the last 24 h: the answer says “seen N times”, and one retrospective alert carries the time it was seen."],
    ["Notify", "Open alerts ordered by severity, then time; a notice on every page, with a chime for high and critical. One alert per entry per camera per 120 s."],
    ["Act", "Acknowledge (who and when), close or mark false positive with a disposition; each step audited and pushed to every control room. Plate review: supervisors and auditors check stored reads against their crops, blind."],
  ];
  steps.forEach(([h, b], i) => {
    numDot(s, 8.45, 1.98 + i * 0.97, i + 1, i === 3 ? C.red : C.cyan);
    s.addText([{ text: h + "  ", options: { bold: true, color: C.ink } }, { text: b, options: { color: C.slate } }],
      { x: 9.05, y: 1.93 + i * 0.97, w: 3.7, h: 0.92, fontFace: FONT, fontSize: 11.5, valign: "top", margin: 0, isTextBox: true });
  });
  s.addNotes("Watchlists come from government systems through adapters (VAHAN and eGujCop are mocks over local fixture files, their fields modelled on the systems' published descriptions). Matching is exact, then one character off, because OCR is never perfect; the card shows the read beside the listed plate so the operator judges the near miss. Severity comes from the source record: wanted person critical, missing person and stolen vehicle high. The retrospective check means a plate listed after the vehicle passed is still caught: on 24 Sep, adding GJ13LU9863 found 48 earlier sightings and raised one alert with the original time. Escalation deadlines, SMS and the 112 ERSS hand-off are design (HLD 8.1), not built. The plate review page (HLD 7.8) is where people check stored reads: in a blind check the reviewer sees only the crop and types the plate before Sentinel's read is shown, and the server grades it; results come per camera and by confidence band. Built and tested 26 Sep; the same day a team member checked 144 real sandbox sightings blind (slide 5).");
}

// 13 ─ Movement history
{
  const s = slide("movement");
  kicker(s, "Vehicle tracking");
  title(s, "A plate given on the spot → its journey across departments", false, { size: 30 });
  framed(s, SCR("search"), M, 1.95, 8.2, 4.6125);
  caption(s, "The simulator shows the same plate on two cameras at once, so the view flags the 7 km leg as implausible, as it would a cloned plate.", M, 6.68, W - 2 * M, 0.3);
  bullets(s, [
    ["A journey, not a list:", "reads grouped into stops by frame time, each with camera, place and dwell, numbered on the map."],
    ["Legs between stops:", "distance, time and average speed."],
    ["Implausible legs flagged:", "implausibly fast (over 150 km/h across 1 km or more): a cloned plate or a misread."],
    ["Near misses kept, marked:", "a stop read one character off is shown as a possible misread and left out of the speeds."],
    ["Evidence and audit:", "a crop per stop, CSV export; every query logged with its stated purpose."],
  ], 9.3, 1.95, 3.45, 4.75, { size: 13, gap: 9 });
  s.addNotes("This is the live test case's core ask: identify, trace and present the movement of a designated vehicle. The query spans every camera that can read plates, whoever owns it, and orders sightings by frame time, not arrival time. Note for judges: the simulated feeds loop the same vehicles through every camera, so the journey in this screenshot is not a physically plausible one; the view says so itself. On real feeds the same flag points at a cloned plate or a misread.");
}

// 14 ─ Live test case mapping
{
  const s = slide("testcase");
  kicker(s, "Live test case");
  title(s, "Every step of the live test case maps to working software");
  const head = { bold: true, color: C.white, fill: { color: C.ink }, fontFace: FONT, fontSize: 13 };
  const cell = (t, o = {}) => ({ text: t, options: { fontFace: FONT, fontSize: 12, color: C.slate, valign: "middle", ...o } });
  const ok = (t) => cell("✓  " + t, { color: C.green, bold: true });
  const req = (t) => cell(t, { bold: true, color: C.ink });
  const rows = [
    [{ text: "Test-case requirement", options: head }, { text: "How Sentinel delivers it", options: head }, { text: "Status", options: head }],
    [req("Onboard ~50 mixed feeds from different departments"), cell("The organisers' sandbox: all 30 cameras onboarded by RTSP, 1.0–2.2 s each (25 Sep) · catalogue sync with a dry-run preview · CSV bulk import"), ok("Done")],
    [req("Centralised monitoring"), cell("Live-health map · WebRTC video wall · uptime and gap reports"), ok("Tested")],
    [req("AI analytics"), cell(`On the sandbox: counts on 30 cameras, intrusion alerts, and ${BLIND.exact} of ${BLIND.plates} plates exact where the view allows (blind-checked by a team member)`), ok("Measured")],
    [req("Track a vehicle by registration number"), cell("Journey tolerant of OCR near-misses · implausible legs flagged · retrospective hit when a plate is listed · CSV"), ok("Tested")],
    [req("Timestamped, location-wise movement history"), cell("Frame-timestamped stops with camera, district, department, dwell and route"), ok("Tested")],
    [req("Cross-check against a watchlist"), cell("VAHAN and eGujCop adapters (mock) · manual entries · exact, then one character off"), ok("Tested")],
    [req("Automated real-time alerts"), cell("Pushed with evidence crop, notice on every page · median 1.06 s from first read to alert"), ok("Measured")],
    [req("Report of detected plates and timestamps"), cell("Per camera and window: vehicles, every read with its time, crops, counts, intrusion alerts; made for the sandbox run — HTML, PDF, CSV"), ok("Made")],
  ];
  s.addTable(rows, { x: M, y: 1.95, w: W - 2 * M, colW: [4.1, 6.3, 1.73], rowH: 0.5, border: { type: "solid", pt: 0.5, color: "E2E8F0" }, fill: { color: C.white } });
  caption(s, "“Tested” = covered by the 34-check end-to-end test or exercised live on the simulator's feeds; “Measured” = bench/results/latency.md. Government DB adapters are mocks over local fixture files. At ~50 cameras on one laptop, every camera is onboarded and viewable; analytics runs on a few at a time, in rotation.", M, 6.5, W - 2 * M, 0.5);
  s.addNotes("A one-to-one mapping from the evaluation's live test case to features in the product, with how each was verified. The alert latency is 31 alerts on 24 Sep, 4 cameras, one worker and the API on the same laptop and clock; it excludes camera-to-worker transport and the browser's display.");
}

// 15 ─ Measured results
{
  const s = slide("measured");
  kicker(s, "Measured, not estimated");
  title(s, "What we measured, and under which conditions");
  const labels = ["4 streams", "8 streams", "12 streams"];
  s.addChart(pres.charts.BAR, [
    { name: "Software decode", labels, values: [4.58, 1.93, 0.91] },
    { name: "Hardware decode (D3D11, Intel UHD iGPU on this laptop)", labels, values: [4.52, 2.88, 1.34] },
  ], { x: M, y: 1.95, w: 6.4, h: 4.1, barDir: "col", barGrouping: "clustered", chartColors: ["94A3B8", C.cyan],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 11, dataLabelColor: C.slate, dataLabelFormatCode: "0.00",
    showLegend: true, legendPos: "b", legendFontSize: 12, legendFontFace: FONT,
    showTitle: true, title: "Analysed fps per stream (target 5), GTX 1650 Ti laptop", titleFontSize: 14, titleColor: C.ink, titleFontFace: FONT,
    catAxisLabelColor: C.muted, catAxisLabelFontSize: 12, valAxisLabelColor: C.muted, valAxisLabelFontSize: 10,
    valAxisMaxVal: 6, valAxisMinVal: 0, valAxisMajorUnit: 1, valGridLine: { color: "E2E8F0", size: 0.5 }, catGridLine: { style: "none" } });
  s.addText("Hardware decode: +49% at 8 and 12 streams, system CPU at 8 streams 94% → 80%. The laptop's integrated-GPU decoder, not NVDEC: a direction, not a server-node figure; 60 streams per node stays an ASSUMPTION.",
    { x: M, y: 6.15, w: 6.4, h: 0.8, fontFace: FONT, fontSize: 12, bold: true, color: C.ink, margin: 0, valign: "top", isTextBox: true });
  const tiles = [
    ["96.8%", `exact reads, close stock camera; 91.2% of plates on screen ≥ 1 s captured (wide camera: 90.2%, 21.7%). Synthetic plates on stock footage. Real Gujarat plates (sandbox): ${BLIND.exact} of ${BLIND.plates} exact, blind-checked by a team member.`, C.ink, 28],
    ["1.06 s", "median from first plate read to alert (p95 1.94 s): 31 alerts, 4 cameras, one laptop, one clock.", C.ink, 28],
    ["~1 ms", "watchlist match per plate read at 100,000 entries; a full edit-distance scan took 45–56 ms.", C.ink, 28],
    ["34 · 20 · 245", "end-to-end checks, security checks and unit tests, all passing.", C.green, 21],
  ];
  tiles.forEach(([v, l, col, size], i) => tile(s, 7.35, 1.95 + i * 1.25, 5.38, 1.13, v, l, { color: col, size, vw: 1.95 }));
  s.addNotes("Every number here is in bench/results with the script that reproduces it. Decode A/B (decode.md): GTX 1650 Ti laptop, both plate detectors on, no object detection, 5 fps target, 25 s per case, two rounds in alternating order. The D3D11 decoder OpenCV opens on this laptop is the Intel UHD integrated GPU's, not the GTX's NVDEC (Windows GPU-engine counters, 24 Sep; the NVIDIA decoder stayed at 0%), so the A/B shows decode offload relieving the CPU, not a server-node figure. ANPR (anpr_eval_current.md): 24 Sep 01:29–01:39 IST, current worker, 4 cameras; the plates are synthetic registrations painted onto Pexels stock footage (filmed on a Mumbai road; the Ahmedabad names are simulated), so this measures the pipeline on real traffic, not OCR on real Gujarat plates. Close camera AMD-TRAF-002 96.8% exact (659/681), capture 91.2% (62/68); wide camera AMD-TRAF-001 90.2% (174/193), capture 21.7% (28/129). Latency (latency.md): 24 Sep 01:00–01:15 IST, includes the ~1 s confirmation hold and 1 s flush, excludes camera transport and browser display. Matcher (matcher.md): 100,011 entries, 0.79 ms median for a one-character-off read, 1.14 ms for an unlisted plate. Security checks: crops, the camera-quality report, department write scope, ingest integrity, plate review, LAN exposure and publish.");
}

// 16 ─ Scale
{
  const s = slide("scale", true);
  kicker(s, "Plan for scale", true);
  title(s, "Sized for 80,000 cameras, every assumption labelled", true);
  const bx = M, by = 2.05, bw = W - 2 * M;
  const tiers = [[0.10, C.cyan, "A · ANPR", "8,000 · 5 fps"], [0.20, "0F766E", "B · Events", "16,000 · 1 fps"], [0.70, "1E293B", "C · View and record", "56,000 · relayed only while watched · no continuous compute"]];
  let cx = bx;
  tiers.forEach(([share, col, name, sub]) => {
    const w = bw * share;
    s.addShape(pres.shapes.RECTANGLE, { x: cx, y: by, w, h: 0.95, fill: { color: col }, line: { color: C.ink, width: 1 } });
    s.addText([{ text: name, options: { bold: true, fontSize: 14, color: C.white, breakLine: true } }, { text: sub, options: { fontSize: 11, color: "CBD5E1" } }],
      { x: cx + 0.12, y: by + 0.08, w: w - 0.2, h: 0.8, fontFace: FONT, margin: 0, valign: "middle", isTextBox: true });
    cx += w;
  });
  const big = [["248", "edge GPU nodes · ≈7.5 per district"], ["2.7 Mbps", "average metadata backhaul, statewide"], ["2.6 TB", "sightings kept hot for 90 days"],
    ["≈ ₹39.7 cr", "hardware capex, ₹15 lakh per edge node"], ["₹100.7 cr", "five-year total · ₹210 per camera per month"]];
  const bw5 = (bw - 4 * 0.2) / 5;
  big.forEach(([v, l], i) => {
    const x = M + i * (bw5 + 0.2);
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 3.35, w: bw5, h: 1.75, rectRadius: 0.12, fill: { color: C.ink2 }, line: { color: "1E3A5F", width: 1 } });
    stat(s, x + 0.2, 3.45, bw5 - 0.3, v, l, { dark: true, size: 30 });
  });
  bullets(s, [
    ["Tiering does the heavy lifting:", "assuming ~10% of cameras need continuous plate reading and 70% only viewing (ASSUMPTIONS the registry replaces), most of the estate costs nothing until watched."],
    ["Video never crosses the backbone for analytics:", "2.7 Mbps of metadata, where carrying every main stream to a central VMS (Model 4) would take 320 Gbps, and 64 Gbps even for sub-streams."],
    ["Every number is reproducible:", "bench/capacity.py, inputs labelled measured or assumed; unit prices are assumptions to be replaced by GeM quotes; per-node capacity is the pilot's first measurement."],
  ], M, 5.4, W - 2 * M, 1.6, { size: 14, dark: true, gap: 6 });
  s.addNotes("The Plan for Scale document derives all of this from bench/capacity.py. Five-year total ₹100.7 crore = hardware ₹39.7 crore + one-time implementation ₹9.9 crore + operating cost ₹51.0 crore over five years; ₹210 per camera per month across all 80,000 cameras. All unit prices are assumptions. The two levers that dominate cost are the share of cameras that need ANPR and streams per GPU node; both get measured in the pilot. Department cameras, recorders and storage are reused, not replaced.");
}

// 16b ─ The core at statewide size, measured
{
  const s = slide("core");
  kicker(s, "Scale, measured");
  title(s, "The core at 80,000 cameras, measured on one laptop");
  framed(s, SCR("scale-map"), M, 1.95, 7.4, 4.1625);
  s.addText("The control-room map against a scale-test registry of 80,000 synthetic cameras placed around district centres: counted per grid cell until zoomed in, then only the cameras in view.",
    { x: M, y: 6.22, w: 7.4, h: 0.5, fontFace: FONT, fontSize: 11, italic: true, color: C.muted, margin: 0, isTextBox: true });
  const tiles = [
    ["706 /s", "sightings ingested and matched against a 100,000-entry watchlist, sustained; the statewide average in the capacity model is 556/s", C.green, 26],
    ["161 ms", "state map view (clusters); street view 25 ms for the cameras in view. The whole registry as one map response was 45 MB and 6 s", C.ink, 26],
    ["337 ms", "one vehicle's 30-day movement history over 3 million sightings, near-miss reads included", C.ink, 26],
    ["46 ms", "a page of the 80,000-camera registry; reports 0.1–0.15 s", C.ink, 26],
  ];
  tiles.forEach(([v, l, col, size], i) => tile(s, 8.3, 1.95 + i * 1.12, 4.43, 1.0, v, l, { color: col, size, vw: 1.45, labelSize: 10.5 }));
  s.addText("One API process and PostgreSQL on the same GTX 1650 Ti laptop: a floor for the core, not a server sizing (bench/core_scale.py → bench/results/core_scale.md).",
    { x: 8.3, y: 6.5, w: 4.43, h: 0.5, fontFace: FONT, fontSize: 10.5, italic: true, color: C.muted, margin: 0, isTextBox: true });
  s.addNotes("bench/core_scale.py builds a separate database from the same schema: 80,000 cameras (8,000 ANPR-viable) across 33 districts, 3.0 million sightings over 30 days drawn from 300,000 plates, 100,100 watchlist entries; starts a second API instance against it (own event channel, no camera probing) and measures. Ingest: 8 concurrent clients posting batches of 50 for 60 s, every read matched against the 100k watchlist in the same request: 706 sightings/s, request median 516 ms, p95 718 ms. Map: above 2,000 cameras the map asks for clusters (ST_SnapToGrid, cell from the zoom) and, from zoom 12, for the cameras in the visible box only. All measured 24 Sep on the laptop that runs everything else.");
}

// 17 ─ Security and privacy
{
  const s = slide("security");
  kicker(s, "Security and privacy");
  title(s, "Accountable by construction, deliberately without face recognition", false, { size: 30 });
  const cards = [
    ["Face recognition: not built, by choice", "Integration route defined (HLD 7.4): one more detector feeding the same watchlist and alert path, subject to a lawful order, gallery governance and a bias test. Wanted and missing persons are tracked through their vehicles."],
    ["Append-only audit", "Logins, plate searches, movement queries with stated purpose, onboarding, zone, watchlist and alert actions, plate reviews (without the plate). UPDATE and DELETE are no-ops in the database."],
    ["Scoped access", "Five roles. Department and district scope applied in SQL to cameras, sightings, alerts and evidence crops; a department can change only its own cameras. 20/20 negative security checks pass."],
    ["Minimal data, closed control plane", "Metadata and small plate crops, served only with a token, the right permission and a camera in scope. Video stays on department recorders. Database, cache and relay control API listen on the local host only."],
  ];
  cards.forEach(([h, b], i) => {
    const x = M + (i % 2) * 6.15, y = 2.05 + Math.floor(i / 2) * 2.3;
    card(s, x, y, 5.95, 2.1);
    s.addText(h, { x: x + 0.3, y: y + 0.2, w: 5.4, h: 0.45, fontFace: FONT, fontSize: 19, bold: true, color: C.ink, margin: 0, isTextBox: true });
    s.addText(b, { x: x + 0.3, y: y + 0.72, w: 5.35, h: 1.3, fontFace: FONT, fontSize: 13.5, color: C.slate, margin: 0, valign: "top", isTextBox: true });
  });
  s.addText("Production adds: state SSO with MFA · vault-held credentials · RBAC enforced at the media relay · camera VLANs · mTLS edge ↔ core · CERT-In reporting · STQC audit.",
    { x: M, y: 6.72, w: W - 2 * M, h: 0.3, fontFace: FONT, fontSize: 11.5, italic: true, color: C.muted, margin: 0, isTextBox: true });
  s.addNotes("Privacy is designed in, not bolted on. The auditor role can read the audit trail and reports but cannot watch footage or search plates — oversight without operational access; it can check stored plate crops on the plate review page, each review audited without the plate text. The 20 security checks (scripts/security_checks.py) cover evidence crops (missing token, served to an operator, missing permission, path traversal), the plate-reading quality report (sign-in needed, own department only, no plate text), department write scope, ingest integrity, plate review (operator and department nodal officer refused; the blind queue carries no plate text or confidence; in blind mode the server computes the verdict), LAN exposure of four control-plane ports, and an anonymous RTSP publish from the LAN. Live viewing is still open on the local network in the PoC; the relay authorisation hook is on the roadmap. HLD 11.4 holds the zones, encryption and threat model.");
}

// 18 ─ Technology
{
  const s = slide("technology");
  kicker(s, "Technology");
  title(s, "Built on open source and open protocols");
  const layers = [
    ["Media", "MediaMTX · FFmpeg · RTSP · WebRTC (WHEP) · HLS"],
    ["Analytics", "OpenCV · PyTorch (CUDA) · ONNX Runtime · Ultralytics YOLO (plates; vehicles and people) · fast-plate-ocr"],
    ["Platform", "Python 3.12 · FastAPI · asyncpg · Argon2 · JWT"],
    ["Data", "PostgreSQL 16 · PostGIS · pg_trgm · fuzzystrmatch · Valkey"],
    ["Control room", "React · Leaflet, react-leaflet / OpenStreetMap · hls.js · Vite"],
    ["Operations", "Docker Compose · uv · end-to-end tests · benchmark and capacity model"],
  ];
  layers.forEach(([l, t], i) => {
    const y = 2.0 + i * 0.72;
    card(s, M, y, W - 2 * M, 0.6, i % 2 ? C.white : C.soft, i % 2 ? "E2E8F0" : C.soft);
    s.addText(l, { x: M + 0.25, y, w: 2.2, h: 0.6, fontFace: FONT, fontSize: 15, bold: true, color: C.cyan, valign: "middle", margin: 0, isTextBox: true });
    s.addText(t, { x: M + 2.5, y, w: 9.5, h: 0.6, fontFace: FONT, fontSize: 15, color: C.ink, valign: "middle", margin: 0, isTextBox: true });
  });
  s.addText("Licences: MIT, BSD, Apache-2.0, PostgreSQL and GPL-2.0 — plus AGPL-3.0 for the two Ultralytics YOLO detectors (a deployment publishes Sentinel under a compatible licence or licenses it commercially) and Hippocratic-2.1 for react-leaflet (not OSI; plain Leaflet, BSD-2, replaces it). Planned for the finale, not yet trained: YOLOX detectors (Apache-2.0) on ONNX Runtime (MIT) to replace them, adopted only if they pass gates written before training. Until then the AGPL models run, and every number here is theirs.",
    { x: M, y: 6.35, w: W - 2 * M, h: 0.65, fontFace: FONT, fontSize: 11.5, italic: true, color: C.muted, margin: 0, valign: "top", isTextBox: true });
  s.addNotes("Every component we build on is open source except react-leaflet, the map bindings, whose Hippocratic 2.1 licence is not OSI-approved (plain Leaflet, BSD-2, replaces it if needed), and the NVIDIA GPU driver and CUDA runtime, which are proprietary but free of charge. We use Valkey, a BSD-licensed fork that speaks the Redis protocol: Redis 7.4 moved to source-available licences, and Redis 8's open-source option is AGPL. The one network-copyleft (AGPL-3.0) licence is the detectors', which we disclose rather than hide; FFmpeg and PostGIS are GPL-family, used unmodified. Both detectors run on Ultralytics YOLO, licensed AGPL-3.0. A licence-clean replacement is planned for the finale: YOLOX detectors (Apache-2.0) run by ONNX Runtime (MIT), with the plate model retrained only on images whose licences allow commercial use. It is not trained yet. It replaces the current models only if it passes adoption gates we wrote down before training (bench/detector_gates.md): no loss of plate capture or exact reads on our own feeds, no loss of plate yield on the sandbox cameras, and no slower analysis. Until then the AGPL models are what runs, and every number in this pack was measured with them. We never quote the plate model's published scores: its own model card says they are inflated by an overlap between its training and test images. Every accuracy figure here is our own measurement. The OCR stays as it is; its author does not document its training data.");
}

// 19 ─ Operational benefits
{
  const s = slide("benefits");
  kicker(s, "Operational benefits");
  title(s, "What changes for the control room, the investigator and the state");
  const cards = [
    ["Follow a vehicle across departments", "One movement history from every ANPR-viable camera, whoever owns it — instead of requesting footage department by department.", "One query instead of a request to each department"],
    ["Catch stolen vehicles while still moving", "Watchlists (VAHAN and eGujCop adapters, mock data in the PoC) matched against every plate read as it happens, with the evidence crop attached.", "Alert about 1 s after the first read (median, measured)"],
    ["Know what the state owns", "One registry with location, ownership, health and retention; gap analysis shows the blind districts.", "Coverage and uptime, per district, per department"],
    ["Evidence ready for the case file", "Timestamped, geo-located sightings with crops; CSV and PDF export; every search carries a stated purpose.", "Detection report in one command"],
    ["Buy freely, integrate anyway", "Vendor-neutral by construction: any camera, recorder or VMS that exposes RTSP onboards the same way.", "No per-channel licence, no lock-in"],
    ["Defensible under scrutiny", "Append-only audit of plate searches, movement queries and operator actions; scoped access; no face recognition by design.", "Oversight without operational access"],
  ];
  cards.forEach(([h, b, metric], i) => {
    const x = M + (i % 3) * 4.1, y = 1.95 + Math.floor(i / 3) * 2.52;
    card(s, x, y, 3.9, 2.4, C.white, C.line);
    numDot(s, x + 0.28, y + 0.26, i + 1, C.cyan);
    s.addText(h, { x: x + 0.82, y: y + 0.22, w: 2.85, h: 0.75, fontFace: FONT, fontSize: 15.5, bold: true, color: C.ink, valign: "top", margin: 0, isTextBox: true });
    s.addText(b, { x: x + 0.28, y: y + 1.0, w: 3.35, h: 0.88, fontFace: FONT, fontSize: 12.5, color: C.slate, valign: "top", margin: 0, isTextBox: true });
    s.addText(metric, { x: x + 0.28, y: y + 1.9, w: 3.35, h: 0.42, fontFace: FONT, fontSize: 11.5, bold: true, color: C.green, valign: "top", margin: 0, isTextBox: true });
  });
  s.addNotes("The benefits the platform is bought for. The one number here, about 1 s from first read to alert, is the measured median on the laptop (bench/results/latency.md); the rest are what changes in how the work is done, not measured savings. The Plan for Scale document carries the cost side and what a central VMS would have cost instead.");
}

// 20 ─ Where each required item is answered
{
  const s = slide("map");
  kicker(s, "Submission map");
  title(s, "Where each required item is answered");
  const roadmap = P.map + 1;
  const head = (t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.ink }, fontFace: FONT, fontSize: 11.5 } });
  const cell = (t, o = {}) => ({ text: String(t), options: { fontFace: FONT, fontSize: 11, color: C.slate, valign: "middle", ...o } });
  const n = (...k) => cell(k.sort((a, b) => a - b).join(", "), { bold: true, color: C.cyan, align: "center" });
  const item = (t) => cell(t, { color: C.ink });
  const opts = { rowH: 0.4, border: { type: "solid", pt: 0.5, color: "E2E8F0" }, fill: { color: C.white } };
  const dims = [
    [head("Step 3: ten dimensions"), head("Slides"), head("HLD · Plan for Scale")],
    [item("1  Overall architecture"), n(P.approach, P.arch), cell("HLD 3, 4")],
    [item("2  Integration strategy"), n(P.registry, P.onboard, P.viewing), cell("HLD 5; databases 8")],
    [item("3  AI and video analytics"), n(P.ai, P.objects, P.intrusion, P.measured), cell("HLD 7")],
    [item("4  Cybersecurity architecture"), n(P.security), cell("HLD 11, 11.4; PfS 7.4")],
    [item("5  Deployment architecture"), n(P.arch, P.scale), cell("HLD 4, 11.4; PfS 2, 7")],
    [item("6  Infrastructure sizing"), n(P.scale, P.core), cell("HLD 12; PfS 3–6")],
    [item("7  Cost-benefit analysis"), n(P.scale, P.benefits), cell("PfS 9")],
    [item("8  Department-wise information"), n(P.registry), cell("HLD 13a.3; PfS 10")],
    [item("9  Scalability strategy"), n(P.measured, P.scale, P.core), cell("HLD 12; PfS 6, 8")],
    [item("10  Future roadmap"), n(roadmap), cell("HLD 14; PfS 8, 11")],
  ];
  s.addTable(dims, { x: M, y: 1.95, w: 5.95, colW: [2.75, 1.05, 2.15], ...opts });
  const areas = [
    [head("Step 7: evaluation areas"), head("Slides"), head("Documents")],
    [item("01  Successful test case"), n(P.govfeeds, P.testcase, P.onboard), cell("HLD 9; government-feed demo and report")],
    [item("02  Solution presentation"), n(P.problem, P.objectives, P.approach), cell("HLD 1–3")],
    [item("03  Solution architecture"), n(P.arch, P.security), cell("HLD 4, 11.4; workflow diagrams")],
    [item("04  Working platform, demo"), cell(`${P.govfeeds}, ${P.registry}–${P.movement}`, { bold: true, color: C.cyan, align: "center" }), cell("Both demo videos; HLD 4.1")],
    [item("05  Video analytics output"), n(P.govfeeds, P.objects, P.intrusion, P.measured), cell("HLD 7, 13; both detection reports")],
    [item("06  Scalability, PoC readiness"), n(P.measured, P.scale, P.core, roadmap), cell("Plan for Scale; HLD 12, 13a")],
    [item("07  Submission completeness"), n(P.map), cell("HLD Appendix A")],
  ];
  s.addTable(areas, { x: 6.78, y: 1.95, w: 5.95, colW: [2.55, 1.15, 2.25], ...opts });
  caption(s, `Slide numbers are this deck's. HLD = High-Level Design v${HLD_VERSION}; PfS = Plan for Scale. HLD Appendix A maps every portal requirement in full, including the live test case step by step (HLD 9).`, 6.78, 5.35, 5.95, 0.7);
  s.addNotes("A map for the evaluators: each of the ten dimensions the portal asks the submission to cover, and each of the seven common evaluation areas, with the slides and document sections that answer it.");
}

// 21 ─ Roadmap and close
{
  const s = slide("roadmap", true);
  kicker(s, "Next", true);
  title(s, "From finale to a statewide rollout", true);
  const phases = [
    ["12–13 Oct", "Grand finale", "Live test case on the government feeds; reads checked blind by people on the plate review page, per camera class."],
    ["0–3 months", "District pilot", "GPU-native edge node, real VAHAN and eGujCop access, SSO, relay authorisation, ONVIF discovery."],
    ["3–18 months", "Rollout", "District by district from the registry; tiers from real camera geometry; Kafka and HA database."],
    ["Beyond", "Extensions", "Vehicle re-identification where plates are unreadable; crowding and wrong-way alerts; VMS SDK adapters."],
  ];
  phases.forEach(([when, what, desc], i) => {
    const x = M + i * 3.07;
    s.addShape(pres.shapes.OVAL, { x: x, y: 2.2, w: 0.34, h: 0.34, fill: { color: i === 0 ? C.cyanL : "1E3A5F" }, line: { color: C.cyanL, width: 1.5 } });
    if (i < 3) s.addShape(pres.shapes.LINE, { x: x + 0.4, y: 2.37, w: 2.6, h: 0, line: { color: "1E3A5F", width: 2 } });
    s.addText(when, { x, y: 2.7, w: 2.85, h: 0.4, fontFace: FONT, fontSize: 14, bold: true, color: C.cyanL, margin: 0, isTextBox: true });
    s.addText(what, { x, y: 3.1, w: 2.85, h: 0.5, fontFace: FONT, fontSize: 22, bold: true, color: C.white, margin: 0, isTextBox: true });
    s.addText(desc, { x, y: 3.65, w: 2.8, h: 1.4, fontFace: FONT, fontSize: 13.5, color: "CBD5E1", margin: 0, valign: "top", isTextBox: true });
  });
  s.addText("One registry. One map. One viewer. For every department's cameras — without replacing any of them.",
    { x: M, y: 5.55, w: W - 2 * M, h: 0.9, fontFace: FONT, fontSize: 26, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addNotes("Close on the principle: integrate, don't replace. Offer the live system and the documents: HLD, Plan for Scale, privacy note, demo video. Nothing in the plate pipeline changes before the submission: every number in the pack was measured on the shipped build. For the finale, the Indian-format fine-tune of the plate reader, tracker changes, a 'check the crop' mark below confidence 0.9, an evidence crop that agrees with the stored plate, and the plate detector at 960 px on plate cameras each sit behind a setting and are adopted only if they pass gates written in advance, by 9 October (bench/pipeline_gates.md). A gain is claimed on our own feeds only, unless a real-plate test passes.");
}

if (P.roadmap !== P.map + 1) throw new Error("the requirements map assumes the roadmap follows it");
pres.writeFile({ fileName: path.join(OUT, "Sentinel-Solution.pptx") }).then((f) => console.log("wrote", f, `(${page} slides)`));
