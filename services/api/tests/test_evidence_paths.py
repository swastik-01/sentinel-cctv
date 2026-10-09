"""Evidence crops: only a JPEG inside its own camera's folder of the store is served (evidence.crop_file). On Windows
a backslash is a path separator, and '<camera>/..\\<other camera>\\<file>' once reached another camera's crop while
the scope was checked against the first camera."""
import pytest

from sentinel_api.routers import evidence

CROP = "1700000000_GJ01AB1234.jpg"


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path / "crops"
    for cam in ("GNR-GSRTC-001", "AMD-AMC-001"):
        (root / cam).mkdir(parents=True)
    (root / "AMD-AMC-001" / CROP).write_bytes(b"\xff\xd8\xff\xd9")
    (root / "AMD-AMC-001" / "notes.txt").write_text("not a crop")
    monkeypatch.setattr(evidence, "CROP_ROOT", root.resolve())
    return root.resolve()


def test_a_crop_in_its_own_cameras_folder_is_served(store):
    assert evidence.crop_file(f"/crops/AMD-AMC-001/{CROP}") == store / "AMD-AMC-001" / CROP


@pytest.mark.parametrize("path", [
    f"/crops/GNR-GSRTC-001/..\\AMD-AMC-001\\{CROP}",     # Windows separators inside the name
    f"/crops/GNR-GSRTC-001/../AMD-AMC-001/{CROP}",       # more than two parts
    f"/crops/../crops/AMD-AMC-001/{CROP}",
    "/crops/AMD-AMC-001/..",
    f"/crops/AMD-AMC-001/C:{CROP}",                      # a drive-relative path
    f"/crops/AMD-AMC-001/{CROP}:stream",                 # an NTFS alternate data stream
    "/crops/AMD-AMC-001/notes.txt",                      # not a JPEG
    "/crops/AMD-AMC-001/missing.jpg",
    f"/crops//{CROP}",
    f"crops/AMD-AMC-001/{CROP}",
    "",
    None,
])
def test_anything_else_is_refused(store, path):
    assert evidence.crop_file(path) is None
