// Headless-Chrome screenshots of the control room via raw CDP (no puppeteer needed).
// Usage: node scripts/shot.mjs ["/;/map;/wall?cams=A,B"]  (pages separated by ;)   env: BASE, API, OUT, WAIT, CHROME, ADMIN_PASSWORD
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const CHROME = process.env.CHROME || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const BASE = process.env.BASE || "http://localhost:5173";
const API = process.env.API || "http://localhost:8000";
const OUT = process.env.OUT || ".";
const WAIT = Number(process.env.WAIT || 5000);
const pages = (process.argv[2] || "/;/map;/wall;/search?plate=GJ01ZZ0001;/alerts?status=all;/health;/registry;/watchlist").split(";");
const port = 9223;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`,
  "--window-size=1600,1000", `--user-data-dir=${process.env.TEMP}/sentinel-shot`,
  "--autoplay-policy=no-user-gesture-required", "--no-first-run", "about:blank"], { stdio: "ignore" });
await sleep(2000);
const login = await (await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "admin", password: process.env.ADMIN_PASSWORD || "admin123" }) })).json();
const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });

await send("Page.enable");
await send("Page.navigate", { url: `${BASE}/login` }); await sleep(1500);
await send("Runtime.evaluate", { expression:
  `localStorage.setItem('sentinel.token', ${JSON.stringify(login.access_token)});` +
  `localStorage.setItem('sentinel.user', ${JSON.stringify(JSON.stringify(login.user))});` });
for (const p of pages) {
  await send("Page.navigate", { url: BASE + p }); await sleep(WAIT);
  const shot = await send("Page.captureScreenshot", { format: "png" });
  const name = (p === "/" ? "overview" : p.replace(/[\/?=&,]/g, "_").replace(/^_/, "")) + ".png";
  writeFileSync(`${OUT}/${name}`, Buffer.from(shot.result.data, "base64"));
  console.log("saved", name);
}
ws.close(); chrome.kill();
