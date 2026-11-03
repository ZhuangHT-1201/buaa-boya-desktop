from datetime import datetime, timedelta

from autoboya.models import ActionResult, AutomationDecision, BoyaCourse, UserRecord
from autoboya.cache import CourseCache
from autoboya.storage import AutoBoyaStore

from boya_kit.config import KitConfig
from boya_kit.runner import is_machine_selectable_course
from boya_kit.runner import GapAwareRunner
from boya_kit.selections import (
    ORIGIN_MACHINE,
    ORIGIN_MANUAL,
    load_selection_origins,
    mark_machine_selection,
    origin_for,
    reconcile_selection_origins,
)


def make_course(
    course_id: int,
    *,
    autonomous: bool,
    category: str = "德育",
    current_count: int = 0,
    max_count: int = 20,
) -> BoyaCourse:
    now = datetime.now()
    return BoyaCourse(
        id=course_id,
        name=f"Course {course_id}",
        category=category,
        sign_config=(
            {
                "signPointList": [
                    {"lat": "39.980", "lng": "116.350", "radius": 8}
                ],
                "signStartDate": (now - timedelta(minutes=5)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "signEndDate": (now + timedelta(minutes=5)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "signOutStartDate": (now - timedelta(minutes=5)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "signOutEndDate": (now + timedelta(minutes=5)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            }
            if autonomous
            else {}
        ),
        select_start=(now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        select_end=(now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        current_count=current_count,
        max_count=max_count,
    )


def test_machine_selection_accepts_only_autonomous_courses() -> None:
    now = datetime.now()
    assert is_machine_selectable_course(
        make_course(1, autonomous=True),
        now,
    )
    assert not is_machine_selectable_course(
        make_course(2, autonomous=False),
        now,
    )


def test_machine_selection_rejects_excluded_full_or_closed_courses() -> None:
    now = datetime.now()
    assert not is_machine_selectable_course(
        make_course(1, autonomous=True, category="其他方面"),
        now,
    )
    assert not is_machine_selectable_course(
        make_course(2, autonomous=True, current_count=20, max_count=20),
        now,
    )
    closed = make_course(3, autonomous=True)
    closed.select_end = (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    assert not is_machine_selectable_course(closed, now)


def test_existing_courses_are_manual_and_machine_provenance_is_persistent(
    tmp_path,
) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    manual = make_course(10, autonomous=False)
    autonomous = make_course(11, autonomous=True)

    origins = reconcile_selection_origins(
        store,
        {"student": [manual, autonomous]},
    )
    assert origin_for(origins, "student", manual.id) == ORIGIN_MANUAL
    assert origin_for(origins, "student", autonomous.id) == ORIGIN_MANUAL

    mark_machine_selection(store, "student", autonomous)
    origins = reconcile_selection_origins(
        store,
        {"student": [manual, autonomous]},
    )
    assert origin_for(origins, "student", autonomous.id) == ORIGIN_MACHINE
    assert load_selection_origins(store)["student"]["11"]["sign_type"] == "autonomous"

    origins = reconcile_selection_origins(store, {"student": [manual]})
    assert "11" not in origins["student"]


def test_execution_rechecks_and_blocks_regular_signin(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    store.upsert_user(
        UserRecord(username="student", enabled=True, campus="北京")
    )
    regular = make_course(20, autonomous=False)
    regular.campus = "北京"
    autonomous = make_course(21, autonomous=True)
    autonomous.campus = "北京"
    cache = CourseCache(store)
    cache.save_courses([regular, autonomous])
    cache.save_selected("student", [])

    runner = GapAwareRunner(store, KitConfig(username="student", dry_run=False))
    selected_ids: list[int] = []

    def fake_select(user: UserRecord, course_id: int) -> ActionResult:
        selected_ids.append(course_id)
        return ActionResult(user.username, "select", course_id, True, "selected")

    runner._select_for_user = fake_select  # type: ignore[method-assign]
    runner.execute_decisions(
        [
            AutomationDecision("select", regular.id, "student"),
            AutomationDecision("select", autonomous.id, "student"),
        ]
    )

    assert selected_ids == [autonomous.id]
    stored = load_selection_origins(store)
    assert "20" not in stored["student"]
    assert stored["student"]["21"]["origin"] == ORIGIN_MACHINE


def test_attendance_includes_manual_and_machine_autonomous_courses(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    store.upsert_user(
        UserRecord(username="student", enabled=True, campus="北京")
    )
    manual_autonomous = make_course(30, autonomous=True)
    manual_autonomous.campus = "北京"
    machine_autonomous = make_course(31, autonomous=True)
    machine_autonomous.campus = "北京"
    manual_regular = make_course(32, autonomous=False)
    manual_regular.campus = "北京"
    cache = CourseCache(store)
    cache.save_courses([])
    cache.save_selected(
        "student",
        [manual_autonomous, machine_autonomous, manual_regular],
    )
    reconcile_selection_origins(
        store,
        {"student": [manual_autonomous, machine_autonomous, manual_regular]},
    )
    mark_machine_selection(store, "student", machine_autonomous)

    runner = GapAwareRunner(store, KitConfig(username="student", dry_run=True))
    decisions = runner.scan_once()
    attendance_pairs = {
        (decision.action, decision.course_id)
        for decision in decisions
        if decision.action in {"sign", "signout"}
    }

    assert attendance_pairs == {
        ("sign", manual_autonomous.id),
        ("signout", manual_autonomous.id),
        ("sign", machine_autonomous.id),
        ("signout", machine_autonomous.id),
    }
    assert not any(
        decision.course_id == manual_regular.id for decision in decisions
    )
