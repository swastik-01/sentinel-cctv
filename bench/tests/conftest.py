"""bench/ is a folder of scripts, not a package: its tests import them by path. Outside pytest's default testpaths, so
`uv run --no-sync pytest` keeps its count; run these with `uv run --no-sync pytest bench/tests`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
