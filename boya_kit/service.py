from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable

from autoboya.auth import AuthClient
from autoboya.exceptions import CaptchaRequired, LoginError
from autoboya.models import UserRecord
from autoboya.storage import (
    AutoBoyaStore,
    try_get_keyring_password,
    try_store_keyring_password,
)

from .config import PROJECT_ROOT, RUN_PID_FILE, STOP_FILE


def mask_username(username: str) -> str:
    if len(username) <= 4:
        return username[:1] + "***"
    return username[:3] + "***" + username[-2:]


def _windows_process_running(pid: int) -> bool:
    process_query_limited_information = 0x1000
    still_active = 259
    handle = ctypes.windll.kernel32.OpenProcess(
        process_query_limited_information, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(
            handle, ctypes.byref(exit_code)
        ):
            return False
        return exit_code.value == still_active
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def process_is_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        if os.name == "nt":
            return _windows_process_running(pid)
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def read_worker_pid(store: AutoBoyaStore) -> int | None:
    path = store.path(RUN_PID_FILE)
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def worker_state(store: AutoBoyaStore) -> dict[str, object]:
    pid = read_worker_pid(store)
    running = process_is_running(pid)
    stopping = store.path(STOP_FILE).exists() and running
    return {
        "running": running,
        "stopping": stopping,
        "pid": pid if running else None,
    }


def _worker_command() -> tuple[list[str], str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--worker"], "exe"
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.exists() else python
    return [str(executable), "-m", "boya_kit.launcher", "--worker"], "source"


def start_worker(store: AutoBoyaStore, log_path: Path) -> int:
    state = worker_state(store)
    if state["running"]:
        return int(state["pid"])

    stop_path = store.path(STOP_FILE)
    if stop_path.exists():
        stop_path.unlink()
    pid_path = store.path(RUN_PID_FILE)
    if pid_path.exists():
        pid_path.unlink()

    args, _mode = _worker_command()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.setdefault("PYTHONUTF8", "1")
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    with log_path.open("a", encoding="utf-8") as log:
        kwargs: dict[str, object] = {
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "cwd": str(PROJECT_ROOT),
            "env": environment,
            "close_fds": os.name != "nt",
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            ) | getattr(subprocess, "DETACHED_PROCESS", 0)
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(args, **kwargs)
    return process.pid


def request_worker_stop(store: AutoBoyaStore) -> None:
    store.init()
    store.path(STOP_FILE).write_text(
        time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8"
    )


def wait_for_worker_stop(store: AutoBoyaStore, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not worker_state(store)["running"]:
            return True
        time.sleep(0.2)
    return not worker_state(store)["running"]


def save_account_password(
    store: AutoBoyaStore,
    username: str,
    password: str,
    campus: str,
    *,
    enabled: bool = True,
) -> tuple[UserRecord, bool]:
    """Save a credential using the OS keyring, with a local fallback."""
    if not password:
        raise ValueError("密码不能为空")
    unsafe = not try_store_keyring_password(username, password)
    password_ref = "unsafe-file" if unsafe else "keyring"
    if unsafe:
        store.save_unsafe_password(username, password)
    record = UserRecord(
        username=username,
        password_ref=password_ref,
        unsafe_password=unsafe,
        enabled=enabled,
        campus=campus,
    )
    store.upsert_user(record)
    return record, unsafe


def password_for_account(store: AutoBoyaStore, username: str) -> str:
    password = try_get_keyring_password(username) or store.load_unsafe_password(username)
    if not password:
        raise RuntimeError("本机没有找到该账号的密码，请重新添加账号")
    return password


def login_account(
    store: AutoBoyaStore,
    username: str,
    password: str,
    captcha_provider: Callable[[object], str] | None = None,
) -> object:
    client = AuthClient(store)
    captcha: str | None = None
    try:
        try:
            client.preflight_login()
        except CaptchaRequired as exc:
            if not captcha_provider:
                raise RuntimeError("登录需要验证码，请在图形界面中重试") from exc
            captcha = captcha_provider(exc.challenge).strip()
            if not captcha:
                raise RuntimeError("未填写验证码，登录已取消") from exc
        session = client.login(username, password, captcha=captcha)
    except LoginError as exc:
        raise RuntimeError(str(exc) or "统一身份认证登录失败") from exc
    store.save_json(
        f"sessions/{username}.json",
        {"bykc_token": session.bykc_token, "cookies": session.cookies},
        mode=0o600,
    )
    return session


def set_account_enabled(
    store: AutoBoyaStore, username: str, enabled: bool
) -> UserRecord:
    user = store.get_user(username)
    if user is None:
        raise ValueError("账号不存在")
    updated = replace(user, enabled=enabled)
    store.upsert_user(updated)
    return updated


def session_exists(store: AutoBoyaStore, username: str) -> bool:
    path = store.path(f"sessions/{username}.json")
    return path.exists() and path.stat().st_size > 2


def _autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --worker'
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.exists() else python
    return f'"{executable}" -m boya_kit.launcher --worker'


def autostart_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "BoyaKit")
            return bool(value)
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> None:
    if os.name != "nt":
        raise RuntimeError("开机自启当前仅支持 Windows")
    import winreg

    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        path,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                "BoyaKit",
                0,
                winreg.REG_SZ,
                _autostart_command(),
            )
        else:
            try:
                winreg.DeleteValue(key, "BoyaKit")
            except FileNotFoundError:
                pass


def tail_text(path: Path, lines: int = 120) -> str:
    if not path.exists():
        return "暂无运行日志。登录账号并开始自动运行后，这里会显示实时记录。"
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"读取日志失败：{exc}"
    return "\n".join(data.splitlines()[-max(1, lines) :])
