"""Story 2.2 验收测试：冲突整单原子拒绝与并发裁决。

证明分五层，顺序固定（architecture 5.4）：L1 约束存在 -> L2 确定性交错 ->
L3 双进程 HTTP -> L4 真值表 C1-C3 -> L5 原子性。另钉住三条复审边界：
`now` 必须在写事务内取、抢锁耗尽映射 503、禁止进程内锁与 check-then-write。
"""

from __future__ import annotations

import re
import sqlite3
import time
from datetime import timedelta
from pathlib import Path

import pytest

from src.app import booking_service
from src.core.errors import Conflict, Unavailable
from src.core.timeutil import add_days, local_at, local_to_utc, now_utc, utc_to_local
from src.data import db, occupancy_repo
from src.data.tx import write_tx
from tests.concurrency_demo import (
    PASSWORD,
    build_jobs,
    duplicate_keys,
    holder_and_waiter,
    intervals_overlap,
    lock_hold_interval,
    lock_wait_interval,
    occupancy_count,
    prepare_database,
    read_trace,
    run_phase,
    round_pairs,
    slot_group,
    start_servers,
    stop_servers,
)

TRUTH_ROUNDS = 100
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture
def lab_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_SECRET_KEY", "unit-test-secret-key-" + "0123456789abcdef" * 2)
    monkeypatch.setenv("LAB_DEFAULT_PASSWORD", "lab-default-2026")
    monkeypatch.setenv("LAB_DB_PATH", str(tmp_path / "lab.db"))
    return tmp_path / "lab.db"


def connect(db_path):
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def fetch(db_path, sql, params=()):
    connection = connect(db_path)
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def seed_equipment(db_path, equipment_id="E1", open_start="00:00", open_end="23:30"):
    connection = connect(db_path)
    try:
        connection.execute(
            "INSERT INTO equipment (id, name, open_start, open_end, active) VALUES (?, ?, ?, ?, 1)",
            (equipment_id, f"设备{equipment_id}", open_start, open_end),
        )
        connection.commit()
    finally:
        connection.close()


def register_student(db_path, student_no):
    from src.app import auth_service

    connection = db.connect(db_path)
    try:
        auth_service.register(connection, student_no=student_no, password=PASSWORD)
    finally:
        connection.close()


def user_id_of(db_path, student_no):
    rows = fetch(db_path, "SELECT id FROM user WHERE student_no = ?", (student_no,))
    assert rows, f"缺少测试账号 {student_no}"
    return rows[0]["id"]


def day_after(offset_days):
    return utc_to_local(add_days(now_utc(), offset_days)).date().isoformat()


def slot_group_of(day, start_hhmm, count):
    start = local_at(day, start_hhmm)
    return [local_to_utc(start + timedelta(minutes=30 * index)) for index in range(count)]


def csrf_token(client, path):
    body = client.get(path).get_data(as_text=True)
    match = CSRF_PATTERN.search(body)
    assert match is not None, f"{path} 未渲染 csrf_token"
    return match.group(1)


def register(client, student_no):
    return client.post(
        "/register",
        data={
            "student_no": student_no,
            "password": PASSWORD,
            "csrf_token": csrf_token(client, "/register"),
        },
    )


def login(client, student_no):
    return client.post(
        "/login",
        data={
            "student_no": student_no,
            "password": PASSWORD,
            "csrf_token": csrf_token(client, "/login"),
        },
    )


def login_student(app, student_no):
    client = app.test_client()
    assert register(client, student_no).status_code == 303
    assert login(client, student_no).status_code == 303
    return client


def post_booking(client, *, slots, equipment_id="E1", day=None):
    cookie = client.get_cookie("csrf")
    assert cookie is not None, "缺少 csrf cookie"
    return client.post(
        "/bookings",
        data={
            "csrf_token": cookie.value,
            "equipment_id": equipment_id,
            "date": day or day_after(1),
            "slot": list(slots),
        },
    )


def counts(db_path):
    return (
        fetch(db_path, "SELECT COUNT(*) AS n FROM booking")[0]["n"],
        fetch(db_path, "SELECT COUNT(*) AS n FROM occupancy")[0]["n"],
    )


def n_occ_for(db_path, booking_id):
    return fetch(
        db_path, "SELECT COUNT(*) AS n FROM occupancy WHERE booking_id = ?", (booking_id,)
    )[0]["n"]


def occ_slots(db_path, slots):
    placeholders = ", ".join("?" for _ in slots)
    return fetch(
        db_path,
        "SELECT COUNT(*) AS n FROM occupancy"
        f" WHERE equipment_id = 'E1' AND slot_start IN ({placeholders})",
        slots,
    )[0]["n"]


def run_http_phase(db_path, tmp_path, *, rounds, credentials, count, base_day_offset, hold_ms):
    """两个真实 src.serve 进程（不同 LAB_PORT、同一 db）承载全部并发请求。"""
    prepare_database(db_path, credentials)
    trace_dir = tmp_path / f"trace-{rounds}-{len(credentials)}"
    trace_dir.mkdir()
    jobs = build_jobs(rounds=rounds, count=count, base_day_offset=base_day_offset)
    servers = start_servers(db_path, 2, trace_dir=trace_dir, hold_ms=hold_ms, log_dir=tmp_path)
    try:
        phase = run_phase(
            ports=[server.address() for server in servers],
            credentials=credentials,
            jobs=jobs,
        )
        records = read_trace(trace_dir)
    finally:
        stop_servers(servers)
    return phase, jobs, records


def test_unique_index_is_plain_unique_on_equipment_slot(lab_env):
    db.initialize(lab_env)
    connection = connect(lab_env)
    try:
        indexes = [
            row
            for row in connection.execute("PRAGMA index_list('occupancy')").fetchall()
            if row["unique"] == 1
        ]
        assert len(indexes) == 1
        index = indexes[0]
        assert (index["unique"], index["origin"], index["partial"]) == (1, "u", 0)
        assert index["name"] == "sqlite_autoindex_occupancy_1"
        columns = connection.execute(
            "PRAGMA index_info('sqlite_autoindex_occupancy_1')"
        ).fetchall()
        assert [column["name"] for column in columns] == ["equipment_id", "slot_start"]
        ddl = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'occupancy'"
        ).fetchone()["sql"]
    finally:
        connection.close()
    assert "CONSTRAINT uq_occupancy_slot UNIQUE (equipment_id, slot_start)" in ddl


def test_deterministic_interleaving_yields_one_success_and_one_conflict(lab_env):
    db.initialize(lab_env)
    seed_equipment(lab_env)
    slot = slot_group(0, count=1, base_day_offset=1)[0]
    first = db.connect(lab_env)
    second = db.connect(lab_env)
    second.execute("PRAGMA busy_timeout = 250")
    try:
        first.execute("BEGIN IMMEDIATE")
        first.execute(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES ('E1', ?, 'lock', NULL, ?)",
            (slot, now_utc()),
        )

        started = time.monotonic()
        with pytest.raises(sqlite3.OperationalError) as busy:
            second.execute("BEGIN IMMEDIATE")
        elapsed = time.monotonic() - started
        assert busy.value.sqlite_errorname in {"SQLITE_BUSY", "SQLITE_BUSY_SNAPSHOT"}
        assert elapsed < 1.0, f"抢锁失败耗时 {elapsed:.3f}s，超出 1 s 预算"

        first.execute("COMMIT")

        second.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError) as clash:
            second.execute(
                "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
                " VALUES ('E1', ?, 'lock', NULL, ?)",
                (slot, now_utc()),
            )
        assert clash.value.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE"
        second.execute("ROLLBACK")
    finally:
        first.close()
        second.close()

    third = db.connect(lab_env)
    try:
        rows = third.execute(
            "SELECT COUNT(*) FROM occupancy WHERE equipment_id = 'E1' AND slot_start = ?",
            (slot,),
        ).fetchone()[0]
    finally:
        third.close()
    assert rows == 1


def test_two_processes_posting_same_group_yield_one_303_and_one_409(lab_env, tmp_path):
    phase, jobs, records = run_http_phase(
        lab_env,
        tmp_path,
        rounds=100,
        credentials=["2025101", "2025102"],
        count=2,
        base_day_offset=1,
        hold_ms=50,
    )

    assert phase["errors"] == []
    for job in jobs:
        assert sorted(phase["by_round"][job["index"]]) == [303, 409]
        assert occupancy_count(lab_env, job["equipment_id"], job["slots"]) == len(job["slots"])
    assert duplicate_keys(lab_env) == []
    pids = {record["pid"] for record in records}
    assert len(pids) == 2, f"trace 只来自 {len(pids)} 个服务进程，未证明跨进程并发"
    pairs = round_pairs(records)
    assert len(pairs) == len(jobs)
    overlaps = []
    for pair in pairs:
        holder, waiter = holder_and_waiter(pair)
        assert holder["pid"] != waiter["pid"], "同轮两个请求落在同一个服务进程，非跨进程并发"
        overlaps.append(
            intervals_overlap(lock_wait_interval(waiter), lock_hold_interval(holder))
        )
    assert all(overlaps), f"{overlaps.count(False)} 轮输家等锁区间与赢家持锁区间不相交"
    print(
        f"L3 2 并发: rounds={len(jobs)} 状态={sorted({tuple(sorted(v)) for v in phase['by_round'].values()})}"
        f" 等锁/持锁区间相交={sum(overlaps)}/{len(overlaps)}"
    )


def test_ten_concurrent_requests_yield_one_303_and_nine_409(lab_env, tmp_path):
    credentials = [f"202520{index:02d}" for index in range(10)]
    phase, jobs, _records = run_http_phase(
        lab_env,
        tmp_path,
        rounds=20,
        credentials=credentials,
        count=2,
        base_day_offset=6,
        hold_ms=0,
    )

    assert phase["errors"] == []
    for job in jobs:
        codes = phase["by_round"][job["index"]]
        assert (
            codes.count(303),
            codes.count(409),
            sum(1 for code in codes if code >= 500),
        ) == (1, 9, 0)
    assert len(jobs) == 20


def test_no_duplicate_keys_after_concurrent_rounds(lab_env, tmp_path):
    phase, jobs, _records = run_http_phase(
        lab_env,
        tmp_path,
        rounds=3,
        credentials=["2025301", "2025302"],
        count=2,
        base_day_offset=1,
        hold_ms=0,
    )

    assert phase["errors"] == []
    assert duplicate_keys(lab_env) == []
    for job in jobs:
        assert occupancy_count(lab_env, job["equipment_id"], job["slots"]) == 2


def test_taken_third_of_four_returns_409_and_writes_nothing(app, db_path):
    seed_equipment(db_path)
    student = login_student(app, "2025001")
    other = login_student(app, "2025002")
    slots = slot_group_of(day_after(1), "10:00", 4)
    assert post_booking(other, slots=[slots[2]]).status_code == 303
    before = counts(db_path)

    response = post_booking(student, slots=slots)
    body = response.get_data(as_text=True)

    assert response.status_code == 409
    assert slots[2] in body and "E1" in body
    assert counts(db_path) == before
    assert "Traceback" not in body


def test_resubmitting_same_group_returns_409_and_keeps_occupancy(app, db_path):
    seed_equipment(db_path)
    student = login_student(app, "2025001")
    slots = slot_group_of(day_after(1), "14:00", 3)
    assert post_booking(student, slots=slots).status_code == 303
    booking_id = fetch(db_path, "SELECT id FROM booking")[0]["id"]
    before = n_occ_for(db_path, booking_id)

    second = post_booking(student, slots=slots)

    assert second.status_code == 409
    assert n_occ_for(db_path, booking_id) == before == 3


def test_conflict_at_fifth_slot_leaves_first_four_unwritten(app, db_path):
    seed_equipment(db_path)
    student = login_student(app, "2025001")
    other = login_student(app, "2025002")
    slots = slot_group_of(day_after(1), "16:00", 8)
    assert post_booking(other, slots=[slots[4]]).status_code == 303
    before = counts(db_path)

    response = post_booking(student, slots=slots)

    assert response.status_code == 409
    assert slots[4] in response.get_data(as_text=True)
    assert counts(db_path) == before
    assert occ_slots(db_path, slots[:4]) == 0


def test_conflict_page_marks_conflicting_cells_and_keeps_selection(app, db_path):
    seed_equipment(db_path)
    student = login_student(app, "2025001")
    other = login_student(app, "2025002")
    slots = slot_group_of(day_after(1), "09:00", 4)
    assert post_booking(other, slots=[slots[1]]).status_code == 303

    response = post_booking(student, slots=slots)
    body = response.get_data(as_text=True)

    assert response.status_code == 409
    conflicted = re.search(r'<li[^>]*data-slot="%s"[^>]*>' % re.escape(slots[1]), body)
    assert conflicted is not None and 'data-conflict="1"' in conflicted.group(0)
    free = re.search(r'<li[^>]*data-slot="%s"[^>]*>' % re.escape(slots[0]), body)
    assert free is not None and 'data-conflict="0"' in free.group(0)
    assert re.search(r'value="%s"[^>]*checked' % re.escape(slots[0]), body) is not None
    assert "data-conflict-page" not in body, "逐格标脏的 409 不应再叠整页提示"


def test_conflict_page_with_empty_reread_is_a_page_notice_not_blank_grid(app, db_path, monkeypatch):
    """409 且重查为空：整页冲突提示 + 原网格 + 原选择，不再是一屏 data-conflict="0"。"""
    seed_equipment(db_path)
    student = login_student(app, "2025001")
    other = login_student(app, "2025002")
    slots = slot_group_of(day_after(1), "13:00", 3)
    assert post_booking(other, slots=[slots[1]]).status_code == 303
    monkeypatch.setattr(occupancy_repo, "select_taken", lambda conn, equipment_id, slots: [])

    response = post_booking(student, slots=slots)
    body = response.get_data(as_text=True)

    assert response.status_code == 409
    assert 'data-conflict-page="1"' in body
    assert "所选 slot 已被占用" in body
    assert len(re.findall(r'data-slot="', body)) == 47, "整页提示必须保留原网格"
    assert 'data-conflict="0"' not in body
    assert re.search(r'value="%s"[^>]*checked' % re.escape(slots[0]), body) is not None
    other_cell = re.search(r'<li[^>]*data-slot="%s"[^>]*>' % re.escape(slots[1]), body)
    assert other_cell is not None and 'data-state="booked_by_other"' in other_cell.group(0), (
        "整页提示必须基于刷新后的占用状态，而不是旧数据"
    )
    assert "Traceback" not in body


def test_plain_slots_page_has_no_conflict_notice(app, db_path):
    seed_equipment(db_path)
    student = login_student(app, "2025001")

    body = student.get(f"/slots?equipment_id=E1&date={day_after(1)}").get_data(as_text=True)

    assert 'data-slot="' in body
    assert "data-conflict-page" not in body
    assert "提交未完成" not in body
    assert 'data-conflict="0"' in body


def test_serve_reports_app_error_as_startup_failure(monkeypatch, capsys):
    """1.4 的启动契约：AppError（含 Unavailable）必须打印"启动失败："并返回 2。"""
    import src.serve as serve

    def broken_app():
        raise Unavailable("数据库繁忙，请稍后重试")

    monkeypatch.setattr(serve, "create_app", broken_app)
    monkeypatch.setenv("LAB_PORT", "5088")

    code = serve.main()

    captured = capsys.readouterr()
    assert code == 2
    assert captured.err.startswith("启动失败：")
    assert "Traceback" not in captured.err + captured.out


def test_commit_failure_rolls_back_and_traces_commit_failed(lab_env, tmp_path, monkeypatch):
    """COMMIT 抛非 OperationalError 时必须显式 ROLLBACK，且 outcome 不得记为 commit。"""
    db.initialize(lab_env)
    trace_dir = tmp_path / "trace-commit-failed"
    trace_dir.mkdir()
    monkeypatch.setenv("LAB_TX_TRACE_DIR", str(trace_dir))
    connection = db.connect(lab_env)
    try:
        connection.executescript(
            """
            CREATE TABLE parent (id TEXT PRIMARY KEY);
            CREATE TABLE child (
                id        TEXT PRIMARY KEY,
                parent_id TEXT REFERENCES parent(id) DEFERRABLE INITIALLY DEFERRED
            );
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            with write_tx(connection):
                connection.execute(
                    "INSERT INTO child (id, parent_id) VALUES ('c1', 'missing-parent')"
                )
        assert connection.in_transaction is False
        assert connection.execute("SELECT COUNT(*) FROM child").fetchone()[0] == 0
    finally:
        connection.close()

    records = read_trace(trace_dir)
    assert len(records) == 1
    record = records[0]
    assert record["outcome"] == "commit_failed"
    assert record["lock_acquired_ns"] is not None
    assert record["lock_released_ns"] is not None
    assert record["lock_released_ns"] >= record["lock_acquired_ns"]


def attempt_booking(db_path, user_id, slots, equipment_id="E1"):
    connection = db.connect(db_path)
    try:
        booking_service.create_booking(connection, user_id, equipment_id, slots)
        return "ok"
    except Conflict:
        return "conflict"
    finally:
        connection.close()


def truth_rounds(db_path, user_id, *, rounds, short_circuit, monkeypatch):
    if short_circuit:
        monkeypatch.setattr(occupancy_repo, "select_taken", lambda conn, equipment_id, slots: [])
    per_round = []
    for index in range(rounds):
        slots = slot_group(index, count=1, base_day_offset=1)
        outcomes = [attempt_booking(db_path, user_id, slots) for _ in range(2)]
        per_round.append((outcomes.count("ok"), outcomes.count("conflict")))
    return per_round


def truth_fixture(lab_env):
    db.initialize(lab_env)
    seed_equipment(lab_env)
    register_student(lab_env, "2025401")
    return user_id_of(lab_env, "2025401")


def test_truth_table_c1_constraint_and_precheck_give_one_success(lab_env, monkeypatch):
    user_id = truth_fixture(lab_env)
    per_round = truth_rounds(
        lab_env, user_id, rounds=TRUTH_ROUNDS, short_circuit=False, monkeypatch=monkeypatch
    )

    assert len(per_round) == TRUTH_ROUNDS
    assert all(successes == 1 and conflicts == 1 for successes, conflicts in per_round)
    print(
        f"C1 successes={sum(item[0] for item in per_round)} conflicts={sum(item[1] for item in per_round)}"
        f" rounds={len(per_round)}"
    )


def test_truth_table_c2_short_circuited_precheck_still_gives_one_success(lab_env, monkeypatch):
    user_id = truth_fixture(lab_env)
    per_round = truth_rounds(
        lab_env, user_id, rounds=TRUTH_ROUNDS, short_circuit=True, monkeypatch=monkeypatch
    )

    assert all(successes == 1 and conflicts == 1 for successes, conflicts in per_round)
    print(
        f"C2 successes={sum(item[0] for item in per_round)} conflicts={sum(item[1] for item in per_round)}"
        f" rounds={len(per_round)}"
    )


def test_truth_table_c3_dropped_constraint_must_show_two_successes(lab_env, monkeypatch):
    user_id = truth_fixture(lab_env)
    rebuild_without_unique_constraint(lab_env)
    per_round = truth_rounds(
        lab_env, user_id, rounds=TRUTH_ROUNDS, short_circuit=True, monkeypatch=monkeypatch
    )

    for successes, conflicts in per_round:
        assert successes == 2, "C3 未出现 2 次成功：这条对照没有打到唯一约束"
        assert conflicts == 0
    assert duplicate_keys(lab_env) != []
    print(
        f"C3 successes={sum(item[0] for item in per_round)} conflicts={sum(item[1] for item in per_round)}"
        f" rounds={len(per_round)} per_round={sorted({item[0] for item in per_round})}"
    )


def rebuild_without_unique_constraint(db_path):
    connection = db.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            CREATE TABLE occupancy_rebuilt (
                equipment_id TEXT NOT NULL,
                slot_start   TEXT NOT NULL,
                kind         TEXT NOT NULL,
                booking_id   TEXT,
                created_at   TEXT NOT NULL
            );
            INSERT INTO occupancy_rebuilt
                SELECT equipment_id, slot_start, kind, booking_id, created_at FROM occupancy;
            DROP TABLE occupancy;
            ALTER TABLE occupancy_rebuilt RENAME TO occupancy;
            CREATE INDEX idx_occupancy_booking ON occupancy(booking_id);
            """
        )
        unique_indexes = [
            row
            for row in connection.execute("PRAGMA index_list('occupancy')").fetchall()
            if row["unique"] == 1
        ]
    finally:
        connection.close()
    assert unique_indexes == [], "C3 前置未生效：唯一约束仍然存在"


def test_busy_begin_is_retried_then_mapped_to_unavailable(lab_env, tmp_path, monkeypatch):
    db.initialize(lab_env)
    delays = []
    monkeypatch.setattr("src.data.tx._sleep", delays.append, raising=False)
    trace_dir = tmp_path / "trace-busy-begin"
    trace_dir.mkdir()
    monkeypatch.setenv("LAB_TX_TRACE_DIR", str(trace_dir))
    blocker = connect(lab_env)
    blocker.execute("BEGIN IMMEDIATE")
    connection = db.connect(lab_env)
    connection.execute("PRAGMA busy_timeout = 10")
    try:
        with pytest.raises(Unavailable):
            with write_tx(connection):
                pass
        assert delays == [0.02, 0.05]
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 10
    finally:
        connection.close()
        blocker.execute("ROLLBACK")
        blocker.close()

    records = read_trace(trace_dir)
    assert len(records) == 1, "抢锁失败也必须留下 trace，不能静默丢样本"
    record = records[0]
    assert record["outcome"] == "begin_busy"
    assert record["lock_acquired_ns"] is None
    assert record["lock_released_ns"] is None
    assert lock_wait_interval(record) == (record["lock_request_ns"], record["exit_ns"])


def test_busy_write_lock_returns_503_not_500(app, db_path, monkeypatch):
    seed_equipment(db_path)
    student = login_student(app, "2025001")
    slots = slot_group_of(day_after(1), "11:00", 2)

    real_connect = db.connect

    def short_busy_timeout(path):
        connection = real_connect(path)
        connection.execute("PRAGMA busy_timeout = 20")
        return connection

    monkeypatch.setattr(db, "connect", short_busy_timeout)
    monkeypatch.setattr("src.data.tx._sleep", lambda _seconds: None, raising=False)
    blocker = connect(db_path)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        response = post_booking(student, slots=slots)
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()

    assert response.status_code == 503
    assert "Traceback" not in response.get_data(as_text=True)


def test_now_is_read_inside_write_tx(lab_env, monkeypatch):
    truth_fixture(lab_env)
    user_id = user_id_of(lab_env, "2025401")
    observed = []

    def spy_now():
        probe = sqlite3.connect(str(lab_env), timeout=0.05)
        probe.isolation_level = None
        try:
            try:
                probe.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                observed.append(True)
            else:
                observed.append(False)
                probe.execute("ROLLBACK")
        finally:
            probe.close()
        return now_utc()

    monkeypatch.setattr(booking_service, "now_utc", spy_now)
    connection = db.connect(lab_env)
    try:
        booking_service.create_booking(
            connection, user_id, "E1", slot_group(0, count=1, base_day_offset=1)
        )
    finally:
        connection.close()

    assert observed == [True], "now_utc() 必须在 write_tx() 内取，不能在事务外取好再传入"


FORBIDDEN_SQL = ("OR IGNORE", "OR REPLACE", "ON CONFLICT DO NOTHING", "BEGIN DEFERRED")
FORBIDDEN_LOCKS = (
    "threading.lock(",
    "threading.rlock(",
    "threading.semaphore(",
    "fcntl.flock",
    "msvcrt.locking",
)


def test_no_in_process_lock_and_no_ignore_or_replace():
    sources = {path: path.read_text(encoding="utf-8") for path in Path("src").rglob("*.py")}
    for path, text in sources.items():
        upper = text.upper()
        for token in FORBIDDEN_SQL:
            assert token not in upper, f"{path} 出现禁用 SQL：{token}"
        lowered = text.lower()
        for token in FORBIDDEN_LOCKS:
            assert token not in lowered, f"{path} 出现进程内锁：{token}"
    assert "BEGIN IMMEDIATE" in sources[Path("src/data/tx.py")]
