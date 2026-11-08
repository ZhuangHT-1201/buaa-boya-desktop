from types import SimpleNamespace

import pytest
from autoboya.models import UserRecord
from autoboya.storage import AutoBoyaStore
from autoboya.exceptions import CaptchaRequired, LoginError

from boya_kit.account_health import (
    STATUS_AUTH_REQUIRED,
    account_health,
    mark_auth_ok,
    mark_auth_required,
)
from boya_kit.config import KitConfig
from boya_kit.runner import (
    GapAwareRunner,
    ReauthenticationRequired,
    _auth_retry_due,
)
from boya_kit import service
from boya_kit import runner as runner_module
from boya_kit.service import (
    _valid_captcha_image,
    cleanup_captcha_files,
    login_account,
)


def test_auth_health_round_trip(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    mark_auth_required(store, "student", "captcha required")
    state = account_health(store, "student")
    assert state["status"] == STATUS_AUTH_REQUIRED
    assert state["error"] == "captcha required"

    mark_auth_ok(store, "student", message="manual login")
    state = account_health(store, "student")
    assert state["status"] == "ok"
    assert state["error"] is None


def test_captcha_validation_and_cleanup(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    directory = store.path("captcha")
    for index in range(50):
        (directory / f"{index:02d}.png").write_bytes(b"x" * 300)
    empty = directory / "empty.jpg"
    empty.write_bytes(b"")

    assert _valid_captcha_image(directory / "00.png")
    assert not _valid_captcha_image(empty)
    cleanup_captcha_files(store, keep=10)
    assert len(list(directory.iterdir())) == 10


def test_login_retries_wrong_captcha(tmp_path, monkeypatch) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    image = store.path("captcha/challenge.png")
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"x" * 500)

    class FakeAuthClient:
        def __init__(self, _store) -> None:
            pass

        def preflight_login(self):
            raise CaptchaRequired(SimpleNamespace(image_path=image))

        def login(self, username, password, captcha=None):
            if captcha != "correct":
                raise LoginError("验证码错误")
            return SimpleNamespace(bykc_token="token", cookies=[])

    monkeypatch.setattr(service, "AuthClient", FakeAuthClient)
    answers = iter(["wrong", "correct"])
    session = login_account(
        store,
        "student",
        "password",
        captcha_provider=lambda _challenge: next(answers),
        allow_ocr=False,
    )

    assert session.bykc_token == "token"
    assert account_health(store, "student")["status"] == "ok"
    assert store.path("sessions/student.json").exists()


def test_login_uses_ocr_when_no_provider(tmp_path, monkeypatch) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    image = store.path("captcha/challenge.png")
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"x" * 500)

    class FakeAuthClient:
        def __init__(self, _store) -> None:
            pass

        def preflight_login(self):
            raise CaptchaRequired(SimpleNamespace(image_path=image))

        def login(self, username, password, captcha=None):
            if captcha != "ocr42":
                raise LoginError("验证码错误")
            return SimpleNamespace(bykc_token="token", cookies=[])

    monkeypatch.setattr(service, "AuthClient", FakeAuthClient)
    monkeypatch.setattr(
        service,
        "ocr_captcha_provider",
        lambda _challenge: "ocr42",
    )
    monkeypatch.setattr(service, "captcha_ocr_available", lambda: True)
    session = login_account(store, "student", "password")
    assert session.bykc_token == "token"
    assert account_health(store, "student")["status"] == "ok"


def test_interactive_login_falls_back_to_manual_after_wrong_ocr(
    tmp_path,
    monkeypatch,
) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    image = store.path("captcha/challenge.png")
    image.write_bytes(b"x" * 500)

    class FakeAuthClient:
        def __init__(self, _store) -> None:
            pass

        def preflight_login(self):
            raise CaptchaRequired(SimpleNamespace(image_path=image))

        def login(self, _username, _password, captcha=None):
            if captcha == "wrong":
                raise LoginError("验证码错误")
            return SimpleNamespace(bykc_token="token", cookies=[])

    monkeypatch.setattr(service, "AuthClient", FakeAuthClient)
    monkeypatch.setattr(service, "captcha_ocr_available", lambda: True)
    monkeypatch.setattr(
        service,
        "ocr_captcha_provider",
        lambda _challenge: "wrong",
    )
    session = login_account(
        store,
        "student",
        "password",
        captcha_provider=lambda _challenge: "manual",
    )

    assert session.bykc_token == "token"


def test_runner_skips_account_that_needs_interactive_login(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    mark_auth_required(store, "student", "CAPTCHA required")
    runner = GapAwareRunner(store, KitConfig(username="student"))

    with pytest.raises(ReauthenticationRequired):
        runner._with_reauth("student", lambda _client: None)


def test_runner_retries_saved_password_without_captcha(tmp_path, monkeypatch) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    store.upsert_user(
        UserRecord(username="student", enabled=True, campus="北京")
    )
    mark_auth_required(store, "student", "session expired")
    calls: list[str] = []

    def fake_login(
        _store,
        username: str,
        _password: str,
        captcha_provider=None,
        *,
        allow_ocr: bool = True,
    ) -> None:
        calls.append(username)
        assert allow_ocr is True
        mark_auth_ok(_store, username, message="background reauthentication")

    monkeypatch.setattr(runner_module, "AUTO_REAUTH_RETRY_SECONDS", 0)
    monkeypatch.setattr(
        runner_module,
        "password_for_account",
        lambda _store, _username: "stored-password",
    )
    monkeypatch.setattr(runner_module, "login_account", fake_login)

    runner = GapAwareRunner(store, KitConfig(username="student"))
    runner._retry_stored_password_logins()

    assert calls == ["student"]
    assert account_health(store, "student")["status"] == "ok"


def test_ocr_unavailable_fails_fast_without_repeated_logins(
    tmp_path,
    monkeypatch,
) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    image = store.path("captcha/challenge.png")
    image.write_bytes(b"x" * 500)
    preflight_calls: list[int] = []

    class FakeAuthClient:
        def __init__(self, _store) -> None:
            pass

        def preflight_login(self):
            preflight_calls.append(1)
            raise CaptchaRequired(SimpleNamespace(image_path=image))

        def login(self, *_args, **_kwargs):
            raise AssertionError("login should not run when OCR is unavailable")

    monkeypatch.setattr(service, "AuthClient", FakeAuthClient)
    monkeypatch.setattr(service, "captcha_ocr_available", lambda: False)

    with pytest.raises(RuntimeError, match="自动识别组件不可用"):
        login_account(store, "student", "password")

    assert len(preflight_calls) == 1


def test_reauthentication_failure_uses_exponential_backoff(
    tmp_path,
    monkeypatch,
) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    store.upsert_user(
        UserRecord(username="student", enabled=True, campus="北京")
    )
    mark_auth_required(store, "student", "session expired")
    monkeypatch.setattr(
        runner_module,
        "password_for_account",
        lambda _store, _username: "stored-password",
    )
    monkeypatch.setattr(
        runner_module,
        "login_account",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("OCR failed")),
    )
    runner = GapAwareRunner(store, KitConfig(username="student"))

    assert runner._auto_relogin("student") is False
    health = account_health(store, "student")
    assert health["failure_count"] == 1
    assert health["next_retry_at"] is not None
    assert _auth_retry_due(health) is False


def test_runner_auto_relogin_on_session_expired(tmp_path, monkeypatch) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    store.upsert_user(
        UserRecord(username="student", enabled=True, campus="北京")
    )
    store.save_json(
        "sessions/student.json",
        {"bykc_token": "old", "cookies": []},
        mode=0o600,
    )
    mark_auth_ok(store, "student")
    calls: list[str] = []

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def ping(self) -> str:
            self.calls += 1
            if self.calls == 1:
                from autoboya.exceptions import SessionExpired

                raise SessionExpired("expired")
            return "ok"

    fake_client = FakeClient()

    def fake_ensure(_store, username: str, captcha_provider=None):
        calls.append(f"ensure:{username}")
        return fake_client

    def fake_login(
        _store,
        username: str,
        _password: str,
        captcha_provider=None,
        *,
        allow_ocr: bool = True,
    ):
        calls.append(f"login:{username}")
        mark_auth_ok(_store, username, message="ocr reauth")
        return SimpleNamespace(bykc_token="new", cookies=[])

    monkeypatch.setattr(
        "autoboya.session.ensure_bykc_client",
        fake_ensure,
    )
    monkeypatch.setattr(
        runner_module,
        "password_for_account",
        lambda _store, _username: "stored-password",
    )
    monkeypatch.setattr(runner_module, "login_account", fake_login)

    runner = GapAwareRunner(store, KitConfig(username="student"))
    result = runner._with_reauth("student", lambda client: client.ping())

    assert result == "ok"
    assert "login:student" in calls
    assert account_health(store, "student")["status"] == "ok"


def test_runner_logs_in_before_using_missing_session(tmp_path, monkeypatch) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    store.upsert_user(
        UserRecord(username="student", enabled=True, campus="北京")
    )
    mark_auth_ok(store, "student")
    runner = GapAwareRunner(store, KitConfig(username="student"))
    login_calls: list[str] = []

    def fake_relogin(username: str) -> bool:
        login_calls.append(username)
        store.save_json(
            "sessions/student.json",
            {"bykc_token": "new", "cookies": []},
            mode=0o600,
        )
        mark_auth_ok(store, username)
        return True

    class FakeClient:
        def ping(self) -> str:
            return "ok"

    runner._auto_relogin = fake_relogin  # type: ignore[method-assign]
    monkeypatch.setattr(
        "autoboya.session.ensure_bykc_client",
        lambda _store, _username: FakeClient(),
    )

    assert runner._with_reauth("student", lambda client: client.ping()) == "ok"
    assert login_calls == ["student"]
