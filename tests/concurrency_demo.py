"""并发证据现场脚本：`python -m tests.concurrency_demo`（不依赖 pytest）。

每个并发进程在 `Barrier` 后同时 POST 同一组 slot 到同一个运行中的服务进程，
统计 303 / 409 / 5xx 与该组 slot 的最终占用行数。写事务区间由
`LAB_TX_TRACE_DIR` 记录，用来断言两侧确实同时进入写路径，而不是恰好一前一后。
"""

from __future__ import annotations

import http.client
import json
import multiprocessing
import os
import tempfile
import threading
import time
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


def run_phase(*, host, port, credentials, jobs, trace_dir=None):
    """`credentials` 每人一个常驻进程；Barrier 让同轮请求同时发出。"""
    previous_trace = os.environ.get("LAB_TX_TRACE_DIR")
    if trace_dir is not None:
        os.environ["LAB_TX_TRACE_DIR"] = str(trace_dir)
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(len(credentials))
    results = context.Queue()
    processes = [
        context.Process(
            target=_booking_worker,
            args=(host, port, student_no, jobs, barrier, results),
            daemon=True,
        )
        for student_no in credentials
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
        if trace_dir is not None:
            if previous_trace is None:
                os.environ.pop("LAB_TX_TRACE_DIR", None)
            else:
                os.environ["LAB_TX_TRACE_DIR"] = previous_trace

    errors = [outcome for outcome in outcomes if outcome[0] == "error"]
    by_round: dict[int, list[int]] = {}
    for kind, index, code, _body in outcomes:
        if kind == "ok":
            by_round.setdefault(index, []).append(code)
    return {"errors": errors, "by_round": by_round}


def read_trace(trace_dir) -> list[dict]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(Path(trace_dir).glob("*.json"))
    ]
    return sorted(records, key=lambda record: record["enter_ns"])


def intervals_overlap(first: dict, second: dict) -> bool:
    return min(first["exit_ns"], second["exit_ns"]) > max(first["enter_ns"], second["enter_ns"])


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


def start_server():
    import logging

    from app import create_app
    from werkzeug.serving import make_server

    application = create_app()
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    application.logger.setLevel(logging.WARNING)
    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = threading.Thread(target=server.serve_forever, name="lab-http", daemon=True)
    thread.start()
    return server, thread, server.server_port


def stop_server(server, thread) -> None:
    server.shutdown()
    thread.join(timeout=30)


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
    os.environ.setdefault("LAB_SECRET_KEY", "concurrency-demo-secret-" + "0" * 40)
    os.environ.setdefault("LAB_DEFAULT_PASSWORD", "lab-default-2026")
    with tempfile.TemporaryDirectory(prefix="lab-concurrency-") as tmp:
        db_path = Path(tmp) / "lab.db"
        os.environ["LAB_DB_PATH"] = str(db_path)
        credentials = ["2025901", "2025902"]
        prepare_database(db_path, [*credentials, *[f"202591{index:02d}" for index in range(10)]])
        server, thread, port = start_server()
        failures = []
        try:
            print(f"# 服务 http://127.0.0.1:{port}  db={db_path}")
            two_way = build_jobs(rounds=ROUNDS_TWO_WAY, count=2, base_day_offset=1)
            trace_dir = Path(tmp) / "trace-two"
            trace_dir.mkdir()
            os.environ["TEST_CLAIM_HOLD_MS"] = "50"
            started = time.monotonic()
            phase = run_phase(
                host="127.0.0.1",
                port=port,
                credentials=credentials,
                jobs=two_way,
                trace_dir=trace_dir,
            )
            elapsed = time.monotonic() - started
            os.environ.pop("TEST_CLAIM_HOLD_MS", None)
            codes = {tuple(sorted(phase["by_round"].get(job["index"], []))) for job in two_way}
            winners = sum(1 for job in two_way if sorted(phase["by_round"].get(job["index"], [])) == [303, 409])
            print(f"# 2 并发 × {ROUNDS_TWO_WAY} 轮 用时 {elapsed:.2f}s")
            print(f"# 每轮状态集合: {sorted(codes)}  合规轮次: {winners}/{len(two_way)}")
            print(f"# 子进程异常: {phase['errors']}")
            records = read_trace(trace_dir)
            overlaps = sum(
                1
                for index in range(0, len(records) - 1, 2)
                if intervals_overlap(records[index], records[index + 1])
            )
            print(f"# 写事务区间记录 {len(records)} 条，相交轮次 {overlaps}/{len(records) // 2}")
            if phase["errors"] or winners != len(two_way):
                failures.append("2 并发轮次未全部满足 1×303 + 1×409")
            if len(records) != 2 * len(two_way) or overlaps != len(two_way):
                failures.append("写事务区间未在每轮都相交")

            ten_way = build_jobs(rounds=ROUNDS_TEN_WAY, count=2, base_day_offset=6)
            ten_credentials = [f"202591{index:02d}" for index in range(10)]
            phase_ten = run_phase(
                host="127.0.0.1",
                port=port,
                credentials=ten_credentials,
                jobs=ten_way,
            )
            ten_ok = 0
            for job in ten_way:
                codes = phase_ten["by_round"].get(job["index"], [])
                if codes.count(303) == 1 and codes.count(409) == 9 and not any(c >= 500 for c in codes):
                    ten_ok += 1
            print(f"# 10 并发 × {ROUNDS_TEN_WAY} 轮 合规轮次: {ten_ok}/{len(ten_way)}")
            if ten_ok != len(ten_way):
                failures.append("10 并发轮次未全部满足 1×303 + 9×409")

            duplicates = duplicate_keys(db_path)
            print(f"# 全库重复 key: {duplicates}")
            if duplicates:
                failures.append("存在同一 key 的多行占用")
        finally:
            stop_server(server, thread)
        if failures:
            for failure in failures:
                print(f"FAIL: {failure}")
            return 1
        print("OK: 每轮 1 成功 + 1 冲突（或 1+9），无 5xx，无重复 key")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
