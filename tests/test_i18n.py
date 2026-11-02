from boya_kit.i18n import ENGLISH, format_text, translate


def test_english_translation() -> None:
    assert translate("账号管理", "en") == "Accounts"
    assert translate("账号管理", "zh") == "账号管理"


def test_formatted_translation() -> None:
    result = format_text("共 {count} 个账号", "en", count=3)
    assert result == "3 account(s)"


def test_dynamic_templates_have_translations() -> None:
    expected = {
        "正在登录 {username}…",
        "已启动批量后台任务，共 {count} 个账号",
        "验证码图片：{path}",
    }
    assert expected.issubset(ENGLISH)


def test_english_catalog_does_not_leak_unlocalized_copy() -> None:
    allowed = {"Language switched to Chinese.", "语言已切换为中文"}
    leaked = {
        source: target
        for source, target in ENGLISH.items()
        if any("\u4e00" <= char <= "\u9fff" for char in target)
        and target not in allowed
    }
    assert leaked == {}
