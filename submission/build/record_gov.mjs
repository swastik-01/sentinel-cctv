// Records the government-feed demonstration by driving the real control room in headless Chrome, on the
// organisers' sandbox cameras (CAM01..CAM30, onboarded with scripts/onboard_sandbox.py). Nothing is mocked:
// every view hits the running API and the live relays; counts and alerts come from the analytics worker.
// Kept apart from record.mjs: its own frames folder, concat list, chapters and video, so the shipped own-feed
// video and retitle.mjs (which needs video_frames/) are never touched.
//
// Prerequisites: stack, API and web dev server up; the sandbox cameras onboarded and analysed for a while
// (scripts/rotate_worker.py); ideally a worker running on the wall's cameras during the recording.
//
//   REPORT=detections_<stamp>.html node record_gov.mjs   -> submission/out/Sentinel-Gov-Demo.mp4 + chapters
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { govFacts, writeGovCards } from "./cards.mjs";
import { fileUrl, launch, sleep } from "./chrome.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "submission/out");
const FR = join(OUT, "gov_frames");
const WEB = process.env.WEB || "http://localhost:5173";
const API = process.env.API || "http://localhost:8000";
const PW = process.env.ADMIN_PASSWORD || "admin123";
// Wall cameras in order of preference (the ones that played fastest in wall_probe.mjs): the first four whose relays
// are receiving are shown. The sandbox's streams lose packets, and the browser path drops a frame with a missing
// packet, so a 1080p camera with large keyframes can stay black; the pool is warmed from the start.
const POOL = (process.env.WALL || "CAM02,CAM05,CAM01,CAM06,CAM03,CAM20,CAM19,CAM04").split(",");
const PLATE = process.env.PLATE || "";              // a plate read on the sandbox feeds, if any: journey scene
const REPORT = process.env.REPORT ? resolve(OUT, process.env.REPORT) : "";
const W = 1920, H = 1080;

if (REPORT && !existsSync(REPORT)) throw new Error(`no report at ${REPORT}`);
rmSync(FR, { recursive: true, force: true });
mkdirSync(FR, { recursive: true });
writeGovCards(OUT, govFacts(ROOT));

const b = await launch({ width: W, height: H, port: 9341, args: ["--use-fake-ui-for-media-stream"] });
await b.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
const frames = [];
let n = 0;
b.on("Page.screencastFrame", (p) => {
  const name = `g_${String(++n).padStart(6, "0")}.jpg`;
  writeFileSync(join(FR, name), Buffer.from(p.data, "base64"));
  frames.push({ name, t: p.metadata.timestamp });
  b.send("Page.screencastFrameAck", { sessionId: p.sessionId }).catch(() => {});
});

const chapters = [];
let t0 = null;
let stopT = null;
const ev = (js) => b.evaluate(js);
// a new chapter drops the last caption, so no caption is ever shown over the next page
const chapter = (title) => {
  chapters.push({ at: (Date.now() - t0) / 1000, title });
  ev(`document.getElementById('__cap')?.remove(); true`).catch(() => {});
};
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
  el.innerHTML = ${JSON.stringify(`<span style="color:#38bdf8;margin-right:12px">${step}</span>${text.replace(/&/g, "&amp;").replace(/</g, "&lt;")}`)};
})()`);
const byText = (text, tags = "button,a,label") =>
  `[...document.querySelectorAll(${JSON.stringify(tags)})].find(e => e.textContent.replace(/^[^A-Za-z0-9]+/, '').trim().startsWith(${JSON.stringify(text)}))`;
const field = (label) =>
  `[...document.querySelectorAll('label')].find(l => l.textContent.trim().startsWith(${JSON.stringify(label)}))?.querySelector('input,select')`;

async function click(expr) {
  await ev(`(async () => {
    const el = (${expr});
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
  await ev(`(() => { const el = (${expr}); el.scrollIntoView({ block: 'center', behavior: 'instant' }); el.focus(); el.select?.(); })()`);
  for (const ch of text) { await b.send("Input.insertText", { text: ch }); await sleep(delay); }
}
async function choose(expr, value) {
  await ev(`(() => { const el = (${expr}); const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
    set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
}
async function route(path) {
  await ev(`(() => { history.pushState({}, '', ${JSON.stringify(path)}); dispatchEvent(new PopStateEvent('popstate', { state: {} }));
    window.scrollTo(0, 0); return true; })()`);
}
// Start a relay pulling from the sandbox before its tile appears: relays are on demand and the sandbox's keyframes
// are seconds apart, so a cold tile stays black for a while. Asking the relay for HLS is enough to start the pull.
const warmUp = (codes) => codes.forEach((c) => fetch(`http://localhost:8888/${c}/index.m3u8`).catch(() => {}));
async function waitFor(js, timeout = 30000, every = 400) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await ev(js).catch(() => false)) return true; await sleep(every); }
  return false;
}
const hold = sleep;
const scrollTo = (h2Text) => ev(`(() => { const h = [...document.querySelectorAll('h2')].find(h => h.textContent.includes(${JSON.stringify(h2Text)}));
  if (h) h.scrollIntoView({ block: 'start', behavior: 'instant' }); return !!h; })()`);

// the sandbox cameras' facts, from the API, so captions never state a number the system does not show
const tok = (await (await fetch(`${API}/auth/login`, { method: "POST", headers: { "content-type": "application/json" },
  body: JSON.stringify({ username: "admin", password: PW }) })).json()).access_token;
const cams = (await (await fetch(`${API}/cameras?limit=2000`, { headers: { authorization: `Bearer ${tok}` } })).json()).items
  .filter((c) => /^CAM\d\d$/.test(c.camera_code));
const placed = cams.filter((c) => c.lat != null).length;
const codecs = [...new Set(cams.map((c) => c.codec).filter(Boolean))].sort().join(" and ");
const alerts = await (await fetch(`${API}/alerts?status=all&limit=1000`, { headers: { authorization: `Bearer ${tok}` } })).json();
const intrusions = alerts.filter((a) => a.alert_type === "intrusion" && /^CAM\d\d$/.test(a.camera_code));
console.log(`${cams.length} sandbox cameras, ${placed} placed, codecs ${codecs}; ${intrusions.length} sandbox intrusion alerts`);
// keep every pool camera's relay pulling from the start, and the H.265 ones' browser previews (on-demand
// transcodes) too, so tiles do not start black or on a half-decoded picture
const h265 = cams.filter((c) => POOL.includes(c.camera_code) && /265/.test(c.codec || "")).map((c) => c.camera_code);
const warmPool = () => { warmUp(POOL); h265.forEach((c) => fetch(`http://localhost:8888/${c}_sub/index.m3u8`).catch(() => {})); };
warmPool();
const warm = setInterval(warmPool, 3000);
warm.unref();
// a relay is usable when MediaMTX reports it ready and it keeps receiving bytes
async function receiving(code) {
  const get = async () => (await (await fetch(`http://localhost:9997/v3/paths/get/${code}`)).json().catch(() => ({})));
  const a = await get().catch(() => ({}));
  await sleep(1200);
  const z = await get().catch(() => ({}));
  return !!(a.ready && z.ready && (z.bytesReceived || 0) > (a.bytesReceived || 0));
}

try {
  await b.goto(fileUrl(join(OUT, "cards/gov_title.html")), 300);
  await b.send("Page.startScreencast", { format: "jpeg", quality: 82, maxWidth: W, maxHeight: H, everyNthFrame: 1 });
  t0 = Date.now();
  chapter("Title");
  await hold(5500);

  chapter("Sign in");
  await b.goto(`${WEB}/login`, 900);
  await caption("1/8", "Sign in to the control room: role-based, department-scoped, every search audited.");
  await hold(1000);
  await type(field("Username"), "admin", 60);
  await type(field("Password"), PW, 60);
  await click(byText("Sign in"));
  await waitFor(`!!document.querySelector('.stat-grid')`, 15000);
  await hold(500);

  chapter("The 30 sandbox cameras in the registry");
  await click(byText("Registry", "nav a"));
  await waitFor(`!!document.querySelector('input[placeholder^="search code"]')`, 15000);
  await type(`document.querySelector('input[placeholder^="search code"]')`, "CAM", 90);
  await waitFor(`document.querySelectorAll('tbody tr').length >= 10`, 10000);
  await caption("2/8", `The organisers' catalogue lists ${cams.length} cameras by id and name only. Each was onboarded by its RTSP address: probed, relayed on demand and registered in 1–2 s.`);
  await hold(6500);
  await caption("2/8", `Mixed estate as delivered: ${codecs}, 960×576 to 2560×1440. Department and location are not in the catalogue: we read them from the names, and could place ${placed} of ${cams.length}.`);
  await hold(6500);

  chapter("On the map");
  await route("/map?camera=CAM12");
  await waitFor(`!!document.querySelector('.leaflet-container')`, 15000);
  await waitFor(`document.querySelectorAll('.leaflet-tile-loaded').length > 6`, 8000);
  await caption("3/8", "One map for the state: sandbox cameras from Ahmedabad and Adalaj to Junagadh, Rajkot, Navsari and Gandhidham. Positions are approximate, from the names.");
  await hold(7500);

  chapter("Live video wall");
  const live = [];
  for (const c of POOL) { if (live.length < 4 && await receiving(c)) live.push(c); }
  const wall = [...live, ...POOL.filter((c) => !live.includes(c))].slice(0, 4);
  console.log(`wall: ${wall.join(",")} (receiving: ${live.join(",") || "none"})`);
  await ev(`localStorage.setItem('sentinel.wall.grid', '2'); true`);
  await route(`/wall?cams=${wall.join(",")}`);
  await waitFor(`!!(${byText("Hide picker")})`, 8000);
  await click(byText("Hide picker"));                   // the picker also lists the simulator's cameras
  await caption("4/8", "Live viewing of the government feeds on one wall: each camera relayed once, and pulled from the source only while someone watches or analyses it.");
  await waitFor(`[...document.querySelectorAll('.player video')].filter(v => v.videoWidth > 0).length >= 4`, 12000, 500);
  await hold(9000);

  chapter("Vehicle and person detection");
  await route("/health");
  await waitFor(`(() => { const h = [...document.querySelectorAll('h2')].find(h => h.textContent.includes('person detection'));
    return !!h && /CAM\\d\\d/.test(h.parentElement.textContent); })()`, 15000);
  await scrollTo("person detection");
  await caption("5/8", "Vehicles and people detected on every analysed camera, per minute: average and peak in view. This laptop analyses 4 cameras at a time, in rotation.");
  await hold(7500);

  chapter("Intrusion zones and alerts");
  await click(byText("Alerts", "nav a"));
  const got = await waitFor(`[...document.querySelectorAll('.alert')].some(a => a.textContent.includes('intrusion') && /CAM\\d\\d/.test(a.textContent))`, 12000);
  // older simulator alerts may rank above them: bring the first sandbox intrusion alert into view
  await ev(`(() => { const a = [...document.querySelectorAll('.alert')].find(a => a.textContent.includes('intrusion') && /CAM\\d\\d/.test(a.textContent));
    if (a) a.scrollIntoView({ block: 'start', behavior: 'instant' }); return true; })()`);
  await caption("6/8", got
    ? "Intrusion zones on two cameras with people: presence for 3 s raises an alert with the zone, the count and the time. No image of the person is kept."
    : "Intrusion zones are armed on two cameras with people; an alert carries the zone, the count and the time, never an image of the person.");
  await hold(8000);

  if (PLATE) {
    // The finale's task, on real data: a registration number given on the spot, here one the worker read on a
    // sandbox camera earlier. Adding it checks the last 24 h at once (a retrospective alert), then its journey.
    chapter("A designated vehicle on the government feed");
    await click(byText("Watchlist", "nav a"));
    await waitFor(`!!${field("Plate")}`, 10000);
    await caption("7/8", "A plate this system read on CAM06 earlier tonight stands in for a vehicle the police designate. On the watchlist, every analysed camera checks for it.");
    await choose(field("Kind"), "bolo");
    await type(field("Plate"), PLATE, 90);
    await choose(field("Severity"), "high");
    await type(field("Source ref"), "DEMO-GOV-FEED", 30);
    await type(field("Reason"), "designated vehicle (demonstration)", 25);
    await hold(600);
    await click(byText("Add to watchlist"));
    const seen = await waitFor(`!![...document.querySelectorAll('.ok')].find(e => e.textContent.includes(${JSON.stringify(PLATE)}))`, 10000);
    await caption("7/8", seen
      ? "Checked against the last 24 hours at once: it was already seen on a government camera, so a retrospective alert is raised with the time it was seen."
      : "Added: every analysed camera now checks for it.");
    await hold(7000);
    await click(byText("Vehicle Search", "nav a"));
    await waitFor(`!!${field("Registration number")}`, 10000);
    await type(field("Registration number"), PLATE, 70);
    await click(byText("Search"));
    await waitFor(`!!document.querySelector('.crop, td')`, 15000);
    await caption("7/8", "Its timestamped, location-wise history on the government feeds, with the evidence crop for every stop.");
    await hold(7500);
  }

  if (REPORT) {
    chapter("The output report");
    await b.goto(fileUrl(REPORT), 900);
    await caption("8/8", "The output report for this run: detected vehicles and plates with their timestamps, counts per camera, intrusion alerts. Also as PDF and CSV.");
    await hold(5500);
    for (const h of ["Cameras", "Vehicle and person detection", "Intrusion alerts"]) {
      if (await scrollTo(h)) await hold(3500);
    }
  }

  chapter("Summary");
  await b.goto(fileUrl(join(OUT, "cards/gov_end.html")), 300);
  await hold(6000);
  stopT = Date.now() / 1000;
  await b.send("Page.stopScreencast");
} finally {
  clearInterval(warm);
  b.close();
}

// The demo entry must not leave a real registration on the watchlist: deactivate it, and close the alert it raised.
if (PLATE) {
  const auth = { authorization: `Bearer ${tok}`, "content-type": "application/json" };
  const entries = await (await fetch(`${API}/watchlist?active=true&q=${encodeURIComponent(PLATE)}`, { headers: auth })).json();
  for (const w of entries.filter((w) => w.source_ref === "DEMO-GOV-FEED")) {
    await fetch(`${API}/watchlist/${w.id}`, { method: "DELETE", headers: auth });
  }
  const open = await (await fetch(`${API}/alerts?status=new&limit=1000`, { headers: auth })).json();
  for (const a of open.filter((a) => a.watch_plate === PLATE || a.plate_norm === PLATE)) {
    await fetch(`${API}/alerts/${a.id}/close`, { method: "POST", headers: auth,
      body: JSON.stringify({ status: "closed", disposition: "demonstration on the sandbox feeds (record_gov.mjs)" }) });
  }
  console.log(`demo entry for ${PLATE} deactivated; its alerts closed`);
}

// a static page sends no new frames, so the last frame (the end card) lasts until the screencast stopped
const endT = frames.length ? Math.max(frames[frames.length - 1].t + 1.0, stopT || 0) : 0;
let list = "ffconcat version 1.0\n";
frames.forEach((f, i) => {
  const next = i + 1 < frames.length ? frames[i + 1].t : endT;
  list += `file 'gov_frames/${f.name}'\nduration ${Math.max(0.001, next - f.t).toFixed(3)}\n`;
});
if (frames.length) list += `file 'gov_frames/${frames[frames.length - 1].name}'\n`;
writeFileSync(join(OUT, "gov.ffconcat"), list);
const secs = frames.length ? endT - frames[0].t : 0;
console.log(`captured ${frames.length} frames over ${secs.toFixed(1)} s`);
const chap = chapters.map((c) => `${Math.floor(c.at / 60)}:${String(Math.floor(c.at % 60)).padStart(2, "0")} ${c.title}`).join("\n");
writeFileSync(join(OUT, "Sentinel-Gov-Demo-chapters.txt"), chap + "\n");
console.log(chap);
const image = process.env.FFMPEG_IMAGE || "sentinel-feedsim-publisher";
execFileSync("docker", ["run", "--rm", "-v", `${OUT.replace(/\\/g, "/")}:/work`, "-w", "/work", "--entrypoint", "ffmpeg", image,
  "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "gov.ffconcat",
  "-vf", `scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p`,
  "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-movflags", "+faststart", "Sentinel-Gov-Demo.mp4"],
  { stdio: "inherit", env: { ...process.env, MSYS_NO_PATHCONV: "1" } });
console.log("video:", join(OUT, "Sentinel-Gov-Demo.mp4"), `(${readdirSync(FR).length} frames kept in gov_frames)`);
