// Which cameras play on the video wall, and how soon? Opens the real control room in headless Chrome,
// signs in, shows a set of cameras on a 2x2 wall and reports when each tile first has a picture.
//   CAMS=CAM04,CAM02,CAM06,CAM05 node wall_probe.mjs
import { launch, sleep } from "./chrome.mjs";

const WEB = process.env.WEB || "http://localhost:5173";
const PW = process.env.ADMIN_PASSWORD || "admin123";
const CAMS = (process.env.CAMS || "CAM04,CAM02,CAM06,CAM05").split(",");
const WAIT = Number(process.env.WAIT_S || 40);

// FAKE_MEDIA_UI=0 runs as an operator's browser does, with no media permission granted. With it granted, Chrome stops
// masking its addresses and offers only LAN candidates, which cannot reach a relay listening on loopback only.
const b = await launch({ width: 1920, height: 1080, port: 9343,
  args: process.env.FAKE_MEDIA_UI === "0" ? [] : ["--use-fake-ui-for-media-stream"] });
const ev = (js) => b.evaluate(js);
try {
  CAMS.forEach((c) => fetch(`http://localhost:8888/${c}/index.m3u8`).catch(() => {}));     // start the relays
  await b.goto(`${WEB}/login`, 900);
  await ev(`(() => { const f = (l) => [...document.querySelectorAll('label')].find(x => x.textContent.trim().startsWith(l)).querySelector('input');
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    for (const [l, v] of [['Username', 'admin'], ['Password', ${JSON.stringify(PW)}]]) { const el = f(l); set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); }
    [...document.querySelectorAll('button')].find(x => x.textContent.includes('Sign in')).click(); return true; })()`);
  await sleep(2500);
  await ev(`localStorage.setItem('sentinel.wall.grid', '2'); history.pushState({}, '', '/wall?cams=${CAMS.join(",")}'); dispatchEvent(new PopStateEvent('popstate', { state: {} })); true`);
  const first = {};
  const t0 = Date.now();
  while ((Date.now() - t0) / 1000 < WAIT && Object.keys(first).length < CAMS.length) {
    // A picture is wider than Chrome's 2x2 placeholder; the tile's badge says how it plays (webrtc, preview or hls).
    const tiles = await ev(`[...document.querySelectorAll('.player')].map(p => ({ t: p.parentElement?.textContent.slice(0, 60) || '',
      w: p.querySelector('video')?.videoWidth || 0, badge: p.querySelector('.player-badge')?.textContent || '' }))`);
    tiles.forEach((x) => { const c = CAMS.find((c) => x.t.includes(c)); if (c && x.w > 16 && !(c in first)) first[c] = `${((Date.now() - t0) / 1000).toFixed(1)} s (${x.badge}, ${x.w} px wide)`; });
    await sleep(500);
  }
  for (const c of CAMS) console.log(`${c}: ${c in first ? `picture after ${first[c]}` : `no picture in ${WAIT} s`}`);
  if (process.env.HIDE) {                     // a clean shot for the deck: picker hidden, pictures settled
    await ev(`[...document.querySelectorAll('button')].find(x => x.textContent.trim().startsWith('Hide picker'))?.click(); true`);
    await sleep(Number(process.env.HIDE) * 1000);
  }
  const shot = await b.send("Page.captureScreenshot", { format: "jpeg", quality: 70 });
  (await import("node:fs")).writeFileSync(process.env.SHOT || "wall_probe.jpg", Buffer.from(shot.data, "base64"));
} finally {
  b.close();
}
