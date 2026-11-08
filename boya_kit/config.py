from __future__ import annotations

import sys
from dataclasses import dataclass, field
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

SOURCE_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else SOURCE_ROOT
)
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
EXAMPLE_CONFIG_PATH = SOURCE_ROOT / "config.example.yaml"

RUN_PID_FILE = "run/boya_kit.pid"
STOP_FILE = "run/boya_kit.stop"
REFRESH_REQUEST_FILE = "run/boya_kit.refresh"
LOG_FILE = "logs/boya_kit.log"

DEFAULT_CONFIG_TEXT = """\
# 博雅自动助手本地配置。账号密码不会写在这里。
username: null
campus: 北京
only_gap_categories: true
prefer_categories:
  - 德育
  - 美育
  - 劳动教育
  - 安全健康
exclude_categories:
  - 其他方面
max_pending_selected: 4
poll_seconds: 60
refresh_seconds: 300
course_refresh_seconds: 30
status_refresh_seconds: 60
dry_run: false
"""


@dataclass
class KitConfig:
    username: str | None = None
    campus: str = "北京"
    only_gap_categories: bool = True
    prefer_categories: list[str] = field(default_factory=lambda: ["德育", "美育", "劳动教育", "安全健康"])
    exclude_categories: list[str] = field(default_factory=lambda: ["其他方面"])
    max_pending_selected: int = 4
    poll_seconds: int = 60
    refresh_seconds: int = 300
    course_refresh_seconds: int = 30
    status_refresh_seconds: int = 60
    dry_run: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KitConfig":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        return cls(**payload)


def load_config(path: Path | None = None) -> KitConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        if EXAMPLE_CONFIG_PATH.exists() and path is None:
            return KitConfig()
        raise FileNotFoundError(f"缺少配置文件: {config_path}（可复制 config.example.yaml）")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("config.yaml 必须是映射（字典）")
    return KitConfig.from_dict(raw)


def ensure_config_file(path: Path | None = None) -> Path:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if EXAMPLE_CONFIG_PATH.exists():
            content = EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8")
        else:
            content = DEFAULT_CONFIG_TEXT
        config_path.write_text(content, encoding="utf-8")
    return config_path


def save_config(kit: KitConfig, path: Path | None = None) -> Path:
    """Persist the editable settings without ever adding credentials."""
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(kit)
    content = "# 博雅自动助手本地配置。账号密码不会写在这里。\n"
    content += yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    config_path.write_text(content, encoding="utf-8")
    return config_path
