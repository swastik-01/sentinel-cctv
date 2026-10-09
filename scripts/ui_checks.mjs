// The control room driven like an operator, in headless Chrome over raw CDP (as shot.mjs; no puppeteer needed).
// Every page for every seeded role (what the menu offers, what a page opened by address says, which controls show),
// then the flows: edit a camera, filter and search the registry, tag / acknowledge / close an alert, a stale
// acknowledge, a blind plate review changed after the reveal, the API going away, a bad token, an unknown address,
// and a phone-width screen.
// Safe to re-run: the camera it makes (ZZUI-*) is deleted at the end, and its sightings and alerts with it; the review's
// crop file is deleted, and its review row through docker compose's psql (where there is none, it says so).
//
// Usage: node scripts/ui_checks.mjs        env: BASE, API, CHROME, ADMIN_PASSWORD, INGEST_KEY, OUT (screenshots)
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = process.env.BASE || "http://localhost:5173";
const API = process.env.API || "http://localhost:8000";
const PW = process.env.ADMIN_PASSWORD || "admin123";
const INGEST_KEY = process.env.INGEST_KEY || "dev_ingest_key_replace_me";
const OUT = process.env.OUT || "";
const port = 9337;
const REPO = join(dirname(fileURLToPath(import.meta.url)), "..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let fails = 0;
const check = (name, ok, info = "") => { fails += !ok; console.log(`  [${ok ? "PASS" : "FAIL"}] ${name} ${info}`); };

// What each page needs (web/src/api.ts PAGE_NEEDS) and what each role holds (infra/postgres/init/02_seed.sql).
const PAGES = { "/map": "cameras.read", "/wall": "streams.view", "/search": "sightings.search", "/alerts": "alerts.read",
  "/health": "reports.read", "/registry": "cameras.read", "/watchlist": "watchlist.read", "/review": "reviews.read",
  "/audit": "audit.read" };
const ROLES = ["admin", "supervisor", "operator", "gsrtc_nodal", "auditor"];

// ---- API helpers (set-up and clean-up only; everything checked goes through the page)
const call = async (path, init = {}, token) => {
  const r = await fetch(API + path, { ...init, headers: { "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers || {}) } });
  return { status: r.status, body: r.status === 204 ? null : await r.json().catch(() => null) };
};
const signIn = async (u) => (await call("/auth/login", { method: "POST", body: JSON.stringify({ username: u, password: PW }) })).body;

// ---- Chrome
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`, "--window-size=1500,950",
  `--user-data-dir=${mkdtempSync(join(tmpdir(), "sentinel-ui-"))}`, "--no-first-run", "about:blank"], { stdio: "ignore" });
let targets;
for (let i = 0; i < 40 && !targets; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(250); } }
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map(); let errors = []; const apiStatus = [];
// The page may call the API as localhost or 127.0.0.1 (api.ts pageHost): its port identifies it.
const API_PORT = new URL(API).port;
const sameApi = (u) => { try { const x = new URL(u); return x.port === API_PORT && ["localhost", "127.0.0.1"].includes(x.hostname); } catch { return false; } };
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); return; }
  if (d.method === "Runtime.exceptionThrown") errors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  if (d.method === "Log.entryAdded" && d.params.entry.level === "error") errors.push(`${d.params.entry.text} ${d.params.entry.url || ""}`);
  if (d.method === "Network.responseReceived" && d.params.type !== "Preflight" && sameApi(d.params.response.url)) apiStatus.push([d.params.response.status, d.params.response.url]);
};
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) throw new Error(`${expr.slice(0, 80)}: ${r.result.exceptionDetails.exception?.description}`);
  return r.result?.result?.value;
};
const until = async (expr, ms = 8000) => {
  for (const t0 = Date.now(); Date.now() - t0 < ms; await sleep(150)) { if (await ev(`!!(${expr})`)) return true; }
  return false;
};
const go = async (path) => { await send("Page.navigate", { url: BASE + path }); await sleep(300); await until("document.readyState === 'complete'"); };
const text = () => ev("document.body.innerText");
const shot = async (name) => {
  if (!OUT) return;
  const s = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(s.result.data, "base64"));
};
const asUser = async (login) => {
  await go("/login");
  await ev(`localStorage.setItem('sentinel.token', ${JSON.stringify(login.access_token)});
            localStorage.setItem('sentinel.user', ${JSON.stringify(JSON.stringify(login.user))}); true`);
};
// React reads typed text from "input" events and choices from "change"; the native setter makes it see the value.
const setVal = (sel, v) => ev(`(() => { const el = ${sel}; if (!el) throw new Error('no element');
  const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(v)});
  el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); return true; })()`);
// Real typing (CDP Input.insertText): the browser applies maxLength, as it does for a person.
const typeInto = async (sel, s) => { await ev(`(() => { const el = ${sel}; el.focus(); el.select(); return true; })()`); await send("Input.insertText", { text: s }); };
const key = (sel, k) => ev(`(${sel}).dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true }))`);
// A trusted Enter, as a person presses it: unlike a dispatched event, it can submit the form around the focused box.
const enter = async () => {
  const k = { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 };
  await send("Input.dispatchKeyEvent", { type: "keyDown", ...k, text: "\r" });
  await send("Input.dispatchKeyEvent", { type: "keyUp", ...k });
};
const q = (css) => `document.querySelector(${JSON.stringify(css)})`;
const byText = (css, t) => `[...document.querySelectorAll(${JSON.stringify(css)})].find(e => e.textContent.trim() === ${JSON.stringify(t)})`;
const field = (label) => `[...document.querySelectorAll('form.modal label')].find(l => l.textContent.trim().startsWith(${JSON.stringify(label)}))?.querySelector('input,select')`;
// allowRefusals: in a flow that provokes a 409 or 422 on purpose, the browser's console line for it is expected.
const realErrors = (allowRefusals = false) => errors.filter((e) => !(allowRefusals && /status of (409|422)/.test(e))).filter((e) => !/favicon\.ico|WHEP|webrtc|\.m3u8|mediamtx|:8889|:8888|ERR_BLOCKED_BY_CLIENT|ERR_INTERNET_DISCONNECTED|Failed to load resource: net::ERR_FAILED/i.test(e));

await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable"); await send("Network.enable");

const suffix = Math.random().toString(16).slice(2, 8).toUpperCase();
const CAM = `ZZUI-${suffix}`;
const PLATE = `GJ96${"CDEFHK"[Math.floor(Math.random() * 6)]}${"MNPRST"[Math.floor(Math.random() * 6)]}${1000 + Math.floor(Math.random() * 8999)}`;
const admin = await signIn("admin");
let watchId = null;
const watchIds = [];
let reviewCrop = null, reviewPlate = null;
try {
  // ---- set-up: one camera and, on it, one watchlist alert
  let r = await call("/cameras", { method: "POST", body: JSON.stringify({ camera_code: CAM, name: `UI check ${suffix}`, department_code: "HOME",
    district: "Gandhinagar", lat: 23.22, lon: 72.65, camera_class: "dome", maintenance: "in_service" }) }, admin.access_token);
  check("set-up: test camera registered", r.status === 201, String(r.status));
  r = await call("/watchlist", { method: "POST", body: JSON.stringify({ kind: "stolen_vehicle", plate: PLATE, severity: "high",
    source: "ui_checks", reason: "UI check" }) }, admin.access_token);
  watchId = r.body?.id;
  r = await call("/ingest/sightings", { method: "POST", headers: { "X-Ingest-Key": INGEST_KEY }, body: JSON.stringify([{ camera_code: CAM,
    event_ts: new Date().toISOString(), plate_text: PLATE, ocr_conf: 0.95, det_conf: 0.9, bbox: [0, 0, 40, 12], track_id: "ui", reads: 3 }]) });
  check("set-up: a watchlist alert raised on it", r.body?.alerts === 1, JSON.stringify(r.body));

  // ---- 1. every page, every role
  console.log("-- pages by role");
  for (const role of ROLES) {
    const login = await signIn(role);
    const perms = login.user.permissions;
    const can = (p) => perms.includes("*") || perms.includes(p);
    await asUser(login);
    await go("/");
    await until(q("nav") + " && document.querySelectorAll('nav a').length > 0");
    const nav = await ev(`[...document.querySelectorAll('nav a')].map(a => new URL(a.href).pathname)`);
    const want = Object.keys(PAGES).filter((p) => can(PAGES[p]));
    check(`${role}: the menu offers exactly the pages the role may open`,
      want.every((p) => nav.includes(p)) && nav.filter((p) => p !== "/").every((p) => want.includes(p)), `menu ${nav.join(" ")}`);
    for (const page of Object.keys(PAGES)) {
      errors = [];
      await go(page === "/alerts" ? "/alerts?status=all" : page);
      await sleep(can(PAGES[page]) ? 1800 : 400);
      const body = await text();
      if (can(PAGES[page])) {
        const ok = !body.includes("not available to your role") && !(await ev(q(".banner-error") + " !== null"));
        check(`${role} ${page}: opens without errors`, ok && realErrors().length === 0, realErrors().slice(0, 2).join(" | ").slice(0, 200));
        if (role === "admin") await shot(`ui${page.replace(/\W/g, "_")}.png`);
      } else {
        check(`${role} ${page}: opened by address, says it is not for the role`, body.includes("not available to your role"));
      }
    }
    await go("/registry"); await until("document.querySelector('tbody a.mono')", 6000);
    // the test camera, or for a user held to another department the first camera they can see
    const btns = await ev(`(() => { const row = (${byText("a.mono", CAM)} ?? document.querySelector('tbody a.mono'))?.closest('tr');
      return row ? [...row.querySelectorAll('button')].map(b => b.textContent.trim()) : null; })()`);
    if (can("cameras.read")) {
      check(`${role}: registry row offers Edit only with cameras.write, Delete only to the administrator`,
        btns !== null && btns.includes("Edit") === can("cameras.write") && btns.includes("Delete") === perms.includes("*"),
        JSON.stringify(btns));
    }
    if (can("alerts.read")) {
      await go("/alerts?status=all"); await until(`document.body.innerText.includes(${JSON.stringify(PLATE)})`, 6000);
      const tagInput = await ev(q(`input[aria-label^="Add a tag to the alert on ${PLATE}"]`) + " !== null");
      check(`${role}: tag box shown only with alerts.ack`, tagInput === can("alerts.ack"));
    }
  }

  // ---- 2. registry flows (supervisor)
  console.log("-- registry flows");
  const sup = await signIn("supervisor");
  await asUser(sup); errors = [];
  await go("/registry");
  await until(byText("a.mono", CAM) + " !== undefined");
  await ev(`${byText("a.mono", CAM)}.closest('tr').querySelector('button').click()`);
  check("Edit opens the dialog with the camera's values", await until(q("form.modal")) &&
    (await ev(`${field("Name")}.value`)) === `UI check ${suffix}` && (await ev(`${field("Camera type")}.value`)) === "dome");
  await setVal(field("Installation year"), "1800");
  apiStatus.length = 0;
  await ev(`${q("form.modal button.btn-primary")}.click()`);
  check("an impossible installation year is refused in the dialog, before any request",
    await until(q("form.modal .error") + `?.textContent.includes("Installation year")`, 3000) && !apiStatus.some(([, u]) => u.includes(`/cameras/${CAM}`)));
  await setVal(field("Latitude"), "");
  await setVal(field("Installation year"), "2016");
  await ev(`${q("form.modal button.btn-primary")}.click()`);
  check("clearing only the latitude is refused in the dialog", await until(q("form.modal .error") + `?.textContent.includes("both latitude")`, 3000));
  await setVal(field("Latitude"), "23.22");
  await setVal(field("Maintenance"), "faulty");
  await setVal(field("AMC / warranty expiry"), "2020-01-31");
  await setVal(field("Maintenance note"), "lens fogged <b>bold?</b>");
  await ev(`${q("form.modal button.btn-primary")}.click()`);
  check("Save closes the dialog and says so", await until(`!${q("form.modal")} && document.body.innerText.includes(${JSON.stringify(`${CAM} saved`)})`));
  await until(`${byText("a.mono", CAM)}?.closest('tr').innerText.includes('faulty')`, 5000);
  const row = await ev(`${byText("a.mono", CAM)}.closest('tr').innerText`);
  check("the row shows the new maintenance state, year and AMC", /faulty/.test(row) && /2016/.test(row) && /2020-01-31/.test(row), row.replace(/\s+/g, " ").slice(0, 160));
  check("an expired AMC is shown red", await ev(`[...${byText("a.mono", CAM)}.closest('tr').querySelectorAll('td')].some(td => td.className.includes('due-past'))`));
  const stored = (await call(`/cameras/${CAM}`, {}, sup.access_token)).body;
  check("the note is stored as text, markup and all", stored?.maintenance_note === "lens fogged <b>bold?</b>", stored?.maintenance_note);
  await ev(`${byText("a.mono", CAM)}.closest('tr').querySelector('button').click()`);
  await until(q("form.modal"));
  await ev(`window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`);
  check("Escape closes the dialog", await until(`!${q("form.modal")}`, 2000));
  await ev(`${byText("a.mono", CAM)}.closest('tr').querySelector('button').click()`);
  await until(q("form.modal"));
  apiStatus.length = 0;
  await ev(`${q("form.modal button.btn-primary")}.click()`);
  check("Save with nothing changed closes without a request", await until(`!${q("form.modal")}`, 2000) && !apiStatus.some(([, u]) => u.includes(`/cameras/${CAM}`) && !u.includes("?")));
  await setVal(q('select[aria-label="Maintenance"]'), "faulty");
  await sleep(1200);
  const codes = await ev(`[...document.querySelectorAll('tbody a.mono')].map(a => a.textContent)`);
  const rowsMaint = await ev(`[...document.querySelectorAll('tbody tr')].map(tr => tr.querySelector('.mt')?.textContent).filter(Boolean)`);
  check("the maintenance filter shows only faulty cameras", codes.includes(CAM) && rowsMaint.every((m) => m === "faulty"), `${codes.length} rows`);
  await setVal(q('select[aria-label="Maintenance"]'), "decommissioned");
  check("an empty result says so", await until(`document.body.innerText.includes('No cameras match these filters')`, 4000));
  await setVal(q('select[aria-label="Maintenance"]'), "");
  apiStatus.length = 0;
  for (const part of ["Z", "ZZ", "ZZU", "ZZUI", "ZZUI-"]) { await setVal(q('input[aria-label="Search"]'), part); await sleep(40); }
  await sleep(900);
  const searches = apiStatus.filter(([, u]) => u.includes("/cameras?") && u.includes("q=")).length;
  const found = await ev(`[...document.querySelectorAll('tbody a.mono')].map(a => a.textContent)`);
  check("typing searches once, after the pause", searches === 1 && found.includes(CAM), `${searches} searches, ${found.length} rows`);
  await setVal(q('input[aria-label="Search"]'), "%");
  await sleep(900);
  check("searching for '%' is literal (no camera has one)", await until(`document.body.innerText.includes('No cameras match these filters')`, 3000));
  await setVal(q('input[aria-label="Search"]'), "");
  check("registry flows raised no page errors", realErrors().length === 0, realErrors().slice(0, 2).join(" | ").slice(0, 200));

  // A watchlist plate and a sighting of it on the test camera: one more alert.
  const raise = async (plate) => {
    const w = await call("/watchlist", { method: "POST", body: JSON.stringify({ kind: "stolen_vehicle", plate, severity: "critical",
      source: "ui_checks", reason: "UI live push" }) }, admin.access_token);
    if (w.body?.id) watchIds.push(w.body.id);
    return call("/ingest/sightings", { method: "POST", headers: { "X-Ingest-Key": INGEST_KEY }, body: JSON.stringify([{ camera_code: CAM,
      event_ts: new Date().toISOString(), plate_text: plate, ocr_conf: 0.97, det_conf: 0.9, bbox: [0, 0, 40, 12], track_id: "ui-live", reads: 3 }]) });
  };
  const variant = (n) => PLATE.slice(0, -4) + String((Number(PLATE.slice(-4)) + n) % 10000).padStart(4, "0");
  const pill = () => ev(`Number([...document.querySelectorAll('nav a')].find(a => a.textContent.includes('Alerts'))?.querySelector('.pill')?.textContent ?? 0)`);
  const cardOf = (plate) => `[...document.querySelectorAll('.card.alert')].find(c => c.innerText.includes(${JSON.stringify(plate)}))`;
  const btnOf = (plate, label) => `[...(${cardOf(plate)}?.querySelectorAll('button') ?? [])].find(b => b.textContent.trim() === ${JSON.stringify(label)})`;

  // ---- 3. alert flows (supervisor; the operator plays the colleague who got there first)
  console.log("-- alert flows");
  errors = [];
  await go("/alerts?status=new");
  check("the new alert is listed", await until(`document.body.innerText.includes(${JSON.stringify(PLATE)})`));
  const card = `[...document.querySelectorAll('.card.alert')].find(c => c.innerText.includes(${JSON.stringify(PLATE)}))`;
  const tagBox = q(`input[aria-label^="Add a tag to the alert on ${PLATE}"]`);
  const cardBtn = (label) => `[...${card}.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(label)})`;
  await setVal(tagBox, "  Patrol   sent ");
  await key(tagBox, "Enter");
  check("Enter adds a tag, its spaces tidied", await until(`${card}?.querySelector('.tag-chip')?.textContent.startsWith('Patrol sent')`));
  await setVal(tagBox, "PATROL SENT"); await key(tagBox, "Enter"); await sleep(600);
  check("the same tag in other capitals is not added twice", (await ev(`${card}.querySelectorAll('.tag-chip').length`)) === 1);
  await typeInto(tagBox, "x".repeat(40));
  check("the tag box stops at 32 characters", (await ev(`${tagBox}.value.length`)) === 32);
  await setVal(tagBox, "<script>"); await key(tagBox, "Enter");
  check("a refused tag shows the API's reason", await until(q("[role=alert]") + `?.textContent.includes('tags')`, 3000),
    await ev(q("[role=alert]") + "?.textContent ?? ''"));
  await setVal(tagBox, "અટકાવેલ"); await key(tagBox, "Enter");
  check("a Gujarati tag is added", await until(`[...${card}.querySelectorAll('.tag-chip')].some(c => c.textContent.startsWith('અટકાવેલ'))`));
  await setVal(q('input[aria-label="Filter by tag"]'), "patrol sent");
  await sleep(1200);
  check("the tag filter keeps the tagged alert", await until(`document.body.innerText.includes(${JSON.stringify(PLATE)})`, 3000));
  await setVal(q('input[aria-label="Filter by tag"]'), "no-such-tag");
  check("a filter nothing carries says so", await until(`document.body.innerText.includes('tagged “no-such-tag”')`, 4000));
  await setVal(q('input[aria-label="Filter by tag"]'), "");
  await until(`document.body.innerText.includes(${JSON.stringify(PLATE)})`, 4000);
  await ev(`${card}.querySelector('button[aria-label="Remove the tag અટકાવેલ"]').click()`);
  check("× removes a tag", await until(`![...${card}.querySelectorAll('.tag-chip')].some(c => c.textContent.startsWith('અટકાવેલ'))`, 4000));
  const alertId = (await call(`/alerts?status=new&limit=1000`, {}, sup.access_token)).body.find((a) => a.plate_norm === PLATE)?.id;
  const op = await signIn("operator");
  await call(`/alerts/${alertId}/ack`, { method: "POST" }, op.access_token);       // a colleague acknowledges first
  check("a colleague's acknowledgement takes the alert off the open list live, without a reload",
    await until(`!document.body.innerText.includes(${JSON.stringify(PLATE)})`, 5000));
  // The same race with the live feed cut: the event socket is blocked, so the page cannot hear the colleague.
  // A stand-in for the event socket that never connects, injected before the page's own code: a dead live link.
  const dead = await send("Page.addScriptToEvaluateOnNewDocument", { source: `(() => {
    const Real = window.WebSocket;
    window.WebSocket = function (url, protocols) {
      if (!String(url).includes("/ws/events")) return new Real(url, protocols);
      const ws = { readyState: 0, send() {}, close() { this.readyState = 3; } };
      setTimeout(() => { ws.readyState = 3; ws.onclose && ws.onclose({ code: 1006 }); }, 50);
      return ws;
    };
  })();` });
  const STALE = variant(3333);
  check("set-up: an alert for the stale-click check", (await raise(STALE)).body?.alerts === 1);
  await go("/alerts?status=new");
  check("with the event socket down, the menu says it is reconnecting",
    await until(`document.querySelector('.live')?.textContent.includes('reconnecting')`, 8000));
  await until(`document.body.innerText.includes(${JSON.stringify(STALE)})`, 5000);
  const staleId = (await call(`/alerts?status=new&limit=1000`, {}, sup.access_token)).body.find((a) => a.plate_norm === STALE)?.id;
  await call(`/alerts/${staleId}/ack`, { method: "POST" }, op.access_token);
  await sleep(500);
  const staleBtn = await ev(`${btnOf(STALE, "Acknowledge")} !== undefined`);
  if (staleBtn) await ev(`${btnOf(STALE, "Acknowledge")}.click()`);
  check("a stale Acknowledge explains and refreshes the list", staleBtn &&
    await until(q("[role=alert]") + `?.textContent.includes('another operator')`, 4000) &&
    await until(`!document.body.innerText.includes(${JSON.stringify(STALE)})`, 4000), staleBtn ? "" : "the card had already gone");
  await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: dead.result.identifier });
  await go("/alerts?status=new");
  check("the event socket reconnects once it can", await until(`document.querySelector('.live')?.textContent.includes('live events')`, 15000));
  await go("/alerts?status=acknowledged");
  await until(`document.body.innerText.includes(${JSON.stringify(PLATE)})`);
  await ev(`${cardBtn("Close")}.click()`);
  await until(q('select[aria-label="Disposition"]'));
  await setVal(q('select[aria-label="Disposition"]'), "Vehicle intercepted");
  await setVal(q('input[aria-label="Note"]'), "at Ch-0 circle");
  await ev(`${cardBtn("Close alert")}.click()`);
  check("Close leaves the acknowledged list", await until(`!document.body.innerText.includes(${JSON.stringify(PLATE)})`, 4000));
  const closed = (await call(`/alerts?status=closed&limit=1000`, {}, sup.access_token)).body.find((a) => a.plate_norm === PLATE);
  check("the disposition keeps both the choice and the note", closed?.disposition === "Vehicle intercepted: at Ch-0 circle", closed?.disposition);
  check("alert flows raised no page errors", realErrors(true).length === 0, realErrors(true).slice(0, 2).join(" | ").slice(0, 200));

  // ---- 3b. live push: an alert raised while the page is open arrives without a reload (needs a real broker)
  console.log("-- live push");
  await go("/alerts?status=new");
  await until(q(".alerts"));
  await sleep(1500);                               // the event socket signs in after the page loads
  const before = await pill();
  const LIVE1 = variant(1111);
  let r1 = await raise(LIVE1);
  check("set-up: a second alert raised while the page is open", r1.body?.alerts === 1, JSON.stringify(r1.body));
  check("it appears in the open list without a reload", await until(`document.body.innerText.includes(${JSON.stringify(LIVE1)})`, 6000));
  check("a card pops up for it", await until(`[...document.querySelectorAll('.toast')].some(t => t.innerText.includes(${JSON.stringify(LIVE1)}))`, 3000));
  const pillExpr = `Number([...document.querySelectorAll('nav a')].find(a => a.textContent.includes('Alerts'))?.querySelector('.pill')?.textContent ?? 0)`;
  check("the menu's open-alert count goes up by one", await until(`${pillExpr} === ${before + 1}`, 4000), `${before} -> ${await pill()}`);
  await go("/map");
  await sleep(1500);
  const LIVE2 = variant(2222);
  r1 = await raise(LIVE2);
  check("on another page, the card still pops up", r1.body?.alerts === 1
    && await until(`[...document.querySelectorAll('.toast')].some(t => t.innerText.includes(${JSON.stringify(LIVE2)}))`, 6000));

  // ---- 3c. plate review (auditor): a mistyped blind reading, changed after the reveal; the first stays on record
  console.log("-- plate review");
  const auditor = await signIn("auditor");
  await asUser(auditor); errors = [];
  const REV = variant(3333);
  const TYPO = REV.slice(0, -2) + String((Number(REV.slice(-2)) + 55) % 100).padStart(2, "0");   // two characters off
  // A crop the browser can show (a broken one disables the check), drawn by the browser itself.
  const jpeg = await ev(`(() => { const c = document.createElement('canvas'); c.width = 220; c.height = 50;
    const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, 220, 50); x.fillStyle = '#000';
    x.font = '28px monospace'; x.fillText(${JSON.stringify(REV)}, 8, 36); return c.toDataURL('image/jpeg').split(',')[1]; })()`);
  mkdirSync(join(REPO, "data", "crops", CAM), { recursive: true });
  reviewCrop = join(REPO, "data", "crops", CAM, `uicheck_${suffix}.jpg`);
  writeFileSync(reviewCrop, Buffer.from(jpeg, "base64"));
  reviewPlate = REV;
  r = await call("/ingest/sightings", { method: "POST", headers: { "X-Ingest-Key": INGEST_KEY }, body: JSON.stringify([{ camera_code: CAM,
    event_ts: new Date().toISOString(), plate_text: REV, ocr_conf: 0.95, det_conf: 0.9, bbox: [0, 0, 40, 12], track_id: "ui-review", reads: 3,
    crop_path: `/crops/${CAM}/uicheck_${suffix}.jpg` }]) });
  await go("/review");
  await until(q("input.prefix"));
  await setVal(q("input.prefix"), CAM);
  await until(`${q("img.review-crop")} && document.body.innerText.includes(${JSON.stringify(CAM)})`);
  await typeInto(q("form.review-card input.review-input"), TYPO);
  await enter();
  const reveal = q(".reveal");
  check("a blind reading typed in the page is graded, and only then Sentinel's read shows",
    await until(`${reveal}?.innerText.includes(${JSON.stringify(REV)}) && ${reveal}.innerText.includes('wrong')`, 6000));
  await ev(`[...document.querySelectorAll('form.review-card button')].find(b => b.textContent.startsWith('Edit my reading')).click(); true`);
  await until(q(".review-edit input"));
  await typeInto(q(".review-edit input"), REV);
  await enter();
  check("Edit my reading: Enter saves the change beside the first reading and stays on the crop",
    await until(`${reveal}?.innerText.includes('Changed after the reveal') && ${reveal}.innerText.includes(${JSON.stringify(TYPO)})`, 6000)
    && await ev(`!${q(".review-edit")} && [...document.querySelectorAll('form.review-card button')].some(b => b.textContent.startsWith('Next'))`));
  await ev(`[...document.querySelectorAll('.my-reviews button')].find(b => b.textContent.startsWith('Show')).click(); true`);
  check("the reviewer's saved checks show both readings; the page raised no errors",
    await until(`[...document.querySelectorAll('.my-review')].some(e => e.innerText.includes(${JSON.stringify(TYPO)})
                 && e.innerText.includes('Changed after the reveal'))`, 6000) && realErrors().length === 0,
    realErrors().slice(0, 2).join(" | ").slice(0, 200));
  await ev(`[...document.querySelectorAll('.review-bar button')].find(b => b.textContent.trim() === 'Results').click(); true`);
  check("Results, plate by plate: Sentinel's read beside the reviewer's first reading and the change",
    await until(`[...document.querySelectorAll('table.plates tbody tr')].some(tr => tr.innerText.includes(${JSON.stringify(REV)})
                 && tr.innerText.includes(${JSON.stringify(TYPO)}) && tr.innerText.includes('after the change'))`, 6000));
  await asUser(sup);

  // ---- 4. failures an operator will meet
  console.log("-- failures");
  await send("Network.setBlockedURLs", { urls: [`http://localhost:${API_PORT}/*`, `http://127.0.0.1:${API_PORT}/*`] });
  await go("/registry");
  check("with the API away, a banner says so", await until(q(".banner-error") + "?.textContent.includes('not answering')", 6000));
  check("and the page says what it could not load", await until(`document.body.innerText.includes('Could not load the registry')`, 3000));
  await send("Network.setBlockedURLs", { urls: [] });
  await go("/registry");
  check("the banner goes once the API answers again", await until(`!${q(".banner-error")} && ${byText("a.mono", CAM)} !== undefined`, 6000));
  await ev(`localStorage.setItem('sentinel.token', 'not-a-token'); true`);
  await go("/alerts");
  check("a bad token goes back to sign-in", await until(`location.pathname === '/login'`, 6000));
  await asUser(sup);
  await go("/no/such/page");
  check("an unknown address goes to the overview", await until(`location.pathname === '/'`, 4000));
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  for (const page of ["/", "/registry", "/alerts", "/health", "/map", "/search"]) {
    await go(page); await sleep(1500);
    const over = await ev("document.documentElement.scrollWidth - window.innerWidth");
    // the content column gets the screen: the menu is a bar above it, not a column beside it
    const main = await ev("document.querySelector('main')?.getBoundingClientRect().width ?? 0");
    check(`phone width ${page}: no sideways scrolling, content takes the width`, over <= 1 && main >= 380, `${over}px over, main ${Math.round(main)}px`);
    await shot(`ui_phone${page.replace(/\W/g, "_")}.png`);
  }
  await send("Emulation.clearDeviceMetricsOverride");
} finally {
  await call(`/cameras/${CAM}`, { method: "DELETE" }, admin.access_token);     // its sightings and alerts go with it
  for (const id of [watchId, ...watchIds].filter(Boolean)) await call(`/watchlist/${id}`, { method: "DELETE" }, admin.access_token);
  if (reviewCrop) {
    rmSync(reviewCrop, { force: true });
    try { rmdirSync(dirname(reviewCrop)); } catch { /* not empty: the test camera kept other crops */ }
  }
  if (reviewPlate) {     // a review outlives its sighting by design (plate_reviews keeps results), so it is removed here
    const out = spawnSync("docker", ["compose", "exec", "-T", "postgres", "psql", "-U", "sentinel", "-d", "sentinel", "-tAc",
      `DELETE FROM plate_reviews WHERE stored_plate = '${reviewPlate}'`], { cwd: REPO, encoding: "utf8" });
    if (out.status !== 0) console.log(`  [WARN] the review row for ${reviewPlate} was not removed (no docker compose here)`);
  }
  ws.close(); chrome.kill();
}
console.log(fails ? `\n${fails} FAILED` : "\nALL PASS");
process.exit(fails ? 1 : 0);
