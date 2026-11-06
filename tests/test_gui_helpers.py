from boya_kit.gui import account_requires_sign_in


def test_account_requires_sign_in_statuses() -> None:
    assert account_requires_sign_in({"auth_status": "auth_required"})
    assert account_requires_sign_in({"auth_status": "login_required"})
    assert not account_requires_sign_in({"auth_status": "ok"})
    assert not account_requires_sign_in({"auth_status": "error"})
    assert not account_requires_sign_in({})
