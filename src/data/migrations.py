"""按 PRAGMA user_version 幂等补齐 migrations/*.sql。

这是启动期的建表引导，不属于业务写路径；业务写一律经 src/data/tx.py 的 write_tx()。
"""

from __future__ import annotations

from pathlib import Path


def apply_migrations(conn, directory) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for path in sorted(Path(directory).glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        if version <= current:
            continue
        script = path.read_text(encoding="utf-8")
        conn.executescript(
            f"BEGIN IMMEDIATE;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;"
        )
        current = version