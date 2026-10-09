// Minimal headless-Chrome driver over the DevTools protocol. No puppeteer: one fewer
// 150 MB download on a hackathon laptop, and everything we need is five CDP calls.
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const CANDIDATES = [
  process.env.CHROME,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/google-chrome", "/usr/bin/chromium",
].filter(Boolean);

export async function launch({ width = 1600, height = 1000, port = 9333, args = [] } = {}) {
  const { existsSync } = await import("node:fs");
  const exe = CANDIDATES.find((p) => existsSync(p));
  if (!exe) throw new Error("Chrome/Edge not found; set CHROME=path");
  const profile = mkdtempSync(join(tmpdir(), "sentinel-chrome-"));
  const proc = spawn(exe, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`,
    `--window-size=${width},${height}`, `--user-data-dir=${profile}`, "--no-first-run",
    "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required", ...args, "about:blank"],
    { stdio: "ignore" });
  let targets;
  for (let i = 0; i < 40; i++) {
    try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; }
    catch { await sleep(250); }
  }
  const page = targets.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  let id = 0;
  const pending = new Map();
  const listeners = new Map();
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) {
      const { res, rej } = pending.get(d.id); pending.delete(d.id);
      d.error ? rej(new Error(`${d.error.message} ${d.error.data || ""}`)) : res(d.result);
    } else if (d.method && listeners.has(d.method)) {
      for (const fn of listeners.get(d.method)) fn(d.params);
    }
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const i = ++id; pending.set(i, { res, rej }); ws.send(JSON.stringify({ id: i, method, params }));
  });
  const on = (method, fn) => { if (!listeners.has(method)) listeners.set(method, []); listeners.get(method).push(fn); };
  const waitFor = (method, timeout = 30000) => new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error(`timeout waiting for ${method}`)), timeout);
    on(method, (p) => { clearTimeout(t); res(p); });
  });
  await send("Page.enable");
  await send("Runtime.enable");
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  };
  const goto = async (url, settle = 500) => {
    const loaded = waitFor("Page.loadEventFired");
    await send("Page.navigate", { url });
    await loaded; await sleep(settle);
  };
  const close = () => { try { ws.close(); } catch {} proc.kill(); };
  return { send, on, evaluate, goto, close, sleep };
}

export const fileUrl = (p) => "file:///" + p.replace(/\\/g, "/").replace(/^\/+/, "");
