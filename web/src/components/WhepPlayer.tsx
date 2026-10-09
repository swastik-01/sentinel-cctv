// Live player, in order: the camera's stream over WebRTC/WHEP (sub-second); when that gives no picture, the relay's
// transcoded preview over WebRTC (a stream the browser cannot take as it is: B-frames, a High-profile feed from the
// internet); then HLS. The registry's browser endpoints already point at the preview for H.265 cameras, so the
// codec prop is informational.
// hls.js (most of this component's weight) loads only when a stream falls back to HLS: WebRTC needs none of it.
import type Hls from "hls.js";
import { ReactNode, useEffect, useRef, useState } from "react";
import { pageHost } from "../api";

type Mode = "connecting" | "webrtc" | "preview" | "hls" | "error";

// Per WHEP address, until when its own stream is known to give no picture here: the next load goes straight to the
// preview instead of waiting out the first try again. A convenience only: without storage the player still gets there.
const PREFER_PREVIEW = "sentinel.preview:";
const PREVIEW_MEMORY_MS = 24 * 3600 * 1000;
const prefersPreview = (u: string) => { try { return Number(localStorage.getItem(PREFER_PREVIEW + u) || 0) > Date.now(); } catch { return false; } };
const rememberPreview = (u: string, on: boolean) => {
  try { if (on) localStorage.setItem(PREFER_PREVIEW + u, String(Date.now() + PREVIEW_MEMORY_MS)); else localStorage.removeItem(PREFER_PREVIEW + u); }
  catch { /* storage unavailable: nothing is remembered */ }
};

/** The relay's transcoded preview of a camera (infra/mediamtx.yml "~^(.+)_sub$": baseline H.264, no B-frames, which
 *  any browser decodes); null when the address already is one. */
export function previewWhep(url: string): string | null {
  const m = url.match(/^(.*\/)([^/?]+)\/whep(\?.*)?$/);
  if (!m || m[2].endsWith("_sub")) return null;
  return `${m[1]}${m[2]}_sub/whep${m[3] ?? ""}`;
}

export default function WhepPlayer({ whep: whepIn, hls: hlsIn, codec, muted = true, overlay }: {
  whep?: string | null; hls?: string | null; codec?: string | null; muted?: boolean;
  overlay?: ReactNode;               // drawn over the picture itself (letterboxing excluded)
}) {
  const whep = whepIn && pageHost(whepIn), hls = hlsIn && pageHost(hlsIn);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [mode, setMode] = useState<Mode>("connecting");
  const [detail, setDetail] = useState<string>("");
  const [box, setBox] = useState({ left: 0, top: 0, width: 100, height: 100 });

  useEffect(() => {
    const v = videoRef.current;
    if (!v || !overlay) return;
    const fit = () => {                 // where object-fit: contain actually puts the picture
      const W = v.clientWidth, H = v.clientHeight, vw = v.videoWidth, vh = v.videoHeight;
      if (!W || !H || !vw || !vh) return;
      const s = Math.min(W / vw, H / vh), w = vw * s, h = vh * s;
      setBox({ left: (W - w) / 2 / W * 100, top: (H - h) / 2 / H * 100, width: w / W * 100, height: h / H * 100 });
    };
    v.addEventListener("loadedmetadata", fit); v.addEventListener("resize", fit);
    const ro = new ResizeObserver(fit); ro.observe(v);
    return () => { v.removeEventListener("loadedmetadata", fit); v.removeEventListener("resize", fit); ro.disconnect(); };
  }, [!!overlay]); // eslint-disable-line

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const pcs: RTCPeerConnection[] = [];
    let hlsInst: Hls | null = null;
    let cancelled = false;
    let hlsStarted = false;
    setMode("connecting"); setDetail("");

    const startHls = async (why: string) => {
      if (cancelled || hlsStarted) return;
      hlsStarted = true;
      setDetail(why);
      if (!hls) { setMode("error"); setDetail(`${why}; no HLS endpoint`); return; }
      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.srcObject = null; video.src = hls; video.play().catch(() => {}); setMode("hls"); return;
      }
      let HlsLib: typeof Hls;
      try { HlsLib = (await import("hls.js")).default; }
      catch { if (!cancelled) { setMode("error"); setDetail("the HLS player did not load"); } return; }
      if (cancelled) return;
      if (!HlsLib.isSupported()) { setMode("error"); setDetail("HLS unsupported"); return; }
      video.srcObject = null;
      hlsInst = new HlsLib({ lowLatencyMode: true, liveSyncDuration: 1.5, maxLiveSyncPlaybackRate: 1.2 });
      hlsInst.on(HlsLib.Events.ERROR, (_e, d) => {
        if (d.fatal && !cancelled) { setMode("error"); setDetail(`HLS ${d.type}: ${d.details}`); }
      });
      hlsInst.loadSource(hls); hlsInst.attachMedia(video);
      video.play().catch(() => {}); setMode("hls");
    };

    /** One WHEP session. ok: the browser decoded a frame (a track alone is not a picture: a profile or B-frames it
     *  cannot take give a track and nothing on screen, or the relay closes the session). connected: the session got
     *  as far as a connection, so another profile from the same relay could play; without it (no route to the relay)
     *  a second WebRTC try would fail the same way. */
    const tryWhep = (url: string, frameMs: number) => new Promise<{ ok: boolean; connected: boolean }>((resolve) => {
      const pc = new RTCPeerConnection({ iceServers: [] });
      pcs.push(pc);
      let done = false, connected = false;
      // A picture, not Chrome's 2x2 placeholder: a placeholder that turns into the real frame counts on its resize.
      const onFrame = () => { if (video.videoWidth > 16 && video.videoHeight > 16) finish(true); };
      const finish = (ok: boolean) => {
        if (done) return;
        done = true; window.clearTimeout(timer);
        video.removeEventListener("loadeddata", onFrame); video.removeEventListener("resize", onFrame);
        if (!ok) pc.close();
        resolve({ ok: ok && !cancelled, connected });
      };
      const timer = window.setTimeout(() => finish(false), frameMs);
      pc.addTransceiver("video", { direction: "recvonly" });
      pc.ontrack = (e) => {
        if (cancelled) return finish(false);
        video.srcObject = e.streams[0];
        video.addEventListener("loadeddata", onFrame); video.addEventListener("resize", onFrame);
        video.play().catch(() => {});
      };
      pc.onconnectionstatechange = () => {
        const s = pc.connectionState;
        if (s === "connected") connected = true;
        if (s !== "failed" && s !== "closed") return;
        if (!done) finish(false);                          // e.g. the relay closed it: no need to wait out the timer
        else if (!cancelled && s === "failed") { pc.close(); startHls("WebRTC connection lost → HLS"); }   // it played, then dropped
      };
      (async () => {
        try {
          await pc.setLocalDescription(await pc.createOffer());
          await new Promise<void>((res) => {
            if (pc.iceGatheringState === "complete") return res();
            const t = window.setTimeout(res, 800);
            pc.onicegatheringstatechange = () => {
              if (pc.iceGatheringState === "complete") { window.clearTimeout(t); res(); }
            };
          });
          const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/sdp" }, body: pc.localDescription!.sdp });
          if (!r.ok) throw new Error(`WHEP ${r.status}`);
          const sdp = await r.text();
          if (/^m=video 0 /m.test(sdp)) throw new Error("no video codec in common");
          await pc.setRemoteDescription({ type: "answer", sdp });
        } catch { finish(false); }
      })();
    });

    const showPreview = () => {
      setMode("preview");
      setDetail("the camera's own stream does not play in a browser: the relay's preview profile is shown");
    };
    (async () => {
      if (!whep) return startHls("no WHEP endpoint");
      const preview = previewWhep(whep);
      let previewTried = false;
      if (preview && prefersPreview(whep)) {
        previewTried = true;
        if ((await tryWhep(preview, 20000)).ok) return showPreview();
        if (cancelled) return;
      }
      // 15 s: an address that already is a preview (H.265 cameras) starts its transcoder for the first viewer.
      const first = await tryWhep(whep, 15000);
      if (first.ok) { if (preview) rememberPreview(whep, false); setMode("webrtc"); return; }
      if (cancelled) return;
      if (preview && !previewTried && first.connected && (await tryWhep(preview, 20000)).ok) {
        rememberPreview(whep, true);
        return showPreview();
      }
      if (!cancelled) startHls(first.connected ? "WebRTC gave no picture → HLS" : "WebRTC could not connect → HLS");
    })();

    return () => {
      cancelled = true;
      pcs.forEach((pc) => pc.close()); hlsInst?.destroy();
      video.srcObject = null; video.removeAttribute("src"); video.load();
    };
  }, [whep, hls, codec]);

  return (
    <div className="player">
      <video ref={videoRef} muted={muted} autoPlay playsInline />
      {overlay && <div className="player-overlay" style={{ left: `${box.left}%`, top: `${box.top}%`, width: `${box.width}%`, height: `${box.height}%` }}>{overlay}</div>}
      <div className={`player-badge ${mode}`} title={detail}>
        {mode === "connecting" ? "connecting…" : mode === "error" ? "no video" : mode}
      </div>
    </div>
  );
}
