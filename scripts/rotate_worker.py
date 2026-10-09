"""Analyse many cameras on one machine by rotation: run the analytics worker on one group of cameras
for a fixed time, stop it, move to the next group. Every group's start and end are appended to a CSV,
because a report on rotated cameras must say which camera was analysed when (a camera not analysed
while a vehicle passed has no sighting of it).

    uv run --no-sync python scripts/rotate_worker.py --minutes 12 --cycles 2 \
        --group CAM17,CAM18,CAM12,CAM14 --group CAM13,CAM15,CAM16,CAM04 ...

Each worker's log goes to <log-dir>/worker_<n>_<group>.log. Ctrl+C stops the current worker cleanly.
"""
from __future__ import annotations

import argparse
import csv
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))


def stop(proc: subprocess.Popen) -> None:
    """Stop the worker and every child it started. On Windows a plain terminate can leave the Python
    child of the console-script launcher running, still holding its cameras."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(20)
        except subprocess.TimeoutExpired:
            proc.kill()
    proc.wait()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", action="append", required=True, help="comma-separated camera codes; repeatable")
    ap.add_argument("--minutes", type=float, default=12)
    ap.add_argument("--cycles", type=int, default=1, help="passes over all groups (0 = until stopped)")
    ap.add_argument("--log-dir", default=str(ROOT / "data" / "rotation"))
    ap.add_argument("--csv", default=None, help="default: <log-dir>/rotation.csv")
    a = ap.parse_args()
    log_dir = Path(a.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    out = Path(a.csv) if a.csv else log_dir / "rotation.csv"
    new = not out.exists()
    groups = [g.upper().replace(" ", "") for g in a.group]
    n, cycle = 0, 0
    try:
        while a.cycles == 0 or cycle < a.cycles:
            for g in groups:
                n += 1
                start = datetime.now(IST)
                log = log_dir / f"worker_{n:03d}_{g.replace(',', '-')}.log"
                env = {**os.environ, "CAMERAS": g, "PYTHONUTF8": "1"}
                print(f"{start:%H:%M:%S} group {n}: {g} for {a.minutes:g} min", flush=True)
                with open(log, "w", encoding="utf-8") as f:
                    # python -m, not the sentinel-worker.exe launcher: the antivirus held such a launcher on 7 Oct
                    proc = subprocess.Popen(["uv", "run", "--no-sync", "python", "-m", "sentinel_analytics.worker"],
                                            cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT)
                    try:
                        proc.wait(timeout=a.minutes * 60)
                        print(f"  worker exited early with code {proc.returncode}; see {log}", flush=True)
                    except subprocess.TimeoutExpired:
                        pass
                    finally:
                        stop(proc)
                end = datetime.now(IST)
                with open(out, "a", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    if new:
                        w.writerow(["run", "cameras", "start_ist", "end_ist", "minutes", "log"])
                        new = False
                    w.writerow([n, g, f"{start:%Y-%m-%dT%H:%M:%S}", f"{end:%Y-%m-%dT%H:%M:%S}",
                                round((end - start).total_seconds() / 60, 1), log.name])
            cycle += 1
    except KeyboardInterrupt:
        print("stopped", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
