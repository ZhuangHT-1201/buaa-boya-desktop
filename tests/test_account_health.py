from types import SimpleNamespace

import pytest
from autoboya.storage import AutoBoyaStore
from autoboya.exceptions import CaptchaRequired, LoginError

from boya_kit.account_health import (
    STATUS_AUTH_REQUIRED,
    account_health,
    mark_auth_ok,
    mark_auth_required,
)
from boya_kit.config import KitConfig
from boya_kit.runner import GapAwareRunner, ReauthenticationRequired
from boya_kit import service
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
    )

    assert session.bykc_token == "token"
    assert account_health(store, "student")["status"] == "ok"
    assert store.path("sessions/student.json").exists()


def test_runner_skips_account_that_needs_interactive_login(tmp_path) -> None:
    store = AutoBoyaStore(tmp_path)
    store.init()
    mark_auth_required(store, "student", "CAPTCHA required")
    runner = GapAwareRunner(store, KitConfig(username="student"))

    with pytest.raises(ReauthenticationRequired):
        runner._with_reauth("student", lambda _client: None)
