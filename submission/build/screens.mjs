// Screenshots of the live control room for the deck: node screens.mjs -> submission/out/screens/*.png
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launch, sleep } from "./chrome.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "submission/out/screens");
const WEB = process.env.WEB || "http://localhost:5173";
const API = process.env.API || "http://localhost:8000";
mkdirSync(OUT, { recursive: true });

const WALL = "GNR-POL-001,AMD-AMC-001,GNR-POL-002,AMD-POL-001,GNR-HLTH-001,GNR-PNCHT-002,AMD-AMC-002,MHS-POL-001,GNR-GSRTC-001";
const SHOTS = [
  ["overview", "/", 5000],
  ["wall", `/wall?cams=${WALL}`, 18000],
  ["alerts", "/alerts?status=all", 4000],
  // A short window: over days, the simulator's looping clips put the same plate on several cameras
  // at once, which the journey view rightly flags as implausible (a cloned plate looks like that).
  ["search", `/search?plate=GJ01ZZ0001&since=${process.env.SEARCH_SINCE || "2026-09-24T01:31"}&until=${process.env.SEARCH_UNTIL || "2026-09-24T01:36"}`, 7000],
  ["health", "/health", 4000],
  ["registry", "/registry", 3000],
  ["map", "/map?camera=GNR-POL-001", 9000],
  ["audit", "/audit", 3000],
  // Intrusion zone drawn over the wide stock-footage camera, with the close one beside it (2x2).
  ["zones", "/wall?cams=AMD-TRAF-001,AMD-TRAF-002,AMD-POL-001,AMD-AMC-001", 18000, 2],
];

const login = await (await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "admin", password: process.env.ADMIN_PASSWORD || "admin123" }) })).json();
const b = await launch({ width: 1600, height: 900, port: 9341 });
try {
  await b.send("Emulation.setDeviceMetricsOverride", { width: 1600, height: 900, deviceScaleFactor: 1.5, mobile: false });
  await b.goto(`${WEB}/login`, 800);
  await b.evaluate(`localStorage.setItem('sentinel.token', ${JSON.stringify(login.access_token)});
    localStorage.setItem('sentinel.user', ${JSON.stringify(JSON.stringify(login.user))});
    localStorage.setItem('sentinel.wall.grid', '3'); true`);
  for (const [name, path, wait, grid] of SHOTS) {
    await b.evaluate(`localStorage.setItem('sentinel.wall.grid', '${grid || 3}'); true`);
    await b.goto(WEB + path, 500);
    await sleep(wait);
    const shot = await b.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(join(OUT, `${name}.png`), Buffer.from(shot.data, "base64"));
    console.log("screen", name);
  }
} finally {
  b.close();
}
