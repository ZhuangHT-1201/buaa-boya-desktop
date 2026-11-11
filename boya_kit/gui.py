from __future__ import annotations

import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from autoboya.storage import AutoBoyaStore

from .config import (
    DEFAULT_CONFIG_PATH,
    LOG_FILE,
    PROJECT_ROOT,
    SOURCE_ROOT,
    KitConfig,
    ensure_config_file,
    load_config,
    save_config,
)
from .i18n import format_text, translate
from .runner import GapAwareRunner, status_payload
from .runtime import ensure_persistent_ca_bundle
from .service import (
    CAPTCHA_REFRESH_SENTINEL,
    autostart_enabled,
    login_account,
    password_for_account,
    request_worker_stop,
    request_worker_refresh,
    save_account_password,
    session_exists,
    set_account_enabled,
    set_autostart,
    start_worker,
    tail_text,
    wait_for_worker_stop,
    worker_state,
)


BG = "#F3F6FB"
CARD = "#FFFFFF"
INK = "#172033"
MUTED = "#6C778B"
FAINT = "#9AA4B5"
LINE = "#E4E9F2"
SIDEBAR = "#101B34"
SIDEBAR_ACTIVE = "#1B2B4C"
ACCENT = "#3F6FE8"
ACCENT_DARK = "#2F5BD1"
ACCENT_SOFT = "#EAF0FF"
GREEN = "#159A6C"
GREEN_SOFT = "#E9F8F2"
AMBER = "#C47A18"
AMBER_SOFT = "#FFF6E8"
RED = "#D14B59"
RED_SOFT = "#FDECEE"

FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Cascadia Mono"
UI_SCALE = 1.0


def px(value: int | float) -> int:
    return max(1, int(round(value * UI_SCALE)))


def account_requires_sign_in(user: dict) -> bool:
    return user.get("auth_status") in {"auth_required", "login_required"}


def _default_language() -> str:
    if os.name != "nt":
        return "en"
    try:
        language_id = __import__("ctypes").windll.kernel32.GetUserDefaultUILanguage()
        return "zh" if (language_id & 0x3FF) == 0x04 else "en"
    except Exception:
        return "en"


def _asset_path(name: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) / "assets" / name
    return SOURCE_ROOT / "assets" / name


class FlatButton(tk.Button):
    def __init__(
        self,
        master,
        text: str,
        command: Callable[[], None],
        *,
        bg: str = ACCENT,
        fg: str = "#FFFFFF",
        hover: str = ACCENT_DARK,
        padx: int = 18,
        pady: int = 9,
        font_size: int = 10,
        **kwargs,
    ) -> None:
        self._normal_bg = bg
        self._hover_bg = hover
        super().__init__(
            master,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=padx,
            pady=pady,
            font=(FONT_UI, font_size, "bold"),
            **kwargs,
        )
        self.bind("<Enter>", lambda _event: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda _event: self.configure(bg=self._normal_bg))


class Card(tk.Frame):
    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("bg", CARD)
        kwargs.setdefault("highlightbackground", LINE)
        kwargs.setdefault("highlightthickness", 1)
        kwargs.setdefault("bd", 0)
        super().__init__(master, **kwargs)


class ScrollableFrame(tk.Frame):
    def __init__(self, master, *, bg: str = CARD) -> None:
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(
            self,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(
            (0, 0),
            window=self.inner,
            anchor="nw",
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, _event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_wheel(self, _event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


class AccountDialog(tk.Toplevel):
    def __init__(
        self,
        app: "BoyaApp",
        on_submit: Callable[[str, str, str, bool], None],
    ) -> None:
        super().__init__(app)
        self.app = app
        self.on_submit = on_submit
        self.title(app.t("添加博雅账号"))
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        width, height = px(520), px(510)
        app.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - width) // 2
        y = app.winfo_rooty() + (app.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self._build()
        self.after(80, self.username_entry.focus_set)

    def _build(self) -> None:
        header = tk.Frame(self, bg=CARD, padx=px(28), pady=px(22))
        header.pack(fill="x")
        tk.Label(
            header,
            text=self.app.t("添加博雅账号"),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 17, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            header,
            text=self.app.t("密码只保存在本机系统凭据中，不会写入配置文件。"),
            bg=CARD,
            fg=MUTED,
            font=(FONT_UI, 9),
            anchor="w",
        ).pack(fill="x", pady=(5, 0))

        body = tk.Frame(self, bg=BG, padx=px(28), pady=px(22))
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text=self.app.t("学号 / 统一身份认证账号"),
            bg=BG,
            fg=INK,
            font=(FONT_UI, 9, "bold"),
            anchor="w",
        ).pack(fill="x")
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(
            body,
            textvariable=self.username_var,
            font=(FONT_UI, 11),
        )
        self.username_entry.pack(fill="x", ipady=7, pady=(7, 16))

        tk.Label(
            body,
            text=self.app.t("统一身份认证密码"),
            bg=BG,
            fg=INK,
            font=(FONT_UI, 9, "bold"),
            anchor="w",
        ).pack(fill="x")
        password_row = tk.Frame(body, bg=BG)
        password_row.pack(fill="x", pady=(7, 16))
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(
            password_row,
            textvariable=self.password_var,
            show="●",
            font=(FONT_UI, 11),
        )
        self.password_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.show_password = tk.BooleanVar(value=False)
        tk.Checkbutton(
            password_row,
            text=self.app.t("显示"),
            variable=self.show_password,
            command=self._toggle_password,
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            selectcolor=BG,
            font=(FONT_UI, 9),
            bd=0,
        ).pack(side="left", padx=(10, 0))

        tk.Label(
            body,
            text=self.app.t("校区"),
            bg=BG,
            fg=INK,
            font=(FONT_UI, 9, "bold"),
            anchor="w",
        ).pack(fill="x")
        self.campus_var = tk.StringVar(value=self.app.t("北京"))
        campus = ttk.Combobox(
            body,
            textvariable=self.campus_var,
            values=(self.app.t("北京"), self.app.t("杭州")),
            state="readonly",
            font=(FONT_UI, 10),
        )
        campus.pack(fill="x", ipady=5, pady=(7, 16))

        self.enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            body,
            text=self.app.t("加入批量自动运行"),
            variable=self.enabled_var,
            bg=BG,
            fg=INK,
            activebackground=BG,
            selectcolor=CARD,
            font=(FONT_UI, 10),
            bd=0,
        ).pack(anchor="w")

        footer = tk.Frame(self, bg=CARD, padx=px(28), pady=px(18))
        footer.pack(fill="x", side="bottom")
        FlatButton(
            footer,
            self.app.t("取消"),
            self.destroy,
            bg="#EDF1F7",
            fg=INK,
            hover="#E0E6F0",
        ).pack(side="right")
        FlatButton(
            footer,
            self.app.t("保存并登录"),
            self._submit,
            padx=22,
        ).pack(side="right", padx=(0, 10))

    def _toggle_password(self) -> None:
        self.password_entry.configure(show="" if self.show_password.get() else "●")

    def _submit(self) -> None:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username:
            messagebox.showwarning(
                self.app.t("还缺账号"),
                self.app.t("请输入学号或统一身份认证账号。"),
                parent=self,
            )
            return
        if not password:
            messagebox.showwarning(
                self.app.t("还缺密码"),
                self.app.t("请输入统一身份认证密码。"),
                parent=self,
            )
            return
        selected_campus = self.campus_var.get()
        campus = "北京" if selected_campus in {self.app.t("北京"), "北京"} else "杭州"
        self.on_submit(username, password, campus, self.enabled_var.get())
        self.destroy()


class CaptchaDialog(tk.Toplevel):
    def __init__(self, app: "BoyaApp", image_path: Path) -> None:
        super().__init__(app)
        self.app = app
        self.answer = ""
        self._photo = None
        self._image_path = image_path
        self.title(app.t("输入登录验证码"))
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self.update_idletasks()
        width = max(px(430), self.winfo_reqwidth())
        height = self.winfo_reqheight()
        x = app.winfo_rootx() + (app.winfo_width() - width) // 2
        y = app.winfo_rooty() + (app.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.after(80, self.entry.focus_set)

    def _build(self) -> None:
        panel = Card(self, padx=px(28), pady=px(24))
        panel.pack(fill="both", expand=True, padx=px(16), pady=px(16))
        tk.Label(
            panel,
            text=self.app.t("统一身份认证验证码"),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            panel,
            text=self.app.t("请查看下方图片并填写验证码，完成本次登录。"),
            bg=CARD,
            fg=MUTED,
            font=(FONT_UI, 9),
        ).pack(anchor="w", pady=(5, 14))
        image_frame = tk.Frame(panel, bg="#F7F9FC", height=px(110))
        image_frame.pack(fill="x", pady=(0, 14))
        image_frame.pack_propagate(False)
        try:
            from PIL import Image, ImageTk

            image = Image.open(self._image_path)
            image.thumbnail((px(360), px(100)))
            self._photo = ImageTk.PhotoImage(image)
            tk.Label(
                image_frame,
                image=self._photo,
                bg="#F7F9FC",
            ).pack(expand=True)
        except Exception:
            tk.Label(
                image_frame,
                text=self.app.tf("验证码图片：{path}", path=self._image_path),
                bg="#F7F9FC",
                fg=MUTED,
                font=(FONT_UI, 8),
                wraplength=px(350),
            ).pack(expand=True)

        self.value_var = tk.StringVar()
        self.entry = ttk.Entry(
            panel,
            textvariable=self.value_var,
            font=(FONT_UI, 13),
            justify="center",
        )
        self.entry.pack(fill="x", ipady=8)
        self.entry.bind("<Return>", lambda _event: self._submit())

        row = tk.Frame(panel, bg=CARD)
        row.pack(fill="x", pady=(16, 0))
        FlatButton(
            row,
            self.app.t("换一张"),
            self._refresh,
            bg="#EDF1F7",
            fg=INK,
            hover="#E0E6F0",
        ).pack(side="left")
        FlatButton(
            row,
            self.app.t("取消"),
            self._cancel,
            bg="#EDF1F7",
            fg=INK,
            hover="#E0E6F0",
        ).pack(side="right")
        FlatButton(row, self.app.t("继续登录"), self._submit).pack(
            side="right", padx=(0, 10)
        )

    def _submit(self) -> None:
        value = self.value_var.get().strip()
        if not value:
            self.entry.focus_set()
            return
        self.answer = value
        self.destroy()

    def _cancel(self) -> None:
        self.answer = ""
        self.destroy()

    def _refresh(self) -> None:
        self.answer = CAPTCHA_REFRESH_SENTINEL
        self.destroy()


class AccountStatusDialog(tk.Toplevel):
    def __init__(self, app: "BoyaApp", user: dict) -> None:
        super().__init__(app)
        self.app = app
        self.user = user
        self.title(app.t("已选课程明细"))
        self.configure(bg=BG)
        self.transient(app)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        width, height = px(1180), px(870)
        app.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - width) // 2
        y = app.winfo_rooty() + (app.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

        username = str(user.get("username", ""))
        courses = user.get("selected", [])
        gaps = user.get("gaps", [])
        remaining_to_select = sum(
            int(gap.get("remaining_to_select", 0)) for gap in gaps
        )
        pending_count = int(user.get("pending_assessment_count", 0))
        passed_count = int(user.get("passed_selected_count", 0))

        header = tk.Frame(self, bg=BG, padx=px(22), pady=px(16))
        header.pack(fill="x")
        title_row = tk.Frame(header, bg=BG)
        title_row.pack(fill="x")
        tk.Label(
            title_row,
            text=app.tf("账号状态 · {username}", username=username),
            bg=BG,
            fg=INK,
            font=(FONT_UI, 15, "bold"),
            anchor="w",
        ).pack(side="left")
        if user.get("requirements_met"):
            status_text = app.t("要求已完成")
            status_bg = GREEN_SOFT
            status_fg = GREEN
        elif remaining_to_select > 0:
            status_text = app.tf(
                "还需选 {count} 门",
                count=remaining_to_select,
            )
            status_bg = AMBER_SOFT
            status_fg = AMBER
        else:
            status_text = app.t("等待考核结果")
            status_bg = ACCENT_SOFT
            status_fg = ACCENT_DARK
        tk.Label(
            title_row,
            text=status_text,
            bg=status_bg,
            fg=status_fg,
            font=(FONT_UI, 8, "bold"),
            padx=px(9),
            pady=px(4),
        ).pack(side="right")
        tk.Label(
            header,
            text=app.t(
                "人工选择与机器选择会分别标记；常规签到课程不会由程序修改或签到。"
            ),
            bg=BG,
            fg=MUTED,
            font=(FONT_UI, 8),
            anchor="w",
            wraplength=px(1000),
            justify="left",
        ).pack(fill="x", pady=(px(5), 0))
        available = int(user.get("open_needed_candidate_count", 0))
        full_open = int(user.get("full_needed_candidate_count", 0))
        next_open = user.get("next_needed_candidate_at")
        live_course_data_ready = bool(
            user.get("live_course_data_ready", True)
        )
        if not live_course_data_ready:
            candidate_text = app.t(
                "实时课程目录暂未刷新；自动选课会使用缓存候选逐门实时复核。"
            )
            candidate_fg = RED
        elif available:
            candidate_text = app.tf(
                "当前有 {available} 门符合缺口的自主签到课程可选",
                available=available,
            )
            candidate_fg = GREEN
        elif full_open:
            candidate_text = app.tf(
                "开放中的缺口课程已满额：{full} 门",
                full=full_open,
            )
            candidate_fg = AMBER
        elif next_open:
            candidate_text = app.tf(
                "下一门符合缺口的自主签到课程开放时间：{time}",
                time=next_open,
            )
            candidate_fg = ACCENT_DARK
        else:
            candidate_text = app.t(
                "当前没有符合缺口且开放的自主签到课程，后台会继续巡检。"
            )
            candidate_fg = MUTED
        tk.Label(
            header,
            text=candidate_text,
            bg=BG,
            fg=candidate_fg,
            font=(FONT_UI, 8, "bold"),
            anchor="w",
            wraplength=px(1000),
            justify="left",
        ).pack(fill="x", pady=(px(5), 0))
        updated_at = app.snapshot.get("status_updated_at")
        courses_updated_at = app.snapshot.get("courses_updated_at")
        tk.Label(
            header,
            text=(
                app.tf(
                    "数据更新时间：{time}",
                    time=updated_at or app.t("尚未同步"),
                )
                + "  ·  "
                + app.tf(
                    "课程目录更新时间：{time}",
                    time=courses_updated_at or app.t("尚未同步"),
                )
            ),
            bg=BG,
            fg=FAINT,
            font=(FONT_UI, 7),
            anchor="w",
        ).pack(fill="x", pady=(px(4), 0))
        if account_requires_sign_in(user):
            tk.Label(
                header,
                text=app.t(
                    "账号登录已失效，当前显示的是上次缓存。请点击“重新登录”并完成验证码。"
                ),
                bg=RED_SOFT,
                fg=RED,
                font=(FONT_UI, 8, "bold"),
                anchor="w",
                padx=px(8),
                pady=px(5),
            ).pack(fill="x", pady=(px(5), 0))

        summary = tk.Frame(self, bg=BG)
        summary.pack(fill="x", padx=px(22), pady=(0, px(10)))
        for index in range(4):
            summary.grid_columnconfigure(index, weight=1)
        summary_values = [
            ("已选", user.get("selected_count", 0), ACCENT),
            ("已通过", passed_count, GREEN),
            ("待考核", pending_count, AMBER),
            ("需选择", remaining_to_select, RED if remaining_to_select else GREEN),
        ]
        for index, (label, value, color) in enumerate(summary_values):
            item = Card(summary, padx=px(12), pady=px(8))
            item.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else px(4), 0 if index == 3 else px(4)),
            )
            tk.Label(
                item,
                text=app.t(label),
                bg=CARD,
                fg=MUTED,
                font=(FONT_UI, 8),
            ).pack(anchor="w")
            tk.Label(
                item,
                text=str(value),
                bg=CARD,
                fg=color,
                font=(FONT_UI, 16, "bold"),
            ).pack(anchor="w")

        category_card = Card(self, padx=px(8), pady=px(8))
        category_card.pack(
            fill="x",
            padx=px(22),
            pady=(0, px(8)),
        )
        tk.Label(
            category_card,
            text=app.t("类别要求"),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=px(5), pady=(0, px(4)))
        category_columns = (
            "category",
            "required",
            "selected",
            "passed",
            "pending",
            "failed",
            "to_select",
        )
        category_tree = ttk.Treeview(
            category_card,
            columns=category_columns,
            show="headings",
            height=4,
        )
        category_headings = {
            "category": "类别",
            "required": "要求",
            "selected": "已选",
            "passed": "已通过",
            "pending": "待考核",
            "failed": "未通过",
            "to_select": "需选择",
        }
        for column in category_columns:
            category_tree.heading(
                column,
                text=app.t(category_headings[column]),
            )
            category_tree.column(
                column,
                width=px(135 if column != "category" else 180),
                anchor="center" if column != "category" else "w",
            )
        category_tree.pack(fill="x")
        for gap in gaps:
            category_tree.insert(
                "",
                "end",
                values=(
                    app.t(str(gap.get("category", ""))),
                    gap.get("required", 0),
                    gap.get("selected", 0),
                    gap.get("completed", 0),
                    gap.get("pending", 0),
                    gap.get("failed", 0),
                    gap.get("remaining_to_select", 0),
                ),
            )

        upcoming = user.get("upcoming_candidates", [])
        upcoming_card = Card(self, padx=px(8), pady=px(8))
        upcoming_card.pack(
            fill="x",
            padx=px(22),
            pady=(0, px(8)),
        )
        tk.Label(
            upcoming_card,
            text=app.t("未来开放的自主签到课程"),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 9, "bold"),
            anchor="w",
        ).pack(fill="x", padx=px(5), pady=(0, px(4)))
        upcoming_columns = (
            "course",
            "category",
            "campus",
            "window",
            "course_start",
            "remaining",
        )
        upcoming_tree = ttk.Treeview(
            upcoming_card,
            columns=upcoming_columns,
            show="headings",
            height=3,
        )
        upcoming_headings = {
            "course": "课程",
            "category": "类别",
            "campus": "校区",
            "window": "选课开放",
            "course_start": "课程开始",
            "remaining": "余量",
        }
        for column in upcoming_columns:
            upcoming_tree.heading(
                column,
                text=app.t(upcoming_headings[column]),
            )
            upcoming_tree.column(
                column,
                width=px(
                    290
                    if column == "course"
                    else 125
                    if column in {"category", "campus", "remaining"}
                    else 190
                ),
                anchor="center" if column != "course" else "w",
            )
        upcoming_tree.pack(fill="x")
        if not upcoming:
            upcoming_tree.insert(
                "",
                "end",
                values=(app.t("暂无符合条件的未来课程"),) + ("",) * 5,
            )
        else:
            def short_time(value: str | None) -> str:
                if not value:
                    return "—"
                return value[5:16] if len(value) >= 16 else value

            for course in upcoming:
                remaining = course.get("remaining")
                upcoming_tree.insert(
                    "",
                    "end",
                    values=(
                        course.get("name", ""),
                        app.t(str(course.get("category", ""))),
                        " / ".join(
                            app.t(part.strip())
                            for part in str(course.get("campus", "")).split("/")
                            if part.strip()
                        )
                        or "—",
                        (
                            f"{short_time(course.get('select_start'))} → "
                            f"{short_time(course.get('select_end'))}"
                        ),
                        short_time(course.get("course_start")),
                        remaining if remaining is not None else "—",
                    ),
                )

        card = Card(self, padx=px(8), pady=px(8))
        card.pack(fill="both", expand=True, padx=px(22), pady=(0, px(10)))
        columns = (
            "course",
            "category",
            "attendance",
            "origin",
            "assessment",
            "score",
            "time",
        )
        tree = ttk.Treeview(card, columns=columns, show="headings")
        headings = {
            "course": "课程",
            "category": "类别",
            "attendance": "签到方式",
            "origin": "选课来源",
            "assessment": "考核结果",
            "score": "成绩",
            "time": "课程时间",
        }
        widths = {
            "course": 250,
            "category": 105,
            "attendance": 130,
            "origin": 100,
            "assessment": 110,
            "score": 70,
            "time": 190,
        }
        for column in columns:
            tree.heading(column, text=app.t(headings[column]))
            tree.column(
                column,
                width=px(widths[column]),
                minwidth=px(60),
                anchor="center" if column != "course" else "w",
            )
        scroll = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        if not courses:
            tree.insert("", "end", values=(app.t("暂无已选课程"),) + ("",) * 6)

        def short_time(value: str | None) -> str:
            if not value:
                return "—"
            return value[5:16] if len(value) >= 16 else value

        assessment_labels = {
            "passed": "考核通过",
            "not_passed": "未通过",
            "pending": "待考核",
            "pending_result": "待公布",
        }
        for course in courses:
            tree.insert(
                "",
                "end",
                values=(
                    course.get("name", ""),
                    app.t(str(course.get("category", ""))),
                    app.t(
                        "自主签到"
                        if course.get("autonomous_sign")
                        else "常规签到"
                    ),
                    app.t(
                        "机器选择"
                        if course.get("origin") == "machine"
                        else "人工选择"
                    ),
                    app.t(
                        assessment_labels.get(
                            str(course.get("assessment_status", "")),
                            "待考核",
                        )
                    ),
                    course.get("score") if course.get("score") is not None else "—",
                    f"{short_time(course.get('start'))}  →  {short_time(course.get('end'))}",
                ),
            )

        footer = tk.Frame(self, bg=BG, padx=px(22))
        footer.pack(fill="x", pady=(0, px(14)))
        FlatButton(
            footer,
            app.t("刷新博雅状态"),
            self._refresh_and_close,
            bg=ACCENT,
            padx=px(16),
            pady=px(8),
        ).pack(side="left")
        FlatButton(
            footer,
            app.t("关闭"),
            self.destroy,
            bg="#E8EDF6",
            fg=INK,
            hover="#DDE4EF",
            padx=px(18),
            pady=px(8),
        ).pack(side="right")

    def _refresh_and_close(self) -> None:
        self.app._manual_refresh()
        self.destroy()


class BoyaApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        global UI_SCALE
        UI_SCALE = min(1.5, max(1.0, self.winfo_screenwidth() / 2048))
        self.tk.call("tk", "scaling", 1.333 * UI_SCALE)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.store = AutoBoyaStore()
        self.store.init()
        ensure_persistent_ca_bundle(self.store)
        preferences = self.store.load_json("ui-preferences.json", {})
        self.language = (
            preferences.get("language", "zh")
            if isinstance(preferences, dict)
            and preferences.get("language") in {"zh", "en"}
            else _default_language()
        )
        ensure_config_file()
        try:
            self.kit = load_config()
        except Exception:
            self.kit = KitConfig()
        self.snapshot: dict = {"users": [], "dry_run": self.kit.dry_run}
        self.worker: dict[str, object] = {"running": False, "stopping": False, "pid": None}
        self._snapshot_key = ""
        self._closed = False
        self._busy: set[str] = set()
        self._auth_prompted: set[str] = set()
        self._batch_login_active = False
        self._batch_login_current = 0
        self._batch_login_total = 0
        self._toast_after: str | None = None
        self.current_page = "dashboard"

        self._configure_window()
        self._configure_styles()
        self._build_shell()
        self._show_page("dashboard")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(80, self._drain_events)
        self.after(250, self._refresh_visuals, True)
        self.after(1200, self._auto_refresh_if_stale)
        self.after(2200, self._periodic_refresh)

    def _configure_window(self) -> None:
        self.title(self.t("博雅自动助手"))
        self.configure(bg=BG)
        self.minsize(px(1050), px(700))
        width, height = px(1220), px(790)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(20, (screen_w - width) // 2)
        y = max(20, (screen_h - height) // 2 - 25)
        self.geometry(f"{width}x{height}+{x}+{y}")
        icon = _asset_path("boya.ico")
        if icon.exists():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=CARD,
            fieldbackground=CARD,
            foreground=INK,
            rowheight=px(42),
            borderwidth=0,
            font=(FONT_UI, 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#F7F9FC",
            foreground=MUTED,
            relief="flat",
            borderwidth=0,
            font=(FONT_UI, 9, "bold"),
            padding=(px(8), px(10)),
        )
        style.map(
            "Treeview",
            background=[("selected", ACCENT_SOFT)],
            foreground=[("selected", INK)],
        )
        style.map("Treeview.Heading", background=[("active", "#F0F3F8")])
        style.configure(
            "TEntry",
            fieldbackground="#F9FBFD",
            foreground=INK,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            padding=px(6),
        )
        style.configure(
            "TCombobox",
            fieldbackground="#F9FBFD",
            foreground=INK,
            bordercolor=LINE,
            arrowcolor=MUTED,
            padding=px(6),
        )
        style.configure(
            "Account.Horizontal.TProgressbar",
            troughcolor="#EDF1F7",
            background=ACCENT,
            borderwidth=0,
            thickness=px(7),
        )
        style.configure(
            "TCheckbutton",
            background=BG,
            foreground=INK,
            font=(FONT_UI, 9),
        )
        style.configure(
            "Vertical.TScrollbar",
            background="#DCE2EC",
            troughcolor=CARD,
            borderwidth=0,
            arrowsize=12,
        )

    def _build_shell(self) -> None:
        self.shell = tk.Frame(self, bg=BG)
        self.shell.pack(fill="both", expand=True)
        self.cache_update_labels: list[tk.Label] = []
        self._build_sidebar(self.shell)
        self.content = tk.Frame(self.shell, bg=BG, padx=px(26), pady=px(20))
        self.content.pack(side="left", fill="both", expand=True)
        self.pages: dict[str, tk.Frame] = {}
        self._build_dashboard_page()
        self._build_accounts_page()
        self._build_settings_page()
        self._build_logs_page()

    def _build_sidebar(self, parent: tk.Frame) -> None:
        sidebar = tk.Frame(parent, bg=SIDEBAR, width=px(224))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=SIDEBAR, padx=px(20), pady=px(22))
        brand.pack(fill="x")
        logo = tk.Label(
            brand,
            text="博" if self.language == "zh" else "B",
            bg=ACCENT,
            fg="#FFFFFF",
            width=2,
            height=1,
            font=(FONT_UI, 16, "bold"),
        )
        logo.pack(side="left")
        brand_text = tk.Frame(brand, bg=SIDEBAR)
        brand_text.pack(side="left", padx=(10, 0))
        tk.Label(
            brand_text,
            text=self.t("博雅自动助手"),
            bg=SIDEBAR,
            fg="#FFFFFF",
            font=(FONT_UI, 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            brand_text,
            text="BOYA DESKTOP",
            bg=SIDEBAR,
            fg="#7281A0",
            font=(FONT_MONO, 7),
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        tk.Frame(sidebar, bg="#22314F", height=1).pack(
            fill="x", padx=px(18), pady=(0, px(18))
        )
        self.nav_buttons: dict[str, tk.Button] = {}
        items = [
            ("dashboard", "总览", "概览与运行控制"),
            ("accounts", "账号管理", "批量账号与登录"),
            ("settings", "运行设置", "节奏、模式与自启"),
            ("logs", "运行日志", "查看后台动态"),
        ]
        for key, label, caption in items:
            button = tk.Button(
                sidebar,
                text=f"  {self.t(label)}\n  {self.t(caption)}",
                command=lambda page=key: self._show_page(page),
                bg=SIDEBAR,
                fg="#AAB5CB",
                activebackground=SIDEBAR_ACTIVE,
                activeforeground="#FFFFFF",
                relief="flat",
                bd=0,
                anchor="w",
                justify="left",
                padx=px(14),
                pady=px(10),
                cursor="hand2",
                font=(FONT_UI, 9),
            )
            button.pack(fill="x", padx=px(12), pady=px(2))
            self.nav_buttons[key] = button

        sidebar_bottom = tk.Frame(sidebar, bg=SIDEBAR, padx=px(18), pady=px(18))
        sidebar_bottom.pack(side="bottom", fill="x")
        language_text = "中文" if self.language == "en" else "English"
        FlatButton(
            sidebar_bottom,
            language_text,
            self._toggle_language,
            bg="#1B2B4C",
            fg="#D6DFF0",
            hover="#263A61",
            padx=px(12),
            pady=px(8),
            font_size=8,
        ).pack(fill="x", pady=(0, px(9)))
        status_box = tk.Frame(
            sidebar_bottom,
            bg=SIDEBAR_ACTIVE,
            padx=px(12),
            pady=px(11),
        )
        status_box.pack(fill="x")
        self.sidebar_dot = tk.Label(
            status_box,
            text="●",
            bg=SIDEBAR_ACTIVE,
            fg="#71809D",
            font=(FONT_UI, 9),
        )
        self.sidebar_dot.pack(side="left")
        self.sidebar_status = tk.Label(
            status_box,
            text=self.t("后台未运行"),
            bg=SIDEBAR_ACTIVE,
            fg="#D4DBE8",
            font=(FONT_UI, 8, "bold"),
            anchor="w",
        )
        self.sidebar_status.pack(side="left", padx=(5, 0), fill="x", expand=True)
        tk.Label(
            sidebar_bottom,
            text=self.t("关闭窗口不会中断后台任务"),
            bg=SIDEBAR,
            fg="#687795",
            font=(FONT_UI, 7),
        ).pack(anchor="w", pady=(10, 0))

    def _page_header(
        self,
        page: tk.Frame,
        title: str,
        subtitle: str,
    ) -> tk.Frame:
        header = tk.Frame(page, bg=BG)
        header.pack(fill="x", pady=(0, 18))
        text = tk.Frame(header, bg=BG)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(
            text,
            text=title,
            bg=BG,
            fg=INK,
            font=(FONT_UI, 20, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            text,
            text=subtitle,
            bg=BG,
            fg=MUTED,
            font=(FONT_UI, 9),
            anchor="w",
        ).pack(fill="x", pady=(4, 0))
        actions = tk.Frame(header, bg=BG)
        actions.pack(side="right")
        return actions

    def t(self, text: str) -> str:
        return translate(text, self.language)

    def tf(self, text: str, **values: object) -> str:
        return format_text(text, self.language, **values)

    def _toggle_language(self) -> None:
        self.language = "en" if self.language == "zh" else "zh"
        self.store.save_json("ui-preferences.json", {"language": self.language})
        current_page = self.current_page
        self.title(self.t("博雅自动助手"))
        self._snapshot_key = ""
        self.shell.destroy()
        self._build_shell()
        self._show_page(current_page)
        self._refresh_visuals(True)
        message = (
            "语言已切换为 English"
            if self.language == "en"
            else "语言已切换为中文"
        )
        self.show_toast(self.t(message), "info")

    def _build_dashboard_page(self) -> None:
        page = tk.Frame(self.content, bg=BG)
        self.pages["dashboard"] = page
        actions = self._page_header(
            page,
            self.t("总览"),
            self.t("登录账号、开始任务，然后让后台安静地处理博雅选课与签到。"),
        )
        self._add_cache_update_label(actions)
        FlatButton(
            actions,
            self.t("同步数据"),
            self._manual_refresh,
            bg="#E8EDF6",
            fg=INK,
            hover="#DDE4EF",
            padx=16,
            pady=8,
        ).pack(side="right", padx=(8, 0))

        hero = tk.Frame(page, bg=SIDEBAR, padx=24, pady=20)
        hero.pack(fill="x")
        hero_left = tk.Frame(hero, bg=SIDEBAR)
        hero_left.pack(side="left", fill="both", expand=True)
        tk.Label(
            hero_left,
            text=self.t("让博雅任务安静地完成"),
            bg=SIDEBAR,
            fg="#FFFFFF",
            font=(FONT_UI, 18, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            hero_left,
            text=self.t("按账号分别识别缺口，自动选课并处理签到 / 签退。"),
            bg=SIDEBAR,
            fg="#ADB8CC",
            font=(FONT_UI, 9),
            anchor="w",
        ).pack(fill="x", pady=(6, 15))
        hero_buttons = tk.Frame(hero_left, bg=SIDEBAR)
        hero_buttons.pack(anchor="w")
        FlatButton(
            hero_buttons,
            self.t("开始自动运行"),
            self._start_automation,
            bg="#1BAD7C",
            hover="#159469",
            padx=19,
            pady=9,
        ).pack(side="left")
        FlatButton(
            hero_buttons,
            self.t("停止后台"),
            self._stop_automation,
            bg="#243452",
            fg="#E4EAF5",
            hover="#2E4164",
            padx=18,
            pady=9,
        ).pack(side="left", padx=(10, 0))

        hero_right = tk.Frame(hero, bg="#162440", padx=22, pady=15)
        hero_right.pack(side="right", padx=(30, 0))
        self.hero_status_label = tk.Label(
            hero_right,
            text=self.t("●  后台未运行"),
            bg="#162440",
            fg="#A6B1C5",
            font=(FONT_UI, 10, "bold"),
            anchor="w",
        )
        self.hero_status_label.pack(fill="x")
        self.hero_status_detail = tk.Label(
            hero_right,
            text=self.t("点击左侧按钮开始"),
            bg="#162440",
            fg="#75839E",
            font=(FONT_UI, 8),
            anchor="w",
            wraplength=px(225),
            justify="left",
        )
        self.hero_status_detail.pack(fill="x", pady=(7, 0))
        tk.Label(
            hero_right,
            text=self.t("窗口可关闭 · 后台继续工作"),
            bg="#162440",
            fg="#557099",
            font=(FONT_UI, 7),
            anchor="w",
        ).pack(fill="x", pady=(10, 0))

        self.dashboard_auth_slot = tk.Frame(page, bg=BG)
        self.dashboard_auth_slot.pack(fill="x")

        metrics = tk.Frame(page, bg=BG)
        metrics.pack(fill="x", pady=12)
        for index in range(3):
            metrics.grid_columnconfigure(index, weight=1)
        self.metric_values: dict[str, tk.Label] = {}
        metric_specs = [
            ("accounts", "已启用账号", ACCENT, "批量运行"),
            ("needed", "待选课程", AMBER, "统计空缺"),
            ("selected", "已选课程", GREEN, "跟踪签到签退"),
        ]
        for column, (key, title, color, hint) in enumerate(metric_specs):
            card = Card(metrics, padx=17, pady=13)
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 6, 0 if column == 2 else 6),
            )
            tk.Frame(card, bg=color, width=4, height=40).pack(
                side="left", fill="y", padx=(0, 12)
            )
            labels = tk.Frame(card, bg=CARD)
            labels.pack(side="left", fill="both", expand=True)
            tk.Label(
                labels,
                text=self.t(title),
                bg=CARD,
                fg=MUTED,
                font=(FONT_UI, 8),
                anchor="w",
            ).pack(fill="x")
            value = tk.Label(
                labels,
                text="0",
                bg=CARD,
                fg=INK,
                font=(FONT_UI, 20, "bold"),
                anchor="w",
            )
            value.pack(fill="x", pady=(1, 0))
            tk.Label(
                labels,
                text=self.t(hint),
                bg=CARD,
                fg=FAINT,
                font=(FONT_UI, 7),
                anchor="w",
            ).pack(fill="x")
            self.metric_values[key] = value

        lower = tk.Frame(page, bg=BG)
        lower.pack(fill="both", expand=True)
        lower.grid_columnconfigure(0, weight=3)
        lower.grid_columnconfigure(1, weight=2)
        lower.grid_rowconfigure(0, weight=1)

        account_card = Card(lower, padx=18, pady=15)
        account_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        title_row = tk.Frame(account_card, bg=CARD)
        title_row.pack(fill="x", pady=(0, 9))
        tk.Label(
            title_row,
            text=self.t("账号进度"),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 11, "bold"),
        ).pack(side="left")
        tk.Button(
            title_row,
            text=self.t("管理账号  ↗"),
            command=lambda: self._show_page("accounts"),
            bg=CARD,
            fg=ACCENT,
            activebackground=CARD,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=(FONT_UI, 8),
        ).pack(side="right")
        self.dashboard_accounts = ScrollableFrame(account_card, bg=CARD)
        self.dashboard_accounts.pack(fill="both", expand=True)

        activity_card = Card(lower, padx=18, pady=15)
        activity_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Label(
            activity_card,
            text=self.t("最近动态"),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 9))
        self.activity_text = tk.Text(
            activity_card,
            bg="#F8FAFD",
            fg="#4B586E",
            relief="flat",
            bd=0,
            padx=11,
            pady=10,
            wrap="word",
            font=(FONT_MONO, 8),
            state="disabled",
            height=8,
        )
        self.activity_text.pack(fill="both", expand=True)

    def _build_accounts_page(self) -> None:
        page = tk.Frame(self.content, bg=BG)
        self.pages["accounts"] = page
        actions = self._page_header(
            page,
            self.t("账号管理"),
            self.t("每个启用账号独立登录、独立统计、独立执行，适合多个账号批量运行。"),
        )
        self._add_cache_update_label(actions)
        FlatButton(
            actions,
            self.t("刷新博雅状态"),
            self._manual_refresh,
            bg="#E8EDF6",
            fg=INK,
            hover="#DDE4EF",
            padx=16,
            pady=8,
        ).pack(side="right", padx=(8, 0))
        FlatButton(
            actions,
            self.t("添加账号"),
            self._open_account_dialog,
            padx=18,
            pady=8,
        ).pack(side="right")

        notice = tk.Frame(page, bg=ACCENT_SOFT, padx=15, pady=11)
        notice.pack(fill="x", pady=(0, 12))
        notice_top = tk.Frame(notice, bg=ACCENT_SOFT)
        notice_top.pack(fill="x")
        tk.Label(
            notice_top,
            text=self.t("批量模式"),
            bg=ACCENT_SOFT,
            fg=ACCENT_DARK,
            font=(FONT_UI, 8, "bold"),
        ).pack(side="left")
        tk.Label(
            notice_top,
            text=self.t("所有标记为“启用”的账号会同时加入后台任务；停用仅暂停该账号。"),
            bg=ACCENT_SOFT,
            fg="#506BAB",
            font=(FONT_UI, 8),
        ).pack(side="left", padx=(9, 0))
        tk.Label(
            notice,
            text=self.t(
                "机器只选自主签到；人工选课不退不改。人工和机器选择的自主签到课程都会自动完成定位签到与签退。"
            ),
            bg=ACCENT_SOFT,
            fg="#506BAB",
            font=(FONT_UI, 8),
            anchor="w",
            justify="left",
            wraplength=px(860),
        ).pack(fill="x", pady=(px(5), 0))

        table_card = Card(page)
        table_card.pack(fill="both", expand=True)
        columns = (
            "username",
            "status",
            "campus",
            "session",
            "origin",
            "needed",
            "selected",
        )
        self.account_tree = ttk.Treeview(
            table_card,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "username": "账号",
            "status": "批量状态",
            "campus": "校区",
            "session": "登录状态",
            "origin": "人工 / 机器",
            "needed": "待补类别",
            "selected": "总数 · 机器/上限",
        }
        widths = {
            "username": 150,
            "status": 85,
            "campus": 75,
            "session": 105,
            "origin": 130,
            "needed": 170,
            "selected": 145,
        }
        for column in columns:
            self.account_tree.heading(column, text=self.t(headings[column]))
            self.account_tree.column(
                column,
                width=px(widths[column]),
                minwidth=px(70),
                anchor="center" if column != "username" else "w",
            )
        scroll = ttk.Scrollbar(
            table_card,
            orient="vertical",
            command=self.account_tree.yview,
        )
        horizontal = ttk.Scrollbar(
            table_card,
            orient="horizontal",
            command=self.account_tree.xview,
        )
        self.account_tree.configure(
            yscrollcommand=scroll.set,
            xscrollcommand=horizontal.set,
        )
        horizontal.pack(side="bottom", fill="x", padx=8, pady=(0, 6))
        self.account_tree.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(8, 0),
            pady=8,
        )
        scroll.pack(side="right", fill="y", pady=8, padx=(0, 6))
        self.account_tree.tag_configure("disabled", foreground="#9AA4B5")
        self.account_tree.tag_configure("auth_required", foreground=RED)
        self.account_tree.bind("<Double-1>", lambda _event: self._login_selected())

        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(12, 0))
        self.account_selection_label = tk.Label(
            toolbar,
            text=self.t("选择一行账号进行操作"),
            bg=BG,
            fg=MUTED,
            font=(FONT_UI, 8),
        )
        self.account_selection_label.pack(side="left")
        FlatButton(
            toolbar,
            self.t("全部停用"),
            lambda: self._set_all_accounts(False),
            bg="#EDF1F7",
            fg=MUTED,
            hover="#E0E6F0",
            padx=13,
            pady=7,
            font_size=8,
        ).pack(side="right", padx=(8, 0))
        FlatButton(
            toolbar,
            self.t("全部启用"),
            lambda: self._set_all_accounts(True),
            bg="#E6F5EF",
            fg=GREEN,
            hover="#D9EDE5",
            padx=13,
            pady=7,
            font_size=8,
        ).pack(side="right", padx=(8, 0))
        FlatButton(
            toolbar,
            self.t("删除"),
            self._delete_selected,
            bg=RED_SOFT,
            fg=RED,
            hover="#F8DDE1",
            padx=13,
            pady=7,
            font_size=8,
        ).pack(side="right", padx=(8, 0))
        FlatButton(
            toolbar,
            self.t("启用 / 停用"),
            self._toggle_selected,
            bg="#EDF1F7",
            fg=INK,
            hover="#E0E6F0",
            padx=13,
            pady=7,
            font_size=8,
        ).pack(side="right", padx=(8, 0))
        FlatButton(
            toolbar,
            self.t("账号状态"),
            self._show_selected_courses,
            bg="#EDF1F7",
            fg=INK,
            hover="#E0E6F0",
            padx=13,
            pady=7,
            font_size=8,
        ).pack(side="right", padx=(8, 0))
        FlatButton(
            toolbar,
            self.t("重新登录"),
            self._login_selected,
            bg=ACCENT,
            padx=13,
            pady=7,
            font_size=8,
        ).pack(side="right", padx=(8, 0))

    def _build_settings_page(self) -> None:
        page = tk.Frame(self.content, bg=BG)
        self.pages["settings"] = page
        self._page_header(
            page,
            self.t("运行设置"),
            self.t("调整巡检频率、并发上限和测试模式。保存后后台下一轮生效。"),
        )
        columns = tk.Frame(page, bg=BG)
        columns.pack(fill="both", expand=True)
        columns.grid_columnconfigure(0, weight=3)
        columns.grid_columnconfigure(1, weight=2)
        columns.grid_rowconfigure(0, weight=1)

        form_card = Card(columns, padx=22, pady=18)
        form_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(
            form_card,
            text=self.t("自动化参数"),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 12, "bold"),
        ).pack(anchor="w", pady=(0, 16))

        self.setting_vars = {
            "poll_seconds": tk.StringVar(),
            "course_refresh_seconds": tk.StringVar(),
            "status_refresh_seconds": tk.StringVar(),
            "max_pending_selected": tk.StringVar(),
            "prefer_categories": tk.StringVar(),
            "exclude_categories": tk.StringVar(),
        }
        self.setting_checks = {
            "only_gap_categories": tk.BooleanVar(),
            "dry_run": tk.BooleanVar(),
            "autostart": tk.BooleanVar(value=autostart_enabled()),
        }
        self._settings_row(
            form_card,
            "巡检间隔（秒）",
            "每次扫描选课与签到窗口的频率，建议 30–120 秒。",
            self.setting_vars["poll_seconds"],
        )
        self._settings_row(
            form_card,
            "课程余量刷新（秒）",
            "直接读取课程开放状态和剩余名额，建议 20–60 秒。",
            self.setting_vars["course_refresh_seconds"],
        )
        self._settings_row(
            form_card,
            "账号状态刷新（秒）",
            "直接读取已选课程、考核结果和统计，建议 60–300 秒。",
            self.setting_vars["status_refresh_seconds"],
        )
        self._settings_row(
            form_card,
            "单账号最多已选",
            "机器已选且未结束的课程达到上限后暂停抢新课；人工选课不计入且不会被修改。",
            self.setting_vars["max_pending_selected"],
        )
        self._settings_row(
            form_card,
            "优先类别",
            "使用中文逗号或英文逗号分隔，例如：德育, 美育。",
            self.setting_vars["prefer_categories"],
        )
        self._settings_row(
            form_card,
            "排除类别",
            "这些类别不会自动选，默认为“其他方面”。",
            self.setting_vars["exclude_categories"],
        )

        checks = tk.Frame(form_card, bg=CARD)
        checks.pack(fill="x", pady=(4, 0))
        self._settings_check(
            checks,
            "只选仍有未完成要求的类别",
            "关闭后会扩大到所有非排除类别的自主签到课。",
            self.setting_checks["only_gap_categories"],
        )
        self._settings_check(
            checks,
            "测试模式（只记录决策，不真实操作）",
            "首次使用建议开启，确认筛选结果后再关闭。",
            self.setting_checks["dry_run"],
        )
        self._settings_check(
            checks,
            "Windows 登录后自动启动后台",
            "无需打开控制台，系统登录后会直接恢复后台巡检。",
            self.setting_checks["autostart"],
        )

        save_row = tk.Frame(form_card, bg=CARD)
        save_row.pack(fill="x", pady=(18, 0))
        FlatButton(
            save_row,
            self.t("保存设置"),
            self._save_settings,
            padx=22,
            pady=9,
        ).pack(side="right")

        side = tk.Frame(columns, bg=BG)
        side.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        safety = Card(side, padx=20, pady=18)
        safety.pack(fill="x")
        tk.Label(
            safety,
            text=self.t("本机与安全"),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 11, "bold"),
        ).pack(anchor="w")
        for text in [
            "密码优先写入 Windows 凭据管理器。",
            "配置文件 config.yaml 不包含密码。",
            "登录会话和缓存位于用户目录 .autoboya。",
            "删除账号不会自动删除系统凭据。",
        ]:
            row = tk.Frame(safety, bg=CARD)
            row.pack(fill="x", pady=(9, 0))
            tk.Label(
                row,
                text="•",
                bg=CARD,
                fg=GREEN,
                font=(FONT_UI, 11, "bold"),
            ).pack(side="left", anchor="n")
            tk.Label(
                row,
                text=self.t(text),
                bg=CARD,
                fg=MUTED,
                font=(FONT_UI, 8),
                wraplength=235,
                justify="left",
            ).pack(side="left", padx=(7, 0), fill="x", expand=True)
        FlatButton(
            safety,
            self.t("打开数据目录"),
            self._open_data_dir,
            bg="#EDF1F7",
            fg=INK,
            hover="#E0E6F0",
            padx=13,
            pady=7,
            font_size=8,
        ).pack(anchor="w", pady=(16, 0))

        tip = tk.Frame(side, bg="#EEF3FF", padx=19, pady=15)
        tip.pack(fill="x", pady=(12, 0))
        tk.Label(
            tip,
            text=self.t("合规提醒"),
            bg="#EEF3FF",
            fg=ACCENT_DARK,
            font=(FONT_UI, 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            tip,
            text=self.t("自动化可能违反学校规定。请确认课程、签到和出勤要求允许后再使用，避免虚假出勤。"),
            bg="#EEF3FF",
            fg="#536A9F",
            font=(FONT_UI, 8),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _settings_row(
        self,
        parent: tk.Frame,
        title: str,
        hint: str,
        variable: tk.StringVar,
    ) -> None:
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", pady=(0, 13))
        labels = tk.Frame(row, bg=CARD)
        labels.pack(side="left", fill="x", expand=True)
        tk.Label(
            labels,
            text=self.t(title),
            bg=CARD,
            fg=INK,
            font=(FONT_UI, 9, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            labels,
            text=self.t(hint),
            bg=CARD,
            fg=FAINT,
            font=(FONT_UI, 7),
            anchor="w",
            wraplength=400,
            justify="left",
        ).pack(fill="x", pady=(2, 0))
        ttk.Entry(
            row,
            textvariable=variable,
            width=24,
            font=(FONT_UI, 9),
        ).pack(side="right", padx=(18, 0), ipady=4)

    def _settings_check(
        self,
        parent: tk.Frame,
        title: str,
        hint: str,
        variable: tk.BooleanVar,
    ) -> None:
        item = tk.Frame(parent, bg=CARD)
        item.pack(fill="x", pady=(2, 9))
        check = tk.Checkbutton(
            item,
            text=self.t(title),
            variable=variable,
            bg=CARD,
            fg=INK,
            activebackground=CARD,
            selectcolor=ACCENT_SOFT,
            font=(FONT_UI, 9, "bold"),
            bd=0,
            anchor="w",
        )
        check.pack(anchor="w")
        tk.Label(
            item,
            text=self.t(hint),
            bg=CARD,
            fg=FAINT,
            font=(FONT_UI, 7),
            anchor="w",
        ).pack(fill="x", padx=(24, 0))

    def _build_logs_page(self) -> None:
        page = tk.Frame(self.content, bg=BG)
        self.pages["logs"] = page
        actions = self._page_header(
            page,
            self.t("运行日志"),
            self.t("显示最近的后台循环、选课、签到和错误记录。"),
        )
        FlatButton(
            actions,
            self.t("打开日志目录"),
            self._open_log_dir,
            bg="#E8EDF6",
            fg=INK,
            hover="#DDE4EF",
            padx=15,
            pady=8,
        ).pack(side="right", padx=(8, 0))
        FlatButton(
            actions,
            self.t("刷新日志"),
            self._refresh_log_text,
            bg="#E8EDF6",
            fg=INK,
            hover="#DDE4EF",
            padx=15,
            pady=8,
        ).pack(side="right")
        log_card = tk.Frame(page, bg="#111B31", padx=2, pady=2)
        log_card.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            log_card,
            bg="#111B31",
            fg="#C9D3E4",
            insertbackground="#FFFFFF",
            relief="flat",
            bd=0,
            padx=17,
            pady=15,
            wrap="word",
            font=(FONT_MONO, 9),
            state="disabled",
        )
        scroll = ttk.Scrollbar(
            log_card,
            orient="vertical",
            command=self.log_text.yview,
        )
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _show_page(self, key: str) -> None:
        self.current_page = key
        for name, page in self.pages.items():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        for name, button in self.nav_buttons.items():
            selected = name == key
            button.configure(
                bg=SIDEBAR_ACTIVE if selected else SIDEBAR,
                fg="#FFFFFF" if selected else "#AAB5CB",
            )
        if key == "settings":
            self._load_settings_form()
        elif key == "accounts":
            self._refresh_accounts_table()
        elif key == "logs":
            self._refresh_log_text()

    def _start_automation(self) -> None:
        users = self.store.user_records()
        enabled = [user for user in users if user.enabled]
        if not users:
            messagebox.showinfo(
                self.t("先添加账号"),
                self.t("还没有博雅账号。先添加账号并完成登录，再开始自动运行。"),
                parent=self,
            )
            self._open_account_dialog()
            return
        if not enabled:
            messagebox.showwarning(
                self.t("没有启用账号"),
                self.t("当前所有账号都已停用，请至少启用一个账号。"),
                parent=self,
            )
            self._show_page("accounts")
            return
        if self.worker.get("running"):
            self.show_toast(self.t("后台已经在运行中"), "info")
            return
        try:
            start_worker(self.store, self.store.path(LOG_FILE))
        except Exception as exc:
            messagebox.showerror(self.t("启动失败"), str(exc), parent=self)
            return
        self.show_toast(
            self.tf("已启动批量后台任务，共 {count} 个账号", count=len(enabled)),
            "success",
        )
        self.after(450, lambda: self._refresh_visuals(True))

    def _stop_automation(self) -> None:
        if not self.worker.get("running"):
            self.show_toast(self.t("后台当前没有运行"), "info")
            return
        if not messagebox.askyesno(
            self.t("停止后台任务"),
            self.t("停止后将不再自动选课、签到或签退。确定停止吗？"),
            parent=self,
        ):
            return
        request_worker_stop(self.store)
        self.show_toast(self.t("正在安全停止后台，请稍候"), "info")
        self.after(500, lambda: self._refresh_visuals(True))

    def _open_account_dialog(self) -> None:
        AccountDialog(self, self._add_account)

    def _add_cache_update_label(self, parent: tk.Widget) -> None:
        label = tk.Label(
            parent,
            text="",
            bg=BG,
            fg=FAINT,
            font=(FONT_UI, 7),
        )
        label.pack(side="right", padx=(0, px(10)))
        self.cache_update_labels.append(label)

    def _add_account(
        self,
        username: str,
        password: str,
        campus: str,
        enabled: bool,
    ) -> None:
        existing = self.store.get_user(username)
        if existing and not messagebox.askyesno(
            self.t("更新账号"),
            self.t("该账号已经存在。是否更新密码和校区并重新登录？"),
            parent=self,
        ):
            return
        self.show_toast(self.t("正在保存凭据并登录，请稍候…"), "info")

        def work() -> None:
            try:
                _record, unsafe = save_account_password(
                    self.store,
                    username,
                    password,
                    campus,
                    enabled=enabled,
                )
                login_account(
                    self.store,
                    username,
                    password,
                    captcha_provider=self._worker_captcha_provider,
                )
                suffix = (
                    self.t("；系统凭据不可用，已改存本机受保护文件")
                    if unsafe
                    else ""
                )
                self.events.put(("login_ok", (username, suffix)))
            except Exception as exc:
                self.events.put(("login_failed", (username, str(exc))))

        self._run_thread(work)

    def _selected_username(self) -> str | None:
        selected = self.account_tree.selection()
        return selected[0] if selected else None

    def _require_selected_username(self) -> str | None:
        username = self._selected_username()
        if not username:
            messagebox.showinfo(
                self.t("先选择账号"),
                self.t("请先在列表中选择一个账号。"),
                parent=self,
            )
            return None
        if username == "__empty__":
            return None
        return username

    def _show_selected_courses(self) -> AccountStatusDialog | None:
        username = self._require_selected_username()
        if not username:
            return None
        user = next(
            (
                item
                for item in self.snapshot.get("users", [])
                if item.get("username") == username
            ),
            None,
        )
        if user:
            return AccountStatusDialog(self, user)
        return None

    def _login_selected(self) -> None:
        username = self._require_selected_username()
        if not username:
            return
        if username in self._busy:
            self.show_toast(self.t("该账号正在操作，请稍候"), "info")
            return
        self._busy.add(username)
        self.show_toast(self.tf("正在登录 {username}…", username=username), "info")

        def work() -> None:
            try:
                password = password_for_account(self.store, username)
                login_account(
                    self.store,
                    username,
                    password,
                    captcha_provider=self._worker_captcha_provider,
                )
                self.events.put(("login_ok", (username, "")))
            except Exception as exc:
                self.events.put(("login_failed", (username, str(exc))))
            finally:
                self._busy.discard(username)

        self._run_thread(work)

    def _login_expired_accounts(self) -> None:
        if self._batch_login_active:
            self.show_toast(
                self.tf(
                    "正在逐个登录失效账号（{current}/{total}）…",
                    current=self._batch_login_current,
                    total=self._batch_login_total,
                ),
                "info",
            )
            return
        usernames = [
            str(user.get("username", ""))
            for user in self.snapshot.get("users", [])
            if account_requires_sign_in(user)
            and str(user.get("username", "")).strip()
        ]
        if not usernames:
            self.show_toast(self.t("当前没有需要重新登录的账号"), "info")
            return
        busy = [username for username in usernames if username in self._busy]
        if busy:
            self.show_toast(
                self.t("有账号正在登录或刷新，请稍后再试"),
                "info",
            )
            return

        self._batch_login_active = True
        self._batch_login_current = 0
        self._batch_login_total = len(usernames)
        self._busy.update(usernames)
        self._render_dashboard()
        self.show_toast(
            self.tf(
                "开始一键登录 {count} 个失效账号，验证码会逐个弹出",
                count=len(usernames),
            ),
            "info",
        )

        def work() -> None:
            results: list[tuple[str, bool, str]] = []
            for index, username in enumerate(usernames, start=1):
                self.events.put(
                    ("batch_login_progress", (index, len(usernames), username))
                )
                try:
                    password = password_for_account(self.store, username)
                    login_account(
                        self.store,
                        username,
                        password,
                        captcha_provider=self._worker_captcha_provider,
                    )
                except Exception as exc:
                    results.append((username, False, str(exc)))
                else:
                    results.append((username, True, ""))
                finally:
                    self._busy.discard(username)
            self.events.put(("batch_login_done", results))

        self._run_thread(work)

    def _toggle_selected(self) -> None:
        username = self._require_selected_username()
        if not username:
            return
        user = self.store.get_user(username)
        if not user:
            return
        set_account_enabled(self.store, username, not user.enabled)
        self._refresh_visuals(True)
        self.show_toast(
            self.tf(
                "{username} 已{status}",
                username=username,
                status=self.t("启用" if not user.enabled else "停用"),
            ),
            "success",
        )

    def _set_all_accounts(self, enabled: bool) -> None:
        users = self.store.user_records()
        if not users:
            return
        if not enabled and not messagebox.askyesno(
            self.t("全部停用"),
            self.t("停用后，这些账号不会参与自动选课和签到。继续吗？"),
            parent=self,
        ):
            return
        for user in users:
            set_account_enabled(self.store, user.username, enabled)
        self._refresh_visuals(True)
        self.show_toast(
            self.tf(
                "已{status}全部账号",
                status=self.t("启用" if enabled else "停用"),
            ),
            "success",
        )

    def _delete_selected(self) -> None:
        username = self._require_selected_username()
        if not username:
            return
        if not messagebox.askyesno(
            self.t("删除账号"),
            self.tf(
                "从程序中删除 {username}？\n\n系统凭据管理器中保存的密码不会被自动清除。",
                username=username,
            ),
            parent=self,
        ):
            return
        self.store.remove_user(username)
        self._refresh_visuals(True)
        self.show_toast(
            self.tf("已删除 {username}", username=username),
            "success",
        )

    def _manual_refresh(self) -> None:
        if self.worker.get("running"):
            request_worker_refresh(self.store)
            self.show_toast(self.t("已通知后台刷新博雅状态"), "info")
            return
        if "refresh" in self._busy:
            return
        self._busy.add("refresh")
        self.show_toast(self.t("正在拉取课程、已选和统计…"), "info")

        def work() -> None:
            try:
                runner = GapAwareRunner(self.store, self.kit)
                runner.refresh_once()
                self.events.put(
                    ("operation_done", ("refresh", self.t("数据同步完成")))
                )
            except Exception as exc:
                self.events.put(("operation_failed", ("refresh", str(exc))))
            finally:
                self._busy.discard("refresh")

        self._run_thread(work)

    def _auto_refresh_if_stale(self) -> None:
        if os.environ.get("BOYA_KIT_DISABLE_AUTO_REFRESH") == "1":
            return
        stats_path = self.store.path("cache/statistics.json")
        try:
            age_seconds = time.time() - stats_path.stat().st_mtime
        except OSError:
            age_seconds = float("inf")
        if age_seconds >= 120:
            self._manual_refresh()

    def _load_settings_form(self) -> None:
        self.setting_vars["poll_seconds"].set(str(self.kit.poll_seconds))
        self.setting_vars["course_refresh_seconds"].set(
            str(self.kit.course_refresh_seconds)
        )
        self.setting_vars["status_refresh_seconds"].set(
            str(self.kit.status_refresh_seconds)
        )
        self.setting_vars["max_pending_selected"].set(
            str(self.kit.max_pending_selected)
        )
        self.setting_vars["prefer_categories"].set(
            "，".join(self.kit.prefer_categories)
        )
        self.setting_vars["exclude_categories"].set(
            "，".join(self.kit.exclude_categories)
        )
        self.setting_checks["only_gap_categories"].set(
            self.kit.only_gap_categories
        )
        self.setting_checks["dry_run"].set(self.kit.dry_run)
        self.setting_checks["autostart"].set(autostart_enabled())

    def _save_settings(self) -> None:
        try:
            poll_seconds = int(self.setting_vars["poll_seconds"].get())
            course_refresh_seconds = int(
                self.setting_vars["course_refresh_seconds"].get()
            )
            status_refresh_seconds = int(
                self.setting_vars["status_refresh_seconds"].get()
            )
            max_pending = int(self.setting_vars["max_pending_selected"].get())
            if not 10 <= poll_seconds <= 3600:
                raise ValueError(self.t("巡检间隔应在 10–3600 秒之间"))
            if not 10 <= course_refresh_seconds <= 300:
                raise ValueError(
                    self.t("课程余量刷新应在 10–300 秒之间")
                )
            if not 30 <= status_refresh_seconds <= 3600:
                raise ValueError(
                    self.t("账号状态刷新应在 30–3600 秒之间")
                )
            if not 1 <= max_pending <= 20:
                raise ValueError(self.t("单账号最多已选应在 1–20 门之间"))
        except ValueError as exc:
            messagebox.showwarning(self.t("设置格式有误"), str(exc), parent=self)
            return

        def split_categories(value: str) -> list[str]:
            normalized = value.replace("，", ",")
            return [item.strip() for item in normalized.split(",") if item.strip()]

        updated = KitConfig(
            username=None,
            campus=self.kit.campus,
            only_gap_categories=self.setting_checks["only_gap_categories"].get(),
            prefer_categories=split_categories(
                self.setting_vars["prefer_categories"].get()
            ),
            exclude_categories=split_categories(
                self.setting_vars["exclude_categories"].get()
            ),
            max_pending_selected=max_pending,
            poll_seconds=poll_seconds,
            refresh_seconds=self.kit.refresh_seconds,
            course_refresh_seconds=course_refresh_seconds,
            status_refresh_seconds=status_refresh_seconds,
            dry_run=self.setting_checks["dry_run"].get(),
        )
        try:
            save_config(updated)
            set_autostart(self.setting_checks["autostart"].get())
        except Exception as exc:
            messagebox.showerror(self.t("保存失败"), str(exc), parent=self)
            return
        self.kit = updated
        self.show_toast(self.t("设置已保存，后台下一轮生效"), "success")

    def _worker_captcha_provider(self, challenge: object) -> str:
        image_path = Path(getattr(challenge, "image_path", "") or "")
        event = threading.Event()
        holder: dict[str, str] = {}
        self.events.put(("captcha", (image_path, event, holder)))
        if not event.wait(600):
            raise RuntimeError(translate("等待验证码超时", self.language))
        return holder.get("value", "")

    def _handle_captcha(self, payload: object) -> None:
        image_path, event, holder = payload
        if self._closed:
            event.set()
            return
        dialog = CaptchaDialog(self, image_path)
        self.wait_window(dialog)
        holder["value"] = dialog.answer
        event.set()

    def _drain_events(self) -> None:
        if self._closed:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "captcha":
                    self._handle_captcha(payload)
                elif kind == "batch_login_progress":
                    current, total, username = payload
                    self._batch_login_current = int(current)
                    self._batch_login_total = int(total)
                    self._render_dashboard()
                    self.show_toast(
                        self.tf(
                            "正在登录 {current}/{total}：{username}",
                            current=current,
                            total=total,
                            username=username,
                        ),
                        "info",
                    )
                elif kind == "batch_login_done":
                    results = payload
                    self._batch_login_active = False
                    self._batch_login_current = 0
                    self._batch_login_total = 0
                    success = sum(1 for _username, ok, _error in results if ok)
                    failed = [
                        (username, error)
                        for username, ok, error in results
                        if not ok
                    ]
                    self._refresh_visuals(True)
                    if failed:
                        details = "\n".join(
                            f"{username}: {error}" for username, error in failed
                        )
                        messagebox.showwarning(
                            self.t("一键登录完成"),
                            self.tf(
                                "成功登录 {success} 个账号，失败 {failed} 个。\n\n失败详情：\n{details}",
                                success=success,
                                failed=len(failed),
                                details=details,
                            ),
                            parent=self,
                        )
                    else:
                        self.show_toast(
                            self.tf(
                                "已重新登录全部 {count} 个失效账号",
                                count=success,
                            ),
                            "success",
                        )
                elif kind == "login_ok":
                    username, suffix = payload
                    self.show_toast(
                        self.tf(
                            "{username} 登录成功{suffix}",
                            username=username,
                            suffix=suffix,
                        ),
                        "success",
                    )
                    self._refresh_visuals(True)
                elif kind == "login_failed":
                    username, error = payload
                    messagebox.showerror(
                        self.t("登录失败"),
                        self.tf(
                            "{username} 登录失败：\n{error}",
                            username=username,
                            error=error,
                        ),
                        parent=self,
                    )
                    self._refresh_visuals(True)
                elif kind == "operation_done":
                    _operation, message = payload
                    self.show_toast(message, "success")
                    self._refresh_visuals(True)
                elif kind == "operation_failed":
                    operation, error = payload
                    operation_label = self.t(
                        "同步数据" if operation == "refresh" else "执行任务"
                    )
                    messagebox.showerror(
                        self.t("操作失败"),
                        self.tf(
                            "{operation}失败：\n{error}",
                            operation=operation_label,
                            error=error,
                        ),
                        parent=self,
                    )
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _periodic_refresh(self) -> None:
        if self._closed:
            return
        self._refresh_visuals(False)
        self.after(2500, self._periodic_refresh)

    def _refresh_visuals(self, force: bool) -> None:
        self.worker = worker_state(self.store)
        self._update_worker_status()
        try:
            payload = status_payload(self.store, self.kit)
            key = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if force or key != self._snapshot_key:
                self.snapshot = payload
                self._snapshot_key = key
                self._render_dashboard()
                self._update_cache_labels()
                if force:
                    self.after(150, self._prompt_auth_issues)
        except Exception:
            pass
        if force:
            self._refresh_accounts_table()
        self._refresh_activity()
        if self.pages.get("logs") and self.pages["logs"].winfo_viewable():
            self._refresh_log_text()

    def _update_cache_labels(self) -> None:
        updated_at = self.snapshot.get("status_updated_at")
        text = self.tf(
            "数据更新时间：{time}",
            time=updated_at or self.t("尚未同步"),
        )
        stale = bool(self.snapshot.get("course_data_stale"))
        if stale:
            text += " · " + self.t(
                "实时课程目录读取中；当前使用缓存候选并逐门复核"
            )
        for label in self.cache_update_labels:
            label.configure(text=text, fg=RED if stale else FAINT)

    def _prompt_auth_issues(self) -> None:
        blocked = [
            user
            for user in self.snapshot.get("users", [])
            if account_requires_sign_in(user)
        ]
        active = {str(user.get("username", "")) for user in blocked}
        self._auth_prompted.intersection_update(active)
        new_accounts = [
            str(user.get("username", ""))
            for user in blocked
            if str(user.get("username", "")) not in self._auth_prompted
        ]
        if not new_accounts:
            return
        self._auth_prompted.update(new_accounts)
        if self.current_page == "accounts" and self.account_tree.exists(new_accounts[0]):
            self.account_tree.selection_set(new_accounts[0])
            self.account_tree.focus(new_accounts[0])
        self.show_toast(
            self.tf(
                "{count} 个账号需要重新登录，请使用总览顶部的一键登录",
                count=len(new_accounts),
            ),
            "error",
        )

    def _update_worker_status(self) -> None:
        running = bool(self.worker.get("running"))
        stopping = bool(self.worker.get("stopping"))
        if running and stopping:
            status = self.t("正在停止")
            color = AMBER
            detail = self.t("正在安全结束当前循环")
            side_text = self.t("后台正在停止")
        elif running:
            status = self.t("后台运行中")
            color = GREEN
            detail = self.tf(
                "PID {pid} · 窗口关闭也不影响任务",
                pid=self.worker.get("pid"),
            )
            side_text = self.t("后台运行中")
        else:
            status = self.t("后台未运行")
            color = "#71809D"
            detail = self.t("点击“开始自动运行”启动")
            side_text = self.t("后台未运行")
        self.hero_status_label.configure(text=f"●  {status}", fg=color)
        self.hero_status_detail.configure(text=detail)
        self.sidebar_dot.configure(fg=color)
        self.sidebar_status.configure(text=side_text)

    def _render_dashboard(self) -> None:
        users = self.snapshot.get("users", [])
        enabled_count = len(users)
        to_select_count = sum(
            int(gap.get("remaining_to_select", 0))
            for user in users
            for gap in user.get("gaps", [])
        )
        selected_count = sum(int(user.get("selected_count", 0)) for user in users)
        self.metric_values["accounts"].configure(text=str(enabled_count))
        self.metric_values["needed"].configure(text=str(to_select_count))
        self.metric_values["selected"].configure(text=str(selected_count))

        for child in self.dashboard_auth_slot.winfo_children():
            child.destroy()
        blocked = [
            user
            for user in users
            if account_requires_sign_in(user)
        ]
        if blocked:
            usernames = [str(user.get("username", "")) for user in blocked]
            alert = tk.Frame(
                self.dashboard_auth_slot,
                bg=RED_SOFT,
                highlightbackground="#F3B8BE",
                highlightthickness=1,
                padx=16,
                pady=11,
            )
            alert.pack(fill="x", pady=(12, 0))
            icon = tk.Label(
                alert,
                text="!",
                bg=RED,
                fg="#FFFFFF",
                font=(FONT_UI, 12, "bold"),
                width=2,
                pady=2,
            )
            icon.pack(side="left", padx=(0, 12))
            alert_text = tk.Frame(alert, bg=RED_SOFT)
            alert_text.pack(side="left", fill="both", expand=True)
            tk.Label(
                alert_text,
                text=self.tf(
                    "{count} 个账号需要重新登录",
                    count=len(blocked),
                ),
                bg=RED_SOFT,
                fg=RED,
                font=(FONT_UI, 10, "bold"),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                alert_text,
                text=self.tf(
                    "{accounts} · 验证码会逐个弹出，完成一个后自动继续下一个",
                    accounts=", ".join(usernames),
                ),
                bg=RED_SOFT,
                fg="#9F3946",
                font=(FONT_UI, 8),
                anchor="w",
                justify="left",
                wraplength=px(780),
            ).pack(fill="x", pady=(3, 0))
            button_text = (
                self.tf(
                    "正在登录 {current}/{total}…",
                    current=self._batch_login_current,
                    total=self._batch_login_total,
                )
                if self._batch_login_active
                else self.tf("一键登录（{count}）", count=len(blocked))
            )
            FlatButton(
                alert,
                button_text,
                self._login_expired_accounts,
                bg=RED,
                hover="#B63D4B",
                padx=16,
                pady=8,
                font_size=9,
            ).pack(side="right", padx=(14, 0))

        for child in self.dashboard_accounts.inner.winfo_children():
            child.destroy()
        if not users:
            empty = tk.Frame(self.dashboard_accounts.inner, bg=CARD, pady=24)
            empty.pack(fill="x")
            tk.Label(
                empty,
                text=self.t("还没有可用账号"),
                bg=CARD,
                fg=INK,
                font=(FONT_UI, 10, "bold"),
            ).pack()
            tk.Label(
                empty,
                text=self.t("添加账号并登录后，这里会显示各类别完成进度。"),
                bg=CARD,
                fg=MUTED,
                font=(FONT_UI, 8),
            ).pack(pady=(5, 10))
            FlatButton(
                empty,
                self.t("添加第一个账号"),
                self._open_account_dialog,
                padx=14,
                pady=7,
                font_size=8,
            ).pack()
            return

        for user in users:
            auth_required = account_requires_sign_in(user)
            item_bg = RED_SOFT if auth_required else "#F8FAFD"
            item = tk.Frame(
                self.dashboard_accounts.inner,
                bg=item_bg,
                highlightbackground=RED if auth_required else item_bg,
                highlightthickness=1 if auth_required else 0,
                padx=12,
                pady=10,
            )
            item.pack(fill="x", pady=(0, 7))
            top = tk.Frame(item, bg=item_bg)
            top.pack(fill="x")
            tk.Label(
                top,
                text=user["username"],
                bg=item_bg,
                fg=RED if auth_required else INK,
                font=(FONT_UI, 9, "bold"),
            ).pack(side="left")
            met = bool(user.get("requirements_met"))
            needed_categories = " / ".join(
                f"{self.t(str(gap.get('category', '')))} ×{gap.get('remaining_to_select', 0)}"
                for gap in user.get("gaps", [])
                if int(gap.get("remaining_to_select", 0)) > 0
            )
            if auth_required:
                status_text = self.t("需重新登录")
                status_bg = RED
                status_fg = "#FFFFFF"
            elif met:
                status_text = self.t("要求已完成")
                status_bg = GREEN_SOFT
                status_fg = GREEN
            elif needed_categories:
                status_text = self.tf(
                    "待补 {categories}",
                    categories=needed_categories,
                )
                status_bg = AMBER_SOFT
                status_fg = AMBER
            elif user.get("gaps"):
                status_text = self.t("等待考核结果")
                status_bg = ACCENT_SOFT
                status_fg = ACCENT_DARK
            else:
                status_text = self.t("等待统计数据")
                status_bg = "#EDF1F7"
                status_fg = MUTED
            tk.Label(
                top,
                text=status_text,
                bg=status_bg,
                fg=status_fg,
                font=(FONT_UI, 7, "bold"),
                padx=7,
                pady=2,
            ).pack(side="right")

            gaps = user.get("gaps", [])
            required = sum(int(gap.get("required", 0)) for gap in gaps)
            completed = sum(int(gap.get("completed", 0)) for gap in gaps)
            progress = 100 if met else (min(100, int(completed * 100 / required)) if required else 0)
            bar_row = tk.Frame(item, bg=item_bg)
            bar_row.pack(fill="x", pady=(8, 0))
            bar = ttk.Progressbar(
                bar_row,
                style="Account.Horizontal.TProgressbar",
                maximum=100,
                value=progress,
            )
            bar.pack(side="left", fill="x", expand=True)
            tk.Label(
                bar_row,
                text=f"{completed}/{required or '—'}  {progress}%",
                bg=item_bg,
                fg=RED if auth_required else MUTED,
                font=(FONT_UI, 7),
            ).pack(side="right", padx=(10, 0))
            valid_count = (
                user.get("valid_count")
                if user.get("valid_count") is not None
                else self.t("未知")
            )
            tk.Label(
                item,
                text=(
                    self.tf(
                        "{campus}校区  ·  已选 {selected} 门  ·  校区有效数 {valid}",
                        campus=self.t(user.get("campus", "")),
                        selected=user.get("selected_count", 0),
                        valid=valid_count,
                    )
                    + "\n"
                    + self.tf(
                        "人工选课 {manual} · 机器选课 {machine} · 自主签到 {autonomous} · 常规签到 {regular}",
                        manual=user.get("manual_selected_count", 0),
                        machine=user.get("machine_selected_count", 0),
                        autonomous=user.get("autonomous_selected_count", 0),
                        regular=user.get("regular_selected_count", 0),
                    )
                    + "\n"
                    + self.tf(
                        "已通过 {passed} 门 · 待考核 {pending} 门",
                        passed=user.get("passed_selected_count", 0),
                        pending=user.get("pending_assessment_count", 0),
                    )
                ),
                bg=item_bg,
                fg="#B25B66" if auth_required else FAINT,
                font=(FONT_UI, 7),
                anchor="w",
            ).pack(fill="x", pady=(5, 0))

    def _refresh_accounts_table(self) -> None:
        if not hasattr(self, "account_tree"):
            return
        selected = self._selected_username()
        for item in self.account_tree.get_children():
            self.account_tree.delete(item)
        snapshot_users = {
            user["username"]: user for user in self.snapshot.get("users", [])
        }
        users = self.store.user_records()
        if not users:
            self.account_tree.insert(
                "",
                "end",
                iid="__empty__",
                values=(
                    self.t("还没有账号，点击右上角“添加账号”"),
                    "—",
                    "—",
                    "—",
                    "—",
                    "—",
                    "—",
                ),
                tags=("disabled",),
            )
            self.account_selection_label.configure(
                text=self.t("添加账号后可进行批量操作")
            )
            return
        for user in users:
            view = snapshot_users.get(user.username, {})
            needed = " / ".join(
                f"{self.t(str(gap.get('category', '')))} ×{gap.get('remaining_to_select', 0)}"
                for gap in view.get("gaps", [])
                if int(gap.get("remaining_to_select", 0)) > 0
            )
            if not needed:
                if user.enabled and view.get("gaps"):
                    needed = self.t("等待考核结果")
                else:
                    needed = self.t("等待统计数据") if user.enabled else "—"
            selected_count = int(view.get("selected_count", 0))
            auth_status = view.get("auth_status")
            manual_count = int(view.get("manual_selected_count", selected_count))
            machine_count = int(view.get("machine_selected_count", 0))
            machine_pending = int(view.get("machine_pending_count", 0))
            if auth_status == "auth_required":
                login_text = "需验证码登录"
            elif auth_status == "login_required" or not session_exists(
                self.store, user.username
            ):
                login_text = "需重新登录"
            elif auth_status == "error":
                login_text = "请求异常"
            else:
                login_text = "已登录"
            self.account_tree.insert(
                "",
                "end",
                iid=user.username,
                values=(
                    user.username,
                    self.t("启用" if user.enabled else "停用"),
                    self.t(user.campus),
                    self.t(login_text),
                    f"{manual_count} / {machine_count}",
                    needed,
                    f"{selected_count} · {machine_pending}/{self.kit.max_pending_selected}",
                ),
                tags=(
                    ("auth_required",)
                    if account_requires_sign_in(view)
                    else ()
                    if user.enabled
                    else ("disabled",)
                ),
            )
        if selected and self.account_tree.exists(selected):
            self.account_tree.selection_set(selected)
        self.account_selection_label.configure(
            text=self.tf("共 {count} 个账号", count=len(users))
        )

    def _refresh_activity(self) -> None:
        if not hasattr(self, "activity_text"):
            return
        text = tail_text(self.store.path(LOG_FILE), 35)
        compact = []
        for line in text.splitlines():
            if not line.strip():
                continue
            line = line.replace('"', "")
            compact.append(line)
        display = "\n".join(compact[-10:]) or self.t("暂无动态")
        self.activity_text.configure(state="normal")
        self.activity_text.delete("1.0", "end")
        self.activity_text.insert("1.0", display)
        self.activity_text.configure(state="disabled")

    def _refresh_log_text(self) -> None:
        if not hasattr(self, "log_text"):
            return
        content = tail_text(self.store.path(LOG_FILE), 300) or self.t(
            "暂无运行日志。登录账号并开始自动运行后，这里会显示实时记录。"
        )
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", content)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _open_data_dir(self) -> None:
        self.store.root.mkdir(parents=True, exist_ok=True)
        os.startfile(self.store.root)

    def _open_log_dir(self) -> None:
        path = self.store.path(LOG_FILE).parent
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def _run_thread(self, target: Callable[[], None]) -> None:
        threading.Thread(target=target, daemon=True).start()

    def show_toast(self, message: str, level: str = "info") -> None:
        color = {
            "success": GREEN,
            "error": RED,
            "info": "#334563",
        }.get(level, "#334563")
        if not hasattr(self, "toast"):
            self.toast = tk.Label(
                self,
                text="",
                fg="#FFFFFF",
                padx=16,
                pady=10,
                font=(FONT_UI, 9, "bold"),
                bd=0,
            )
        if self._toast_after:
            self.after_cancel(self._toast_after)
        self.toast.configure(text=message, bg=color)
        self.toast.place(relx=0.985, rely=0.965, anchor="se")
        self.toast.lift()
        self._toast_after = self.after(3200, self.toast.place_forget)

    def _on_close(self) -> None:
        running = bool(self.worker.get("running"))
        if running and not messagebox.askyesno(
            self.t("关闭控制台"),
            self.t("后台任务仍在运行。关闭窗口不会停止自动选课与签到。\n\n确定关闭控制台吗？"),
            parent=self,
        ):
            return
        self._closed = True
        self.destroy()


def launch_gui() -> None:
    if os.name == "nt":
        try:
            ctypes = __import__("ctypes")
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = BoyaApp()
    app.mainloop()
