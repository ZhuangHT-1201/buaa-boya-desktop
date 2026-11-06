from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path

from autoboya.cache import CourseCache
from autoboya.exceptions import CaptchaRequired, LoginError
from autoboya.logging import configure_logging, log_event, mask_username
from autoboya.models import ActionResult, AutomationDecision, BoyaCourse, UserRecord
from autoboya.rules import (
    has_autonomous_sign,
    in_window,
    is_auto_select_candidate,
    parse_dt,
    sign_window_for,
)
from autoboya.scheduler import (
    AutomationRunner,
    is_hangzhou_course,
    select_failure_attempts,
    user_has_selected,
)
from autoboya.storage import AutoBoyaStore

from .account_health import (
    STATUS_AUTH_REQUIRED,
    account_health,
    load_account_health,
    mark_auth_error,
    mark_auth_ok,
    mark_auth_required,
)
from .config import (
    LOG_FILE,
    REFRESH_REQUEST_FILE,
    RUN_PID_FILE,
    STOP_FILE,
    KitConfig,
    load_config,
)
from .gaps import (
    gaps_payload,
    needed_categories,
    prefer_sort_key,
    requirements_met,
    selection_requirements_met,
)
from .notify import notify_auth_required
from .selections import (
    ORIGIN_MACHINE,
    ORIGIN_MANUAL,
    load_selection_origins,
    mark_machine_selection,
    origin_for,
    reconcile_selection_origins,
)
from .service import cleanup_captcha_files

logger = logging.getLogger(__name__)


class ReauthenticationRequired(RuntimeError):
    """The account needs an interactive sign-in before network work can continue."""


class GapAwareRunner(AutomationRunner):
    """AutoBoya 自动化 + 按统计缺口过滤选课。"""

    def __init__(self, store: AutoBoyaStore, kit: KitConfig) -> None:
        super().__init__(store)
        self.kit = kit

    def enabled_users(self) -> list[UserRecord]:
        users = [u for u in self.store.user_records() if u.enabled]
        if self.kit.username:
            users = [u for u in users if u.username == self.kit.username]
        return users

    def run_forever(self) -> None:
        self.store.init()
        cleanup_captcha_files(self.store)
        configure_logging(self.store, console=False)
        _attach_kit_file_logger(self.store.path(LOG_FILE))
        self.store.path(RUN_PID_FILE).parent.mkdir(parents=True, exist_ok=True)
        self.store.path(RUN_PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
        stop = self.store.path(STOP_FILE)
        if stop.exists():
            stop.unlink()
        refresh_request = self.store.path(REFRESH_REQUEST_FILE)
        if refresh_request.exists():
            refresh_request.unlink()
        last_refresh = 0.0
        try:
            from .config import DEFAULT_CONFIG_PATH

            config_mtime = DEFAULT_CONFIG_PATH.stat().st_mtime
        except OSError:
            config_mtime = 0.0
        user_fingerprint = _user_fingerprint(self.store)
        try:
            while not stop.exists():
                now = time.time()
                try:
                    try:
                        from .config import DEFAULT_CONFIG_PATH

                        current_mtime = DEFAULT_CONFIG_PATH.stat().st_mtime
                        if current_mtime != config_mtime:
                            self.kit = load_config()
                            config_mtime = current_mtime
                            log_event(logger, logging.INFO, "settings reloaded from config")
                    except OSError:
                        pass
                    current_users = _user_fingerprint(self.store)
                    if current_users != user_fingerprint:
                        try:
                            self.refresh_once()
                        except Exception as exc:
                            log_event(
                                logger,
                                logging.ERROR,
                                "cache refresh failed after account change",
                                error=exc,
                            )
                        last_refresh = now
                        user_fingerprint = current_users
                        refresh_request.unlink(missing_ok=True)
                        log_event(logger, logging.INFO, "account list changed; caches refreshed")
                    requested_refresh = refresh_request.exists()
                    if requested_refresh:
                        try:
                            self.refresh_once()
                            last_refresh = now
                            log_event(
                                logger,
                                logging.INFO,
                                "manual cache refresh completed",
                            )
                        except Exception as exc:
                            log_event(
                                logger,
                                logging.ERROR,
                                "manual cache refresh failed",
                                error=exc,
                            )
                        finally:
                            refresh_request.unlink(missing_ok=True)
                    if not requested_refresh and now - last_refresh >= self.kit.refresh_seconds:
                        try:
                            self.refresh_once()
                        except Exception as exc:
                            log_event(
                                logger,
                                logging.ERROR,
                                "periodic cache refresh failed",
                                error=exc,
                            )
                        last_refresh = now
                        refresh_request.unlink(missing_ok=True)
                    decisions = self.scan_once()
                    self.log_heartbeat(decisions)
                    self.execute_decisions(decisions)
                except Exception as exc:
                    log_event(logger, logging.ERROR, "boya_kit loop failed", error=exc)
                _sleep_and_watch_stop(
                    stop,
                    refresh_request,
                    max(5, self.kit.poll_seconds),
                )
        finally:
            pid = self.store.path(RUN_PID_FILE)
            if pid.exists():
                pid.unlink()

    def request_stop(self) -> None:
        self.store.init()
        self.store.path(STOP_FILE).write_text(datetime.now().isoformat(), encoding="utf-8")

    def refresh_once(self) -> None:
        users = self.enabled_users()
        if not users:
            return
        import random

        health = load_account_health(self.store)
        pool_candidates = [
            user
            for user in users
            if health.get(user.username, {}).get("status") != STATUS_AUTH_REQUIRED
        ]
        random.shuffle(pool_candidates)
        courses_refreshed = False
        for pool_user in pool_candidates:
            try:
                _config, courses = self._with_reauth(
                    pool_user.username,
                    lambda client: (client.get_all_config(), client.query_courses()),
                    retry_attempts=3,
                )
            except ReauthenticationRequired:
                continue
            except Exception as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "course pool refresh failed for account; trying another account",
                    user=mask_username(pool_user.username),
                    error=exc,
                )
                continue
            self.cache.save_courses(courses)
            courses_refreshed = True
            break
        if not courses_refreshed:
            log_event(
                logger,
                logging.WARNING,
                "course pool could not be refreshed; using cached catalog",
            )

        for user in users:
            if account_health(self.store, user.username).get("status") == STATUS_AUTH_REQUIRED:
                continue
            try:
                selected, statistics = self._with_reauth(
                    user.username,
                    lambda client: self._query_user_status(client),
                    retry_attempts=3,
                )
            except ReauthenticationRequired:
                continue
            except Exception as exc:
                mark_auth_error(self.store, user.username, str(exc))
                log_event(
                    logger,
                    logging.ERROR,
                    "account cache refresh failed",
                    user=mask_username(user.username),
                    error=exc,
                )
                continue
            self.cache.save_selected(user.username, selected)
            self.cache.save_statistics(user.username, statistics)
        reconcile_selection_origins(
            self.store,
            self._selected_by_user(self.cache.load_selected()),
        )

    def _query_user_status(self, client):
        from autoboya.scheduler import current_semester_window

        statistics = client.query_statistics()
        info = statistics.get("semesterInfo") if isinstance(statistics, dict) else None
        if isinstance(info, dict):
            start = info.get("semesterStartDate")
            end = info.get("semesterEndDate")
        else:
            start = end = None
        if not start or not end:
            start, end = current_semester_window(client.get_all_config())
        selected = client.query_chosen_courses(start, end)
        return selected, statistics

    def scan_once(self) -> list[AutomationDecision]:
        now = datetime.now()
        courses = self.cache.parsed_courses()
        selected_by_user = self._selected_by_user(self.cache.load_selected())
        users = self.enabled_users()
        stats_all = self.cache.load_statistics()
        origins = load_selection_origins(self.store)

        decisions: list[AutomationDecision] = []

        for user in users:
            if (
                account_health(self.store, user.username).get("status")
                == STATUS_AUTH_REQUIRED
            ):
                continue
            stats = stats_all.get(user.username, {}) if isinstance(stats_all, dict) else {}
            selected = selected_by_user.get(user.username, [])
            pending = [c for c in selected if _is_pending(c, now)]
            machine_pending = [
                course
                for course in pending
                if origin_for(origins, user.username, course.id) == ORIGIN_MACHINE
            ]

            # 签到 / 签退：不依赖缺口
            for course in selected:
                if not has_autonomous_sign(course):
                    continue
                if sign_window_for(course, 1, now):
                    decisions.append(AutomationDecision(action="sign", course_id=course.id, username=user.username))
                if sign_window_for(course, 2, now):
                    decisions.append(AutomationDecision(action="signout", course_id=course.id, username=user.username))

            if selection_requirements_met(
                stats,
                exclude=self.kit.exclude_categories,
            ):
                log_event(
                    logger,
                    logging.INFO,
                    "all requirement slots selected; skip auto-select",
                    user=mask_username(user.username),
                )
                continue

            if len(machine_pending) >= self.kit.max_pending_selected:
                log_event(
                    logger,
                    logging.INFO,
                    "machine-selected pending cap reached; skip auto-select",
                    user=mask_username(user.username),
                    pending=len(machine_pending),
                    cap=self.kit.max_pending_selected,
                )
                continue

            needed = needed_categories(stats, exclude=self.kit.exclude_categories)
            if self.kit.only_gap_categories and not needed:
                log_event(
                    logger,
                    logging.INFO,
                    "no unfilled category slots; skip auto-select",
                    user=mask_username(user.username),
                )
                continue

            candidates = [
                course
                for course in courses
                if is_machine_selectable_course(course, now)
                and course.category not in self.kit.exclude_categories
                and (not self.kit.only_gap_categories or course.category in needed)
                and not user_has_selected(selected_by_user, user.username, course.id)
            ]
            candidates.sort(
                key=lambda c: (
                    prefer_sort_key(c.category, self.kit.prefer_categories),
                    c.select_end or "",
                    c.id,
                )
            )
            remaining_slots = max(
                0,
                self.kit.max_pending_selected - len(machine_pending),
            )
            for course in candidates[:remaining_slots]:
                decisions.append(
                    AutomationDecision(action="select", course_id=course.id, username=user.username)
                )

        return decisions

    def execute_decisions(self, decisions: list[AutomationDecision]) -> list[ActionResult]:
        if self.kit.dry_run:
            for decision in decisions:
                log_event(
                    logger,
                    logging.INFO,
                    "dry-run decision",
                    action=decision.action,
                    course_id=decision.course_id,
                    user=mask_username(decision.username) if decision.username else None,
                )
            return []

        # 父类 select 会对所有用户尝试；这里改成只对 decision.username 执行
        results: list[ActionResult] = []
        now = datetime.now()
        selected_raw = self.cache.load_selected()
        selected_by_user = self._selected_by_user(selected_raw)
        courses_by_id = {course.id: course for course in self.cache.parsed_courses()}
        from autoboya.config import ACTION_JOURNAL_FILE
        from autoboya.scheduler import SELECT_FAILURE_LIMIT, journal_key, select_failure_key, record_select_failure

        journal = self.store.load_json(ACTION_JOURNAL_FILE, {})
        users_by_name = {u.username: u for u in self.enabled_users()}

        for decision in decisions:
            if decision.action == "select":
                username = decision.username
                if not username or username not in users_by_name:
                    continue
                user = users_by_name[username]
                course = courses_by_id.get(decision.course_id)
                if course is None:
                    continue
                if not is_machine_selectable_course(course, now):
                    log_event(
                        logger,
                        logging.WARNING,
                        "blocked non-autonomous or ineligible auto-select",
                        user=mask_username(username),
                        course_id=decision.course_id,
                        category=course.category,
                    )
                    continue
                if user_has_selected(selected_by_user, username, decision.course_id):
                    continue
                key = journal_key(username, "select", decision.course_id)
                if journal.get(key):
                    continue
                if select_failure_attempts(journal, username, decision.course_id) >= SELECT_FAILURE_LIMIT:
                    continue
                result = self._select_for_user(user, decision.course_id)
                results.append(result)
                if result.ok:
                    journal[key] = result.message
                    journal.pop(select_failure_key(username, decision.course_id), None)
                    mark_machine_selection(
                        self.store,
                        username,
                        course,
                    )
                elif result.terminal:
                    attempts = record_select_failure(journal, username, decision.course_id, result.message)
                    log_event(
                        logger,
                        logging.WARNING,
                        "auto select failed",
                        user=mask_username(username),
                        course_id=decision.course_id,
                        attempts=attempts,
                        reason=result.message,
                    )
                continue

            username = decision.username
            if not username:
                continue
            key = journal_key(username, decision.action, decision.course_id)
            if journal.get(key):
                continue
            course = next((item for item in selected_by_user.get(username, []) if item.id == decision.course_id), None)
            if course is None or not has_autonomous_sign(course):
                continue
            result = self._sign_for_user(username, course, decision.action)
            results.append(result)
            if result.ok:
                journal[key] = result.message

        self.store.save_json(ACTION_JOURNAL_FILE, journal)
        return results

    def _with_reauth(self, username: str, operation, retry_attempts: int = 1):
        current_health = account_health(self.store, username)
        if current_health.get("status") == STATUS_AUTH_REQUIRED:
            raise ReauthenticationRequired(
                current_health.get("error") or "account requires interactive login"
            )
        for attempt in range(1, retry_attempts + 1):
            try:
                result = super()._with_reauth(username, operation)
            except CaptchaRequired as exc:
                detail = str(exc) or "CAPTCHA required"
                capture_path = getattr(
                    getattr(exc, "challenge", None),
                    "image_path",
                    None,
                )
                mark_auth_required(
                    self.store,
                    username,
                    detail,
                    capture_path,
                )
                notify_auth_required(username)
                raise ReauthenticationRequired(detail) from exc
            except LoginError as exc:
                detail = str(exc) or "unified authentication login failed"
                mark_auth_required(self.store, username, detail)
                notify_auth_required(username)
                raise ReauthenticationRequired(detail) from exc
            except Exception as exc:
                if attempt >= retry_attempts:
                    mark_auth_error(self.store, username, str(exc))
                    raise
                log_event(
                    logger,
                    logging.WARNING,
                    "BoyA request failed; retrying",
                    user=mask_username(username),
                    attempt=attempt,
                    error=exc,
                )
                time.sleep(attempt * 2)
            else:
                mark_auth_ok(self.store, username)
                return result


def _attach_kit_file_logger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    target = str(path.resolve())
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler):
            existing = getattr(handler, "baseFilename", None)
            if existing and str(Path(existing).resolve()) == target:
                return
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(handler)


def is_machine_selectable_course(course: BoyaCourse, now: datetime) -> bool:
    """Machine selection is strictly limited to currently selectable check-in courses."""
    return (
        not is_hangzhou_course(course)
        and has_autonomous_sign(course)
        and is_auto_select_candidate(
            course,
            now,
            ignore_selected=True,
        )
    )


def _is_pending(course: BoyaCourse, now: datetime) -> bool:
    """已选且课程尚未结束，算作占用名额。"""
    from autoboya.rules import parse_dt

    end = parse_dt(course.course_end)
    if end is None:
        return True
    return end >= now


def _sleep_and_watch_stop(
    stop: Path,
    refresh_request: Path,
    seconds: int,
) -> None:
    """Keep the worker responsive to the GUI stop request."""
    deadline = time.monotonic() + seconds
    while (
        not stop.exists()
        and not refresh_request.exists()
        and time.monotonic() < deadline
    ):
        time.sleep(min(1.0, max(0.05, deadline - time.monotonic())))


def _user_fingerprint(store: AutoBoyaStore) -> tuple[tuple[str, bool, str], ...]:
    return tuple(
        sorted((user.username, user.enabled, user.campus) for user in store.user_records())
    )


def status_payload(store: AutoBoyaStore, kit: KitConfig) -> dict:
    cache = CourseCache(store)
    stats_all = cache.load_statistics()
    selected_raw = cache.load_selected()
    origins = load_selection_origins(store)
    courses = cache.parsed_courses()
    users = [u for u in store.user_records() if u.enabled]
    if kit.username:
        users = [u for u in users if u.username == kit.username]

    from autoboya.bykc import parse_course

    out_users = []
    for user in users:
        health = account_health(store, user.username)
        session_path = store.path(f"sessions/{user.username}.json")
        auth_status = health.get("status") or (
            "logged_in" if session_path.exists() else "login_required"
        )
        stats = stats_all.get(user.username, {}) if isinstance(stats_all, dict) else {}
        selected_items = selected_raw.get(user.username, []) if isinstance(selected_raw, dict) else []
        selected_pairs = (
            [(item, parse_course(item)) for item in selected_items]
            if isinstance(selected_items, list)
            else []
        )
        selected = [course for _item, course in selected_pairs]
        selected_rows = []
        now = datetime.now()
        for item, course in selected_pairs:
            assessment_status = _course_assessment_status(item, course, now)
            selected_rows.append(
                {
                    "id": course.id,
                    "name": course.name,
                    "category": course.category,
                    "sign_method": course.sign_method,
                    "autonomous_sign": has_autonomous_sign(course),
                    "origin": origin_for(origins, user.username, course.id),
                    "pending": _is_pending(course, now),
                    "assessment_status": assessment_status,
                    "pass": item.get("pass"),
                    "score": item.get("score"),
                    "selected_at": item.get("selectDate"),
                    "start": course.course_start,
                    "end": course.course_end,
                    "location": course.location,
                }
            )
        gaps = gaps_payload(stats)
        needed = needed_categories(stats, exclude=kit.exclude_categories)
        selected_ids = {course.id for course in selected}
        candidate_status = _candidate_diagnostics(
            courses,
            selected_ids,
            needed,
            now,
        )
        out_users.append(
            {
                "username": user.username,
                "campus": user.campus,
                "auth_status": auth_status,
                "auth_error": health.get("error"),
                "captcha_path": health.get("captcha_path"),
                "last_auth_success_at": health.get("last_success_at"),
                "requirements_met": requirements_met(stats, exclude=kit.exclude_categories),
                "needed_categories": needed,
                "gaps": gaps,
                "valid_count": stats.get("validCount") if isinstance(stats, dict) else None,
                "selected_count": len(selected),
                "manual_selected_count": sum(
                    1 for row in selected_rows if row["origin"] == ORIGIN_MANUAL
                ),
                "machine_selected_count": sum(
                    1 for row in selected_rows if row["origin"] == ORIGIN_MACHINE
                ),
                "autonomous_selected_count": sum(
                    1 for row in selected_rows if row["autonomous_sign"]
                ),
                "regular_selected_count": sum(
                    1 for row in selected_rows if not row["autonomous_sign"]
                ),
                "machine_pending_count": sum(
                    1
                    for row in selected_rows
                    if row["origin"] == ORIGIN_MACHINE and row["pending"]
                ),
                "passed_selected_count": sum(
                    1
                    for row in selected_rows
                    if row["assessment_status"] == "passed"
                ),
                "failed_selected_count": sum(
                    1
                    for row in selected_rows
                    if row["assessment_status"] == "not_passed"
                ),
                "pending_assessment_count": sum(
                    1
                    for row in selected_rows
                    if row["assessment_status"] in {"pending", "pending_result"}
                ),
                **candidate_status,
                "selected": selected_rows,
            }
        )
    def modified_at(relative: str) -> str | None:
        path = store.path(relative)
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except OSError:
            return None

    return {
        "users": out_users,
        "dry_run": kit.dry_run,
        "only_gap_categories": kit.only_gap_categories,
        "status_updated_at": modified_at("cache/statistics.json"),
        "courses_updated_at": modified_at("cache/courses.json"),
    }


def _course_assessment_status(
    item: dict,
    course: BoyaCourse,
    now: datetime,
) -> str:
    pass_value = item.get("pass")
    if pass_value is True or str(pass_value) == "1":
        return "passed"
    end = parse_dt(course.course_end)
    finished = end is not None and end < now
    if pass_value is False or str(pass_value) == "0":
        return "not_passed" if finished else "pending"
    return "pending_result" if finished else "pending"


def _candidate_diagnostics(
    courses: list[BoyaCourse],
    selected_ids: set[int],
    needed_categories: list[str],
    now: datetime,
) -> dict[str, object]:
    needed = set(needed_categories)
    relevant = [
        course
        for course in courses
        if course.id not in selected_ids
        and not is_hangzhou_course(course)
        and has_autonomous_sign(course)
        and course.category in needed
    ]
    open_courses = [
        course
        for course in relevant
        if in_window(course.select_start, course.select_end, now)
    ]
    full_open = [
        course
        for course in open_courses
        if course.current_count is not None
        and course.max_count is not None
        and course.current_count >= course.max_count
    ]
    available = [
        course
        for course in open_courses
        if course not in full_open
    ]
    future: list[tuple[datetime, BoyaCourse]] = []
    for course in relevant:
        starts = parse_dt(course.select_start)
        if starts is None or starts <= now:
            continue
        if course.current_count is not None and course.max_count is not None:
            if course.current_count >= course.max_count:
                continue
        future.append((starts, course))
    next_open = min(future, key=lambda item: item[0])[0] if future else None
    upcoming = []
    for starts, course in sorted(future, key=lambda item: item[0])[:10]:
        campus = (
            " / ".join(str(value) for value in course.campus)
            if isinstance(course.campus, list)
            else str(course.campus or "")
        )
        remaining = (
            max(0, course.max_count - course.current_count)
            if course.current_count is not None and course.max_count is not None
            else None
        )
        upcoming.append(
            {
                "id": course.id,
                "name": course.name,
                "category": course.category,
                "campus": campus,
                "select_start": course.select_start,
                "select_end": course.select_end,
                "course_start": course.course_start,
                "remaining": remaining,
            }
        )
    return {
        "open_needed_candidate_count": len(available),
        "full_needed_candidate_count": len(full_open),
        "next_needed_candidate_at": (
            next_open.isoformat(sep=" ", timespec="minutes")
            if next_open
            else None
        ),
        "upcoming_candidates": upcoming,
    }
