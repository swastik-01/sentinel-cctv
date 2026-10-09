from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_url: str = "http://localhost:8000"
    ingest_key: str = "dev_ingest_key_replace_me"

    # Sharding: worker i of n takes cameras where index % n == i. Scale out = run more workers.
    worker_id: str = "worker-1"
    worker_index: int = 0
    worker_count: int = 1
    cameras: str = ""            # optional comma-separated explicit list, overrides sharding
    max_streams: int = 12
    # The registry stores relay addresses as the API sees them (rtsp://localhost:8554/<code>). A worker on another
    # machine sets this to the relay machine's LAN address; localhost addresses are rewritten to it.
    relay_host: str = ""

    device: str = "cuda"         # cuda | cpu
    hw_decode: str = "auto"      # auto = ask OpenCV for a hardware video decoder, fall back per camera | off
    fp16: bool | None = None     # None = auto (off on GTX 16xx, which NaNs in half precision)
    detect_fps: float = 5.0      # frames analysed per camera per second (not decode fps)
    plate_model: str = "models/plate-yolov11n.pt"
    plate_model_hf: str = "morsetechlab/yolov11-license-plate-detection"
    plate_model_hf_file: str = "license-plate-finetune-v1n.pt"
    ocr_model: str = "cct-xs-v2-global-model"
    min_plate_conf: float = Field(0.35, ge=0, le=1)
    min_ocr_conf: float = Field(0.35, ge=0, le=1)   # per-character minimum; best read wins later
    max_letters_from_digits: int = 1    # drop a read that fits a plate only after more digits than this were made
                                        # letters (a hoarding's phone number); a large value turns it off
    confirm_s: float = 1.0              # hold a new track this long before emitting the best read
    confirm_reads: int = 3              # ...or until this many reads agree
    min_reads: int = 2                  # drop tracks seen fewer times than this...
    slow_fps: float = 2.0               # ...unless the camera is analysed below this rate, where one
    single_read_conf: float = 0.6       # read at or above this confidence is accepted (see tracker.py)
    static_text_window_s: float = 600.0  # same text, same place again within this: fixed text, muted (static_text.py);
                                         # 0 turns it off (the simulator loops each vehicle past one spot every 60 s)
    static_text_mute_s: float = 1800.0   # how long such text stays muted after it was last read
    track_log: str = ""                 # evaluation only: append every harvested track (all reads) to this JSONL
    detector: str = "both"              # yolo | classical | both (classical = text-line finder, CPU)
    ocr_threads: int = 2                # ONNX intra-op threads; keep low so decoders are not starved
    dedup_seconds: float = 8.0          # same plate on same camera within this window = one sighting
    # Object analytics: a second, general-purpose detector (COCO) on the frames the plate path
    # already pulls. Gives per-camera person/vehicle counts and vehicle type/colour on sightings.
    object_detection: bool = True       # false = exactly the plate-only worker
    object_model: str = "models/yolo11n.pt"
    min_object_conf: float = Field(0.40, ge=0, le=1)
    object_imgsz: int = 640
    object_fps: float = 5.0             # per-camera cap; can never exceed the achieved plate rate
    object_max_batch: int = 8           # frames per object pass; oldest-due cameras go first
    count_window_s: float = 60.0        # one counts row per camera per window
    # Counts-only worker (counts.py, `sentinel-counts`): keyframes only, many cameras, beside the plate worker.
    counts_fps: float = 1.0             # frames counted per camera per second at most (keyframes permitting)
    counts_max_streams: int = 60
    counts_exclude: str = ""            # the plate workers' cameras: comma-separated, never counted twice
    counts_batch: int = 16              # frames per object pass
    counts_worker_id: str = "counts-1"
    attribute_vehicle: bool = True      # vehicle type onto plate sightings
    attribute_colour: bool = True       # vehicle colour onto plate sightings (heuristic, see attribute.py)
    crop_dir: str = "data/crops"
    save_crops: bool = True
    batch_flush_s: float = 1.0
    ingest_timeout_s: float = 5.0       # a hung API must not stall analysis for long
    startup_wait_s: float = 300.0       # how long a starting worker waits for the API before giving up
    # Store-and-forward: batches the API cannot take wait here and replay on reconnect.
    spool_dir: str = "data/spool"
    spool_max_mb: float = 512.0         # oldest batches are dropped past this, with a warning
    watchlist_refresh_s: float = 60.0   # edge copy of the active vehicle watchlist
    heartbeat_s: float = 15.0
    log_every_s: float = 30.0

    enable_face_recognition: bool = False  # never true; see docs/privacy-dpdp.md

    @property
    def camera_list(self) -> list[str]:
        return [c.strip().upper() for c in self.cameras.split(",") if c.strip()]

    @property
    def counts_exclude_list(self) -> list[str]:
        return [c.strip().upper() for c in self.counts_exclude.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
