"""全局唯一的事务入口：写事务只能是 BEGIN IMMEDIATE（ADR-001、R2）。"""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def write_tx(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")