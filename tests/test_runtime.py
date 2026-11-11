import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import certifi
import httpx
from autoboya.storage import AutoBoyaStore

from boya_kit.runner import SafeRotatingFileHandler
from boya_kit.runtime import CA_BUNDLE_FILE, ensure_persistent_ca_bundle


def test_ca_bundle_survives_missing_packaged_copy(tmp_path, monkeypatch) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    source = tmp_path / "packaged-cacert.pem"
    source.write_bytes(Path(certifi.where()).read_bytes())
    monkeypatch.setattr(certifi, "where", lambda: str(source))
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("CURL_CA_BUNDLE", raising=False)

    destination = ensure_persistent_ca_bundle(store)

    assert destination == store.path(CA_BUNDLE_FILE)
    assert destination.read_bytes() == source.read_bytes()

    source.unlink()
    assert ensure_persistent_ca_bundle(store) == destination
    assert os.environ["SSL_CERT_FILE"] == str(destination)
    with httpx.Client():
        pass


def test_safe_log_rotation_does_not_raise_on_windows_lock(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "worker.log"
    handler = SafeRotatingFileHandler(
        path,
        maxBytes=10,
        backupCount=1,
        encoding="utf-8",
    )

    def blocked_rotation(_handler) -> None:
        raise PermissionError("file is in use")

    monkeypatch.setattr(
        RotatingFileHandler,
        "doRollover",
        blocked_rotation,
    )
    handler.doRollover()

    assert handler._next_rollover_attempt > time.monotonic()
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "message",
        (),
        None,
    )
    assert handler.shouldRollover(record) is False
    handler.close()
