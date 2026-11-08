import pytest
from autoboya.storage import AutoBoyaStore

from boya_kit.locking import LockUnavailable, file_lock


def test_file_lock_prevents_concurrent_owner(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()

    with file_lock(store, "run/test.lock"):
        with pytest.raises(LockUnavailable):
            with file_lock(store, "run/test.lock"):
                pass

    with file_lock(store, "run/test.lock"):
        pass


def test_file_lock_reclaims_lock_from_dead_process(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    lock_path = store.path("run/stale.lock")
    lock_path.write_text("999999:0:dead-owner", encoding="ascii")

    with file_lock(
        store,
        "run/stale.lock",
        stale_after=0.0,
    ):
        assert lock_path.exists()
