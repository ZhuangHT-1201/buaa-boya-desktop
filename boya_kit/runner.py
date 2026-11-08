from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx

from autoboya.cache import CourseCache
from autoboya.exceptions import (
    AlreadySelected,
    BoyaApiError,
    CaptchaRequired,
    CourseFull,
    CourseNotOpen,
    LoginError,
    SelectionLimitReached,
    SessionExpired,
)
from autoboya.logging import configure_logging, log_event, mask_username
from autoboya.models import ActionResult, AutomationDecision, BoyaCourse, UserRecord
from autoboya.rules import (
    has_autonomous_sign,
    in_window,
    is_auto_select_candidate,
    parse_dt,
    random_point_in_radius,
    sign_window_for,
)
from autoboya.scheduler import (
    AutomationRunner,
    is_hangzhou_course,
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
    parse_gaps,
    prefer_sort_key,
    requirements_met,
)
from .captcha_ocr import captcha_ocr_available
from .locking import LockUnavailable, file_lock
from .notify import notify_auth_required
from .selections import (
    ORIGIN_MACHINE,
    ORIGIN_MANUAL,
    load_selection_origins,
    mark_machine_selection,
    origin_for,
    reconcile_selection_origins,
)
from .service import (
    AccountLoginBusy,
    cleanup_captcha_files,
    login_account,
    password_for_account,
)

logger = logging.getLogger(__name__)

# Retry OCR/password re-login quickly so check-in is not blocked after session loss.
AUTO_REAUTH_RETRY_SECONDS = 45
AUTO_REAUTH_MAX_BACKOFF_SECONDS = 1800


class ReauthenticationRequired(RuntimeError):
    """The account needs an interactive sign-in before network work can continue."""


class GapAwareRunner(AutomationRunner):
    """AutoBoya 自动化 + 按统计缺口过滤选课。"""

    def __init__(self, store: AutoBoyaStore, kit: KitConfig) -> None:
        super().__init__(store)
        self.kit = kit
        self._course_catalog_fresh = False
        self._selection_ready_users: set[str] = set()

    def enabled_users(self) -> list[UserRecord]:
        users = [u for u in self.store.user_records() if u.enabled]
        if self.kit.username:
            users = [u for u in users if u.username == self.kit.username]
        return users

    def run_forever(self) -> None:
        self.store.init()
        try:
            with file_lock(
                self.store,
                "run/worker.lock",
                stale_after=0.0,
            ):
                self._run_forever_locked()
        except LockUnavailable:
            logger.warning("another Boya worker is already active")

    def _run_forever_locked(self) -> None:
        self.store.init()
        cleanup_captcha_files(self.store)
        configure_logging(self.store, console=False)
        _attach_kit_file_logger(self.store.path(LOG_FILE))
        log_event(
            logger,
            logging.INFO,
            "worker runtime ready",
            captcha_ocr=captcha_ocr_available(),
        )
        self.store.path(RUN_PID_FILE).parent.mkdir(parents=True, exist_ok=True)
        self.store.path(RUN_PID_FILE).write_text(str(os.getpid()), encoding="utf-8")
        stop = self.store.path(STOP_FILE)
        if stop.exists():
            stop.unlink()
        refresh_request = self.store.path(REFRESH_REQUEST_FILE)
        if refresh_request.exists():
            refresh_request.unlink()
        last_course_refresh = 0.0
        last_status_refresh = 0.0
        try:
            from .config import DEFAULT_CONFIG_PATH

            config_mtime = DEFAULT_CONFIG_PATH.stat().st_mtime
        except OSError:
            config_mtime = 0.0
        user_fingerprint = _user_fingerprint(self.store)
        try:
            while not stop.exists():
                now = time.time()
                course_attempted = False
                status_attempted = False
                course_seconds = max(10, self.kit.course_refresh_seconds)
                status_seconds = max(30, self.kit.status_refresh_seconds)
                scan_seconds = max(
                    5,
                    min(
                        self.kit.poll_seconds,
                        course_seconds,
                        status_seconds,
                    ),
                )
                try:
                    try:
                        from .config import DEFAULT_CONFIG_PATH

                        current_mtime = DEFAULT_CONFIG_PATH.stat().st_mtime
                        if current_mtime != config_mtime:
                            self.kit = load_config()
                            config_mtime = current_mtime
                            last_course_refresh = 0.0
                            last_status_refresh = 0.0
                            log_event(logger, logging.INFO, "settings reloaded from config")
                    except OSError:
                        pass
                    current_users = _user_fingerprint(self.store)
                    if current_users != user_fingerprint:
                        try:
                            self.refresh_once()
                        except Exception as exc:
                            self._course_catalog_fresh = False
                            self._selection_ready_users.clear()
                            log_event(
                                logger,
                                logging.ERROR,
                                "cache refresh failed after account change",
                                error=exc,
                            )
                        course_attempted = True
                        status_attempted = True
                        last_course_refresh = time.time()
                        last_status_refresh = time.time()
                        user_fingerprint = current_users
                        refresh_request.unlink(missing_ok=True)
                        log_event(logger, logging.INFO, "account list changed; caches refreshed")
                    requested_refresh = refresh_request.exists()
                    if requested_refresh:
                        try:
                            self.refresh_once()
                            course_attempted = True
                            status_attempted = True
                            last_course_refresh = time.time()
                            last_status_refresh = time.time()
                            log_event(
                                logger,
                                logging.INFO,
                                "manual cache refresh completed",
                            )
                        except Exception as exc:
                            self._course_catalog_fresh = False
                            self._selection_ready_users.clear()
                            log_event(
                                logger,
                                logging.ERROR,
                                "manual cache refresh failed",
                                error=exc,
                            )
                        finally:
                            refresh_request.unlink(missing_ok=True)
                    elif now - last_course_refresh >= course_seconds:
                        try:
                            courses_fresh = self.refresh_courses_once()
                            recovered = self._retry_stored_password_logins(
                                max_attempts=1
                            )
                            if not courses_fresh and recovered:
                                self.refresh_courses_once()
                        except Exception as exc:
                            self._course_catalog_fresh = False
                            log_event(
                                logger,
                                logging.ERROR,
                                "live course refresh failed",
                                error=exc,
                            )
                        course_attempted = True
                        last_course_refresh = time.time()
                    if not requested_refresh and now - last_status_refresh >= status_seconds:
                        try:
                            self.refresh_user_statuses_once()
                        except Exception as exc:
                            self._selection_ready_users.clear()
                            log_event(
                                logger,
                                logging.ERROR,
                                "account status refresh failed",
                                error=exc,
                            )
                        status_attempted = True
                        last_status_refresh = time.time()
                    decisions = self.scan_once(
                        allow_selection=self._course_catalog_fresh,
                        selection_usernames=self._selection_ready_users,
                    )
                    self.log_heartbeat(decisions)
                    self.execute_decisions(decisions)
                    if not requested_refresh and refresh_request.exists():
                        try:
                            if not (course_attempted and status_attempted):
                                self.refresh_once()
                                course_attempted = True
                                status_attempted = True
                            log_event(
                                logger,
                                logging.INFO,
                                "manual cache refresh satisfied by current cycle",
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
                except Exception as exc:
                    log_event(logger, logging.ERROR, "boya_kit loop failed", error=exc)
                _sleep_and_watch_stop(
                    stop,
                    refresh_request,
                    scan_seconds,
                )
        finally:
            pid = self.store.path(RUN_PID_FILE)
            if pid.exists():
                pid.unlink()

    def request_stop(self) -> None:
        self.store.init()
        self.store.path(STOP_FILE).write_text(datetime.now().isoformat(), encoding="utf-8")

    def refresh_once(self) -> bool:
        courses_fresh = self.refresh_courses_once()
        recovered = self._retry_stored_password_logins(max_attempts=1)
        if not courses_fresh and recovered:
            courses_fresh = self.refresh_courses_once()
        self.refresh_user_statuses_once()
        return courses_fresh

    def refresh_courses_once(self) -> bool:
        users = self.enabled_users()
        if not users:
            self._course_catalog_fresh = False
            return False

        health = load_account_health(self.store)
        pool_candidates = [
            user
            for user in users
            if health.get(user.username, {}).get("status") != STATUS_AUTH_REQUIRED
        ]
        pool_candidates.sort(
            key=lambda user: (
                health.get(user.username, {}).get("status") == "ok",
                str(health.get(user.username, {}).get("last_success_at") or ""),
            ),
            reverse=True,
        )
        for pool_user in pool_candidates:
            try:
                courses = self._with_reauth(
                    pool_user.username,
                    lambda client: client.query_courses(page_size=200),
                    retry_attempts=1,
                )
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
            self._course_catalog_fresh = True
            log_event(
                logger,
                logging.INFO,
                "live course catalog refreshed",
                course_count=len(courses),
            )
            return True
        self._course_catalog_fresh = False
        log_event(
            logger,
            logging.WARNING,
            "live course catalog unavailable; auto-select paused",
        )
        return False

    def refresh_user_statuses_once(self) -> set[str]:
        users = self.enabled_users()
        ready: set[str] = set()
        pending = [
            user
            for user in users
            if account_health(self.store, user.username).get("status")
            != STATUS_AUTH_REQUIRED
        ]

        def fetch(user: UserRecord):
            try:
                selected, statistics = self._with_reauth(
                    user.username,
                    lambda client: self._query_user_status(client),
                    retry_attempts=1,
                )
                return user, selected, statistics, None
            except Exception as exc:
                return user, None, None, exc

        with ThreadPoolExecutor(
            max_workers=min(4, max(1, len(pending))),
            thread_name_prefix="boya-status",
        ) as executor:
            futures = {
                executor.submit(fetch, user): user
                for user in pending
            }
            for future in as_completed(futures):
                fallback_user = futures[future]
                try:
                    user, selected, statistics, error = future.result()
                except Exception as exc:
                    user, selected, statistics, error = (
                        fallback_user,
                        None,
                        None,
                        exc,
                    )
                if isinstance(error, ReauthenticationRequired):
                    continue
                if error is not None:
                    mark_auth_error(self.store, user.username, str(error))
                    log_event(
                        logger,
                        logging.ERROR,
                        "account cache refresh failed",
                        user=mask_username(user.username),
                        error=error,
                    )
                    continue
                self.cache.save_selected(user.username, selected or [])
                self.cache.save_statistics(user.username, statistics or {})
                ready.add(user.username)
        reconcile_selection_origins(
            self.store,
            self._selected_by_user(self.cache.load_selected()),
        )
        self._selection_ready_users = ready
        return ready

    def _retry_stored_password_logins(
        self,
        *,
        max_attempts: int | None = None,
    ) -> int:
        now = datetime.now()
        attempted = 0
        recovered = 0
        for user in self.enabled_users():
            health = account_health(self.store, user.username)
            if health.get("status") != STATUS_AUTH_REQUIRED:
                continue
            if not _auth_retry_due(health, now):
                continue
            if max_attempts is not None and attempted >= max_attempts:
                break
            attempted += 1
            if self._auto_relogin(user.username):
                recovered += 1
                log_event(
                    logger,
                    logging.INFO,
                    "stored-password reauthentication succeeded",
                    user=mask_username(user.username),
                    ocr=captcha_ocr_available(),
                )
            else:
                log_event(
                    logger,
                    logging.WARNING,
                    "stored-password reauthentication still requires attention",
                    user=mask_username(user.username),
                    error=account_health(self.store, user.username).get("error"),
                )
        return recovered

    def _auto_relogin(self, username: str) -> bool:
        """Re-login with stored password and local captcha OCR when needed."""
        previous = account_health(self.store, username)
        try:
            password = password_for_account(self.store, username)
            login_account(
                self.store,
                username,
                password,
                allow_ocr=True,
            )
            return True
        except AccountLoginBusy:
            log_event(
                logger,
                logging.INFO,
                "account login already in progress in another process",
                user=mask_username(username),
            )
            return False
        except Exception as exc:
            failure_count = int(previous.get("failure_count") or 0) + 1
            delay = min(
                AUTO_REAUTH_MAX_BACKOFF_SECONDS,
                AUTO_REAUTH_RETRY_SECONDS
                * (2 ** min(6, max(0, failure_count - 1))),
            )
            next_retry_at = (
                datetime.now() + timedelta(seconds=delay)
            ).isoformat(timespec="seconds")
            captcha_path = None
            challenge_path = getattr(getattr(exc, "challenge", None), "image_path", None)
            if challenge_path:
                captcha_path = challenge_path
            else:
                health = account_health(self.store, username)
                raw_path = health.get("captcha_path")
                captcha_path = Path(raw_path) if raw_path else None
            mark_auth_required(
                self.store,
                username,
                str(exc),
                captcha_path,
                failure_count=failure_count,
                next_retry_at=next_retry_at,
            )
            if previous.get("status") != STATUS_AUTH_REQUIRED:
                notify_auth_required(username)
            return False

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

    def scan_once(
        self,
        *,
        allow_selection: bool = True,
        selection_usernames: set[str] | None = None,
    ) -> list[AutomationDecision]:
        now = datetime.now()
        courses = self.cache.parsed_courses()
        selected_by_user = self._selected_by_user(self.cache.load_selected())
        users = self.enabled_users()
        stats_all = self.cache.load_statistics()
        origins = load_selection_origins(self.store)

        decisions: list[AutomationDecision] = []

        selected_raw = self.cache.load_selected()
        for user in users:
            if (
                account_health(self.store, user.username).get("status")
                == STATUS_AUTH_REQUIRED
            ):
                continue
            stats = stats_all.get(user.username, {}) if isinstance(stats_all, dict) else {}
            selected = selected_by_user.get(user.username, [])
            selected_items = (
                selected_raw.get(user.username, [])
                if isinstance(selected_raw, dict)
                else []
            )
            if not isinstance(selected_items, list):
                selected_items = []
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

            if not allow_selection or (
                selection_usernames is not None
                and user.username not in selection_usernames
            ):
                log_event(
                    logger,
                    logging.WARNING,
                    "auto-select paused until live account data is available",
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

            category_quotas: dict[str, int] = {}
            if self.kit.only_gap_categories:
                category_quotas = {
                    gap.category: gap.remaining_to_select
                    for gap in parse_gaps(
                        stats,
                        selected_items=selected_items,
                        now=now,
                    )
                    if gap.remaining_to_select > 0
                    and gap.category not in self.kit.exclude_categories
                }
                if not category_quotas:
                    log_event(
                        logger,
                        logging.INFO,
                        "no unfilled category slots; skip auto-select",
                        user=mask_username(user.username),
                    )
                    continue
            needed = set(category_quotas)

            candidates = [
                course
                for course in courses
                if is_machine_selectable_course(course, now)
                and course.category not in self.kit.exclude_categories
                and (
                    not self.kit.only_gap_categories
                    or course.category in needed
                )
                and not user_has_selected(selected_by_user, user.username, course.id)
            ]
            candidates.sort(
                key=lambda c: (
                    prefer_sort_key(c.category, self.kit.prefer_categories),
                    # Prefer courses with remaining seats first when live counts exist.
                    0
                    if (
                        c.current_count is not None
                        and c.max_count is not None
                        and c.current_count < c.max_count
                    )
                    else 1,
                    c.select_end or "",
                    c.id,
                )
            )
            remaining_slots = max(
                0,
                self.kit.max_pending_selected - len(machine_pending),
            )
            selected_count = 0
            for course in candidates:
                if selected_count >= remaining_slots:
                    break
                if self.kit.only_gap_categories:
                    quota = category_quotas.get(course.category, 0)
                    if quota <= 0:
                        continue
                    category_quotas[course.category] = quota - 1
                decisions.append(
                    AutomationDecision(action="select", course_id=course.id, username=user.username)
                )
                selected_count += 1

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
        from autoboya.scheduler import journal_key

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
                try:
                    fresh_course = self._fresh_course_for_selection(
                        username,
                        decision.course_id,
                    )
                except ReauthenticationRequired:
                    log_event(
                        logger,
                        logging.WARNING,
                        "auto-select paused because account requires sign-in",
                        user=mask_username(username),
                        course_id=decision.course_id,
                    )
                    continue
                except Exception as exc:
                    log_event(
                        logger,
                        logging.WARNING,
                        "could not verify live course before selection",
                        user=mask_username(username),
                        course_id=decision.course_id,
                        error=exc,
                    )
                    continue
                course = fresh_course
                if not is_machine_selectable_course(course, now):
                    log_event(
                        logger,
                        logging.INFO,
                        "live course is no longer selectable",
                        user=mask_username(username),
                        course_id=decision.course_id,
                    )
                    continue
                if user_has_selected(selected_by_user, username, decision.course_id):
                    continue
                key = journal_key(username, "select", decision.course_id)
                if journal.get(key):
                    continue
                result = self._select_for_user(user, decision.course_id)
                results.append(result)
                if result.ok:
                    journal[key] = result.message
                    mark_machine_selection(
                        self.store,
                        username,
                        course,
                    )
                elif result.terminal:
                    log_event(
                        logger,
                        logging.WARNING,
                        "auto select failed",
                        user=mask_username(username),
                        course_id=decision.course_id,
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

    def _fresh_course_for_selection(
        self,
        username: str,
        course_id: int,
    ) -> BoyaCourse:
        return self._with_reauth(
            username,
            lambda client: client.query_course_detail(course_id),
        )

    def _select_for_user(self, user: UserRecord, course_id: int) -> ActionResult:
        try:
            self._with_reauth(
                user.username,
                lambda client: client.select_course(course_id),
            )
        except BoyaApiError as exc:
            return ActionResult(
                user.username,
                "select",
                course_id,
                False,
                str(exc),
            )
        except AlreadySelected as exc:
            try:
                self._refresh_user_cache(user.username)
            except Exception:
                pass
            return ActionResult(
                user.username,
                "select",
                course_id,
                False,
                str(exc),
            )
        except (CourseFull, CourseNotOpen, SelectionLimitReached) as exc:
            return ActionResult(
                user.username,
                "select",
                course_id,
                False,
                str(exc),
            )
        except Exception as exc:
            return ActionResult(
                user.username,
                "select",
                course_id,
                False,
                str(exc),
            )

        try:
            self._refresh_user_cache(user.username)
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "course selected but post-selection status refresh failed",
                user=mask_username(user.username),
                course_id=course_id,
                error=exc,
            )
        return ActionResult(
            user.username,
            "select",
            course_id,
            True,
            "selected",
        )

    def _sign_for_user(
        self,
        username: str,
        course: BoyaCourse | None,
        action: str,
    ) -> ActionResult:
        if not course or not course.sign_config.get("signPointList"):
            return ActionResult(
                username,
                action,
                course.id if course else 0,
                False,
                "missing sign point",
            )
        point = course.sign_config["signPointList"][-1]
        lat, lng = random_point_in_radius(
            float(point["lat"]),
            float(point["lng"]),
            float(point.get("radius") or 8),
        )
        sign_type = 1 if action == "sign" else 2
        try:
            self._with_reauth(
                username,
                lambda client: client.sign_course(
                    course.id,
                    lat,
                    lng,
                    sign_type,
                ),
            )
        except Exception as exc:
            return ActionResult(
                username,
                action,
                course.id,
                False,
                str(exc),
            )

        try:
            self._refresh_user_cache(username)
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "attendance succeeded but post-action status refresh failed",
                user=mask_username(username),
                course_id=course.id,
                action=action,
                error=exc,
            )
        return ActionResult(
            username,
            action,
            course.id,
            True,
            "signed",
        )

    def _with_reauth(self, username: str, operation, retry_attempts: int = 1):
        from autoboya.session import ensure_bykc_client

        current_health = account_health(self.store, username)
        if current_health.get("status") == STATUS_AUTH_REQUIRED:
            if not _auth_retry_due(current_health) or not self._auto_relogin(username):
                raise ReauthenticationRequired(
                    current_health.get("error")
                    or account_health(self.store, username).get("error")
                    or "account requires interactive login"
                )
        elif not _has_stored_session(self.store, username):
            if not self._auto_relogin(username):
                detail = (
                    account_health(self.store, username).get("error")
                    or "missing saved session"
                )
                raise ReauthenticationRequired(detail)

        for attempt in range(1, retry_attempts + 1):
            try:
                client = ensure_bykc_client(self.store, username)
                http_client = getattr(client, "client", None)
                if isinstance(http_client, httpx.Client):
                    http_client.timeout = httpx.Timeout(
                        20.0,
                        connect=10.0,
                    )
                try:
                    result = operation(client)
                except SessionExpired:
                    log_event(
                        logger,
                        logging.WARNING,
                        "session expired; attempting OCR-assisted re-login",
                        user=mask_username(username),
                    )
                    if not self._auto_relogin(username):
                        detail = (
                            account_health(self.store, username).get("error")
                            or "session expired; captcha login required"
                        )
                        raise ReauthenticationRequired(detail)
                    client = ensure_bykc_client(self.store, username)
                    http_client = getattr(client, "client", None)
                    if isinstance(http_client, httpx.Client):
                        http_client.timeout = httpx.Timeout(
                            20.0,
                            connect=10.0,
                        )
                    result = operation(client)
            except ReauthenticationRequired:
                raise
            except CaptchaRequired as exc:
                if self._auto_relogin(username):
                    continue
                detail = (
                    account_health(self.store, username).get("error")
                    or str(exc)
                    or "CAPTCHA required"
                )
                raise ReauthenticationRequired(detail) from exc
            except LoginError as exc:
                if self._auto_relogin(username):
                    continue
                detail = (
                    account_health(self.store, username).get("error")
                    or str(exc)
                    or "unified authentication login failed"
                )
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
        raise RuntimeError("account request failed after retries")


def _auth_retry_due(
    health: dict[str, object],
    now: datetime | None = None,
) -> bool:
    now = now or datetime.now()
    try:
        next_retry = datetime.fromisoformat(
            str(health.get("next_retry_at") or "")
        )
        return now >= next_retry
    except ValueError:
        pass
    try:
        updated_at = datetime.fromisoformat(
            str(health.get("updated_at") or "")
        )
    except ValueError:
        return True
    return (now - updated_at).total_seconds() >= AUTO_REAUTH_RETRY_SECONDS


def _has_stored_session(store: AutoBoyaStore, username: str) -> bool:
    session = store.load_json(f"sessions/{username}.json", {})
    if not isinstance(session, dict):
        return False
    token = session.get("bykc_token")
    cookies = session.get("cookies")
    return bool(token) and isinstance(cookies, list)


def _attach_kit_file_logger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    target = str(path.resolve())
    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler):
            existing = getattr(handler, "baseFilename", None)
            if existing and str(Path(existing).resolve()) == target:
                return
    handler = RotatingFileHandler(
        path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
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

    def modified_at(relative: str) -> str | None:
        path = store.path(relative)
        try:
            return datetime.fromtimestamp(path.stat().st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except OSError:
            return None

    def cache_age(relative: str) -> float:
        try:
            return max(0.0, time.time() - store.path(relative).stat().st_mtime)
        except OSError:
            return float("inf")

    course_age_seconds = cache_age("cache/courses.json")
    status_age_seconds = cache_age("cache/statistics.json")
    courses_stale = course_age_seconds > max(
        120,
        kit.course_refresh_seconds * 3,
    )
    statuses_stale = status_age_seconds > max(
        180,
        kit.status_refresh_seconds * 3,
    )

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
        if not isinstance(selected_items, list):
            selected_items = []
        selected_pairs = [
            (item, parse_course(item))
            for item in selected_items
            if isinstance(item, dict)
        ]
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
                    "checkin": item.get("checkin"),
                    "selected_at": item.get("selectDate"),
                    "start": course.course_start,
                    "end": course.course_end,
                    "location": course.location,
                }
            )
        gaps = gaps_payload(stats, selected_items=selected_items, now=now)
        needed = needed_categories(
            stats,
            exclude=kit.exclude_categories,
            selected_items=selected_items,
            now=now,
        )
        selected_ids = {course.id for course in selected}
        candidate_status = _candidate_diagnostics(
            courses,
            selected_ids,
            needed,
            now,
        )
        if courses_stale:
            candidate_status = {
                "open_needed_candidate_count": 0,
                "full_needed_candidate_count": 0,
                "next_needed_candidate_at": None,
                "upcoming_candidates": [],
                "live_course_data_ready": False,
            }
        else:
            candidate_status["live_course_data_ready"] = True
        out_users.append(
            {
                "username": user.username,
                "campus": user.campus,
                "auth_status": auth_status,
                "auth_error": health.get("error"),
                "captcha_path": health.get("captcha_path"),
                "last_auth_success_at": health.get("last_success_at"),
                "requirements_met": requirements_met(
                    stats,
                    exclude=kit.exclude_categories,
                    selected_items=selected_items,
                    now=now,
                ),
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

    return {
        "users": out_users,
        "dry_run": kit.dry_run,
        "only_gap_categories": kit.only_gap_categories,
        "status_updated_at": modified_at("cache/statistics.json"),
        "courses_updated_at": modified_at("cache/courses.json"),
        "course_data_stale": courses_stale,
        "status_data_stale": statuses_stale,
        "course_data_age_seconds": course_age_seconds,
        "status_data_age_seconds": status_age_seconds,
    }


def _course_assessment_status(
    item: dict,
    course: BoyaCourse,
    now: datetime,
) -> str:
    from .gaps import course_assessment_outcome

    outcome = course_assessment_outcome(
        item,
        now,
        course_end=course.course_end,
    )
    if outcome == "passed":
        return "passed"
    if outcome == "failed":
        return "not_passed"
    end = parse_dt(course.course_end)
    finished = end is not None and end < now
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
