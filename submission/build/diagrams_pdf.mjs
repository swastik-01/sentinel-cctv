// Workflow and integration diagrams as one PDF, one diagram per landscape page, for the
// submission form's single "Workflow / Integration Diagram" link.
//   node diagrams_pdf.mjs   -> submission/out/Sentinel-Workflow-Diagrams.pdf
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "./chrome.mjs";
import { htmlToPdf } from "./render.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "submission/out");

// Order follows a camera's path through the system; captions match the HLD's figure captions.
const PAGES = [
  ["d1-architecture", "Statewide architecture (target design)", "Department estates are untouched; district edge nodes relay and analyse video; only metadata reaches the state core, and a plate crop when an alert or search asks for it. Store-and-forward is built and tested in the PoC; the event bus, database standby and crop object store are design."],
  ["d3-onboarding", "Integration workflow: onboarding a camera by stream URL", "The camera sees one session; credentials never leave the server; a department user can onboard only their own department's cameras. Measured: 1.2–2.0 s end to end on an idle stack (17 Sep)."],
  ["d4-anpr-pipeline", "Analytics workflow: from RTSP frame to watchlist alert", "Hardware decode where available; plate detection and OCR, and vehicle and person detection, on the same frames; a per-character vote across each track's reads; a repeat filter; matching and alerting. Laptop measurements, 24 Sep."],
  ["d5-alert-workflow", "Alert workflow: from sighting to closed alert", "Open alerts in severity order; near misses labelled; a plate added to the watchlist is checked against the last 24 hours. Every operator action is audited."],
  ["d8-security-zones", "Security zones (target design)", "Each arrow is a permitted flow; video leaves the district only to authorised viewers. The PoC runs every zone on one laptop over plain HTTP: HLD 11.4 says what is built and what is not."],
  ["d2-poc-components", "Proof of concept, as built", "Every box is running code in the repository. VAHAN and eGujCop are mock adapters; two cameras are stock footage with synthetic plates."],
  ["d7-data-model", "Core data model", "Video is not stored in the platform; sightings and counts are partitioned by time."],
  ["d6-scale", "Statewide sizing", "Derived in the Plan for Scale document from bench/capacity.py. Streams per node, tier shares and unit prices are ASSUMPTIONS until measured or quoted."],
];

const html = `<!doctype html><meta charset="utf-8"><title>Sentinel — workflow and integration diagrams</title>
<style>
@page { size: A4 landscape; margin: 12mm 14mm 16mm; }
body { font: 13px/1.45 "Segoe UI", Arial, sans-serif; color: #0f172a; margin: 0; }
section { page-break-after: always; display: flex; flex-direction: column; gap: 6px; height: 176mm; }
section:last-child { page-break-after: auto; }
.kicker { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #0369a1; font-weight: 700; }
h1 { font-size: 20px; margin: 0; }
p { margin: 0; color: #475569; }
.fig { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; }
.fig img { max-width: 100%; max-height: 100%; }
</style>
${PAGES.map(([file, title, caption], i) => `<section>
  <div class="kicker">Sentinel · Gujarat Police Innovation Challenge 2026 · figure ${i + 1} of ${PAGES.length}</div>
  <h1>${title}</h1><p>${caption}</p>
  <div class="fig"><img src="../../../docs/diagrams/${file}.svg" alt="${title}"></div>
</section>`).join("\n")}`;

mkdirSync(join(OUT, "html"), { recursive: true });
const htmlPath = join(OUT, "html", "Sentinel-Workflow-Diagrams.html");
writeFileSync(htmlPath, html);
const browser = await launch({ port: 9336 });
try {
  await htmlToPdf(browser, htmlPath, join(OUT, "Sentinel-Workflow-Diagrams.pdf"));
  console.log("pdf Sentinel-Workflow-Diagrams.pdf");
} finally {
  browser.close();
}
