from __future__ import annotations

from datetime import datetime
from typing import Any

from autoboya.models import BoyaCourse
from autoboya.rules import has_autonomous_sign
from autoboya.storage import AutoBoyaStore


SELECTION_ORIGINS_FILE = "cache/selection_origins.json"
ORIGIN_MANUAL = "manual"
ORIGIN_MACHINE = "machine"


def load_selection_origins(store: AutoBoyaStore) -> dict[str, dict[str, dict[str, Any]]]:
    raw = store.load_json(SELECTION_ORIGINS_FILE, {})
    if not isinstance(raw, dict):
        return {}
    return {
        str(username): {
            str(course_id): record
            for course_id, record in records.items()
            if isinstance(record, dict)
        }
        for username, records in raw.items()
        if isinstance(records, dict)
    }


def origin_for(
    origins: dict[str, dict[str, dict[str, Any]]],
    username: str,
    course_id: int,
) -> str:
    record = origins.get(username, {}).get(str(course_id), {})
    return (
        ORIGIN_MACHINE
        if record.get("origin") == ORIGIN_MACHINE
        else ORIGIN_MANUAL
    )


def reconcile_selection_origins(
    store: AutoBoyaStore,
    selected_by_user: dict[str, list[BoyaCourse]],
) -> dict[str, dict[str, dict[str, Any]]]:
    """Keep machine provenance only while it still matches the selected course."""
    origins = load_selection_origins(store)
    recorded_at = datetime.now().isoformat(timespec="seconds")
    for username, courses in selected_by_user.items():
        previous = origins.get(username, {})
        current: dict[str, dict[str, Any]] = {}
        for course in courses:
            course_key = str(course.id)
            old = previous.get(course_key, {})
            origin = (
                ORIGIN_MACHINE
                if old.get("origin") == ORIGIN_MACHINE
                else ORIGIN_MANUAL
            )
            current[course_key] = {
                "origin": origin,
                "recorded_at": old.get("recorded_at") or recorded_at,
                "name": course.name,
                "sign_type": (
                    "autonomous" if has_autonomous_sign(course) else "regular"
                ),
            }
        origins[username] = current
    store.save_json(SELECTION_ORIGINS_FILE, origins)
    return origins


def mark_machine_selection(
    store: AutoBoyaStore,
    username: str,
    course: BoyaCourse,
) -> None:
    origins = load_selection_origins(store)
    user_records = origins.setdefault(username, {})
    user_records[str(course.id)] = {
        "origin": ORIGIN_MACHINE,
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "name": course.name,
        "sign_type": (
            "autonomous" if has_autonomous_sign(course) else "regular"
        ),
    }
    store.save_json(SELECTION_ORIGINS_FILE, origins)
