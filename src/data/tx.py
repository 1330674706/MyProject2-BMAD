"""全局唯一的事务入口：写事务只能是 BEGIN IMMEDIATE（ADR-001、R2）。

抢锁失败（`SQLITE_BUSY`）在进入事务前重试有限次，耗尽后映射为 `Unavailable`（503），
不允许冒泡成 500。`TEST_CLAIM_HOLD_MS` 与 `LAB_TX_TRACE_DIR` 只服务于并发证据：
生产环境不设置这两个变量时，额外开销为零。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from src.core.errors import Unavailable

BUSY_MESSAGE = "数据库繁忙，请稍后重试"
BUSY_RETRY_DELAYS = (0.02, 0.05)
BUSY_ERRONAMES = frozenset({"SQLITE_BUSY", "SQLITE_BUSY_SNAPSHOT"})
TRACE_ENV = "LAB_TX_TRACE_DIR"
HOLD_ENV = "TEST_CLAIM_HOLD_MS"

_sleep = time.sleep


def _errorname(error):
    return getattr(error, "sqlite_errorname", "")


def _test_hold_seconds() -> float:
    try:
        milliseconds = int(os.environ.get(HOLD_ENV, ""))
    except ValueError:
        return 0.0
    return max(0, milliseconds) / 1000


def _begin_immediate(conn) -> None:
    """首试按连接配置的 busy_timeout 等锁；重试只退避、不再等锁。

    这样最坏总等待 = busy_timeout + 20 ms + 50 ms（默认 1.07 s），落在 D4 的
    1.2 s 预算内；超过预算说明出现了慢事务或外部锁，快速失败比无限等待更诚实。
    """
    configured_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    attempts = len(BUSY_RETRY_DELAYS) + 1
    try:
        for attempt in range(attempts):
            try:
                conn.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as error:
                if _errorname(error) not in BUSY_ERRONAMES:
                    raise
                if attempt + 1 == attempts:
                    raise Unavailable(BUSY_MESSAGE) from None
                _sleep(BUSY_RETRY_DELAYS[attempt])
                conn.execute("PRAGMA busy_timeout = 0")
    finally:
        try:
            conn.execute(f"PRAGMA busy_timeout = {int(configured_timeout)}")
        except sqlite3.Error:
            pass


def _rollback(conn) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _trace(enter_ns: int, outcome: str) -> None:
    directory = os.environ.get(TRACE_ENV)
    if not directory:
        return
    record = {
        "pid": os.getpid(),
        "thread": threading.get_ident(),
        "enter_ns": enter_ns,
        "exit_ns": time.monotonic_ns(),
        "outcome": outcome,
    }
    name = f"{record['pid']}-{record['thread']}-{enter_ns}.json"
    try:
        Path(directory, name).write_text(json.dumps(record), encoding="utf-8")
    except OSError:
        pass


@contextmanager
def write_tx(conn):
    enter_ns = time.monotonic_ns()
    outcome = "commit"
    _begin_immediate(conn)
    try:
        hold = _test_hold_seconds()
        if hold:
            _sleep(hold)
        yield conn
    except BaseException:
        outcome = "rollback"
        _rollback(conn)
        raise
    else:
        try:
            conn.execute("COMMIT")
        except sqlite3.OperationalError as error:
            if _errorname(error) in BUSY_ERRONAMES:
                outcome = "busy"
                _rollback(conn)
                raise Unavailable(BUSY_MESSAGE) from None
            outcome = "error"
            _rollback(conn)
            raise
    finally:
        _trace(enter_ns, outcome)
