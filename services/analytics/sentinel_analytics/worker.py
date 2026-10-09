"""Analytics worker: N cameras in, plate sightings and object counts out.

Loop: gather the newest frame from every camera that has one → one batched plate
detector call, and one batched object detector (COCO) call on the same frames → OCR each
plate candidate on CPU → validate as an Indian plate → bind it to the vehicle box it sits
in (type, colour) → de-duplicate per camera → queue for the API. Object detections also
feed a per-camera count window, flushed as one row per camera per window.
Frames older than the sampling interval are skipped, so a slow GPU degrades to a lower
analysis rate instead of falling behind. The object pass only ever sees frames the plate
path already pulled, so it cannot take frames away from ANPR.
"""
from __future__ import annotations

import logging
import signal
import time
from urllib.parse import urlsplit, urlunsplit

from sentinel_common import letters_from_digits, looks_like_indian_plate, mask_plate, normalise_plate

from .attribute import bind_parent, frame_has_colour, vehicle_colour
from .config import get_settings
from .detect import PlateDetector
from .objects import CountWindow, ObjectDetector
from .ocr import PlateOCR
from .sink import ApiSink
from .stream import RtspSource
from .static_text import StaticText
from .tracker import PlateDeduper
from .zones import ZoneWatch, zones_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sentinel.worker")


def pick_cameras(all_cams: list[dict]) -> list[dict]:
    s = get_settings()
    cams = sorted(all_cams, key=lambda c: c["camera_code"])
    if s.camera_list:
        missing = sorted(set(s.camera_list) - {c["camera_code"] for c in cams})
        if missing:
            log.warning("CAMERAS names %d camera(s) not enabled for analytics or without a stream: %s",
                        len(missing), ", ".join(missing))
        cams = [c for c in cams if c["camera_code"] in s.camera_list]
    else:
        cams = [c for i, c in enumerate(cams) if i % s.worker_count == s.worker_index]
    if len(cams) > s.max_streams:
        dropped = [c["camera_code"] for c in cams[s.max_streams:]]
        log.warning("MAX_STREAMS=%d: %d camera(s) will NOT be analysed by this worker: %s. Raise MAX_STREAMS, "
                    "list cameras with CAMERAS=, or add a worker (WORKER_INDEX/WORKER_COUNT)",
                    s.max_streams, len(dropped), ", ".join(dropped))
    return cams[: s.max_streams]


def via_relay_host(url: str, relay_host: str) -> str:
    """The camera's stream address as this machine must use it: a localhost relay address points at RELAY_HOST
    when the worker runs on another machine than the relay. Other addresses are left alone."""
    if not relay_host or not url:
        return url
    parts = urlsplit(url)
    if parts.hostname not in ("localhost", "127.0.0.1"):
        return url
    netloc = parts.netloc.rsplit("@", 1)
    host = relay_host + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=f"{netloc[0]}@{host}" if len(netloc) == 2 else host))


def loopback_ipv4(url: str) -> str:
    """'localhost' in a stream address as 127.0.0.1. On 8 Oct, against a relay listening on IPv4 loopback only, both
    workers failed to open rtsp://localhost:8554/...: PyAV at once (ExitError), OpenCV only after its 30 s open
    timeout, on every attempt; rtsp://127.0.0.1:8554/... opened at once. Docker Desktop hides this by answering on
    both loopbacks."""
    parts = urlsplit(url)
    if parts.hostname != "localhost":
        return url
    userinfo = parts.netloc.rsplit("@", 1)
    host = "127.0.0.1" + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=f"{userinfo[0]}@{host}" if len(userinfo) == 2 else host))


ALLOWED_SCHEMES = ("rtsp", "rtsps", "http", "https")


def allowed_source(url: str) -> bool:
    """Only stream schemes reach the decoders. The registry's stream fields are text a department user can write,
    and FFmpeg would open file:// or any other protocol it knows if handed one."""
    return urlsplit(url or "").scheme.lower() in ALLOWED_SCHEMES


def check_read(text: str, conf: float, min_conf: float, max_from_digits: int) -> str:
    """'gate' when a read is not a confident Indian plate; 'digits' when it fits one only after more than
    `max_from_digits` digits were turned into letters (a hoarding's phone number reads like that); else 'ok'."""
    if not text or conf < min_conf or not looks_like_indian_plate(normalise_plate(text)):
        return "gate"
    if letters_from_digits(text) > max_from_digits:
        return "digits"
    return "ok"


def fetch_cameras(sink, wait_s: float, sleep=time.sleep) -> list:
    """The camera list, waiting for the API if it is down (restarting, or not up yet at boot): an edge worker that
    gives up at once stays down until someone restarts it. Raises after `wait_s` of failures."""
    delay, waited = 2.0, 0.0
    while True:
        try:
            return sink.cameras()
        except Exception as e:  # noqa: BLE001
            if waited >= wait_s:
                raise
            log.warning("API not reachable (%s); retrying in %.0f s", e, delay)
            sleep(delay)
            waited += delay
            delay = min(delay * 2, 30.0)


def run() -> int:
    s = get_settings()
    if s.enable_face_recognition:
        log.error("ENABLE_FACE_RECOGNITION is set; this worker does not implement it by design")
    sink = ApiSink()
    try:
        cams = pick_cameras(fetch_cameras(sink, s.startup_wait_s))
    except Exception as e:  # noqa: BLE001
        log.error("cannot fetch camera list from %s after %.0f s: %s", s.api_url, s.startup_wait_s, e)
        return 1
    bad = [c["camera_code"] for c in cams if not allowed_source(c["rtsp_url"])]
    if bad:
        log.warning("not analysed, stream address is not rtsp/http: %s", ", ".join(bad))
        cams = [c for c in cams if c["camera_code"] not in bad]
    if not cams:
        log.error("no cameras assigned to %s (index %d of %d)", s.worker_id, s.worker_index, s.worker_count)
        return 1
    log.info("%s: %d cameras: %s", s.worker_id, len(cams), ", ".join(c["camera_code"] for c in cams))

    detector, ocr = PlateDetector(), PlateOCR()
    sources = {c["camera_code"]: RtspSource(c["camera_code"],
                                            loopback_ipv4(via_relay_host(c["rtsp_url"], s.relay_host)),
                                            s.detect_fps * 1.5, s.hw_decode).start()
               for c in cams}
    dedup = {code: PlateDeduper(code, s.dedup_seconds, s.confirm_s, s.confirm_reads, s.min_reads,
                                s.slow_fps, s.single_read_conf) for code in sources}
    static = {code: StaticText(code, s.static_text_window_s, s.static_text_mute_s) for code in sources}
    last_analysed: dict[str, float] = {}
    if s.track_log:                     # evaluation only: every track's reads, to compare plate-choice rules
        import json
        track_file = open(s.track_log, "a", encoding="utf-8")   # noqa: SIM115 - kept open for the run
        for d in dedup.values():
            d.track_log = lambda rec: (track_file.write(json.dumps(rec) + "\n"), track_file.flush())
    interval = 1.0 / s.detect_fps
    next_due = {code: 0.0 for code in sources}
    analysed = {code: 0 for code in sources}
    gated = {code: 0 for code in sources}       # reads that passed the gate, and those of them dropped as
    not_plate = {code: 0 for code in sources}   # not a plate: counts only, the text is never logged
    reads_total = 0
    t_flush = t_beat = t_log = time.time()
    sink.refresh_watchlist()
    t_watch = t_log
    if sink.spool.pending():
        log.info("%d spooled batches from an earlier outage will replay", len(sink.spool.pending()))

    objects = ObjectDetector()
    obj_interval = 1.0 / s.object_fps if s.object_fps > 0 else 0.0
    next_obj_due = {code: t_log for code in sources}          # epoch seconds, like `now`
    windows = {code: CountWindow(code, s.count_window_s, t_log) for code in sources} if objects.ready else {}
    zone_watch = {c["camera_code"]: ZoneWatch(c["camera_code"], zs) for c in cams if (zs := zones_for(c))}
    if zone_watch and objects.ready:
        log.info("intrusion zones: %s", ", ".join(f"{c} ({len(z.zones)})" for c, z in zone_watch.items()))
    elif zone_watch:
        log.warning("intrusion zones are configured but object detection is off: they will not be watched")
    obj_frames = obj_ms = 0.0
    typed = coloured = 0
    running = True

    def stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    while running:
        now = time.time()
        batch_codes, batch_frames = [], []
        for code, src in sources.items():
            if now < next_due[code]:
                continue
            f = src.latest()
            if f is None:
                continue
            next_due[code] = now + interval
            batch_codes.append((code, f))
            batch_frames.append(f.image)

        if batch_frames:
            t0 = time.perf_counter()
            boxes_per_frame = detector.detect_batch(batch_frames)

            # Object pass on the same frames: cameras whose object sample is due, oldest first,
            # capped per tick so its cost is bounded and no camera is starved.
            objs_per_frame: list = [None] * len(batch_frames)   # None = not analysed, [] = nothing seen
            if objects.ready:
                due = sorted((i for i, (code, _) in enumerate(batch_codes) if now >= next_obj_due[code]),
                             key=lambda i: next_obj_due[batch_codes[i][0]])[: s.object_max_batch]
                if due:
                    t1 = time.perf_counter()
                    for i, objs in zip(due, objects.detect_batch([batch_frames[i] for i in due])):
                        code, f = batch_codes[i]
                        objs_per_frame[i] = objs
                        windows[code].add(objs, f.ts.timestamp())
                        next_obj_due[code] = now + obj_interval
                        if code in zone_watch:
                            h, w = f.image.shape[:2]
                            for e in zone_watch[code].update(objs, f.ts.timestamp(), w, h, obj_interval):
                                sink.add_event(e)
                    obj_frames += len(due)
                    obj_ms += (time.perf_counter() - t1) * 1000

            jobs = []   # every plate candidate from every camera, OCR'd in one call
            for i, ((code, f), boxes) in enumerate(zip(batch_codes, boxes_per_frame)):
                analysed[code] += 1
                if code in last_analysed:
                    dedup[code].observe_interval(now - last_analysed[code])
                last_analysed[code] = now
                for (x, y, w, h, dconf) in boxes:
                    pad = int(h * 0.15)
                    crop = f.image[max(0, y - pad): y + h + pad, max(0, x - pad): x + w + pad]
                    parent = bind_parent((x, y, w, h), objs_per_frame[i]) if s.attribute_vehicle else None
                    jobs.append((code, f, i, (x, y, w, h, dconf), crop, parent))
            has_colour: dict[int, bool] = {}
            for (code, f, i, (x, y, w, h, dconf), crop, parent), (text, oconf) in zip(
                    jobs, ocr.read_many([j[4] for j in jobs])):
                verdict = check_read(text, oconf, s.min_ocr_conf, s.max_letters_from_digits)
                if verdict == "gate":
                    continue
                gated[code] += 1
                if verdict == "digits":
                    not_plate[code] += 1
                    continue
                vtype = vcolour = None
                if parent is not None:          # colour only for reads that survived OCR: CPU is scarce
                    vtype = (parent.label, parent.conf)
                    if s.attribute_colour:
                        if i not in has_colour:
                            has_colour[i] = frame_has_colour(f.image)
                        vcolour = vehicle_colour(f.image, parent, (x, y, w, h)) if has_colour[i] else None
                dedup[code].offer(text, oconf, dconf, (x, y, w, h), f.ts.timestamp(), crop, vtype, vcolour, now)
            dt = time.perf_counter() - t0
            if dt > interval * 1.5:
                log.debug("batch of %d took %.0f ms (> interval)", len(batch_frames), dt * 1000)
        else:
            time.sleep(0.01)

        for code, d in dedup.items():
            for r in d.harvest(now):
                if not static[code].allow(r.plate_norm, r.bbox, r.ts):
                    continue            # fixed text (a hoarding) or a parked vehicle, read again in place
                reads_total += 1
                typed += r.vehicle_type is not None
                coloured += r.vehicle_color is not None
                path = sink.save_crop(code, r.plate_norm, r.ts, r.crop)
                sink.add(code, r, path)
                # masked: the log file is outside the database's scoping, audit and retention
                log.info("%s: %s (ocr %.2f, %d reads)%s @ %s", code, mask_plate(r.plate_norm), r.ocr_conf, r.count,
                         f" {r.vehicle_color or '?'} {r.vehicle_type}" if r.vehicle_type else "",
                         time.strftime("%H:%M:%S", time.gmtime(r.ts)))

        for code, w in windows.items():
            if w.due(now):
                sink.add_event(w.to_event(now, objects.name))
                windows[code] = CountWindow(code, s.count_window_s, now)

        if now - t_flush >= s.batch_flush_s:
            sink.flush()
            t_flush = now
        if now - t_watch >= s.watchlist_refresh_s:
            sink.refresh_watchlist()
            t_watch = now
        if now - t_beat >= s.heartbeat_s:
            fps = {c: round(analysed[c] / max(1e-6, now - t_log), 2) for c in sources}
            sink.heartbeat(s.worker_id, list(sources), fps)
            t_beat = now
            for d in dedup.values():
                d.gc()
        if now - t_log >= s.log_every_s:
            span = now - t_log
            online = sum(1 for x in sources.values() if x.stats.connected)
            hiccups = sum(x.stats.decode_hiccups for x in sources.values())
            disc = sum(x.stats.discontinuities for x in sources.values())
            no_pts = [c for c, x in sources.items() if not x.stats.pts_usable]
            pending = len(sink.spool.pending())
            log.info("%d/%d streams up | analysed %.1f fps total | sightings %d sent %d alerts %d failed %d "
                     "| decode hiccups %d | discontinuities %d%s%s",
                     online, len(sources), sum(analysed.values()) / span, reads_total, sink.sent,
                     sink.alerts, sink.failed, hiccups, disc,
                     f" | decode-clock timing on {','.join(no_pts)}" if no_pts else "",
                     f" | spooled {sink.spooled} replayed {sink.replayed} pending {pending} batches"
                     f" local alerts {sink.local_alerts}" if sink.spooled or pending else "")
            muted = {c: f.dropped for c, f in static.items() if f.dropped}
            if muted:
                log.info("fixed text not stored (same text, same place): %s",
                         ", ".join(f"{c} {n}" for c, n in muted.items()))
            dropped = {c: n for c, n in not_plate.items() if n}
            if dropped:
                log.info("reads dropped as not a plate (%d+ letters made from digits), of reads passing the gate: %s",
                         s.max_letters_from_digits + 1, ", ".join(f"{c} {n}/{gated[c]}" for c, n in dropped.items()))
            slow = [f"{c} {1 / d.interval:.1f}" for c, d in dedup.items() if d.slow]
            if slow:
                log.warning("analysed below %.1f fps per camera: %s | holding tracks longer; single confident "
                            "reads accepted (%d so far)", s.slow_fps, ", ".join(slow),
                            sum(d.single_reads for d in dedup.values()))
            if objects.ready:
                log.info("objects: %.1f fps analysed, %.0f ms/frame | sightings with type %d/%d, colour %d/%d "
                         "| count rows sent %d", obj_frames / span, obj_ms / max(1, obj_frames),
                         typed, reads_total, coloured, reads_total, sink.events_sent)
                obj_frames = obj_ms = 0.0
            for c in analysed:
                analysed[c] = 0
            t_log = now

    for src in sources.values():
        src.stop()
    for w in windows.values():          # partial windows are still real data; window_s says how long
        if w.frames:
            sink.add_event(w.to_event(time.time(), objects.name))
    sink.flush()
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
