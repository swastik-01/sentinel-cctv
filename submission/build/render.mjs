// Render helpers.
//   node render.mjs diagrams              docs/diagrams/*.svg -> submission/out/diagrams/*.png (2x)
//   node render.mjs pdf in.html out.pdf   HTML -> A4 PDF
//   node render.mjs png in.html out.png [width] [height]
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { fileUrl, launch } from "./chrome.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

export async function svgToPng(browser, svgPath, pngPath, scale = 2) {
  const svg = readFileSync(svgPath, "utf8");
  const m = svg.match(/viewBox="0 0 ([\d.]+) ([\d.]+)"/);
  if (!m) throw new Error(`${svgPath}: needs viewBox="0 0 W H"`);
  const [w, h] = [Math.ceil(+m[1]), Math.ceil(+m[2])];
  await browser.send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: scale, mobile: false });
  await browser.goto(fileUrl(svgPath), 300);
  const shot = await browser.send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: w, height: h, scale: 1 } });
  writeFileSync(pngPath, Buffer.from(shot.data, "base64"));
  return { w, h };
}

export async function htmlToPdf(browser, htmlPath, pdfPath) {
  await browser.send("Emulation.clearDeviceMetricsOverride");
  await browser.goto(fileUrl(htmlPath), 800);
  await browser.evaluate("document.fonts.ready.then(() => true)");
  const r = await browser.send("Page.printToPDF", {
    printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
    headerTemplate: "<div></div>",
    footerTemplate: `<div style="font:8px Arial;color:#667;width:100%;padding:0 14mm;display:flex;justify-content:space-between">
      <span class="title"></span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
    marginTop: 0, marginBottom: 0.45, marginLeft: 0, marginRight: 0,
  });
  writeFileSync(pdfPath, Buffer.from(r.data, "base64"));
}

async function main() {
  const [cmd, a, b, c, d] = process.argv.slice(2);
  const browser = await launch({ port: 9334 });
  try {
    if (cmd === "diagrams") {
      const src = join(ROOT, "docs/diagrams");
      const out = join(ROOT, "submission/out/diagrams");
      mkdirSync(out, { recursive: true });
      for (const f of readdirSync(src).filter((x) => x.endsWith(".svg"))) {
        const { w, h } = await svgToPng(browser, join(src, f), join(out, basename(f, ".svg") + ".png"));
        console.log(`diagram ${f} ${w}x${h}`);
      }
    } else if (cmd === "pdf") {
      await htmlToPdf(browser, resolve(a), resolve(b));
      console.log("pdf", b);
    } else if (cmd === "png") {
      await browser.send("Emulation.setDeviceMetricsOverride", { width: +(c || 1600), height: +(d || 900), deviceScaleFactor: 1, mobile: false });
      await browser.goto(fileUrl(resolve(a)), 800);
      const shot = await browser.send("Page.captureScreenshot", { format: "png" });
      writeFileSync(resolve(b), Buffer.from(shot.data, "base64"));
      console.log("png", b);
    } else {
      console.log("usage: render.mjs diagrams | pdf in.html out.pdf | png in.html out.png [w] [h]");
    }
  } finally { browser.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
