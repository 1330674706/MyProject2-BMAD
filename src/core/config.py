"""运行配置只从环境变量读取；缺失即启动失败（§15、ADR-004）。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    """配置不合法；进程必须启动失败，不得回退默认值。"""


@dataclass(frozen=True)
class Config:
    db_path: Path
    secret_key: str
    default_password: str


def load_config(environ=None) -> Config:
    env = os.environ if environ is None else environ

    secret_key = env.get("LAB_SECRET_KEY", "")
    if len(secret_key.encode("utf-8")) < 32:
        raise ConfigError("LAB_SECRET_KEY 必须由环境变量提供且不少于 32 字节")

    default_password = env.get("LAB_DEFAULT_PASSWORD", "")
    if len(default_password) < 8:
        raise ConfigError("LAB_DEFAULT_PASSWORD 必须由环境变量提供且不少于 8 位")

    db_path = Path(env.get("LAB_DB_PATH") or "./data/lab.db")
    return Config(db_path=db_path, secret_key=secret_key, default_password=default_password)