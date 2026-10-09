// Swap the end card of the government-feed recording and re-encode it, without re-recording:
//   node recard_gov.mjs
// Needs submission/out/gov_frames/ and gov.ffconcat from record_gov.mjs. The end card is the last frame; it is held
// for HOLD seconds (the recorder's own hold). Back up Sentinel-Gov-Demo.mp4 first: it is overwritten.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { H, W, govFacts, writeGovCards } from "./cards.mjs";
import { fileUrl, launch } from "./chrome.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "submission/out");
const LIST = join(OUT, "gov.ffconcat");
const HOLD = Number(process.env.HOLD || 6);
if (!existsSync(LIST)) throw new Error("no gov.ffconcat: nothing to re-card");

// the last frame of the concat list is the end card (listed twice: the concat demuxer's closing line)
const lines = readFileSync(LIST, "utf-8").trimEnd().split("\n");
const last = lines[lines.length - 1].match(/^file '(.+)'$/);
if (!last) throw new Error("gov.ffconcat does not end with a file line");
const cardFrame = join(OUT, last[1]);

writeGovCards(OUT, govFacts(ROOT));
const b = await launch({ width: W, height: H, port: 9344 });
try {
  await b.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await b.goto(fileUrl(join(OUT, "cards/gov_end.html")), 800);
  const shot = await b.send("Page.captureScreenshot", { format: "jpeg", quality: 82 });
  writeFileSync(cardFrame, Buffer.from(shot.data, "base64"));
} finally {
  b.close();
}

// hold the end card: its duration is the line before the closing file line
const d = lines.length - 2;
if (!/^duration /.test(lines[d])) throw new Error("unexpected gov.ffconcat layout");
lines[d] = `duration ${Math.max(HOLD, Number(lines[d].split(" ")[1])).toFixed(3)}`;
writeFileSync(LIST, lines.join("\n") + "\n");

const image = process.env.FFMPEG_IMAGE || "sentinel-feedsim-publisher";
execFileSync("docker", ["run", "--rm", "-v", `${OUT.replace(/\\/g, "/")}:/work`, "-w", "/work", "--entrypoint", "ffmpeg", image,
  "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "gov.ffconcat",
  "-vf", `scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p`,
  "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-movflags", "+faststart", "Sentinel-Gov-Demo.mp4"],
  { stdio: "inherit", env: { ...process.env, MSYS_NO_PATHCONV: "1" } });
console.log(`re-carded: ${join(OUT, "Sentinel-Gov-Demo.mp4")} (end card held ${HOLD} s)`);
