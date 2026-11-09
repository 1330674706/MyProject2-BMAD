"""Story 1.4：一条命令启动、/health 与设备种子导入（先红后绿）。"""

from __future__ import annotations

import csv
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRET_KEY = "ops-test-secret-key-" + "0123456789abcdef" * 2
DEFAULT_PASSWORD = "lab-default-2026"
HEADER = ["equipment_id", "name", "open_start", "open_end"]
ADMIN_USER = "20260001"
ADMIN_PASSWORD = "admin-seed-2026"
CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_in_use(port):
            return True
        time.sleep(0.05)
    return False


def _base_env(tmp_path: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("LAB_")}
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["LAB_DB_PATH"] = str(tmp_path / "data" / "lab.db")
    return env


def _start_server(tmp_path: Path, *, secret_key: str | None = SECRET_KEY):
    port = _free_port()
    env = _base_env(tmp_path)
    env["LAB_HOST"] = "127.0.0.1"
    env["LAB_PORT"] = str(port)
    env["LAB_DEFAULT_PASSWORD"] = DEFAULT_PASSWORD
    if secret_key is not None:
        env["LAB_SECRET_KEY"] = secret_key
    log_path = tmp_path / "server.log"
    log = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "src.serve"],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return proc, port, log, log_path


def _stop_server(proc: subprocess.Popen, log) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    log.close()


def _log_text(log_path: Path) -> str:
    try:
        return log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "<no server log>"


def _get_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def _run_server_expect_failure(tmp_path: Path, *, secret_key: str | None, password: str | None):
    port = _free_port()
    env = _base_env(tmp_path)
    env["LAB_HOST"] = "127.0.0.1"
    env["LAB_PORT"] = str(port)
    if secret_key is not None:
        env["LAB_SECRET_KEY"] = secret_key
    if password is not None:
        env["LAB_DEFAULT_PASSWORD"] = password
    proc = subprocess.run(
        [sys.executable, "-m", "src.serve"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return proc, port


def _write_seed(tmp_path: Path, rows: list[list[str]]) -> Path:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    path = seed_dir / "equipment.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def _run_seed(tmp_path: Path) -> subprocess.CompletedProcess:
    return _run_seed_with_db(tmp_path, tmp_path / "data" / "lab.db")


def _run_seed_with_db(tmp_path: Path, db_path: Path) -> subprocess.CompletedProcess:
    env = _base_env(tmp_path)
    env["LAB_DB_PATH"] = str(db_path)
    return subprocess.run(
        [sys.executable, "-m", "src.seed"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def _run_seed_with_env(tmp_path: Path, **extra: str) -> subprocess.CompletedProcess:
    env = _base_env(tmp_path)
    env.update(extra)
    return subprocess.run(
        [sys.executable, "-m", "src.seed"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def _equipment_rows(db_path: Path) -> list[tuple[str, str, str, str]]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT id, name, open_start, open_end FROM equipment ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _audit_count(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    finally:
        conn.close()


def _user_rows(db_path: Path) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            "SELECT student_no, role, active, password_hash FROM user ORDER BY student_no"
        ).fetchall()
    finally:
        conn.close()


def _app_for_seeded_db(monkeypatch, db_path: Path):
    from app import create_app

    monkeypatch.setenv("LAB_SECRET_KEY", SECRET_KEY)
    monkeypatch.setenv("LAB_DEFAULT_PASSWORD", DEFAULT_PASSWORD)
    monkeypatch.setenv("LAB_DB_PATH", str(db_path))
    application = create_app()
    application.config.update(TESTING=True)
    return application


def _login(client, student_no: str, password: str):
    match = CSRF_PATTERN.search(client.get("/login").get_data(as_text=True))
    assert match is not None, "登录页未渲染 csrf_token"
    return client.post(
        "/login",
        data={"student_no": student_no, "password": password, "csrf_token": match.group(1)},
    )


def _initialize_db(db_path: Path) -> None:
    from src.data.db import initialize

    db_path.parent.mkdir(parents=True, exist_ok=True)
    initialize(db_path)


def _write_raw_seed(tmp_path: Path, payload: bytes) -> Path:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    path = seed_dir / "equipment.csv"
    path.write_bytes(payload)
    return path


def test_one_command_starts_server_and_health_returns_200(tmp_path):
    proc, port, log, log_path = _start_server(tmp_path)
    try:
        assert _wait_for_port(port), _log_text(log_path)
        assert _get_status(f"http://127.0.0.1:{port}/health") == 200
    finally:
        _stop_server(proc, log)


def test_missing_secret_key_fails_and_never_listens(tmp_path):
    proc, port = _run_server_expect_failure(tmp_path, secret_key=None, password=DEFAULT_PASSWORD)
    assert proc.returncode != 0
    assert "LAB_SECRET_KEY" in (proc.stdout + proc.stderr)
    assert not _port_in_use(port)


def test_missing_default_password_fails_and_never_listens(tmp_path):
    proc, port = _run_server_expect_failure(tmp_path, secret_key=SECRET_KEY, password=None)
    assert proc.returncode != 0
    assert "LAB_DEFAULT_PASSWORD" in (proc.stdout + proc.stderr)
    assert not _port_in_use(port)


def test_seed_imports_equipment_twice_without_duplicates(tmp_path):
    _write_seed(
        tmp_path,
        [
            ["EQ-001", "示波器", "08:00", "22:00"],
            ["EQ-002", "万用表", "09:00", "18:00"],
            ["EQ-003", "直流电源", "08:30", "20:30"],
        ],
    )
    db_path = tmp_path / "data" / "lab.db"

    first = _run_seed(tmp_path)
    second = _run_seed(tmp_path)

    assert (first.returncode, second.returncode) == (0, 0), first.stdout + first.stderr + second.stdout + second.stderr
    assert _equipment_rows(db_path) == [
        ("EQ-001", "示波器", "08:00", "22:00"),
        ("EQ-002", "万用表", "09:00", "18:00"),
        ("EQ-003", "直流电源", "08:30", "20:30"),
    ]
    assert _audit_count(db_path) == 3


def test_seed_upserts_existing_equipment_id(tmp_path):
    _write_seed(tmp_path, [["EQ-001", "旧名称", "08:00", "22:00"]])
    db_path = tmp_path / "data" / "lab.db"
    assert _run_seed(tmp_path).returncode == 0

    _write_seed(tmp_path, [["EQ-001", "新名称", "09:00", "21:00"]])
    assert _run_seed(tmp_path).returncode == 0

    assert _equipment_rows(db_path) == [("EQ-001", "新名称", "09:00", "21:00")]


def test_seed_reports_line_number_and_rolls_back_whole_file(tmp_path):
    _write_seed(
        tmp_path,
        [
            ["EQ-001", "示波器", "08:00", "22:00"],
            ["EQ-002", "万用表", "", "18:00"],
            ["EQ-003", "直流电源", "08:30", "20:30"],
        ],
    )
    db_path = tmp_path / "data" / "lab.db"

    proc = _run_seed(tmp_path)

    assert proc.returncode != 0
    assert "第 3 行" in proc.stdout
    assert _equipment_rows(db_path) == []


def test_seed_without_csv_fails_before_creating_database(tmp_path):
    proc = _run_seed(tmp_path)

    assert proc.returncode != 0
    assert "equipment.csv" in (proc.stdout + proc.stderr)
    assert not (tmp_path / "data" / "lab.db").exists()


def test_seed_reports_the_physical_line_of_a_later_bad_row(tmp_path):
    _write_seed(
        tmp_path,
        [
            ["EQ-001", "示波器", "08:00", "22:00"],
            ["EQ-002", "万用表", "09:00", "18:00"],
            ["EQ-003", "直流电源", "08:30", "25:00"],
        ],
    )
    db_path = tmp_path / "data" / "lab.db"

    proc = _run_seed(tmp_path)

    assert proc.returncode != 0
    assert "第 4 行" in proc.stdout
    assert _equipment_rows(db_path) == []


def test_seed_rejects_duplicate_equipment_id(tmp_path):
    _write_seed(
        tmp_path,
        [
            ["EQ-001", "示波器", "08:00", "22:00"],
            ["EQ-002", "万用表", "09:00", "18:00"],
            ["EQ-001", "重复设备", "08:00", "22:00"],
        ],
    )
    db_path = tmp_path / "data" / "lab.db"

    proc = _run_seed(tmp_path)

    assert proc.returncode != 0
    assert "第 4 行" in proc.stdout
    assert _equipment_rows(db_path) == []


def test_seed_rejects_wrong_header_without_creating_database(tmp_path):
    _write_raw_seed(
        tmp_path,
        "name,equipment_id,open_start,open_end\n示波器,EQ-001,08:00,22:00\n".encode("utf-8"),
    )

    proc = _run_seed(tmp_path)

    assert proc.returncode != 0
    assert "表头" in proc.stdout
    assert not (tmp_path / "data" / "lab.db").exists()


def test_seed_reports_non_utf8_csv_clearly(tmp_path):
    _write_raw_seed(
        tmp_path,
        "equipment_id,name,open_start,open_end\nEQ-001,示波器,08:00,22:00\n".encode("gbk"),
    )

    proc = _run_seed(tmp_path)

    assert proc.returncode != 0
    assert "UTF-8" in proc.stdout


def test_seed_honors_lab_db_path_outside_cwd(tmp_path):
    _write_seed(tmp_path, [["EQ-001", "示波器", "08:00", "22:00"]])
    alt_db = tmp_path / "alt" / "lab.db"
    alt_db.parent.mkdir()

    proc = _run_seed_with_db(tmp_path, alt_db)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _equipment_rows(alt_db) == [("EQ-001", "示波器", "08:00", "22:00")]
    assert not (tmp_path / "data" / "lab.db").exists()


def test_seed_rolls_back_when_a_write_fails_midway(tmp_path):
    _write_seed(
        tmp_path,
        [
            ["EQ-001", "示波器", "08:00", "22:00"],
            ["EQ-002", "万用表", "09:00", "18:00"],
            ["EQ-003", "直流电源", "08:30", "20:30"],
        ],
    )
    db_path = tmp_path / "data" / "lab.db"
    _initialize_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TRIGGER reject_eq002 BEFORE INSERT ON equipment"
            " WHEN NEW.id = 'EQ-002' BEGIN SELECT RAISE(ABORT, 'boom'); END"
        )
        conn.commit()
    finally:
        conn.close()

    proc = _run_seed(tmp_path)

    assert proc.returncode != 0
    assert _equipment_rows(db_path) == []


def test_seed_refuses_to_shrink_a_window_over_occupied_slots(tmp_path):
    db_path = tmp_path / "data" / "lab.db"
    _initialize_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO user (id, student_no, role, password_hash, created_at)"
            " VALUES ('u1', '20260001', 'student', 'hash', '2026-11-09T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO equipment (id, name, open_start, open_end) VALUES"
            " ('EQ-001', '示波器', '08:00', '22:00')"
        )
        conn.execute(
            "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
            " VALUES ('b1', 'u1', 'EQ-001', '2026-11-09T00:00:00Z', '2026-11-09T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES ('EQ-001', '2030-01-01T13:00:00Z', 'booking', 'b1', '2026-11-09T00:00:00Z')"
        )
        conn.commit()
    finally:
        conn.close()
    _write_seed(tmp_path, [["EQ-001", "示波器", "09:00", "18:00"]])

    proc = _run_seed(tmp_path)

    assert proc.returncode != 0
    assert _equipment_rows(db_path) == [("EQ-001", "示波器", "08:00", "22:00")]


def test_invalid_lab_port_fails_before_touching_the_database(tmp_path):
    env = _base_env(tmp_path)
    env.update(
        {
            "LAB_HOST": "127.0.0.1",
            "LAB_PORT": "70000",
            "LAB_SECRET_KEY": SECRET_KEY,
            "LAB_DEFAULT_PASSWORD": DEFAULT_PASSWORD,
        }
    )

    proc = subprocess.run(
        [sys.executable, "-m", "src.serve"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert proc.returncode != 0
    assert "LAB_PORT" in (proc.stdout + proc.stderr)
    assert not (tmp_path / "data" / "lab.db").exists()


def test_health_is_not_200_when_the_database_is_unavailable(app, tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False, LAB_DB_PATH=str(broken))

    response = app.test_client().get("/health")

    assert response.status_code != 200


def test_seed_creates_admin_account_that_can_log_in_as_admin(tmp_path, monkeypatch):
    _write_seed(tmp_path, [["EQ-001", "示波器", "08:00", "22:00"]])
    db_path = tmp_path / "data" / "lab.db"

    proc = _run_seed_with_env(
        tmp_path,
        LAB_ADMIN_USER=ADMIN_USER,
        LAB_ADMIN_PASSWORD=ADMIN_PASSWORD,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = _user_rows(db_path)
    assert [(row["student_no"], row["role"], row["active"]) for row in rows] == [
        (ADMIN_USER, "admin", 1)
    ]
    assert rows[0]["password_hash"] != ADMIN_PASSWORD

    application = _app_for_seeded_db(monkeypatch, db_path)
    client = application.test_client()
    assert _login(client, ADMIN_USER, ADMIN_PASSWORD).status_code == 303
    assert client.get("/admin/equipments").status_code == 200


def test_seed_upserts_admin_without_adding_rows(tmp_path):
    _write_seed(tmp_path, [["EQ-001", "示波器", "08:00", "22:00"]])
    db_path = tmp_path / "data" / "lab.db"

    first = _run_seed_with_env(
        tmp_path,
        LAB_ADMIN_USER=ADMIN_USER,
        LAB_ADMIN_PASSWORD=ADMIN_PASSWORD,
    )
    second = _run_seed_with_env(
        tmp_path,
        LAB_ADMIN_USER=ADMIN_USER,
        LAB_ADMIN_PASSWORD=ADMIN_PASSWORD,
    )

    assert (first.returncode, second.returncode) == (0, 0), (
        first.stdout + first.stderr + second.stdout + second.stderr
    )
    rows = _user_rows(db_path)
    assert [(row["student_no"], row["role"]) for row in rows] == [(ADMIN_USER, "admin")]
    assert _equipment_rows(db_path) == [("EQ-001", "示波器", "08:00", "22:00")]


def test_seed_without_admin_variables_skips_admin_and_exits_zero(tmp_path):
    _write_seed(tmp_path, [["EQ-001", "示波器", "08:00", "22:00"]])
    db_path = tmp_path / "data" / "lab.db"

    proc = _run_seed(tmp_path)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "LAB_ADMIN_USER" in proc.stderr and "LAB_ADMIN_PASSWORD" in proc.stderr
    assert _user_rows(db_path) == []
    assert _equipment_rows(db_path) == [("EQ-001", "示波器", "08:00", "22:00")]
