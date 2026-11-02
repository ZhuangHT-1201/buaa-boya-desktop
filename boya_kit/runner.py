from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path

from autoboya.cache import CourseCache
from autoboya.logging import configure_logging, log_event, mask_username
from autoboya.models import ActionResult, AutomationDecision, BoyaCourse, UserRecord
from autoboya.rules import has_autonomous_sign, is_auto_select_candidate, sign_window_for
from autoboya.scheduler import (
    AutomationRunner,
    course_matches_user_campus,
    select_failure_attempts,
    user_has_selected,
)
from autoboya.storage import AutoBoyaStore

from .config import LOG_FILE, RUN_PID_FILE, STOP_FILE, KitConfig, load_config
from .gaps import needed_categories, parse_gaps, prefer_sort_key, requirements_met

logger = logging.getLogger(__name__)


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
        configure_logging(self.store, console=False)
        _attach_kit_file_logger(self.store.path(LOG_FILE))
        self.store.path(RUN_PID_FILE).parent.mkdir(parents=True, exist_ok=True)
        self.store.path(RUN_PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
        stop = self.store.path(STOP_FILE)
        if stop.exists():
            stop.unlink()
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
                        self.refresh_once()
                        last_refresh = now
                        user_fingerprint = current_users
                        log_event(logger, logging.INFO, "account list changed; caches refreshed")
                    if now - last_refresh >= self.kit.refresh_seconds:
                        self.refresh_once()
                        last_refresh = now
                    decisions = self.scan_once()
                    self.log_heartbeat(decisions)
                    self.execute_decisions(decisions)
                except Exception as exc:
                    log_event(logger, logging.ERROR, "boya_kit loop failed", error=exc)
                _sleep_and_watch_stop(stop, max(5, self.kit.poll_seconds))
        finally:
            pid = self.store.path(RUN_PID_FILE)
            if pid.exists():
                pid.unlink()


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

    def request_stop(self) -> None:
        self.store.init()
        self.store.path(STOP_FILE).write_text(datetime.now().isoformat(), encoding="utf-8")

    def refresh_once(self) -> None:
        # 复用父类逻辑，但仅针对启用/指定用户
        users = self.enabled_users()
        if not users:
            return
        # 临时把 store 用户过滤交给父类：直接调用父类 refresh，再靠 execute 过滤
        # 父类会刷新全部 enabled users；这里手动做限定版
        import random

        from autoboya.scheduler import current_semester_window

        pool_user = random.choice(users)
        config, courses = self._with_reauth(
            pool_user.username,
            lambda client: (client.get_all_config(), client.query_courses()),
        )
        self.cache.save_courses(courses)
        start, end = current_semester_window(config)
        for user in users:
            selected, statistics = self._with_reauth(
                user.username,
                lambda client: (client.query_chosen_courses(start, end), client.query_statistics()),
            )
            self.cache.save_selected(user.username, selected)
            self.cache.save_statistics(user.username, statistics)

    def scan_once(self) -> list[AutomationDecision]:
        now = datetime.now()
        courses = self.cache.parsed_courses()
        selected_by_user = self._selected_by_user(self.cache.load_selected())
        users = self.enabled_users()
        stats_all = self.cache.load_statistics()

        decisions: list[AutomationDecision] = []

        for user in users:
            stats = stats_all.get(user.username, {}) if isinstance(stats_all, dict) else {}
            selected = selected_by_user.get(user.username, [])
            pending = [c for c in selected if _is_pending(c, now)]

            # 签到 / 签退：不依赖缺口
            for course in selected:
                if not has_autonomous_sign(course):
                    continue
                if sign_window_for(course, 1, now):
                    decisions.append(AutomationDecision(action="sign", course_id=course.id, username=user.username))
                if sign_window_for(course, 2, now):
                    decisions.append(AutomationDecision(action="signout", course_id=course.id, username=user.username))

            if requirements_met(stats, exclude=self.kit.exclude_categories):
                log_event(
                    logger,
                    logging.INFO,
                    "requirements met; skip auto-select",
                    user=mask_username(user.username),
                )
                continue

            if len(pending) >= self.kit.max_pending_selected:
                log_event(
                    logger,
                    logging.INFO,
                    "pending selected cap reached; skip auto-select",
                    user=mask_username(user.username),
                    pending=len(pending),
                    cap=self.kit.max_pending_selected,
                )
                continue

            needed = needed_categories(stats, exclude=self.kit.exclude_categories)
            if self.kit.only_gap_categories and not needed:
                # 统计还没刷出来时，回退到「非排除类别」
                needed = []

            candidates = [
                course
                for course in courses
                if is_auto_select_candidate(course, now, ignore_selected=True)
                and course_matches_user_campus(course, user)
                and course.category not in self.kit.exclude_categories
                and (not self.kit.only_gap_categories or not needed or course.category in needed)
                and not user_has_selected(selected_by_user, user.username, course.id)
            ]
            candidates.sort(
                key=lambda c: (
                    prefer_sort_key(c.category, self.kit.prefer_categories),
                    c.select_end or "",
                    c.id,
                )
            )
            remaining_slots = max(0, self.kit.max_pending_selected - len(pending))
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
                if course and not course_matches_user_campus(course, user):
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
            result = self._sign_for_user(username, course, decision.action)
            results.append(result)
            if result.ok:
                journal[key] = result.message

        self.store.save_json(ACTION_JOURNAL_FILE, journal)
        return results


def _is_pending(course: BoyaCourse, now: datetime) -> bool:
    """已选且课程尚未结束，算作占用名额。"""
    from autoboya.rules import parse_dt

    end = parse_dt(course.course_end)
    if end is None:
        return True
    return end >= now


def _sleep_and_watch_stop(stop: Path, seconds: int) -> None:
    """Keep the worker responsive to the GUI stop request."""
    deadline = time.monotonic() + seconds
    while not stop.exists() and time.monotonic() < deadline:
        time.sleep(min(1.0, max(0.05, deadline - time.monotonic())))


def _user_fingerprint(store: AutoBoyaStore) -> tuple[tuple[str, bool, str], ...]:
    return tuple(
        sorted((user.username, user.enabled, user.campus) for user in store.user_records())
    )


def status_payload(store: AutoBoyaStore, kit: KitConfig) -> dict:
    cache = CourseCache(store)
    stats_all = cache.load_statistics()
    selected_raw = cache.load_selected()
    users = [u for u in store.user_records() if u.enabled]
    if kit.username:
        users = [u for u in users if u.username == kit.username]

    from autoboya.bykc import parse_course

    out_users = []
    for user in users:
        stats = stats_all.get(user.username, {}) if isinstance(stats_all, dict) else {}
        selected_items = selected_raw.get(user.username, []) if isinstance(selected_raw, dict) else []
        selected = [parse_course(item) for item in selected_items] if isinstance(selected_items, list) else []
        gaps = [g.__dict__ for g in parse_gaps(stats)]
        needed = needed_categories(stats, exclude=kit.exclude_categories)
        out_users.append(
            {
                "username": user.username,
                "campus": user.campus,
                "requirements_met": requirements_met(stats, exclude=kit.exclude_categories),
                "needed_categories": needed,
                "gaps": gaps,
                "valid_count": stats.get("validCount") if isinstance(stats, dict) else None,
                "selected_count": len(selected),
                "selected": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "category": c.category,
                        "sign_method": c.sign_method,
                        "start": c.course_start,
                        "end": c.course_end,
                        "location": c.location,
                    }
                    for c in selected
                ],
            }
        )
    return {"users": out_users, "dry_run": kit.dry_run, "only_gap_categories": kit.only_gap_categories}
