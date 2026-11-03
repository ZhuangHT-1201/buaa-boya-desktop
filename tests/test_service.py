from autoboya.storage import AutoBoyaStore

from boya_kit.config import REFRESH_REQUEST_FILE, KitConfig
from boya_kit.service import request_worker_refresh


def test_default_full_refresh_is_five_minutes() -> None:
    assert KitConfig().refresh_seconds == 300


def test_manual_refresh_request_file(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    request_worker_refresh(store)
    assert store.path(REFRESH_REQUEST_FILE).exists()
