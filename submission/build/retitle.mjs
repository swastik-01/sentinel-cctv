// Swap the title card of an existing recording and re-encode it, without re-recording:
//   node retitle.mjs
// Needs submission/out/video_frames/ and frames.ffconcat from the recording (record.mjs keeps them).
// The title is the first frame; its duration in frames.ffconcat is kept, so the video length does not change.
// Back up Sentinel-Demo.mp4 first: it is overwritten.
import { execFileSync } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { H, W, writeCards } from "./cards.mjs";
import { fileUrl, launch } from "./chrome.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "submission/out");
const FIRST = join(OUT, "video_frames", "f_000001.jpg");
if (!existsSync(FIRST) || !existsSync(join(OUT, "frames.ffconcat"))) throw new Error("no recording frames to retitle");

writeCards(OUT);
const b = await launch({ width: W, height: H, port: 9342 });
try {
  await b.send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await b.goto(fileUrl(join(OUT, "cards/title.html")), 800);
  const shot = await b.send("Page.captureScreenshot", { format: "jpeg", quality: 82 });
  writeFileSync(FIRST, Buffer.from(shot.data, "base64"));
} finally {
  b.close();
}

const image = process.env.FFMPEG_IMAGE || "sentinel-feedsim-publisher";
execFileSync("docker", ["run", "--rm", "-v", `${OUT.replace(/\\/g, "/")}:/work`, "-w", "/work", "--entrypoint", "ffmpeg", image,
  "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", "frames.ffconcat",
  "-vf", `scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,fps=25,format=yuv420p`,
  "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-movflags", "+faststart", "Sentinel-Demo.mp4"],
  { stdio: "inherit", env: { ...process.env, MSYS_NO_PATHCONV: "1" } });
console.log("retitled:", join(OUT, "Sentinel-Demo.mp4"));
