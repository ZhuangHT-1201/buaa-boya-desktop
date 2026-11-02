from __future__ import annotations

import logging
import sys
import traceback

from autoboya.storage import AutoBoyaStore

from boya_kit.config import LOG_FILE, load_config


def _record_gui_crash() -> str:
    store = AutoBoyaStore()
    store.init()
    log_path = store.path("logs/gui-crash.log")
    detail = traceback.format_exc()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(detail + "\n")
    if sys.platform == "win32":
        try:
            import ctypes

            message = (
                "程序启动失败，详情已写入：\n"
                f"{log_path}\n\n"
                f"{traceback.format_exc(limit=3)}"
            )
            ctypes.windll.user32.MessageBoxW(
                None,
                message,
                "博雅自动助手启动失败",
                0x10,
            )
        except Exception:
            pass
    return str(log_path)


def main() -> None:
    if "--worker" in sys.argv[1:]:
        from boya_kit.runner import GapAwareRunner

        store = AutoBoyaStore()
        runner = GapAwareRunner(store, load_config())
        try:
            runner.run_forever()
        except Exception:
            logging.exception("BoyaKit worker terminated unexpectedly")
            if getattr(sys, "frozen", False):
                store.path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
                with store.path(LOG_FILE).open("a", encoding="utf-8") as handle:
                    handle.write("后台进程异常退出，详情见 autoboya.log\n")
        return
    try:
        from boya_kit.gui import launch_gui

        launch_gui()
    except Exception:
        _record_gui_crash()


if __name__ == "__main__":
    main()
