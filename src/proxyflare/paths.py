"""Where Proxyflare keeps its files, so commands work the same from any directory."""

import os
from pathlib import Path

__all__ = ["CONFIG_DIR_ENV", "get_config_dir", "get_env_file", "get_workers_file"]

CONFIG_DIR_ENV = "PROXYFLARE_CONFIG_DIR"


def get_config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_ENV)
    return Path(override).expanduser() if override else Path.home() / ".config" / "proxyflare"


def get_env_file() -> Path:
    return get_config_dir() / ".env"


def get_workers_file() -> Path:
    return get_config_dir() / "workers.json"
