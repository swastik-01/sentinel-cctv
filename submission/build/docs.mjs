// Markdown docs -> print-styled HTML -> A4 PDF.
//   node docs.mjs            builds HLD, Plan for Scale, Privacy, leave-behind and since-submission PDFs into submission/out/
//   node docs.mjs leave      builds only the PDFs whose file name contains the argument(s)
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { marked } from "marked";
import { launch } from "./chrome.mjs";
import { htmlToPdf } from "./render.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "submission/out");
const TMP = join(OUT, "html");

// The leave-behind: one A4 sheet, two sides, no cover page, no contents list, tighter type
const LEAVE_CSS = `
@page :first { margin: 14mm 15mm 12mm; }
body { font-size: 9.3pt; line-height: 1.4; }
h1 { font-size: 20pt; margin: 0 0 2px; }
.lb-head { color: #475569; font-size: 9.5pt; margin: 0 0 8px; padding-bottom: 6px; border-bottom: 2px solid #0b1220; }
.gu { font-family: "Nirmala UI", "Shruti", "Noto Sans Gujarati", "Segoe UI", sans-serif; font-weight: 600; color: #0b1220; font-size: 10.5pt; }
h2 { font-size: 12.5pt; margin: 10px 0 4px; }
table { font-size: 8.6pt; margin: 4px 0 6px; } th, td { padding: 3px 6px; }
figure { margin: 4px auto 6px; width: 92%; } figure img { width: 100%; }
ul { margin: 2px 0; } li { margin: 1px 0; }
`;

const DOCS = [
  { src: "docs/hld.md", out: "Sentinel-HLD.pdf" },
  { src: "docs/leave-behind.md", out: "Sentinel-Leave-Behind.pdf", meta: { cover: false, toc: false, title: "Sentinel — leave-behind", css: LEAVE_CSS } },
  // the jury's addendum: what changed between the submission and the finale. Its tables are taller than a page's
  // remainder, so unlike the HLD's they may split between pages (rows still stay whole).
  { src: "docs/since-submission.md", out: "Sentinel-Since-Submission.pdf", meta: { cover: false, toc: false, title: "Sentinel — since the submission", css: LEAVE_CSS + "table { page-break-inside: auto; }" } },
  { src: "docs/plan-for-scale.md", out: "Sentinel-Plan-for-Scale.pdf",
    meta: { title: "Sentinel — Plan for Scale", subtitle: "Sizing, deployment and resilience for 80,000 cameras", doc: "Plan for Scale · Gujarat Police Innovation Challenge 2026", version: "1.4 · 9 October 2026" } },
  { src: "docs/privacy-dpdp.md", out: "Sentinel-Privacy-DPDP.pdf",
    meta: { title: "Sentinel — Privacy and Proportionality", subtitle: "Design position under the DPDP Act, 2023", doc: "Supporting note · Gujarat Police Innovation Challenge 2026", version: "1.3 · 8 October 2026" } },
];

function frontMatter(md) {
  const m = md.match(/^---\n([\s\S]*?)\n---\n/);
  if (!m) return [{}, md];
  const meta = Object.fromEntries(m[1].split("\n").map((l) => l.split(/:\s(.+)/).slice(0, 2)).filter((x) => x[1]));
  return [meta, md.slice(m[0].length)];
}

const CSS = `
@page { size: A4; margin: 16mm 15mm 14mm; }
@page :first { margin: 0; }
* { box-sizing: border-box; }
body { font: 10.4pt/1.5 "Segoe UI", Arial, sans-serif; color: #0f172a; margin: 0; }
.cover { height: 297mm; padding: 38mm 22mm 20mm; background: #0b1220; color: #fff; display: flex; flex-direction: column; page-break-after: always; }
.cover .mark { width: 46px; height: 46px; border-radius: 11px; background: linear-gradient(135deg,#38bdf8,#6366f1); display: grid; place-items: center; font-weight: 800; font-size: 24px; margin-bottom: 28px; }
.cover h1 { font-size: 34pt; line-height: 1.1; margin: 0 0 14px; font-weight: 700; color: #fff; }
.cover .sub { font-size: 15pt; color: #cbd5e1; max-width: 150mm; }
.cover .meta { margin-top: auto; font-size: 10.5pt; color: #94a3b8; border-top: 1px solid #1e293b; padding-top: 12px; }
.cover .meta b { color: #e2e8f0; font-weight: 600; }
.toc { margin-bottom: 18px; padding: 10px 14px 4px; background: #f1f5f9; border-radius: 8px; }
.toc h2 { margin: 0 0 4px; font-size: 12pt; }
.toc ol { padding-left: 18px; columns: 2; column-gap: 24px; margin: 4px 0 8px; font-size: 9.6pt; } .toc li { margin: 1px 0; }
h1, h2, h3 { color: #0b1220; line-height: 1.25; }
h2 { font-size: 16pt; margin: 22px 0 8px; padding-top: 4px; page-break-after: avoid; }
h3 { font-size: 12pt; margin: 16px 0 6px; page-break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 20px; } li { margin: 2px 0; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9.2pt; background: #f1f5f9; padding: 0 3px; border-radius: 3px; }
pre { background: #0f172a; color: #e2e8f0; padding: 10px 12px; border-radius: 6px; font-size: 8.4pt; line-height: 1.35; overflow: hidden; page-break-inside: avoid; }
pre code { background: none; color: inherit; padding: 0; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 9.2pt; page-break-inside: avoid; }
tr { page-break-inside: avoid; }
th { background: #0f172a; color: #fff; text-align: left; font-weight: 600; padding: 5px 7px; }
td { padding: 4px 7px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tbody tr:nth-child(even) td { background: #f8fafc; }
figure { margin: 10px 0 14px; page-break-inside: avoid; }
figure img { width: 100%; border: 1px solid #e2e8f0; border-radius: 6px; }
figcaption { font-size: 8.8pt; color: #475569; margin-top: 4px; }
figcaption b { color: #0f172a; }
strong { color: #0b1220; }
blockquote { margin: 8px 0; padding: 6px 12px; background: #f1f5f9; border-radius: 6px; color: #334155; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 16px 0; }
`;

function build(src, metaOverride) {
  const md = readFileSync(join(ROOT, src), "utf8").replace(/\r\n/g, "\n");
  let [meta, body] = frontMatter(md);
  meta = { ...meta, ...(metaOverride || {}) };
  const cover = meta.cover !== false;
  if (metaOverride && cover) body = body.replace(/^# .+\n/, "");      // drop the doc's own H1; the cover carries it
  let fig = 0;
  const toc = [];
  const renderer = new marked.Renderer();
  renderer.image = ({ href, text }) => {
    fig += 1;
    const abs = href.startsWith("http") ? href : pathToFileURL(join(ROOT, dirname(src), href)).href;
    return `<figure><img src="${abs}" alt=""><figcaption><b>Figure ${fig}.</b> ${text}</figcaption></figure>`;
  };
  renderer.heading = ({ tokens, depth }) => {
    const text = tokens.map((t) => t.raw ?? t.text).join("");
    const id = "h-" + toc.length;
    if (depth === 2) toc.push({ id, text });
    return `<h${depth} id="${id}">${marked.parseInline(text)}</h${depth}>`;
  };
  // Inline images that are alone in a paragraph become figures, not <p><figure>.
  let html = marked.parse(body, { renderer, gfm: true }).replace(/<p>(<figure>[\s\S]*?<\/figure>)<\/p>/g, "$1");
  const tocHtml = toc.length > 4 && meta.toc !== false ? `<section class="toc"><h2>Contents</h2><ol>${toc.map((t) => `<li>${marked.parseInline(t.text.replace(/^\d+\.\s*/, ""))}</li>`).join("")}</ol></section>` : "";
  const coverHtml = cover ? `<section class="cover"><div class="mark">S</div><h1>${meta.title || ""}</h1><div class="sub">${meta.subtitle || ""}</div>
<div class="meta"><b>${meta.doc || ""}</b><br>${meta.version || ""}<br>Repository: Sentinel · all figures generated from the running system and its benchmark</div></section>` : "";
  return `<!doctype html><html><head><meta charset="utf-8"><title>${meta.title || "Sentinel"}</title><style>${CSS}${meta.css || ""}</style></head><body>
${coverHtml}
${tocHtml}
<main>${html}</main></body></html>`;
}

mkdirSync(TMP, { recursive: true });
const only = process.argv.slice(2).map((a) => a.toLowerCase());
const browser = await launch({ port: 9335 });
try {
  for (const d of DOCS.filter((d) => !only.length || only.some((o) => d.out.toLowerCase().includes(o)))) {
    const htmlPath = join(TMP, d.out.replace(".pdf", ".html"));
    writeFileSync(htmlPath, build(d.src, d.meta));
    await htmlToPdf(browser, htmlPath, join(OUT, d.out));
    console.log("pdf", d.out);
  }
} finally {
  browser.close();
}
