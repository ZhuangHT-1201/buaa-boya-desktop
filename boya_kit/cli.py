from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from autoboya.storage import AutoBoyaStore

from . import __version__
from .config import DEFAULT_CONFIG_PATH, LOG_FILE, ensure_config_file, load_config
from .runner import GapAwareRunner, status_payload

app = typer.Typer(add_completion=False, help="北航博雅缺口优先自动化（基于 AutoBoya）")
console = Console()


@app.callback()
def _root() -> None:
    """北航博雅：按类别缺口自动选自主签到课，并到点签到/签退。"""


@app.command(help="显示版本。")
def version() -> None:
    typer.echo(__version__)


@app.command(help="复制示例配置并初始化 AutoBoya 数据目录。")
def init() -> None:
    path = ensure_config_file()
    store = AutoBoyaStore()
    store.init()
    console.print(f"已准备配置: {path}")
    console.print(f"AutoBoya 数据目录: {store.root}")
    console.print("下一步: python -m boya_kit setup")


@app.command(help="交互式添加账号并登录（密码只在本机输入，不会写入项目文件）。")
def setup(
    username: Optional[str] = typer.Option(None, "--user", help="学号/统一身份账号"),
    campus: str = typer.Option("北京", "--campus", help="北京 或 杭州"),
) -> None:
    ensure_config_file()
    user = username or typer.prompt("学号/统一身份账号").strip()
    if campus not in {"北京", "杭州"}:
        raise typer.BadParameter("campus 只能是 北京 或 杭州")

    # 让用户通过 stdin 输入密码，交给 autoboya
    console.print("请输入统一身份认证密码（输入时可见性由终端决定，不会写入 config.yaml）：")
    proc = subprocess.run(
        [sys.executable, "-m", "autoboya", "user", "add", user, "--campus", campus, "--password-stdin"],
        check=False,
    )
    if proc.returncode != 0:
        raise typer.Exit(proc.returncode)

    console.print("开始登录（若出现验证码，按提示打开图片并输入）…")
    login = subprocess.run([sys.executable, "-m", "autoboya", "login", user], check=False)
    if login.returncode != 0:
        raise typer.Exit(login.returncode)

    # 保持批量模式：账号启用状态由 AutoBoya 账号列表管理，不在配置中绑定单账号。
    _patch_config_defaults(campus)
    console.print("登录成功。已完成登录的启用账号会一起参与批量任务。")


@app.command(help="刷新课程/已选/统计缓存。")
def refresh() -> None:
    kit = load_config()
    store = AutoBoyaStore()
    store.init()
    GapAwareRunner(store, kit).refresh_once()
    console.print("缓存已刷新")


@app.command(help="查看缺口、已选课与完成进度。")
def status(
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    kit = load_config()
    store = AutoBoyaStore()
    store.init()
    payload = status_payload(store, kit)
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if not payload["users"]:
        console.print("没有已启用账号。先运行: python -m boya_kit setup")
        raise typer.Exit(1)
    for user in payload["users"]:
        console.print(f"\n[bold]{user['username'][:3]}***[/bold]  校区={user['campus']}  有效数={user['valid_count']}")
        console.print(
            "进度: "
            + ("[green]本学期类别要求已齐[/green]" if user["requirements_met"] else f"待补 {', '.join(user['needed_categories']) or '未知'}")
        )
        table = Table(show_header=True, header_style="bold")
        table.add_column("类型")
        table.add_column("要求", justify="right")
        table.add_column("已选", justify="right")
        table.add_column("完成", justify="right")
        table.add_column("未完成", justify="right")
        for gap in user["gaps"]:
            table.add_row(
                gap["category"],
                str(gap["required"]),
                str(gap["selected"]),
                str(gap["completed"]),
                str(gap["undone"]),
            )
        console.print(table)
        if user["selected"]:
            console.print("已选课程:")
            for course in user["selected"]:
                console.print(
                    f"  - [{course['id']}] {course['name']} | {course['category']} | "
                    f"{course['sign_method']} | {course['start'] or '?'} ~ {course['end'] or '?'}"
                )
        else:
            console.print("暂无已选课程（或尚未 refresh）")


@app.command("preview", help="预览本轮会自动选哪些课（按缺口过滤），不产生真实操作。")
def preview() -> None:
    kit = load_config()
    # 强制 dry-run 语义
    kit.dry_run = True
    store = AutoBoyaStore()
    store.init()
    runner = GapAwareRunner(store, kit)
    decisions = runner.scan_once()
    selects = [d for d in decisions if d.action == "select"]
    signs = [d for d in decisions if d.action in {"sign", "signout"}]
    console.print(f"将自动选课 {len(selects)} 门，签到/签退决策 {len(signs)} 条")
    courses = {c.id: c for c in runner.cache.parsed_courses()}
    for d in selects:
        course = courses.get(d.course_id)
        name = course.name if course else "?"
        category = course.category if course else "?"
        console.print(f"  select {d.course_id} {name} [{category}] -> {d.username}")
    for d in signs:
        console.print(f"  {d.action} {d.course_id} -> {d.username}")


@app.command("run-once", help="刷新并执行一轮（真实选课/签到，除非 config dry_run=true）。")
def run_once() -> None:
    kit = load_config()
    store = AutoBoyaStore()
    store.init()
    runner = GapAwareRunner(store, kit)
    runner.refresh_once()
    results = runner.execute_decisions(runner.scan_once())
    typer.echo(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))


@app.command(help="后台启动缺口优先循环。")
def run() -> None:
    kit = load_config()
    store = AutoBoyaStore()
    store.init()
    log_path = store.path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "-m", "boya_kit", "run-worker"]
    with log_path.open("a", encoding="utf-8") as log:
        kwargs = {
            "stdin": subprocess.DEVNULL,
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "cwd": str(DEFAULT_CONFIG_PATH.parent),
            "close_fds": os.name != "nt",
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
                subprocess, "DETACHED_PROCESS", 0
            )
        else:
            kwargs["start_new_session"] = True
        process = subprocess.Popen(args, **kwargs)
    console.print(f"已后台启动 pid={process.pid}  logs={log_path}")
    if kit.dry_run:
        console.print("[yellow]注意: config.yaml 中 dry_run=true，不会产生真实操作[/yellow]")


@app.command("run-worker", hidden=True)
def run_worker() -> None:
    kit = load_config()
    store = AutoBoyaStore()
    GapAwareRunner(store, kit).run_forever()


@app.command(help="请求停止 boya_kit 后台循环。")
def stop() -> None:
    GapAwareRunner(AutoBoyaStore(), load_config()).request_stop()
    console.print("已请求停止")


@app.command(help="查看 boya_kit 日志尾部。")
def logs(lines: int = typer.Option(80, "--lines")) -> None:
    path = AutoBoyaStore().path(LOG_FILE)
    if not path.exists():
        console.print("暂无日志")
        return
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in content[-lines:]:
        typer.echo(line)


def _patch_config_defaults(campus: str) -> None:
    import yaml

    path = ensure_config_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        data = {}
    data["username"] = None
    data["campus"] = campus
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    app()
