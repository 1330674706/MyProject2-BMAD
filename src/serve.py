"""python -m src.serve：单进程、threaded=True 的唯一启动入口（§15、NFR-2）。"""

from __future__ import annotations

import os
import sqlite3
import sys

from app import create_app
from src.core.config import ConfigError
from src.core.errors import AppError


def main() -> int:
    port_text = os.environ.get("LAB_PORT") or "5000"
    try:
        port = int(port_text)
    except ValueError:
        print(f"启动失败：LAB_PORT 必须是整数，当前为 {port_text!r}", file=sys.stderr)
        return 2
    if not 0 < port <= 65535:
        print(f"启动失败：LAB_PORT 必须在 1-65535 之间，当前为 {port}", file=sys.stderr)
        return 2

    try:
        application = create_app()
    except (AppError, ConfigError, sqlite3.Error, OSError) as error:
        print(f"启动失败：{error}", file=sys.stderr)
        return 2

    host = os.environ.get("LAB_HOST") or "0.0.0.0"
    application.run(host=host, port=port, threaded=True, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
