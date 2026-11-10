"""并发证据现场脚本：`python -m tests.concurrency_demo`（不依赖 pytest）。

被测服务是两个真实的 `python -m src.serve` 进程（不同端口、同一 data/lab.db），
每个并发客户端进程在 `Barrier` 后同时 POST 同一组 slot，统计 303 / 409 / 5xx 与
该组 slot 的最终占用行数。`tx.py` 经 `LAB_TX_TRACE_DIR` 记录等锁/持锁区间，
用来断言"输家等锁区间与赢家持锁区间相交"，而不是任意两条整体区间相交。
"""

from __future__ import annotations

import http.client
import json
import multiprocessing
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlencode

from src.app import auth_service
from src.core.errors import Conflict
from src.core.timeutil import add_days, local_at, local_to_utc, now_utc, utc_to_local
from src.data import db

PASSWORD = "lab-concurrency-2026"
EQUIPMENT_ID = "CONC-E1"
OPEN_START = "00:00"
OPEN_END = "23:30"
SLOTS_PER_DAY = 47
PHASE_TIMEOUT_SECONDS = 600
ROUNDS_TWO_WAY = 100
ROUNDS_TEN_WAY = 20
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRET_KEY = "concurrency-demo-secret-" + "0" * 40
DEFAULT_PASSWORD = "lab-default-2026"


def future_day(offset_days: int) -> str:
    """以仓库唯一的时间入口推导未来本地日期，避免测试自己取当前时刻。"""
    return utc_to_local(add_days(now_utc(), offset_days)).date().isoformat()


def slot_group(round_index: int, *, count: int, base_day_offset: int) -> list[str]:
    """为每轮分配互不重叠、对齐、且在 7 天窗口内的连续 slot 组。"""
    groups_per_day = max(1, SLOTS_PER_DAY // count)
    day = future_day(base_day_offset + round_index // groups_per_day)
    start = local_at(day, OPEN_START) + timedelta(
        minutes=30 * (round_index % groups_per_day) * count
    )
    return [local_to_utc(start + timedelta(minutes=30 * offset)) for offset in range(count)]


class Browser:
    """够用的 cookie 客户端：不自动跟随重定向，303 原样返回。"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.cookies: dict[str, str] = {}

    def request(self, method: str, path: str, form: list[tuple[str, str]] | None = None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=60)
        headers = {}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        body = None
        if form is not None:
            body = urlencode(form)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read().decode("utf-8", "replace")
            for name, value in response.getheaders():
                if name.lower() == "set-cookie":
                    pair = value.split(";", 1)[0]
                    cookie_name, _, cookie_value = pair.partition("=")
                    self.cookies[cookie_name.strip()] = cookie_value.strip()
            return response.status, payload
        finally:
            connection.close()

    def csrf(self) -> str:
        return self.cookies.get("csrf", "")

    def login(self, student_no: str) -> int:
        self.request("GET", "/login")
        status, _ = self.request(
            "POST",
            "/login",
            [
                ("student_no", student_no),
                ("password", PASSWORD),
                ("csrf_token", self.csrf()),
            ],
        )
        return status

    def book(self, equipment_id: str, day: str, slots: list[str]) -> tuple[int, str]:
        form = [
            ("csrf_token", self.csrf()),
            ("equipment_id", equipment_id),
            ("date", day),
        ]
        form.extend(("slot", slot) for slot in slots)
        return self.request("POST", "/bookings", form)


def _booking_worker(host, port, student_no, jobs, barrier, results):
    browser = Browser(host, port)
    try:
        status = browser.login(student_no)
        if status != 303:
            results.put(("error", -1, f"login={status}", ""))
            return
        for job in jobs:
            barrier.wait(timeout=PHASE_TIMEOUT_SECONDS)
            code, body = browser.book(job["equipment_id"], job["day"], job["slots"])
            results.put(("ok", job["index"], code, body))
    except BaseException as error:  # noqa: BLE001 - 子进程异常必须带回主进程
        results.put(("error", -1, type(error).__name__, str(error)))


def run_phase(*, ports, credentials, jobs):
    """`credentials` 每人一个常驻进程，按序轮流打点到 `ports` 里的真实服务进程。"""
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(len(credentials))
    results = context.Queue()
    processes = [
        context.Process(
            target=_booking_worker,
            args=(*(ports[index % len(ports)]), student_no, jobs, barrier, results),
            daemon=True,
        )
        for index, student_no in enumerate(credentials)
    ]
    for process in processes:
        process.start()
    outcomes = []
    try:
        expected = len(jobs) * len(credentials)
        for _ in range(expected):
            outcomes.append(results.get(timeout=PHASE_TIMEOUT_SECONDS))
    finally:
        for process in processes:
            process.join(timeout=PHASE_TIMEOUT_SECONDS)
            if process.is_alive():
                process.terminate()
                process.join()

    errors = [outcome for outcome in outcomes if outcome[0] == "error"]
    by_round: dict[int, list[int]] = {}
    for kind, index, code, _body in outcomes:
        if kind == "ok":
            by_round.setdefault(index, []).append(code)
    return {"errors": errors, "by_round": by_round}


def read_trace(trace_dir) -> list[dict]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in Path(trace_dir).glob("*.json")
    ]
    return sorted(records, key=lambda record: record["enter_ns"])


def lock_wait_interval(record) -> tuple[int, int]:
    """输家的等锁区间：从请求 BEGIN IMMEDIATE 到拿到锁（或最终放弃）。"""
    acquired = record.get("lock_acquired_ns")
    return (record["lock_request_ns"], acquired if acquired is not None else record["exit_ns"])


def lock_hold_interval(record) -> tuple[int, int]:
    """赢家的持锁区间：BEGIN IMMEDIATE 返回成功到 COMMIT/ROLLBACK 结束。"""
    return (record["lock_acquired_ns"], record["lock_released_ns"])


def intervals_overlap(first, second) -> bool:
    return min(first[1], second[1]) > max(first[0], second[0])


def holder_and_waiter(pair):
    """同一轮的两条 trace：赢家 outcome == commit，输家必须是回滚。

    只认 `commit` / `rollback` 两种结论；出现 `begin_busy`、`begin_failed`、
    `commit_busy`、`commit_failed` 时说明这一轮无效，直接判失败而不是硬凑配对。
    """
    holders = [record for record in pair if record["outcome"] == "commit"]
    waiters = [record for record in pair if record["outcome"] == "rollback"]
    if len(holders) != 1 or len(waiters) != 1:
        outcomes = [record["outcome"] for record in pair]
        raise AssertionError(f"同轮 trace 无法判定赢家/输家（outcome={outcomes}）：{pair}")
    return holders[0], waiters[0]


def round_pairs(records):
    ordered = sorted(records, key=lambda record: record["enter_ns"])
    if len(ordered) % 2:
        raise AssertionError(f"trace 记录数 {len(ordered)} 不是偶数")
    return [ordered[index : index + 2] for index in range(0, len(ordered), 2)]


def build_jobs(*, rounds, count, base_day_offset, equipment_id=EQUIPMENT_ID):
    jobs = []
    for index in range(rounds):
        slots = slot_group(index, count=count, base_day_offset=base_day_offset)
        jobs.append(
            {
                "index": index,
                "equipment_id": equipment_id,
                "day": utc_to_local(slots[0]).date().isoformat(),
                "slots": slots,
            }
        )
    return jobs


def prepare_database(db_path: Path, student_nos) -> None:
    db.initialize(db_path)
    connection = db.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO equipment (id, name, open_start, open_end, active) VALUES (?, ?, ?, ?, 1)",
            (EQUIPMENT_ID, "并发测试设备", OPEN_START, OPEN_END),
        )
        for student_no in student_nos:
            try:
                auth_service.register(connection, student_no=student_no, password=PASSWORD)
            except Conflict:
                pass
    finally:
        connection.close()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ServeProcess:
    """一个真实 `python -m src.serve` 子进程；`/health` 200 才算可用。"""

    def __init__(self, process, port, log, log_path):
        self.process = process
        self.port = port
        self.log = log
        self.log_path = log_path

    @property
    def host(self) -> str:
        return "127.0.0.1"

    def address(self):
        return (self.host, self.port)

    def log_text(self) -> str:
        try:
            self.log.flush()
            return self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "<no server log>"

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)
        self.log.close()


def serve_env(db_path, port, *, trace_dir=None, hold_ms=None) -> dict[str, str]:
    env = dict(os.environ)
    for name in ("TEST_CLAIM_HOLD_MS", "LAB_TX_TRACE_DIR"):
        env.pop(name, None)
    env.update(
        {
            "LAB_SECRET_KEY": SECRET_KEY,
            "LAB_DEFAULT_PASSWORD": DEFAULT_PASSWORD,
            "LAB_DB_PATH": str(db_path),
            "LAB_HOST": "127.0.0.1",
            "LAB_PORT": str(port),
        }
    )
    if trace_dir is not None:
        env["LAB_TX_TRACE_DIR"] = str(trace_dir)
    if hold_ms:
        env["TEST_CLAIM_HOLD_MS"] = str(hold_ms)
    return env


def _health_ok(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def start_servers(db_path, count=2, *, trace_dir=None, hold_ms=None, log_dir=None, timeout=90.0):
    log_dir = Path(log_dir if log_dir is not None else tempfile.gettempdir())
    servers = []
    try:
        for _ in range(count):
            port = free_port()
            log_path = log_dir / f"serve-{port}.log"
            log = log_path.open("w", encoding="utf-8")
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", "src.serve"],
                    cwd=str(PROJECT_ROOT),
                    env=serve_env(db_path, port, trace_dir=trace_dir, hold_ms=hold_ms),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except BaseException:
                log.close()
                raise
            servers.append(ServeProcess(process, port, log, log_path))
        for server in servers:
            deadline = time.monotonic() + timeout
            while True:
                if server.process.poll() is not None:
                    raise RuntimeError(f"服务进程 :{server.port} 提前退出：{server.log_text()}")
                if _health_ok(server.port):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError(f"服务进程 :{server.port} 未在 {timeout}s 内就绪")
                time.sleep(0.05)
    except BaseException:
        stop_servers(servers)
        raise
    return servers


def stop_servers(servers) -> None:
    for server in servers:
        server.stop()


def occupancy_count(db_path: Path, equipment_id: str, slots) -> int:
    connection = db.connect(db_path)
    try:
        placeholders = ", ".join("?" for _ in slots)
        return connection.execute(
            "SELECT COUNT(*) FROM occupancy"
            f" WHERE equipment_id = ? AND slot_start IN ({placeholders})",
            (equipment_id, *slots),
        ).fetchone()[0]
    finally:
        connection.close()


def duplicate_keys(db_path: Path):
    connection = db.connect(db_path)
    try:
        return connection.execute(
            "SELECT equipment_id, slot_start, COUNT(*) FROM occupancy"
            " GROUP BY 1, 2 HAVING COUNT(*) > 1"
        ).fetchall()
    finally:
        connection.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lab-concurrency-") as tmp:
        db_path = Path(tmp) / "lab.db"
        credentials = ["2025901", "2025902"]
        prepare_database(db_path, [*credentials, *[f"202591{index:02d}" for index in range(10)]])
        trace_dir = Path(tmp) / "trace-two"
        trace_dir.mkdir()
        servers = start_servers(db_path, 2, trace_dir=trace_dir, hold_ms=50, log_dir=Path(tmp))
        failures = []
        try:
            ports = [server.address() for server in servers]
            urls = ", ".join(f"http://{host}:{port}" for host, port in ports)
            print(f"# 服务 {urls}  db={db_path}")
            two_way = build_jobs(rounds=ROUNDS_TWO_WAY, count=2, base_day_offset=1)
            started = time.monotonic()
            phase = run_phase(ports=ports, credentials=credentials, jobs=two_way)
            elapsed = time.monotonic() - started
            codes = {tuple(sorted(phase["by_round"].get(job["index"], []))) for job in two_way}
            winners = sum(
                1 for job in two_way if sorted(phase["by_round"].get(job["index"], [])) == [303, 409]
            )
            print(f"# 2 并发 × {ROUNDS_TWO_WAY} 轮 用时 {elapsed:.2f}s")
            print(f"# 每轮状态集合: {sorted(codes)}  合规轮次: {winners}/{len(two_way)}")
            print(f"# 子进程异常: {phase['errors']}")
            trace_records = read_trace(trace_dir)
            overlaps = sum(
                1
                for pair in round_pairs(trace_records)
                if intervals_overlap(*_wait_versus_hold(pair))
            )
            pairs = len(two_way)
            pids = sorted({record["pid"] for record in trace_records})
            print(
                f"# trace {len(trace_records)} 条，来自 {len(pids)} 个服务进程 {pids}；"
                f"输家等锁区间与赢家持锁区间相交 {overlaps}/{pairs}"
            )
            if phase["errors"] or winners != len(two_way):
                failures.append("2 并发轮次未全部满足 1×303 + 1×409")
            if overlaps != pairs:
                failures.append("等锁/持锁区间未在每轮都相交")
            if len(pids) != 2:
                failures.append(f"trace 只覆盖 {len(pids)} 个服务进程，未证明跨进程并发")

            ten_way = build_jobs(rounds=ROUNDS_TEN_WAY, count=2, base_day_offset=6)
            ten_credentials = [f"202591{index:02d}" for index in range(10)]
            phase_ten = run_phase(ports=ports, credentials=ten_credentials, jobs=ten_way)
            ten_ok = 0
            for job in ten_way:
                round_codes = phase_ten["by_round"].get(job["index"], [])
                if (
                    round_codes.count(303) == 1
                    and round_codes.count(409) == 9
                    and not any(code >= 500 for code in round_codes)
                ):
                    ten_ok += 1
            print(f"# 10 并发 × {ROUNDS_TEN_WAY} 轮 合规轮次: {ten_ok}/{len(ten_way)}")
            if ten_ok != len(ten_way):
                failures.append("10 并发轮次未全部满足 1×303 + 9×409")

            duplicates = duplicate_keys(db_path)
            print(f"# 全库重复 key: {duplicates}")
            if duplicates:
                failures.append("存在同一 key 的多行占用")
        finally:
            stop_servers(servers)
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}")
            return 1
        print("OK: 每轮 1 成功 + 1 冲突（或 1+9），无 5xx，无重复 key，锁区间相交")
        return 0


def _wait_versus_hold(pair):
    holder, waiter = holder_and_waiter(pair)
    return lock_wait_interval(waiter), lock_hold_interval(holder)


if __name__ == "__main__":
    raise SystemExit(main())
