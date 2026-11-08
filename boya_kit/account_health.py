from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from autoboya.storage import AutoBoyaStore

from .locking import file_lock


ACCOUNT_HEALTH_FILE = "cache/account_health.json"
STATUS_OK = "ok"
STATUS_AUTH_REQUIRED = "auth_required"
STATUS_ERROR = "error"


def load_account_health(store: AutoBoyaStore) -> dict[str, dict[str, Any]]:
    raw = store.load_json(ACCOUNT_HEALTH_FILE, {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(username): record
        for username, record in raw.items()
        if isinstance(record, dict)
    }


def account_health(store: AutoBoyaStore, username: str) -> dict[str, Any]:
    record = load_account_health(store).get(username, {})
    if record.get("status") == STATUS_AUTH_REQUIRED:
        session_path = store.path(f"sessions/{username}.json")
        try:
            updated_at = datetime.fromisoformat(str(record.get("updated_at", "")))
            if session_path.stat().st_mtime > updated_at.timestamp():
                record = {
                    **record,
                    "status": STATUS_OK,
                    "error": None,
                    "captcha_path": None,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
        except (OSError, ValueError):
            pass
    return record


def _save(store: AutoBoyaStore, username: str, record: dict[str, Any]) -> None:
    with file_lock(
        store,
        "cache/account_health.lock",
        timeout=5.0,
        stale_after=60.0,
    ):
        health = load_account_health(store)
        health[username] = record
        store.save_json(ACCOUNT_HEALTH_FILE, health)


def mark_auth_ok(
    store: AutoBoyaStore,
    username: str,
    *,
    message: str = "",
) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    previous = account_health(store, username)
    _save(
        store,
        username,
        {
            "status": STATUS_OK,
            "updated_at": now,
            "last_success_at": now,
            "message": message,
            "error": None,
            "captcha_path": None,
            "previous_error": previous.get("error"),
            "failure_count": 0,
            "next_retry_at": None,
        },
    )


def mark_auth_required(
    store: AutoBoyaStore,
    username: str,
    error: str,
    captcha_path: Path | None = None,
    *,
    failure_count: int | None = None,
    next_retry_at: str | None = None,
) -> None:
    previous = account_health(store, username)
    _save(
        store,
        username,
        {
            **previous,
            "status": STATUS_AUTH_REQUIRED,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error": error,
            "captcha_path": str(captcha_path) if captcha_path else None,
            "failure_count": (
                failure_count
                if failure_count is not None
                else int(previous.get("failure_count") or 0)
            ),
            "next_retry_at": next_retry_at,
        },
    )


def mark_auth_error(store: AutoBoyaStore, username: str, error: str) -> None:
    previous = account_health(store, username)
    _save(
        store,
        username,
        {
            **previous,
            "status": STATUS_ERROR,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error": error,
            "captcha_path": None,
        },
    )


def clear_account_health(store: AutoBoyaStore, username: str) -> None:
    health = load_account_health(store)
    if username in health:
        health.pop(username, None)
        store.save_json(ACCOUNT_HEALTH_FILE, health)
