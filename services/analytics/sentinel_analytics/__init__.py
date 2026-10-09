"""Sentinel analytics worker.

Environment for OpenCV's FFmpeg backend is set here, before anything imports cv2
(ultralytics imports it on load): force RTSP over TCP and a socket timeout, as the
sandbox rules require.
"""
import os

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000|max_delay;500000")
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
# AV_LOG_ERROR: decoder complaints when joining mid-GOP are surfaced (and counted per stream),
# never treated as fatal. Set OPENCV_FFMPEG_LOGLEVEL=-8 to silence them entirely.
os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "16")
