from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from autoboya.bykc import parse_category, parse_course
from autoboya.rules import parse_dt


@dataclass(frozen=True)
class CategoryGap:
    category: str
    required: int
    selected: int
    completed: int
    failed: int
    undone: int

    @property
    def remaining_to_select(self) -> int:
        """Unfilled requirement slots that still need a course selection."""
        return max(0, self.required - self.valid_selected)

    @property
    def valid_selected(self) -> int:
        """Selected courses that are not already known to have failed."""
        return max(0, self.selected - self.failed)

    @property
    def pending(self) -> int:
        """Selected courses that are neither passed nor marked failed yet."""
        return max(0, self.selected - self.completed - self.failed)

    @property
    def remaining_to_pass(self) -> int:
        """Requirement slots not yet completed, including pending/failed courses."""
        return max(0, self.required - self.completed)

    @property
    def needs_more(self) -> bool:
        return self.remaining_to_select > 0


def label_after_pipe(value: str) -> str:
    return value.split("|", 1)[1] if "|" in value else value


def iter_stat_rows(stats: dict[str, Any]):
    statistical = stats.get("statistical")
    if not isinstance(statistical, dict):
        return
    for categories in statistical.values():
        if not isinstance(categories, dict):
            continue
        for key, value in categories.items():
            if isinstance(value, dict):
                yield label_after_pipe(str(key)), value


def course_assessment_outcome(
    item: dict[str, Any],
    now: datetime | None = None,
    *,
    course_end: str | None = None,
) -> str:
    """Map one queryChosenCourse row to passed / failed / pending using system fields."""
    now = now or datetime.now()
    course = parse_course(item)
    pass_value = item.get("pass")
    if pass_value is True or str(pass_value) == "1":
        return "passed"
    end = parse_dt(course_end) or parse_dt(course.course_end)
    finished = end is not None and end < now
    if pass_value is False or str(pass_value) == "0":
        return "failed" if finished else "pending"
    if finished and _attendance_clearly_failed(item):
        return "failed"
    return "pending"


def _attendance_clearly_failed(item: dict[str, Any]) -> bool:
    """Only treat finished courses as failed when the system already says so."""
    checkin = item.get("checkin")
    if checkin is False or checkin == 0 or checkin == "0":
        return True
    sign_info = item.get("signInfo")
    if isinstance(sign_info, dict):
        signed_in = sign_info.get("signIn") or sign_info.get("checkIn")
        signed_out = sign_info.get("signOut") or sign_info.get("checkOut")
        if signed_in is False or signed_out is False:
            return True
        if signed_in in (0, "0") or signed_out in (0, "0"):
            return True
    return False


def assessment_counts_from_selected(
    selected_items: Iterable[dict[str, Any]] | None,
    now: datetime | None = None,
) -> dict[str, dict[str, int]]:
    """Aggregate per-category completed/failed/pending from chosen-course rows."""
    now = now or datetime.now()
    counts: dict[str, dict[str, int]] = {}
    if not selected_items:
        return counts
    for item in selected_items:
        if not isinstance(item, dict):
            continue
        category = parse_category(item) or label_after_pipe(
            str(item.get("courseKind") or item.get("kindName") or "")
        )
        if not category:
            course_info = item.get("courseInfo")
            if isinstance(course_info, dict):
                category = parse_category(course_info)
        if not category:
            continue
        bucket = counts.setdefault(
            category,
            {"selected": 0, "completed": 0, "failed": 0, "pending": 0},
        )
        bucket["selected"] += 1
        outcome = course_assessment_outcome(item, now)
        if outcome == "passed":
            bucket["completed"] += 1
        elif outcome == "failed":
            bucket["failed"] += 1
        else:
            bucket["pending"] += 1
    return counts


def parse_gaps(
    stats: dict[str, Any] | None,
    selected_items: Iterable[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[CategoryGap]:
    """Build gaps from queryStatisticByUserId, reconciled with chosen-course pass data."""
    if not isinstance(stats, dict) or not stats:
        return []
    now = now or datetime.now()
    local = assessment_counts_from_selected(selected_items, now)
    gaps: list[CategoryGap] = []
    seen: set[str] = set()
    for category, item in iter_stat_rows(stats):
        seen.add(category)
        local_counts = local.get(category, {})
        selected = _as_int(item.get("selectAssessmentCount"))
        completed = max(
            _as_int(item.get("completeAssessmentCount")),
            _as_int(local_counts.get("completed")),
        )
        failed = max(
            _as_int(item.get("failAssessmentCount")),
            _as_int(local_counts.get("failed")),
        )
        # Prefer the live selected list length when present; otherwise trust statistics.
        if local_counts:
            selected = max(selected, _as_int(local_counts.get("selected")))
        gaps.append(
            CategoryGap(
                category=category,
                required=_as_int(item.get("assessmentCount")),
                selected=selected,
                completed=completed,
                failed=failed,
                undone=_as_int(item.get("undoneAssessmentCount")),
            )
        )
    for category, local_counts in local.items():
        if category in seen:
            continue
        gaps.append(
            CategoryGap(
                category=category,
                required=0,
                selected=_as_int(local_counts.get("selected")),
                completed=_as_int(local_counts.get("completed")),
                failed=_as_int(local_counts.get("failed")),
                undone=_as_int(local_counts.get("pending")),
            )
        )
    return gaps


def needed_categories(
    stats: dict[str, Any] | None,
    exclude: Iterable[str] = (),
    selected_items: Iterable[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[str]:
    excluded = set(exclude)
    return [
        g.category
        for g in parse_gaps(stats, selected_items=selected_items, now=now)
        if g.needs_more and g.category not in excluded
    ]


def requirements_met(
    stats: dict[str, Any] | None,
    exclude: Iterable[str] = (),
    selected_items: Iterable[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> bool:
    gaps = parse_gaps(stats, selected_items=selected_items, now=now)
    if not gaps:
        return False
    excluded = set(exclude)
    return all(
        g.remaining_to_pass == 0 or g.category in excluded
        for g in gaps
    )


def selection_requirements_met(
    stats: dict[str, Any] | None,
    exclude: Iterable[str] = (),
    selected_items: Iterable[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> bool:
    gaps = parse_gaps(stats, selected_items=selected_items, now=now)
    if not gaps:
        return False
    excluded = set(exclude)
    return all(
        g.remaining_to_select == 0 or g.category in excluded
        for g in gaps
    )


def gaps_payload(
    stats: dict[str, Any] | None,
    selected_items: Iterable[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    return [
        {
            **gap.__dict__,
            "valid_selected": gap.valid_selected,
            "remaining_to_select": gap.remaining_to_select,
            "pending": gap.pending,
            "remaining_to_pass": gap.remaining_to_pass,
        }
        for gap in parse_gaps(stats, selected_items=selected_items, now=now)
    ]


def prefer_sort_key(category: str, prefer: list[str]) -> tuple[int, str]:
    try:
        return prefer.index(category), category
    except ValueError:
        return len(prefer), category


def _as_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except Exception:
        return 0
