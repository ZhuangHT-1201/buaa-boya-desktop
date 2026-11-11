from __future__ import annotations

import os
import uuid
from pathlib import Path

from autoboya.storage import AutoBoyaStore


CA_BUNDLE_FILE = "runtime/cacert.pem"


def ensure_persistent_ca_bundle(store: AutoBoyaStore) -> Path | None:
    """Keep a CA bundle outside PyInstaller's temporary extraction directory."""
    destination = store.path(CA_BUNDLE_FILE)
    destination.parent.mkdir(parents=True, exist_ok=True)

    source: Path | None = None
    try:
        import certifi

        candidate = Path(certifi.where())
        if candidate.is_file() and candidate.stat().st_size > 0:
            source = candidate
    except Exception:
        source = None

    if source is not None:
        try:
            if (
                not destination.is_file()
                or destination.stat().st_size != source.stat().st_size
            ):
                temporary = destination.with_name(
                    f"{destination.name}.{uuid.uuid4().hex}.tmp"
                )
                temporary.write_bytes(source.read_bytes())
                os.replace(temporary, destination)
        except OSError:
            pass

    if not destination.is_file() or destination.stat().st_size <= 0:
        return None

    bundle = str(destination)
    os.environ["SSL_CERT_FILE"] = bundle
    os.environ["REQUESTS_CA_BUNDLE"] = bundle
    os.environ["CURL_CA_BUNDLE"] = bundle
    return destination
