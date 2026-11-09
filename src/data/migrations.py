"""按 PRAGMA user_version 幂等补齐 migrations/*.sql。

这是启动期的建表引导，不属于业务写路径；业务写一律经 src/data/tx.py 的 write_tx()。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.data.tx import write_tx


def _statements(script: str):
    buffer = ""
    for char in script:
        buffer += char
        if char == ";" and sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                yield statement
            buffer = ""
    remainder = buffer.strip()
    if remainder:
        yield remainder


def apply_migrations(conn, directory) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for path in sorted(Path(directory).glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version <= current:
            continue
        script = path.read_text(encoding="utf-8")
        with write_tx(conn):
            for statement in _statements(script):
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {version}")
        current = version
