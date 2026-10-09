// Live event feed over the API's WebSocket. One connection per tab, fan-out to subscribers.
import { useEffect, useState } from "react";
import { API, token } from "./api";

export type LiveEvent = { type: string; at: string; [k: string]: any };
type Handler = (e: LiveEvent) => void;

const handlers = new Set<Handler>();
const statusHandlers = new Set<(ok: boolean) => void>();
let ws: WebSocket | null = null;
let backoff = 1000;
let started = false;
let connected = false;
let pingTimer: number | undefined;

function setConnected(v: boolean) {
  connected = v;
  statusHandlers.forEach((h) => h(v));
}

function connect() {
  const t = token();
  if (!t) { window.setTimeout(connect, 2000); return; }
  // The token goes in the first message, never in the URL (proxy logs, browser history and screenshots keep URLs).
  ws = new WebSocket(API.replace(/^http/, "ws") + "/ws/events");
  ws.onopen = () => {
    ws?.send(JSON.stringify({ type: "auth", token: t }));
    backoff = 1000;
    setConnected(true);
    pingTimer = window.setInterval(() => ws?.readyState === 1 && ws.send("ping"), 20000);
  };
  ws.onmessage = (m) => {
    try { const e = JSON.parse(m.data); handlers.forEach((h) => h(e)); } catch { /* ignore */ }
  };
  ws.onclose = () => {
    setConnected(false);
    window.clearInterval(pingTimer);
    window.setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, 15000);
  };
  ws.onerror = () => ws?.close();
}

export function startEvents() {
  if (!started) { started = true; connect(); }
}

export function useEvents(handler: Handler, deps: any[] = []) {
  useEffect(() => {
    handlers.add(handler);
    return () => { handlers.delete(handler); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export function useLiveStatus() {
  const [ok, setOk] = useState(connected);
  useEffect(() => {
    statusHandlers.add(setOk);
    return () => { statusHandlers.delete(setOk); };
  }, []);
  return ok;
}
