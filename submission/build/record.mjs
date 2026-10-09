// Records the 2–3 minute demo video by driving the real control room in headless Chrome.
// Nothing is mocked: every click hits the running API, every alert comes from the live
// analytics worker. Prerequisites: stack up, API up, web dev server up, worker running,
// and `uv run --no-sync python scripts/demo_prep.py` a few minutes beforehand.
//
//   node record.mjs            -> submission/out/Sentinel-Demo.mp4 + chapters.txt
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { writeCards } from "./cards.mjs";
import { fileUrl, launch, sleep } from "./chrome.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "submission/out");
const FR = join(OUT, "video_frames");
const WEB = process.env.WEB || "http://localhost:5173";
const API = process.env.API || "http://localhost:8000";
const CATALOGUE = process.env.CATALOGUE || "http://localhost:8010";
const PW = process.env.ADMIN_PASSWORD || "admin123";
const W = 1920, H = 1080;

rmSync(FR, { recursive: true, force: true });
mkdirSync(FR, { recursive: true });

// ------------------------------------------------------------------ title and end cards
writeCards(OUT);

// ------------------------------------------------------------------ browser + screencast
const b = await launch({ width: W, height: H, port: 9340, args: ["--use-fake-ui-for-media-stream"] });
await b.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
const frames = [];
let n = 0;
b.on("Page.screencastFrame", (p) => {
  const name = `f_${String(++n).padStart(6, "0")}.jpg`;
  writeFileSync(join(FR, name), Buffer.from(p.data, "base64"));
  frames.push({ name, t: p.metadata.timestamp });
  b.send("Page.screencastFrameAck", { sessionId: p.sessionId }).catch(() => {});
});

const chapters = [];
let t0 = null;
const chapter = (title) => chapters.push({ at: (Date.now() - t0) / 1000, title });

const ev = (js) => b.evaluate(js);
const caption = (step, text) => ev(`(() => {
  let el = document.getElementById('__cap');
  if (!el) {
    el = document.createElement('div'); el.id = '__cap'; document.body.appendChild(el);
    Object.assign(el.style, { position: 'fixed', left: '50%', bottom: '30px', transform: 'translateX(-50%)',
      maxWidth: '1320px', width: 'max-content', background: 'rgba(2,6,23,0.9)', color: '#fff',
      font: '600 23px/1.42 "Segoe UI", Arial, sans-serif', padding: '15px 24px', borderRadius: '14px',
      zIndex: 2147483647, boxShadow: '0 10px 34px rgba(0,0,0,.5)', border: '1px solid rgba(56,189,248,.55)',
      pointerEvents: 'none' });
  }
  el.innerHTML = ${JSON.stringify(`<span style="color:#38bdf8;margin-right:12px">${step}</span>${text}`)};
})()`);
const find = (expr) => `(${expr})`;
const byText = (text, tags = "button,a,label") =>
  `[...document.querySelectorAll(${JSON.stringify(tags)})].find(e => e.textContent.replace(/^[^A-Za-z0-9]+/, '').trim().startsWith(${JSON.stringify(text)}))`;
const field = (label) =>
  `[...document.querySelectorAll('label')].find(l => l.textContent.trim().startsWith(${JSON.stringify(label)}))?.querySelector('input,select')`;

async function click(expr) {
  await ev(`(async () => {
    const el = ${find(expr)};
    if (!el) throw new Error('not found: ' + ${JSON.stringify(expr)});
    el.scrollIntoView({ block: 'center', behavior: 'instant' });
    await new Promise(r => setTimeout(r, 120));
    const r = el.getBoundingClientRect();
    const d = document.createElement('div');
    Object.assign(d.style, { position: 'fixed', left: (r.left + r.width / 2 - 24) + 'px', top: (r.top + r.height / 2 - 24) + 'px',
      width: '48px', height: '48px', borderRadius: '50%', border: '3px solid #f59e0b', background: 'rgba(245,158,11,.28)',
      zIndex: 2147483646, pointerEvents: 'none', transition: 'transform .5s ease-out, opacity .5s ease-out' });
    document.body.appendChild(d);
    await new Promise(r => setTimeout(r, 380));
    d.style.transform = 'scale(1.9)'; d.style.opacity = '0';
    el.click();
    setTimeout(() => d.remove(), 700);
  })()`);
}
async function type(expr, text, delay = 32) {
  await ev(`(() => { const el = ${find(expr)}; el.scrollIntoView({ block: 'center', behavior: 'instant' }); el.focus(); el.select?.(); })()`);
  for (const ch of text) { await b.send("Input.insertText", { text: ch }); await sleep(delay); }
}
async function choose(expr, value) {
  await ev(`(() => { const el = ${find(expr)}; const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
    set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('change', { bubbles: true })); })()`);
}
async function route(path) {
  await ev(`(() => { history.pushState({}, '', ${JSON.stringify(path)}); dispatchEvent(new PopStateEvent('popstate', { state: {} })); })()`);
}
async function waitFor(js, timeout = 30000, every = 400) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await ev(js).catch(() => false)) return true; await sleep(every); }
  return false;
}
const hold = sleep;

// ------------------------------------------------------------------ the script
try {
  await b.goto(fileUrl(join(OUT, "cards/title.html")), 300);
  await b.send("Page.startScreencast", { format: "jpeg", quality: 82, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
  t0 = Date.now();
  chapter("Title");
  await hold(4500);

  // 1 — login
  chapter("Role-based sign-in");
  await b.goto(`${WEB}/login`, 900);
  await caption("1/11", "Sign in. Five roles — from control-room operator to privacy auditor — with department scoping.");
  await hold(1400);
  await type(field("Username"), "admin", 70);
  await type(field("Password"), PW, 70);
  await click(byText("Sign in"));
  await waitFor(`!!document.querySelector('.stat-grid')`, 15000);
  await hold(600);

  // 2 — overview
  chapter("Control room overview");
  await caption("2/11", "Control-room overview: 14 cameras from 5 departments, live health, plate reads arriving from the analytics worker.");
  await hold(6000);

  // 3 — map
  chapter("GIS registry map");
  await route("/map?camera=GNR-POL-001");
  await waitFor(`!!document.querySelector('.leaflet-container')`);
  await caption("3/11", "One map for every department. Colour is live health — select a camera for its live stream and registry record.");
  await hold(4000);
  await click(byText("district coverage", "label"));
  await hold(3000);

  // 4 — onboard an unfamiliar feed
  chapter("Onboard a camera by stream URL");
  await click(byText("Registry", "nav a"));
  await waitFor(`!!${field("Stream URL")}`);
  await caption("4/11", "A feed nobody has configured: paste its RTSP URL. Sentinel probes it, relays it and registers it.");
  await hold(1200);
  await type(field("Stream URL"), "rtsp://viewer:s3cret@localhost:8554/GNR-POL-002", 28);
  await type(field("Camera code"), "GNR-MUNI-101", 40);
  await type(field("Name"), "Sector 11 junction, north arm", 22);
  await choose(field("Department"), "MUNI");
  await type(field("District"), "Gandhinagar", 30);
  await type(field("Latitude"), "23.2206", 40);
  await type(field("Longitude"), "72.6474", 40);
  await hold(500);
  await click(byText("Probe & onboard"));
  await waitFor(`!![...document.querySelectorAll('.ok')].find(e => e.textContent.includes('GNR-MUNI-101'))`, 30000);
  await caption("4/11", "Onboarded in seconds: codec and resolution learned from the stream itself. The password never reaches a browser.");
  // warm the on-demand H.265 -> H.264 preview so the wall shows it immediately
  fetch("http://localhost:8888/GNR-MUNI-101_sub/index.m3u8").catch(() => {});
  await hold(4000);

  // 5 — video wall
  chapter("Unified video wall");
  // scene 6 shows an H.265 camera through its on-demand H.264 preview: keep that transcode warm
  const warm = setInterval(() => fetch("http://localhost:8888/AMD-TRAF-002_sub/index.m3u8").catch(() => {}), 3000);
  warm.unref();   // never keeps the recorder alive if a scene throws
  await ev(`localStorage.setItem('sentinel.wall.grid', '2'); true`);
  await route("/wall?cams=GNR-MUNI-101,AMD-AMC-001,GNR-HLTH-001,GNR-GSRTC-001");
  await caption("5/11", "One video wall across departments: the H.265 camera onboarded a moment ago, a 1080p municipal camera, an analog D1 hospital feed.");
  await waitFor(`[...document.querySelectorAll('.player video')].filter(v => v.videoWidth > 0).length >= 3`, 20000, 500);
  await hold(9000);

  // cut a camera's feed off-screen; health monitoring will pick it up for scene 9
  await fetch(`${CATALOGUE}/admin/outage/AMD-GSRTC-001?seconds=240`, { method: "POST" });

  // 6 — vehicle and person detection on real traffic
  chapter("Vehicle and person detection");
  await route("/");
  await waitFor(`!!document.querySelector('.stat-grid')`);
  await caption("6/11", "A second detector runs on the frames ANPR already reads: vehicles and people in view, averaged per analysed frame, with the peak.");
  await hold(5000);
  await caption("6/11", "Two cameras replay real traffic, every plate swapped for a synthetic registration, so the detector has real vehicles and people to find.");
  await route("/wall?cams=AMD-TRAF-001,AMD-TRAF-002,AMD-POL-001,GNR-GSRTC-001");   // fresh mount from another page
  await waitFor(`[...document.querySelectorAll('.player video')].filter(v => v.videoWidth > 0).length >= 4`, 9000, 500);
  clearInterval(warm);
  await hold(6000);
  await caption("6/11", "Each plate read now says what it is on: vehicle type and colour, voted across the vehicle's reads, and left blank when unsure.");
  await route("/search?camera=AMD-TRAF-002");
  await waitFor(`document.querySelectorAll('tbody tr td.small').length > 3`, 8000);
  await hold(5000);
  await caption("6/11", "Per camera: average and peak in view. Synthetic cameras honestly read zero. People are counted, never identified — no box, image or track is kept.");
  await route("/health");
  await waitFor(`(() => { const h = [...document.querySelectorAll('h2')].find(h => h.textContent.includes('person detection'));
    return !!h && h.parentElement.textContent.includes('AMD-TRAF-001'); })()`, 10000);
  await hold(400);
  await ev(`(() => { const h = [...document.querySelectorAll('h2')].find(h => h.textContent.includes('person detection')); h.scrollIntoView({ block: 'start', behavior: 'instant' }); return true; })()`);
  await hold(5500);

  // 7 — watchlist from government systems
  chapter("Watchlists (mock VAHAN and eGujCop)");
  await click(byText("Watchlist", "nav a"));
  await waitFor(`!!${byText("Sync VAHAN")}`);
  await caption("7/11", "Watchlists come from government systems. Sync VAHAN and eGujCop (mock adapters with the real record shapes).");
  await hold(1800);
  await click(byText("Sync VAHAN"));
  await hold(2200);
  await click(byText("Sync eGujCop"));
  await hold(3500);

  // 8 — live alerts
  chapter("Real-time watchlist alerts");
  await click(byText("Alerts", "nav a"));
  await caption("8/11", "Every plate read is matched against the watchlist as it happens. Waiting for the next vehicle to pass a camera…");
  const got = await waitFor(`document.querySelectorAll('.alert').length > 0`, 40000, 300);
  await caption("8/11", got
    ? "Alert: a watchlisted vehicle just passed a camera — pushed live with location, time and the evidence crop."
    : "No watchlisted vehicle has passed yet on this loop — alerts appear here the moment one does.");
  await hold(5500);
  if (got) {
    await click(byText("Acknowledge"));
    await caption("8/11", "The operator acknowledges; closing or marking a false positive records a disposition. Every action is audited.");
    await hold(4000);
  }

  // 9 — movement history
  chapter("Vehicle movement history");
  await click(byText("Vehicle Search", "nav a"));
  await waitFor(`!!${field("Registration number")}`);
  await caption("9/11", "A registration number given on the spot: full timestamped, location-wise movement history across departments.");
  await type(field("Registration number"), "GJ 01 ZZ 0001", 70);
  await click(byText("Search"));
  await waitFor(`!!document.querySelector('.crop, td')`, 15000);
  await hold(4500);
  await caption("9/11", "Timeline, evidence crops and route, exportable as CSV. (Simulated feeds loop vehicles through every camera, so this route is not a real journey.)");
  await hold(5500);

  // 10 — health
  chapter("Health monitoring and gap analysis");
  await click(byText("Health & Reports", "nav a"));
  await caption("10/11", "We cut one camera's feed a minute ago. Health monitoring caught it within one 20-second cycle; gaps are reported per district.");
  await hold(6000);

  // 11 — audit
  chapter("Audit trail and privacy");
  await click(byText("Audit trail", "nav a"));
  await caption("11/11", "Accountable by design: every plate search, movement query, onboarding and alert action is in an append-only audit trail. No face recognition.");
  await hold(5500);

  chapter("Summary");
  await b.goto(fileUrl(join(OUT, "cards/end.html")), 300);
  await hold(6000);
  await b.send("Page.stopScreencast");
} finally {
  b.close();
}

// ------------------------------------------------------------------ assemble
const endT = frames.length ? frames[frames.length - 1].t + 1.0 : 0;
let list = "ffconcat version 1.0\n";
frames.forEach((f, i) => {
  const next = i + 1 < frames.length ? frames[i + 1].t : endT;
  list += `file 'video_frames/${f.name}'\nduration ${Math.max(0.001, next - f.t).toFixed(3)}\n`;
});
if (frames.length) list += `file 'video_frames/${frames[frames.length - 1].name}'\n`;
writeFileSync(join(OUT, "frames.ffconcat"), list);
const secs = frames.length ? endT - frames[0].t : 0;
console.log(`captured ${frames.length} frames over ${secs.toFixed(1)} s (${(frames.length / secs).toFixed(1)} fps avg)`);

const chap = chapters.map((c) => `${String(Math.floor(c.at / 60)).padStart(1, "0")}:${String(Math.floor(c.at % 60)).padStart(2, "0")} ${c.title}`).join("\n");
writeFileSync(join(OUT, "Sentinel-Demo-chapters.txt"), chap + "\n");
console.log(chap);

const image = process.env.FFMPEG_IMAGE || "sentinel-feedsim-publisher";
execFileSync("docker", ["run", "--rm", "-v", `${OUT.replace(/\\/g, "/")}:/work`, "-w", "/work", "--entrypoint", "ffmpeg", image,
  "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "frames.ffconcat",
  "-vf", `scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p`,
  "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-movflags", "+faststart", "Sentinel-Demo.mp4"],
  { stdio: "inherit", env: { ...process.env, MSYS_NO_PATHCONV: "1" } });
console.log("video:", join(OUT, "Sentinel-Demo.mp4"));
console.log("frames kept in", FR, `(${readdirSync(FR).length})`);
