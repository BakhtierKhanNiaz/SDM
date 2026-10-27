"""SHA-256 input and hashing, and SDM's saved settings (M9)."""

import hashlib

import pytest

from sdm.core.checksums import InvalidChecksumError, normalize_sha256, sha256_of
from sdm.storage.database import DownloadStore
from sdm.ui.preferences import Preferences, load_preferences, save_preferences

PYTHON_ORG = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15"


@pytest.mark.parametrize(
    "text",
    [
        PYTHON_ORG,
        PYTHON_ORG.upper(),
        "d297e5ff019966817ad8502465176139\nf2d3d840fa4ed84b13bed399a6ab1f15",  # as python.org
        f"  sha256:{PYTHON_ORG} ",
        f"SHA256 {PYTHON_ORG}",
    ],
)
def test_published_checksums_are_accepted_as_printed(text):
    assert normalize_sha256(text) == PYTHON_ORG


def test_empty_means_no_check():
    assert normalize_sha256("") is None
    assert normalize_sha256("   ") is None
    assert normalize_sha256(None) is None


@pytest.mark.parametrize(
    "text", [PYTHON_ORG[:-1], PYTHON_ORG + "0", "g" * 64, "md5:" + "a" * 32, "a" * 40]
)
def test_anything_else_is_refused(text):
    with pytest.raises(InvalidChecksumError):
        normalize_sha256(text)


def test_sha256_of_a_file(tmp_path):
    data = b"x" * (3 * 1024 * 1024 + 7)  # more than one 1 MiB piece
    path = tmp_path / "f.bin"
    path.write_bytes(data)
    assert sha256_of(path) == hashlib.sha256(data).hexdigest()


@pytest.fixture
def store(tmp_path):
    store = DownloadStore(tmp_path / "sdm.db")
    yield store
    store.close()


def test_preferences_default_and_round_trip(store):
    assert load_preferences(store) == Preferences()
    chosen = Preferences(speed_limit_kib=500, connections=2, default_folder="D:\\Downloads",
                         remember_last_folder=False, keep_in_tray=True, notify=False)  # fmt: skip
    save_preferences(store, chosen)
    assert load_preferences(store) == chosen
    assert chosen.speed_limit_bytes == 500 * 1024
    assert Preferences().speed_limit_bytes is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("prefs.speed_limit_kib", "-5"),
        ("prefs.speed_limit_kib", "lots"),
        ("prefs.speed_limit_kib", "99999999999"),
        ("prefs.connections", "0"),
        ("prefs.connections", "9"),
        ("prefs.notify", "yes"),
        ("prefs.default_folder", "C:\\" + "a" * 2000),
    ],
)
def test_damaged_settings_fall_back_to_defaults(store, key, value):
    store.set_setting(key, value)
    assert load_preferences(store) == Preferences()


@pytest.mark.parametrize(
    ("stored", "loaded"),
    [("chrome,firefox", "chrome,firefox"), ("", ""), ("?", "?"), ("chrome,evil", "?")],
)
def test_the_connected_browsers_are_remembered(store, stored, loaded):
    save_preferences(store, Preferences(browsers=stored))
    assert load_preferences(store).browsers == loaded
