// Generates docs/diagrams/*.svg. One visual language for every diagram in the HLD and deck:
//   blue  = video       green = metadata / events     red = alerts
//   amber = government integration (dashed)            grey dashed = control plane
//   dashed grey boxes = existing department infrastructure, which Sentinel does not replace
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "docs/diagrams");
const FONT = "Segoe UI, Arial, Helvetica, sans-serif";
const MONO = "Consolas, 'Courier New', monospace";

const STYLE = {
  plain: { fill: "#FFFFFF", stroke: "#334155" },
  ours: { fill: "#E0F2FE", stroke: "#0369A1" },
  store: { fill: "#ECFDF5", stroke: "#047857" },
  ext: { fill: "#FEF3C7", stroke: "#B45309" },
  ui: { fill: "#FFE4E6", stroke: "#BE123C" },
  dept: { fill: "#F8FAFC", stroke: "#94A3B8", dash: "6 4" },
  dark: { fill: "#0F172A", stroke: "#0F172A", text: "#FFFFFF", sub: "#CBD5E1" },
};
const EDGE = {
  video: { color: "#0369A1", width: 2.2 },
  meta: { color: "#047857", width: 2.2 },
  alert: { color: "#DC2626", width: 2.2 },
  control: { color: "#64748B", width: 1.6, dash: "5 4" },
  ext: { color: "#B45309", width: 1.8, dash: "6 4" },
  plain: { color: "#334155", width: 1.5 },
};

const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

class Diagram {
  constructor(w, h) { this.w = w; this.h = h; this.back = []; this.mid = []; this.front = []; this.nodes = {}; }

  zone(x, y, w, h, label, { fill = "#F1F5F9", stroke = "#CBD5E1" } = {}) {
    this.back.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="16" fill="${fill}" stroke="${stroke}" stroke-width="1.2"/>`);
    if (label) this.back.push(`<text x="${x + 16}" y="${y + 22}" font-family="${FONT}" font-size="12" font-weight="700" letter-spacing="1.2" fill="#475569">${esc(label.toUpperCase())}</text>`);
  }

  node(id, x, y, w, h, title, lines = [], style = "plain", { center = false, badge = null, titleSize = 14.5, lineGap = 17, top = 26 } = {}) {
    const s = STYLE[style];
    this.nodes[id] = { x, y, w, h };
    this.mid.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" fill="${s.fill}" stroke="${s.stroke}" stroke-width="1.6"${s.dash ? ` stroke-dasharray="${s.dash}"` : ""}/>`);
    const tx = center ? x + w / 2 : x + 14 + (badge != null ? 30 : 0);
    const anchor = center ? "middle" : "start";
    if (badge != null) {
      this.mid.push(`<circle cx="${x + 26}" cy="${y + top - 5}" r="13" fill="${s.stroke}"/>`,
        `<text x="${x + 26}" y="${y + top - 0.5}" text-anchor="middle" font-family="${FONT}" font-size="13" font-weight="700" fill="#FFFFFF">${badge}</text>`);
    }
    this.mid.push(`<text x="${tx}" y="${y + top}" text-anchor="${anchor}" font-family="${FONT}" font-size="${titleSize}" font-weight="700" fill="${s.text || "#0F172A"}">${esc(title)}</text>`);
    lines.forEach((ln, i) => {
      const mono = typeof ln === "object" && ln.mono;
      const accent = typeof ln === "object" && ln.accent;
      const t = typeof ln === "object" ? ln.t : ln;
      const lx = center ? x + w / 2 : x + 14;
      this.mid.push(`<text x="${lx}" y="${y + top + 20 + i * lineGap}" text-anchor="${anchor}" font-family="${mono ? MONO : FONT}" font-size="${mono ? 12 : 12.5}" ${accent ? `font-weight="700" fill="${accent}"` : `fill="${s.sub || "#475569"}"`}>${esc(t)}</text>`);
    });
    return this;
  }

  // Port on a node side: l r t b, with t in [0,1] along the side.
  p(id, side, t = 0.5) {
    const n = this.nodes[id];
    if (!n) throw new Error(`no node ${id}`);
    return { l: [n.x, n.y + n.h * t], r: [n.x + n.w, n.y + n.h * t], t: [n.x + n.w * t, n.y], b: [n.x + n.w * t, n.y + n.h] }[side];
  }

  edge(points, kind = "plain", label = null, { at = null, both = false, labelSide = "center" } = {}) {
    const e = EDGE[kind];
    const d = points.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
    this.mid.push(`<path d="${d}" fill="none" stroke="${e.color}" stroke-width="${e.width}"${e.dash ? ` stroke-dasharray="${e.dash}"` : ""} marker-end="url(#m-${kind})"${both ? ` marker-start="url(#m-${kind})"` : ""} stroke-linejoin="round"/>`);
    if (label) {
      let [lx, ly] = at || (() => {
        const [a, b] = [points[Math.floor((points.length - 1) / 2)], points[Math.floor((points.length - 1) / 2) + 1]];
        return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      })();
      this.label(lx, ly, label, e.color, labelSide);
    }
    return this;
  }

  label(x, y, text, color = "#334155", align = "center") {
    const lines = Array.isArray(text) ? text : [text];
    const w = Math.max(...lines.map((l) => l.length)) * 6.3 + 12;
    const h = lines.length * 15 + 6;
    const rx = align === "left" ? x : align === "right" ? x - w : x - w / 2;
    this.front.push(`<rect x="${rx}" y="${y - h / 2}" width="${w}" height="${h}" rx="4" fill="#FFFFFF" fill-opacity="0.94"/>`);
    lines.forEach((l, i) => this.front.push(
      `<text x="${rx + w / 2}" y="${y - h / 2 + 15 + i * 15}" text-anchor="middle" font-family="${FONT}" font-size="11.5" font-weight="600" fill="${color}">${esc(l)}</text>`));
  }

  text(x, y, str, { size = 12.5, weight = 400, color = "#475569", anchor = "start", font = FONT } = {}) {
    this.front.push(`<text x="${x}" y="${y}" text-anchor="${anchor}" font-family="${font}" font-size="${size}" font-weight="${weight}" fill="${color}">${esc(str)}</text>`);
  }

  raw(s, layer = "mid") { this[layer].push(s); }

  legend(x, y, items, { title = "Legend", cols = 1, colW = 150 } = {}) {
    this.front.push(`<text x="${x}" y="${y}" font-family="${FONT}" font-size="11" font-weight="700" letter-spacing="1" fill="#64748B">${esc(title.toUpperCase())}</text>`);
    items.forEach(([kind, text], i) => {
      const cx = x + (i % cols) * colW, cy = y + 20 + Math.floor(i / cols) * 20;
      if (STYLE[kind] && !EDGE[kind]) {
        const s = STYLE[kind];
        this.front.push(`<rect x="${cx}" y="${cy - 9}" width="26" height="14" rx="3" fill="${s.fill}" stroke="${s.stroke}" stroke-width="1.4"${s.dash ? ` stroke-dasharray="4 3"` : ""}/>`);
      } else {
        const e = EDGE[kind];
        this.front.push(`<path d="M${cx},${cy - 2} L${cx + 26},${cy - 2}" stroke="${e.color}" stroke-width="${e.width}"${e.dash ? ` stroke-dasharray="${e.dash}"` : ""} marker-end="url(#m-${kind})"/>`);
      }
      this.front.push(`<text x="${cx + 36}" y="${cy + 2}" font-family="${FONT}" font-size="12" fill="#334155">${esc(text)}</text>`);
    });
  }

  svg() {
    const markers = Object.entries(EDGE).map(([k, e]) =>
      `<marker id="m-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${e.color}"/></marker>`).join("");
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${this.w} ${this.h}" width="${this.w}" height="${this.h}">
<defs>${markers}</defs>
<rect width="${this.w}" height="${this.h}" fill="#FFFFFF"/>
${this.back.join("\n")}
${this.mid.join("\n")}
${this.front.join("\n")}
</svg>`;
  }
}

const out = {};

// ---------------------------------------------------------------- D1 statewide architecture
{
  const d = new Diagram(1200, 680);
  d.zone(16, 16, 282, 530, "Department estates · unchanged");
  d.zone(330, 16, 400, 530, "District edge · ×33");
  d.zone(762, 16, 422, 530, "State core · GSDC + DR");

  const depts = [
    ["Police (Home Dept)", ["IP cameras and NVRs", "Hikvision · Dahua · CP Plus"]],
    ["Municipal Corporations", ["Enterprise VMS", "Honeywell · Milestone · others"]],
    ["GSRTC · Health · Panchayat", ["DVRs, analog + encoders", "7–15 day local retention"]],
    ["RTO · FCS · 20+ departments", ["Mixed IP and analog", "local and cloud storage"]],
    ["Private-shared cameras", ["Societies · malls · shops", "where legally permitted"]],
  ];
  depts.forEach(([t, l], i) => d.node(`dep${i}`, 32, 50 + i * 96, 250, 82, t, l, "dept"));

  d.node("relay", 350, 50, 360, 128, "Media relay (MediaMTX)",
    ["One upstream session per camera", "RTSP to analytics · WebRTC/HLS to viewers", "H.265 → H.264 preview only when watched", "View-only cameras connect on demand"], "ours");
  d.node("ai", 350, 214, 360, 132, "GPU analytics nodes",
    ["NVDEC decode → plate detector → OCR", "Per-camera tracks + character voting", "Tier A: ANPR 5 fps · Tier B: events 1 fps", "Cameras sharded across nodes"], "ours");
  d.node("spool", 350, 380, 170, 140, "Store-and-forward",["Batches kept on disk", "while the core is out,", "replayed in order", "Cached watchlist logs", "hits; alert on replay", { t: "built in the PoC", accent: "#047857" }], "store");
  d.node("crops", 540, 380, 170, 140, "Evidence store", ["Plate crops, 30 days,", "fetched on alert/search", "Design: object store", "PoC: local disk, served", "with token + scope only"], "store");

  d.node("api", 782, 50, 382, 84, "Sentinel API · stateless, load-balanced", ["Onboarding · registry · search · alerts · RBAC"], "ours");
  d.node("bus", 782, 166, 180, 96, "Event bus", ["Kafka, partitioned", "by district"], "ours");
  d.node("match", 984, 166, 180, 96, "Watchlist matcher", ["Exact + 1-edit fuzzy", "alert fan-out"], "ours");
  d.node("db", 782, 290, 180, 104, "PostGIS", ["Registry and GIS", "sightings, partitioned", "primary + sync standby"], "store");
  d.node("audit", 984, 290, 180, 104, "Audit log", ["Append-only", "plate searches, actions"], "store");
  d.node("adapt", 782, 420, 382, 96, "Government DB adapters", ["VAHAN · SARTHI · eGujCop · AFIS/NAFIS", "One contract: fetch() → watchlist entries"], "ext");

  d.node("rooms", 350, 578, 360, 86, "Control rooms · State + 33 districts", ["Video wall · map · vehicle search · alerts"], "ui");
  d.node("govt", 782, 578, 382, 86, "NIC and State systems", ["VAHAN · SARTHI · CCTNS (eGujCop) · NAFIS"], "ext");

  // departments -> relay via a collector
  depts.forEach((_, i) => d.edge([d.p(`dep${i}`, "r"), [312, d.p(`dep${i}`, "r")[1]]], "video"));
  d.raw(`<path d="M312,91 L312,475" stroke="${EDGE.video.color}" stroke-width="2.2"/>`);
  d.edge([[312, 114], d.p("relay", "l", 0.5)], "video");
  d.label(312, 530, ["RTSP · ONVIF", "vendor API"], EDGE.video.color);
  d.edge([d.p("relay", "b"), d.p("ai", "t")], "video", "RTSP · local network", { at: [530, 196] });
  d.edge([d.p("ai", "b", 0.24), d.p("spool", "t")], "meta");
  d.edge([d.p("ai", "b", 0.76), d.p("crops", "t")], "meta");
  d.edge([[710, 240], [782, 240]], "meta");
  d.label(746, 296, ["metadata", "only"], EDGE.meta.color);
  d.edge([d.p("bus", "r"), d.p("match", "l")], "meta");
  d.edge([d.p("match", "t"), d.p("api", "b", 0.79)], "alert", "alert", { at: [1073, 150] });
  d.edge([d.p("adapt", "t", 0.24), d.p("db", "b")], "ext", "watchlist", { at: [873, 407] });
  d.edge([d.p("adapt", "b", 0.5), d.p("govt", "t", 0.5)], "ext", "authorised API access", { at: [973, 547] });
  d.edge([d.p("relay", "r", 0.8), [722, 152], [722, 600], d.p("rooms", "r", 0.25)], "video");
  d.label(722, 470, ["live", "video"], EDGE.video.color);
  d.edge([d.p("api", "l", 0.5), [754, 92], [754, 643], [710, 643]], "alert");
  d.label(754, 604, ["alerts", "WebSocket"], EDGE.alert.color);
  d.legend(32, 574, [["video", "Video"], ["meta", "Metadata / events"], ["alert", "Alerts"], ["ext", "Govt integration"], ["dept", "Existing infra"]], { cols: 2, colW: 132 });
  out["d1-architecture"] = d;
}

// ---------------------------------------------------------------- D2 PoC as built
{
  const d = new Diagram(1200, 640);
  d.zone(16, 16, 246, 608, "Sources");
  d.zone(286, 16, 380, 608, "Media and analytics");
  d.zone(722, 16, 462, 608, "Platform");

  d.node("sim", 30, 50, 218, 132, "Feed simulator", ["FFmpeg replay as live RTSP", "12 synthetic + 2 stock footage", "14 cameras · 5 departments", "H.264 + H.265 · D1 to 1080p", "Sandbox-style catalogue API"], "dept");
  d.node("cam", 30, 206, 218, 96, "Any RTSP camera / VMS", ["Onboarded by URL", "credentials stay server-side"], "dept");
  d.node("sandbox", 30, 326, 218, 96, "Sandbox / govt feed", ["30 cameras onboarded", "by RTSP address (its", "catalogue: id + name)"], "dept");
  d.node("govdb", 30, 446, 218, 96, "VAHAN · eGujCop", ["Mock adapters over", "local fixture files"], "ext");

  d.node("mtx", 302, 50, 348, 112, "MediaMTX", ["RTSP :8554 · WebRTC/WHEP :8889", "HLS :8888 · control API :9997 (host only)", "On-demand H.265 → H.264 preview"], "ours");
  d.node("worker", 302, 206, 348, 194, "Analytics worker · Python", ["Frame-PTS timestamps · reconnect/backoff", "Hardware decode, software fallback per camera", "YOLOv11n plates + text-line finder", "YOLO11n COCO: vehicles and people", "fast-plate-ocr CCT-XS v2 · ONNX Runtime", "Vote · type/colour · counts · intrusion zones", "Plate crops to local disk · batched ingest", "Outage spool + cached watchlist · heartbeats"], "ours");
  d.node("bench", 302, 426, 348, 72, "sentinel-bench + capacity.py", ["Per-stream cost → 80,000-camera sizing"], "plain");

  d.node("api", 740, 50, 424, 180, "Sentinel API · FastAPI", ["Auth (JWT) · RBAC with department scoping", "Registry · CSV import · catalogue sync", "Onboarding: probe → relay → register", "GIS · sightings · journeys · evidence crops", "Watchlist · adapters · plate and intrusion alerts", "Reports · audit · health monitor + relay healing"], "ours");
  d.node("pg", 740, 272, 202, 128, "PostgreSQL 16", ["PostGIS · pg_trgm", "fuzzystrmatch", "Partitioned sightings", "Append-only audit"], "store");
  d.node("redis", 962, 272, 202, 128, "Valkey", ["Redis-compatible pub/sub", "→ WebSocket clients"], "store");
  d.node("web", 740, 446, 424, 108, "React control room", ["Overview · Leaflet map · video wall + zone editor", "Vehicle search (journey view) · alerts by priority", "Health · registry · watchlist · audit trail"], "ui");

  d.edge([[248, 86], [302, 86]], "video", "publish", { at: [275, 106] });
  d.edge([d.p("cam", "r"), [274, 254], [274, 140], [302, 140]], "video");
  d.label(274, 196, ["RTSP pull"], EDGE.video.color);
  d.edge([d.p("mtx", "b"), d.p("worker", "t")], "video", "RTSP over TCP", { at: [476, 184] });
  d.edge([[650, 76], [740, 76]], "control", null, { both: true });
  d.edge([[650, 140], [658, 140], [658, 520], [740, 520]], "video");
  d.label(610, 520, "WebRTC / HLS", EDGE.video.color);
  d.edge([d.p("sandbox", "r"), [266, 374], [266, 580], [690, 580], [690, 184], [740, 184]], "control");
  d.label(478, 580, "catalogue sync (GET /cameras)", EDGE.control.color);
  d.edge([d.p("govdb", "r"), [258, 494], [258, 604], [706, 604], [706, 200], [740, 200]], "ext");
  d.label(478, 604, "adapter fetch → watchlist", EDGE.ext.color);
  d.edge([[650, 218], [740, 218]], "meta");
  d.label(695, 238, "POST /ingest", EDGE.meta.color);
  d.edge([d.p("api", "b", 0.2396), d.p("pg", "t")], "plain", null, { both: true });
  d.edge([d.p("api", "b", 0.7618), d.p("redis", "t")], "alert", "publish", { at: [1063, 251] });
  d.edge([d.p("redis", "b"), d.p("web", "t", 0.7618)], "alert", "WebSocket", { at: [1063, 423] });
  d.edge([[952, 446], [952, 230]], "control", null, { both: true });
  d.label(952, 423, "REST + JWT", EDGE.control.color);
  d.edge([d.p("worker", "b"), d.p("bench", "t")], "plain");
  d.legend(740, 578, [["video", "Video"], ["meta", "Metadata"], ["alert", "Alerts"], ["control", "Control"]], { cols: 4, colW: 108, title: "" });
  out["d2-poc-components"] = d;
}

// ---------------------------------------------------------------- D3 onboarding sequence
{
  const d = new Diagram(1200, 760);
  const lanes = [["op", "Operator", "ui", 120], ["api", "Sentinel API", "ours", 380], ["mtx", "MediaMTX relay", "ours", 640], ["cam", "Camera / VMS", "dept", 880], ["db", "PostGIS · audit", "store", 1090]];
  const X = Object.fromEntries(lanes.map(([k, , , x]) => [k, x]));
  lanes.forEach(([k, t, s, x]) => {
    d.node(k, x - 90, 20, 180, 48, t, [], s, { center: true, top: 30 });
    d.raw(`<path d="M${x},68 L${x},720" stroke="#CBD5E1" stroke-width="1.5" stroke-dasharray="4 4"/>`, "back");
  });
  let y = 116;
  const msg = (from, to, text, kind = "plain", { ret = false, note = null } = {}) => {
    const dir = X[to] > X[from] ? 1 : -1;
    const x1 = X[from] + 4 * dir, x2 = X[to] - 4 * dir;
    d.edge([[x1, y], [x2, y]], ret ? "control" : kind);
    d.text((x1 + x2) / 2, y - 9, text, { anchor: "middle", size: 12.5, weight: 600, color: ret ? "#475569" : EDGE[kind].color });
    if (note) d.text(Math.max(x1, x2) + 12, y + 4, note, { size: 11.5, color: "#64748B" });
    y += 50;
  };
  msg("op", "api", "POST /onboard/stream { code, dept, location, rtsp://user:***@… }", "plain", { note: "another department's camera → 403" });
  msg("api", "mtx", "add relay path · source URL · RTSP over TCP", "control");
  msg("mtx", "cam", "DESCRIBE · SETUP · PLAY", "video");
  msg("cam", "mtx", "H.265 1280×720 stream", "video", { ret: true });
  msg("api", "mtx", "poll path state", "control");
  msg("mtx", "api", "ready · tracks: H265 · 1280×720", "control", { ret: true });
  msg("api", "mtx", "view-only camera → switch relay to on-demand", "control");
  msg("api", "db", "upsert camera + camera_sources (URL stays server-side)", "meta");
  msg("api", "db", "audit camera.onboarded_* (credentials masked)", "meta");
  msg("api", "op", "RTSP / WHEP / HLS endpoints on the relay", "plain", { ret: true });
  d.raw(`<rect x="160" y="${y - 22}" width="290" height="30" rx="6" fill="#0F172A"/>`, "front");
  d.text(305, y - 2, "measured 17 Sep: 1.2–2.0 s, idle stack", { anchor: "middle", size: 12.5, weight: 700, color: "#FFFFFF" });
  y += 40;
  d.raw(`<rect x="24" y="${y - 20}" width="1152" height="${760 - y + 4}" rx="10" fill="#F8FAFC" stroke="#E2E8F0"/>`, "back");
  d.text(40, y, "EVERY HEALTH INTERVAL (20 s)", { size: 11, weight: 700, color: "#64748B" });
  y += 30;
  msg("api", "mtx", "relay missing after a media-server restart? → re-register", "control", { note: "tested 17 Sep: 2/2 relays restored" });
  d.legend(40, y - 8, [["video", "Media session"], ["control", "Control plane"], ["meta", "Persistence"]], { cols: 3, colW: 160, title: "" });
  out["d3-onboarding"] = d;
}

// ---------------------------------------------------------------- D4 ANPR pipeline
{
  const d = new Diagram(1200, 536);
  const W1 = 270, gap = 24;
  const row1 = [
    ["Ingest", ["RTSP over TCP · reconnect + backoff", "Hardware decode, software fallback", "All frames decoded, ~1.5× rate to BGR", "Frame-PTS timestamps, loop re-anchor"], "HW decode: +49% fps at 8 streams"],
    ["Sample", ["Latest frame only — never a queue", "5 frames/s per camera target", "Slow analysis lowers rate, no lag", "Batch all due cameras together"], "stale frames skipped"],
    ["Detect", ["YOLOv11n plates + text-line finder", "YOLO11n COCO: vehicles, people", "Same frames, one batch per model", "FP16 auto-off on GTX 16xx (NaN)"], "objects: ~15 ms / frame"],
    ["Read (OCR)", ["fast-plate-ocr CCT-XS v2", "10 slots — Indian plates fit", "One batched call per cycle", "Confidence = weakest character"], "read: GI01ZZOOO1"],
  ];
  row1.forEach(([t, l, ex], i) => d.node(`s${i}`, 24 + i * (W1 + gap), 24, W1, 176, t, [...l, { t: ex, accent: "#0369A1", mono: i === 3 }], "ours", { badge: i + 1, top: 34, lineGap: 22 }));
  const row2 = [
    ["Normalise", ["Layouts: SS RR L(1–3) NNNN · BH series", "Position-aware O/0 · I/1 · B/8 repair", "Look-alike state codes: GI → GJ", "Reject non-plates (overlay text)"], "→ GJ01ZZ0001"],
    ["Track and vote", ["Per-camera tracks · merge reads ≤ 2 edits apart", "Hold ≥ 1 s and ≥ 2.5 analysis intervals", "One-offs dropped; below 2 fps one read ≥ 0.6 kept", "Per-character vote · vehicle box: type, colour", "Repeat filter: 1-char variant = same vehicle"], "GJ13WF8306 · white/silver car"],
    ["Match and alert", ["Store sighting (partitioned table)", "Watchlist: exact, else one character off", "Single-read sighting: exact match only", "120 s cooldown per entry per camera", "Push over WebSocket · crop attached"], "VAHAN stolen → HIGH alert"],
  ];
  const W2 = 368;
  row2.forEach(([t, l, ex], i) => d.node(`t${i}`, 24 + i * (W2 + 22), 256, W2, 176, t, [...l, { t: ex, accent: i === 2 ? "#DC2626" : "#047857", mono: i < 2 }], i === 2 ? "ui" : "store", { badge: i + 5, top: 34, lineGap: 22 }));
  for (let i = 0; i < 3; i++) d.edge([d.p(`s${i}`, "r"), d.p(`s${i + 1}`, "l")], "video");
  d.edge([d.p("s3", "b"), [d.p("s3", "b")[0], 228], [d.p("t0", "t")[0], 228], d.p("t0", "t")], "meta");
  d.label(634, 228, "plate candidates + text", EDGE.meta.color);
  d.edge([d.p("t0", "r"), d.p("t1", "l")], "meta");
  d.edge([d.p("t1", "r"), d.p("t2", "l")], "alert");
  d.text(24, 470, "Measured 24 Sep on a GTX 1650 Ti laptop, 4 cameras, 15 min: over 1,400 sightings, 31 watchlist alerts; first read → alert row median 1.06 s, p95 1.94 s.", { size: 13, color: "#334155" });
  d.text(24, 492, "Hardware decode (D3D11, the laptop's Intel iGPU, not NVDEC): +49% analysed fps per stream at 8 and 12 streams. Keeping frames on the GPU is production design.", { size: 13, color: "#334155" });
  d.text(24, 514, "API unreachable: batches spool to disk and replay in order with their frame times; hits on a cached watchlist are logged at the edge, alerted on replay.", { size: 13, color: "#334155" });
  out["d4-anpr-pipeline"] = d;
}

// ---------------------------------------------------------------- D5 alert workflow
{
  const d = new Diagram(1200, 516);
  const X = [24, 224, 424, 624, 824, 1024];
  const top = [
    ["sight", "Sighting stored", ["frame timestamp", "camera · crop", "replays keep their time"], "store"],
    ["match", "Watchlist match", ["exact plate, else one", "character off (masks);", "single read: exact only"], "ours"],
    ["cool", "Cooldown", ["same entry + camera", "within 120 s → skip", "(zones: per zone)"], "ours"],
    ["alert", "Alert raised", ["severity from source", "near miss labelled:", "read ≈ watchlist plate"], "ui"],
    ["push", "Real-time push", ["Valkey pub/sub", "→ WebSocket"], "ours"],
    ["room", "Control room", ["severity first, then", "newest · crop shown", "card on every page,", "chime: high, critical"], "ui"],
  ];
  top.forEach(([id, t, l, s], i) => d.node(id, X[i], 40, 164, 118, t, l, s));
  for (let i = 0; i < 5; i++) d.edge([d.p(top[i][0], "r"), d.p(top[i + 1][0], "l")], i >= 2 ? "alert" : "meta");

  d.node("wl", 224, 220, 164, 100, "Watchlist", ["active · valid_until", "FIR / source ref"], "store");
  d.edge([d.p("wl", "t"), d.p("match", "b")], "plain", "lookup", { at: [306, 189] });
  // a plate listed after the vehicle passed: checked at once against the last 24 h
  d.node("retro", 424, 220, 164, 100, "Late-listing check", ["last 24 h of sightings", "manual: exact + 1 off", "CSV, adapter: exact only"], "ours");
  d.edge([d.p("wl", "r"), d.p("retro", "l")], "plain");
  d.edge([d.p("retro", "r"), [706, 270], d.p("alert", "b")], "alert");
  d.label(706, 212, ["one alert,", "retrospective"], EDGE.alert.color);
  const src = [["vahan", "VAHAN", ["stolen · blacklisted", "vehicles"]], ["egc", "eGujCop", ["wanted · missing", "BOLO vehicles"]], ["man", "Manual / CSV", ["with FIR reference", "and expiry"]]];
  src.forEach(([id, t, l], i) => d.node(id, 24 + i * 200, 400, 164, 96, t, l, "ext"));
  src.forEach(([id], i) => d.edge([d.p(id, "t"), [106 + i * 200, 360], [306, 360], d.p("wl", "b")], "ext"));
  d.label(306, 360, "adapter sync · add entry", EDGE.ext.color);

  d.node("ack", 1024, 220, 164, 90, "Acknowledge", ["who and when, seen", "live in every room"], "plain");
  d.node("close", 1024, 380, 164, 116, "Close", ["or mark as a", "false positive,", "with a disposition"], "plain");
  d.node("move", 824, 220, 164, 90, "Movement history", ["journey: stops, hops,", "implausible speeds"], "ours");
  d.node("audit", 824, 380, 164, 116, "Audit log", ["who acknowledged,", "closed, searched —", "append-only"], "store");
  d.edge([d.p("room", "b"), d.p("ack", "t")], "plain");
  d.edge([d.p("ack", "b"), d.p("close", "t")], "plain");
  d.edge([d.p("room", "b", 0.12), [1044, 180], [906, 180], d.p("move", "t")], "plain", "investigate", { at: [960, 180] });
  d.edge([d.p("ack", "l", 0.8), [1006, 292], [1006, 438], d.p("audit", "r", 0.5)], "control");
  d.edge([d.p("close", "l", 0.8), [1000, 473]], "control");
  d.edge([d.p("move", "b"), d.p("audit", "t")], "control", "purpose recorded", { at: [906, 345] });
  d.legend(624, 400, [["meta", "Data"], ["alert", "Alert path"], ["ext", "Watchlist sources"], ["control", "Audited actions"]], { cols: 1, colW: 170 });
  out["d5-alert-workflow"] = d;
}

// ---------------------------------------------------------------- D6 scale
{
  const d = new Diagram(1200, 640);
  d.text(24, 32, "80,000 CAMERAS · TIERED BY WHAT EACH CAMERA'S POSITION ALLOWS", { size: 12, weight: 700, color: "#475569" });
  const bw = 1152, bx = 24, by = 46;
  const tiers = [[0.10, "#0369A1", "#FFFFFF", "A · ANPR", "8,000 · 5 fps"], [0.20, "#0F766E", "#FFFFFF", "B · Events", "16,000 · 1 fps keyframes"], [0.70, "#E2E8F0", "#0F172A", "C · View and record", "56,000 · relayed only while watched · no continuous compute"]];
  let cx = bx;
  tiers.forEach(([share, fill, fg, name, sub]) => {
    const w = bw * share;
    d.raw(`<rect x="${cx}" y="${by}" width="${w}" height="62" fill="${fill}"/>`);
    d.text(cx + 12, by + 26, name, { size: 14, weight: 700, color: fg });
    d.text(cx + 12, by + 46, sub, { size: 12, color: fg });
    cx += w;
  });
  d.raw(`<rect x="${bx}" y="${by}" width="${bw}" height="62" fill="none" stroke="#94A3B8" rx="2"/>`, "front");

  d.zone(24, 140, 700, 330, "District edge · 33 districts · 248 GPU nodes");
  for (let i = 0; i < 33; i++) {
    const col = i % 11, row = Math.floor(i / 11);
    const x = 44 + col * 61, y = 180 + row * 70;
    d.raw(`<rect x="${x}" y="${y}" width="50" height="54" rx="7" fill="#E0F2FE" stroke="#0369A1" stroke-width="1.3"/>`);
    for (let k = 0; k < 3; k++) d.raw(`<rect x="${x + 9}" y="${y + 10 + k * 12}" width="32" height="7" rx="2" fill="#0369A1" fill-opacity="${0.35 + k * 0.2}"/>`);
  }
  d.text(44, 408, "≈ 7.5 GPU nodes per district, co-located with the district control room", { size: 13, weight: 600, color: "#0F172A" });
  d.text(44, 430, "Relay + analytics + local spool + crop store · video stays inside the district network", { size: 12.5, color: "#475569" });
  d.text(44, 452, "Node count = tier A ÷ 60 streams + tier B ÷ 250 streams, + 25% headroom (assumptions to be measured)", { size: 12.5, color: "#475569" });

  d.zone(760, 140, 416, 330, "State core");
  d.node("dc", 780, 176, 376, 132, "GSDC primary", ["API cluster behind load balancer", "PostGIS primary + synchronous standby", "Kafka · watchlist matcher · audit", "Government DB adapters"], "ours");
  d.node("dr", 780, 350, 376, 96, "DR site", ["Asynchronous replica · RPO minutes", "RTO target under 4 hours"], "store");
  d.edge([d.p("dc", "b"), d.p("dr", "t")], "meta", "replication", { at: [968, 329] });
  d.edge([[724, 242], [780, 242]], "meta");
  d.label(742, 214, ["metadata", "2.7 Mbps"], EDGE.meta.color);

  const stats = [["56,000", "inference frames/s", "statewide, tiers A + B"], ["2.7 Mbps", "metadata backhaul", "average, all districts"], ["2.6 TB", "sightings, 90 days", "48 M rows/day, partitioned"], ["11.5 TB", "plate crops, 30 days", "kept at the edge"], ["≈ ₹39.7 cr", "capex, assumed prices", "248 nodes × ₹15 lakh + core"]];
  stats.forEach(([v, l, s], i) => {
    const x = 24 + i * 234;
    d.raw(`<rect x="${x}" y="500" width="218" height="118" rx="12" fill="#0F172A"/>`);
    d.text(x + 18, 548, v, { size: 30, weight: 700, color: "#FFFFFF" });
    d.text(x + 18, 576, l, { size: 13.5, weight: 600, color: "#E2E8F0" });
    d.text(x + 18, 598, s, { size: 12, color: "#94A3B8" });
  });
  out["d6-scale"] = d;
}

// ---------------------------------------------------------------- D7 data model
{
  const d = new Diagram(1200, 760);
  const ent = (id, x, y, w, name, fields, color = "#0369A1", note = null) => {
    const h = 34 + fields.length * 19 + (note ? 22 : 8);
    d.nodes[id] = { x, y, w, h };
    d.raw(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="9" fill="#FFFFFF" stroke="${color}" stroke-width="1.6"/>`);
    d.raw(`<path d="M${x},${y + 9} a9,9 0 0 1 9,-9 h${w - 18} a9,9 0 0 1 9,9 v21 h-${w} z" fill="${color}"/>`);
    d.raw(`<text x="${x + 12}" y="${y + 21}" font-family="${MONO}" font-size="14" font-weight="700" fill="#FFFFFF">${esc(name)}</text>`);
    fields.forEach((f, i) => {
      const key = f.startsWith("*");
      d.raw(`<text x="${x + 12}" y="${y + 50 + i * 19}" font-family="${MONO}" font-size="12" fill="${key ? "#0F172A" : "#475569"}"${key ? ' font-weight="700"' : ""}>${esc(key ? f.slice(1) : f)}</text>`);
    });
    if (note) d.raw(`<text x="${x + 12}" y="${y + h - 10}" font-family="${FONT}" font-size="11.5" font-style="italic" fill="${color}">${esc(note)}</text>`);
  };
  ent("dep", 24, 24, 250, "departments", ["*id", "code  (HOME, MUNI, GSRTC…)", "name"], "#475569");
  ent("dis", 24, 150, 250, "districts", ["*id", "name · range_name", "centroid · boundary (geography)"], "#475569");
  ent("src", 24, 296, 250, "source_systems", ["*id", "department_id", "vendor · product · mode", "adapter · credentials_ref", "remains_independent = true"], "#475569");
  ent("cam", 318, 24, 290, "cameras", ["*id · camera_code", "department_id · district_id", "source_system_id", "location  geography(Point)", "camera_class · mode · ownership", "vendor · codec · resolution · fps", "retention_days · storage", "rtsp_url · whep_url · hls_url", "anpr_viable · analytics_enabled", "health · last_seen_at", "tags  (incl. intrusion zones)"], "#0369A1");
  ent("csrc", 318, 330, 290, "camera_sources", ["*camera_id", "source_url  (server-side only)", "on_demand · probed codec/size"], "#0369A1");
  ent("hc", 318, 470, 290, "camera_health_checks", ["camera_id · checked_at", "reachable · latency_ms · state"], "#0369A1");
  ent("sig", 652, 24, 250, "vehicle_sightings", ["*id · event_ts  (frame time)", "camera_id", "plate_text · plate_norm", "ocr_conf · det_conf", "vehicle_type · vehicle_color", "bbox · track_id · crop_path"], "#047857", "partitioned by month · trigram index");
  ent("det", 652, 250, 250, "detection_events", ["*id · event_ts", "camera_id · event_type", "  (object_counts, intrusion)", "label · value · detail"], "#047857", "partitioned by month");
  ent("wl", 940, 24, 236, "watchlist_entries", ["*id · kind", "plate_norm · subject_name", "severity · source", "source_ref  (FIR)", "active · valid_until"], "#B45309", "+ watchlist_masks (near misses)");
  ent("al", 940, 250, 236, "alerts", ["*id · watchlist_id", "alert_type · camera_id", "sighting_id/ts · retrospective", "match_score · exact_match", "severity · status · detail", "acknowledged_by/at", "closed_at · disposition"], "#DC2626");
  ent("usr", 652, 430, 250, "users", ["*id · username", "role_id", "department_id · district_id", "(NULL = statewide scope)"], "#6D28D9");
  ent("role", 652, 596, 250, "roles", ["*id · code", "permissions  jsonb"], "#6D28D9");
  ent("aud", 940, 470, 236, "audit_log", ["at · actor · action", "object_type · object_id", "purpose · ip · detail"], "#6D28D9", "UPDATE / DELETE → no-op");
  const rel = (pts) => d.edge(pts, "plain");
  rel([[318, 62], [274, 62]]);
  rel([[318, 104], [300, 104], [300, 196], [274, 196]]);
  rel([[318, 132], [288, 132], [288, 356], [274, 356]]);
  rel([d.p("csrc", "t"), d.p("cam", "b")]);
  rel([d.p("hc", "t"), d.p("csrc", "b")]);
  rel([[652, 62], [608, 62]]);
  rel([d.p("det", "l", 0.4), [630, d.p("det", "l", 0.4)[1]], [630, 150], [608, 150]]);
  rel([d.p("al", "l", 0.3), [920, d.p("al", "l", 0.3)[1]], [920, d.p("sig", "r", 0.5)[1]], d.p("sig", "r", 0.5)]);
  rel([d.p("al", "t", 0.5), d.p("wl", "b", 0.5)]);
  rel([d.p("usr", "b"), d.p("role", "t")]);
  rel([[940, 522], [920, 522], [920, 468], [902, 468]]);
  d.text(24, 736, "Video is not stored here: it stays on department recorders. The platform holds registry, metadata, evidence crops and the audit trail.", { size: 13, color: "#334155" });
  out["d7-data-model"] = d;
}

// ---------------------------------------------------------------- D8 security zones (target design)
{
  const d = new Diagram(1200, 770);
  d.zone(16, 16, 226, 540, "Camera networks");
  d.zone(266, 16, 300, 540, "District edge · ×33");
  d.zone(590, 16, 360, 540, "State core · GSDC + DR");
  d.zone(970, 16, 214, 540, "External systems");
  d.zone(266, 572, 684, 152, "Control rooms");

  d.node("cams", 30, 48, 198, 96, "Cameras · NVR · VMS", ["IP · analog via DVR", "department-owned"], "dept");
  d.node("priv", 30, 160, 198, 84, "Private-shared", ["by written agreement"], "dept");
  d.node("vlan", 30, 260, 198, 110, "Camera VLAN", ["no internet egress", "reachable only from", "the district edge"], "plain");
  d.node("ro", 30, 386, 198, 120, "Read-only access", ["one viewer account per", "camera or recorder;", "Sentinel never writes", "to department devices"], "plain");

  d.node("fw", 282, 48, 268, 72, "Edge firewall", ["only bridge: camera VLAN ↔ backbone"], "plain");
  d.node("relay", 282, 136, 268, 118, "Media relay (MediaMTX)", ["pulls RTSP · one session per camera", "viewers: WebRTC (DTLS-SRTP) · HLS", "each view authorised by the API", "control API: from the core only"], "ours");
  d.node("ai", 282, 270, 268, 100, "GPU analytics nodes", ["to the core: metadata only", "video analysed in the district", "cached watchlist for outages"], "ours");
  d.node("disk", 282, 386, 268, 120, "Edge storage · encrypted disk", ["plate crops (30 days) · spool", "cached watchlist · local alerts", "full-disk encryption, unlocked", "at boot by the core"], "store");

  // The gateway is the core's only entrance: a tall bar every inbound flow meets.
  d.nodes.gw = { x: 604, y: 48, w: 44, h: 492 };
  d.raw(`<rect x="604" y="48" width="44" height="492" rx="10" fill="${STYLE.ours.fill}" stroke="${STYLE.ours.stroke}" stroke-width="1.6"/>`);
  d.raw(`<text transform="translate(631,294) rotate(-90)" text-anchor="middle" font-family="${FONT}" font-size="13" font-weight="700" fill="#0F172A">${esc("Gateway · TLS · WAF · rate limits · SSO + MFA · mTLS")}</text>`);
  d.node("api", 662, 48, 274, 100, "Sentinel API · stateless", ["RBAC; dept/district scope in SQL", "every search and action audited"], "ours");
  d.node("db", 662, 168, 131, 120, "PostGIS", ["TLS only", "encrypted volumes", "sync standby"], "store");
  d.node("vault", 805, 168, 131, 120, "Vault + HSM", ["signing keys", "camera credentials", "node certificates", "disk keys"], "dark");
  d.node("audit", 662, 308, 131, 112, "Audit log", ["append-only", "insert-only role", "→ SIEM, 180 days", "kept in India"], "store");
  d.node("adapt", 805, 308, 131, 112, "Adapters", ["egress proxy", "read-only accounts", "listed endpoints"], "ext");
  d.node("dr", 662, 440, 274, 100, "DR site", ["asynchronous encrypted replica", "same zones and controls"], "store");

  d.node("vahan", 984, 48, 186, 84, "VAHAN · SARTHI", ["NIC · read-only lookups"], "ext");
  d.node("egc", 984, 152, 186, 84, "eGujCop (CCTNS)", ["wanted · missing · BOLO"], "ext");
  d.node("afis", 984, 256, 186, 84, "AFIS · NAFIS", ["declared; access awaited"], "ext");
  d.node("erss", 984, 360, 186, 110, "112 ERSS · SMS", ["and e-mail gateways", "alert hand-off", { t: "design · not built", accent: "#B45309" }], "ext");

  d.node("rooms", 282, 608, 360, 100, "Operator browsers · police network", ["HTTPS + WSS to the gateway", "live video straight from the edge relay", "no path to cameras, database or keys"], "ui");
  d.node("roles", 660, 608, 276, 100, "Five roles, scoped", ["admin · supervisor · operator", "dept nodal officer · auditor", "searches and actions audited"], "ui");

  // cameras -> edge firewall -> relay: the relay pulls, nothing on the camera side dials out
  d.edge([d.p("cams", "r"), [254, d.p("cams", "r")[1]]], "video");
  d.edge([d.p("priv", "r"), [254, d.p("priv", "r")[1]]], "video");
  d.raw(`<path d="M254,84 L254,202" stroke="${EDGE.video.color}" stroke-width="2.2"/>`);
  d.edge([[254, 84], d.p("fw", "l")], "video");
  d.label(254, 150, "RTSP pull", EDGE.video.color);
  d.edge([d.p("fw", "b"), d.p("relay", "t")], "video");
  d.edge([d.p("relay", "b"), d.p("ai", "t")], "video");
  d.edge([d.p("ai", "b"), d.p("disk", "t")], "meta");

  // edge -> core: metadata over mTLS; the relay asks the API before serving a viewer
  d.edge([[550, 320], [604, 320]], "meta");
  d.label(584, 305, "mTLS", EDGE.meta.color);
  d.edge([[550, 170], [604, 170]], "control");
  d.label(584, 155, "auth hook", EDGE.control.color);
  d.edge([d.p("gw", "r", 0.1), [662, d.p("gw", "r", 0.1)[1]]], "plain");
  d.edge([d.p("api", "b", 0.24), d.p("db", "t")], "plain", null, { both: true });
  d.edge([d.p("api", "b", 0.76), d.p("vault", "t")], "control");

  // core -> government systems, only through the adapters' egress proxy
  d.edge([d.p("adapt", "r"), [956, d.p("adapt", "r")[1]]], "ext");
  d.raw(`<path d="M956,90 L956,415" stroke="${EDGE.ext.color}" stroke-width="1.8" stroke-dasharray="6 4"/>`);
  for (const id of ["vahan", "egc", "afis", "erss"]) d.edge([[956, d.p(id, "l")[1]], d.p(id, "l")], "ext");
  d.label(956, 142, "TLS · read-only", EDGE.ext.color);

  // control rooms: live video from the edge relay, everything else through the gateway
  d.edge([d.p("relay", "r", 0.85), [560, d.p("relay", "r", 0.85)[1]], [560, 608]], "video");
  d.label(554, 562, "WebRTC · HLS", EDGE.video.color, "right");
  d.edge([d.p("gw", "b"), [626, 608]], "alert", null, { both: true });
  d.label(632, 562, "HTTPS · WSS", EDGE.alert.color, "left");

  d.legend(24, 600, [["video", "Video"], ["meta", "Metadata"], ["alert", "UI and alerts"], ["ext", "Govt integration"], ["control", "Control plane, keys"], ["dept", "Existing infra"]]);
  d.text(24, 752, "Target design. The PoC runs every zone on one laptop over plain HTTP, with one shared ingest key and one HS256 secret: HLD 11.4 says what is built and what is not.", { size: 13, color: "#334155" });
  out["d8-security-zones"] = d;
}

mkdirSync(OUT, { recursive: true });
for (const [name, dg] of Object.entries(out)) {
  writeFileSync(join(OUT, `${name}.svg`), dg.svg());
  console.log("wrote", name);
}
