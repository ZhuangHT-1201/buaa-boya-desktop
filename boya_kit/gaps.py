from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


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
        return max(0, self.required - self.selected)

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


def parse_gaps(stats: dict[str, Any] | None) -> list[CategoryGap]:
    if not isinstance(stats, dict) or not stats:
        return []
    gaps: list[CategoryGap] = []
    for category, item in iter_stat_rows(stats):
        gaps.append(
            CategoryGap(
                category=category,
                required=_as_int(item.get("assessmentCount")),
                selected=_as_int(item.get("selectAssessmentCount")),
                completed=_as_int(item.get("completeAssessmentCount")),
                failed=_as_int(item.get("failAssessmentCount")),
                undone=_as_int(item.get("undoneAssessmentCount")),
            )
        )
    return gaps


def needed_categories(stats: dict[str, Any] | None, exclude: Iterable[str] = ()) -> list[str]:
    excluded = set(exclude)
    return [g.category for g in parse_gaps(stats) if g.needs_more and g.category not in excluded]


def requirements_met(stats: dict[str, Any] | None, exclude: Iterable[str] = ()) -> bool:
    gaps = parse_gaps(stats)
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
) -> bool:
    gaps = parse_gaps(stats)
    if not gaps:
        return False
    excluded = set(exclude)
    return all(
        g.remaining_to_select == 0 or g.category in excluded
        for g in gaps
    )


def gaps_payload(stats: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [
        {
            **gap.__dict__,
            "remaining_to_select": gap.remaining_to_select,
            "pending": gap.pending,
            "remaining_to_pass": gap.remaining_to_pass,
        }
        for gap in parse_gaps(stats)
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
