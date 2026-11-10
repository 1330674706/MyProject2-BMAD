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


def _trace(
    *,
    enter_ns: int,
    lock_request_ns: int,
    lock_acquired_ns,
    lock_released_ns,
    outcome: str,
) -> None:
    directory = os.environ.get(TRACE_ENV)
    if not directory:
        return
    record = {
        "pid": os.getpid(),
        "thread": threading.get_ident(),
        "enter_ns": enter_ns,
        "lock_request_ns": lock_request_ns,
        "lock_acquired_ns": lock_acquired_ns,
        "lock_released_ns": lock_released_ns,
        "exit_ns": time.monotonic_ns(),
        "outcome": outcome,
    }
    name = f"{record['pid']}-{record['thread']}-{enter_ns}.json"
    try:
        Path(directory, name).write_text(json.dumps(record), encoding="utf-8")
    except OSError:
        pass


def _release(conn, lock_acquired_ns):
    """回滚并记录锁真正交还的时刻；没有拿到锁就没有持锁区间。"""
    if lock_acquired_ns is None:
        return None
    _rollback(conn)
    return time.monotonic_ns()


@contextmanager
def write_tx(conn):
    enter_ns = time.monotonic_ns()
    lock_request_ns = time.monotonic_ns()
    lock_acquired_ns = None
    lock_released_ns = None
    outcome = "rollback"
    try:
        try:
            _begin_immediate(conn)
        except Unavailable:
            outcome = "begin_busy"
            raise
        except BaseException:
            # BEGIN 没拿到锁（也不是忙等耗尽）：没有事务可回滚，记真实原因。
            outcome = "begin_failed"
            raise
        lock_acquired_ns = time.monotonic_ns()
        try:
            hold = _test_hold_seconds()
            if hold:
                _sleep(hold)
            yield conn
        except BaseException:
            outcome = "rollback"
            lock_released_ns = _release(conn, lock_acquired_ns)
            raise
        else:
            try:
                conn.execute("COMMIT")
            except sqlite3.OperationalError as error:
                if _errorname(error) in BUSY_ERRONAMES:
                    outcome = "commit_busy"
                    lock_released_ns = _release(conn, lock_acquired_ns)
                    raise Unavailable(BUSY_MESSAGE) from None
                outcome = "commit_failed"
                lock_released_ns = _release(conn, lock_acquired_ns)
                raise
            except sqlite3.Error:
                # 例如延迟外键在 COMMIT 时抛 IntegrityError：必须显式回滚，
                # 且不得把这次提交记成 commit。
                outcome = "commit_failed"
                lock_released_ns = _release(conn, lock_acquired_ns)
                raise
            except BaseException:
                # 非 sqlite3 异常同样要把事务收干净，不能让连接停在事务里。
                outcome = "commit_failed"
                lock_released_ns = _release(conn, lock_acquired_ns)
                raise
            else:
                outcome = "commit"
                lock_released_ns = time.monotonic_ns()
    finally:
        _trace(
            enter_ns=enter_ns,
            lock_request_ns=lock_request_ns,
            lock_acquired_ns=lock_acquired_ns,
            lock_released_ns=lock_released_ns,
            outcome=outcome,
        )
