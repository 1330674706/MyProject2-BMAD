"""Story 3.4 验收测试：自然周 CSV 导出与追加式操作日志。

行为经公开入口（`GET /admin/export`、`GET /admin/audit`）观察；
用户、设备与占用行直接 INSERT 播种，五类动作经用例层触发。
"""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from datetime import datetime

import pytest
from werkzeug.security import generate_password_hash

from src.app import audit as audit_service
from src.app import auth_service, booking_service
from src.core import redact
from src.core.timeutil import local_to_utc

PASSWORD_HASH = generate_password_hash("P@ssw0rd-lab")
NOW = "2026-11-09T00:00:00Z"  # 本地周一 08:00
ADMIN_ID = "a" * 32
STUDENT_A = "b" * 32
STUDENT_B = "c" * 32
MONDAY = "2026-11-09"
PREVIOUS_MONDAY = "2026-11-02"
CSV_HEADER = "设备,slot 开始,slot 结束,学号,booking_id,状态"


@pytest.fixture
def clock(monkeypatch):
    def fixed_now():
        return NOW

    from src.app import slot_service

    monkeypatch.setattr(slot_service, "now_utc", fixed_now)


def connect(db_path):
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_user(db_path, user_id, student_no, role="student"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO user (id, student_no, role, password_hash, password_version, active, created_at)"
            " VALUES (?, ?, ?, ?, 1, 1, ?)",
            (user_id, student_no, role, PASSWORD_HASH, "2026-11-09T00:00:00Z"),
        )
    finally:
        conn.close()


def seed_equipment(db_path, equipment_id="E1", name=None, open_start="08:00", open_end="22:00"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO equipment (id, name, open_start, open_end, active) VALUES (?, ?, ?, ?, 1)",
            (equipment_id, name or f"设备{equipment_id}", open_start, open_end),
        )
    finally:
        conn.close()


def utc_at(day, hhmm):
    return local_to_utc(datetime.fromisoformat(f"{day}T{hhmm}:00"))


def seed_booking(
    db_path,
    *,
    booking_id,
    owner_id,
    times,
    equipment_id="E1",
    day="2026-11-11",
    created_at="2026-11-09T00:00:00Z",
):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (booking_id, owner_id, equipment_id, created_at, created_at),
        )
        conn.executemany(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, 'booking', ?, ?)",
            [(equipment_id, utc_at(day, hhmm), booking_id, created_at) for hhmm in times],
        )
    finally:
        conn.close()


def seed_lock(db_path, *, slot_start, equipment_id="E1"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, 'lock', NULL, ?)",
            (equipment_id, slot_start, "2026-11-09T00:00:00Z"),
        )
    finally:
        conn.close()


def seed_audit(
    db_path,
    *,
    action,
    created_at,
    target_type="booking",
    before_json=None,
    after_json='{"slots": []}',
):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO audit_log (actor_id, action, target_type, target_id, before_json, after_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ADMIN_ID, action, target_type, "f" * 32, before_json, after_json, created_at),
        )
    finally:
        conn.close()


def table_counts(db_path):
    conn = connect(db_path)
    try:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("user", "equipment", "booking", "occupancy", "audit_log")
        }
    finally:
        conn.close()


def login_as(client, user_id, role="student", password_version=1):
    with client.session_transaction() as session:
        session["uid"] = user_id
        session["role"] = role
        session["pv"] = password_version


def admin_client(app, db_path):
    seed_user(db_path, ADMIN_ID, "A0001", role="admin")
    client = app.test_client()
    login_as(client, ADMIN_ID, role="admin")
    return client


def fetch_export(client, week):
    resp = client.get(f"/admin/export?week={week}")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_data()
    text = body.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    return body, text, rows


def row_slots(rows):
    return [row["slot 开始"] for row in rows]


def audit_rows(html):
    return re.findall(r'data-audit-action="([^"]+)"', html)


def test_export_starts_with_bom_and_has_one_line_per_booking_slot(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    for index in range(5):
        seed_booking(
            db_path,
            booking_id=f"{index + 1:032x}",
            owner_id=STUDENT_A,
            times=[f"{8 + index:02d}:00"],
        )
    client = admin_client(app, db_path)

    body = client.get(f"/admin/export?week={MONDAY}").get_data()

    assert body.startswith(b"\xef\xbb\xbf") and len(
        [line for line in body.decode("utf-8-sig").splitlines() if line]
    ) == 6


def test_export_header_is_exact_and_multi_slot_booking_repeats_booking_id(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    multi_id = "1" * 32
    seed_booking(
        db_path,
        booking_id=multi_id,
        owner_id=STUDENT_A,
        times=["14:00", "14:30", "15:00"],
    )
    seed_booking(db_path, booking_id="2" * 32, owner_id=STUDENT_A, times=["16:00"])
    client = admin_client(app, db_path)

    _, text, rows = fetch_export(client, MONDAY)
    header = text.splitlines()[0]

    assert header == CSV_HEADER and len([r for r in rows if r["booking_id"] == multi_id]) == 3
    assert [row["slot 结束"] for row in rows if row["booking_id"] == multi_id] == [
        "2026-11-11 14:30",
        "2026-11-11 15:00",
        "2026-11-11 15:30",
    ]
    assert all(row["状态"] == "有效" and row["学号"] == "2025001" for row in rows)


def test_cancelled_booking_is_absent_from_export(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    cancelled_bid = "3" * 32
    seed_booking(db_path, booking_id=cancelled_bid, owner_id=STUDENT_A, times=["10:00"])
    seed_booking(db_path, booking_id="4" * 32, owner_id=STUDENT_A, times=["11:00"])
    conn = connect(db_path)
    try:
        booking_service.cancel_booking(conn, STUDENT_A, cancelled_bid, now=NOW)
    finally:
        conn.close()
    client = admin_client(app, db_path)

    _, _, rows = fetch_export(client, MONDAY)

    assert cancelled_bid not in {row["booking_id"] for row in rows}


def test_natural_week_boundary_uses_local_monday_midnight(app, db_path, clock):
    seed_equipment(db_path, open_start="00:00", open_end="23:30")
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id="5" * 32, owner_id=STUDENT_A, day="2026-11-09", times=["00:00"])
    seed_booking(db_path, booking_id="6" * 32, owner_id=STUDENT_A, day="2026-11-08", times=["23:30"])
    client = admin_client(app, db_path)
    mon_slot = "2026-11-09 00:00"
    previous_slot = "2026-11-08 23:30"

    _, _, rows_w = fetch_export(client, MONDAY)
    _, _, rows_previous = fetch_export(client, PREVIOUS_MONDAY)

    assert mon_slot in row_slots(rows_w) and mon_slot not in row_slots(rows_previous)
    assert previous_slot in row_slots(rows_previous) and previous_slot not in row_slots(rows_w)


def test_lock_rows_are_excluded_from_export(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id="7" * 32, owner_id=STUDENT_A, times=["10:00"])
    seed_booking(db_path, booking_id="8" * 32, owner_id=STUDENT_A, times=["11:00"])
    lock_slot_local = "2026-11-11 16:00"
    seed_lock(db_path, slot_start=utc_at("2026-11-11", "16:00"))
    client = admin_client(app, db_path)

    _, _, csv_rows = fetch_export(client, MONDAY)

    assert len(csv_rows) == 2 and lock_slot_local not in row_slots(csv_rows)


def test_audit_page_lists_all_five_action_kinds_with_complete_rows(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_user(db_path, STUDENT_B, "2025002")
    conn = connect(db_path)
    try:
        created = booking_service.create_booking(
            conn, STUDENT_A, "E1", [utc_at("2026-11-11", "14:00")], now=NOW
        )
        cancelled = booking_service.create_booking(
            conn, STUDENT_A, "E1", [utc_at("2026-11-11", "18:00")], now=NOW
        )
        booking_service.cancel_booking(conn, STUDENT_A, cancelled, now=NOW)
        edited = booking_service.create_booking(
            conn, STUDENT_A, "E1", [utc_at("2026-11-11", "20:00")], now=NOW
        )
        booking_service.edit_booking(
            conn, ADMIN_ID, edited, "E1", [utc_at("2026-11-11", "20:30")], now=NOW
        )
        booking_service.lock_slots(
            conn, ADMIN_ID, "E1", [utc_at("2026-11-11", "12:00")], now=NOW
        )
        auth_service.reset_password(
            conn,
            target_user_id=STUDENT_B,
            actor_id=ADMIN_ID,
            default_password="lab-default-2026",
        )
    finally:
        conn.close()
    client = admin_client(app, db_path)

    html = client.get("/admin/audit").get_data(as_text=True)
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT actor_id, action, target_type, target_id, created_at, before_json, after_json"
            " FROM audit_log ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    assert {"booking_create", "booking_cancel", "booking_edit", "lock", "password_reset"} <= set(
        audit_rows(html)
    )
    assert all(r["actor_id"] and (r["before_json"] or r["after_json"]) for r in rows)
    assert all(r["target_type"] and r["target_id"] and r["created_at"] for r in rows)
    assert "2025001" in html and "A0001" in html
    assert 'data-audit-created-at="2026-11-09 08:00:00"' in html
    assert "password_version" in html
    assert created and cancelled and edited


def test_audit_page_is_read_only_and_has_no_edit_entry(app, db_path, clock):
    client = admin_client(app, db_path)

    html = client.get("/admin/audit").get_data(as_text=True)
    put = client.put("/admin/audit")
    delete = client.delete("/admin/audit")

    assert (put.status_code, delete.status_code) == (405, 405)
    assert "<form" not in html.lower()
    assert 'method="post"' not in html.lower()
    assert not re.search(r"/admin/audit/[^\"']*(edit|delete)", html)


def test_export_and_audit_bodies_never_leak_credentials(app, db_path, clock):
    plain_pw = app.config["LAB_DEFAULT_PASSWORD"]
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id="9" * 32, owner_id=STUDENT_A, times=["10:00"])
    conn = connect(db_path)
    try:
        auth_service.reset_password(
            conn, target_user_id=STUDENT_A, actor_id=ADMIN_ID, default_password=plain_pw
        )
        hashes = [row["password_hash"] for row in conn.execute("SELECT password_hash FROM user")]
    finally:
        conn.close()
    client = admin_client(app, db_path)

    export_body = client.get(f"/admin/export?week={MONDAY}").get_data().decode("utf-8-sig")
    audit_body = client.get("/admin/audit").get_data(as_text=True)

    for body in (export_body, audit_body):
        assert plain_pw not in body and all(h not in body for h in hashes)
        assert "password_hash" not in body and "csrf_token" not in body
        assert "session" not in body.lower()


def test_password_reset_audit_records_only_password_version(app, db_path, clock):
    seed_user(db_path, STUDENT_A, "2025001")
    conn = connect(db_path)
    try:
        auth_service.reset_password(
            conn,
            target_user_id=STUDENT_A,
            actor_id=ADMIN_ID,
            default_password="lab-default-2026",
        )
        r = conn.execute(
            "SELECT before_json, after_json FROM audit_log WHERE action = 'password_reset'"
        ).fetchone()
    finally:
        conn.close()

    assert set(json.loads(r["before_json"])) == {"password_version"} and set(
        json.loads(r["after_json"])
    ) == {"password_version"}


def test_export_rejects_bad_week_with_400(app, db_path, clock):
    client = admin_client(app, db_path)

    for value in ("not-a-week", "2026-W54", "9999-12-31"):
        resp = client.get(f"/admin/export?week={value}")
        assert resp.status_code == 400 and "Content-Disposition" not in resp.headers


def test_export_empty_week_is_header_only(app, db_path, clock):
    client = admin_client(app, db_path)

    _, text, rows = fetch_export(client, MONDAY)

    assert rows == [] and [line for line in text.splitlines() if line] == [CSV_HEADER]


def test_export_and_audit_require_admin(app, db_path, clock):
    seed_user(db_path, STUDENT_A, "2025001")
    student = app.test_client()
    login_as(student, STUDENT_A)
    anonymous = app.test_client()
    before = table_counts(db_path)

    assert student.get(f"/admin/export?week={MONDAY}").status_code == 403
    assert student.get("/admin/audit").status_code == 403
    assert anonymous.get(f"/admin/export?week={MONDAY}").status_code == 401
    assert anonymous.get("/admin/audit").status_code == 401
    assert table_counts(db_path) == before


def test_export_sets_csv_attachment_headers(app, db_path, clock):
    client = admin_client(app, db_path)

    resp = client.get(f"/admin/export?week={MONDAY}")

    assert resp.mimetype == "text/csv"
    assert resp.headers["Content-Disposition"] == 'attachment; filename="bookings-2026-11-09.csv"'


def test_week_page_links_to_this_week_export_and_audit(app, db_path, clock):
    seed_equipment(db_path)
    client = admin_client(app, db_path)

    html = client.get(f"/admin/week?week={MONDAY}").get_data(as_text=True)

    assert f'href="/admin/export?week={MONDAY}"' in html and 'href="/admin/audit"' in html


def test_export_neutralizes_formula_prefix_and_newlines(app, db_path, clock):
    seed_equipment(db_path, name='=HYPERLINK("http://x","点我")\n第二行')
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id="a" * 32, owner_id=STUDENT_A, times=["10:00"])
    client = admin_client(app, db_path)

    _, text, rows = fetch_export(client, MONDAY)

    assert rows[0]["设备"] == '\'=HYPERLINK("http://x","点我") 第二行'
    assert len([line for line in text.splitlines() if line]) == 2
    assert not any(line.startswith("=") for line in text.splitlines())


def test_audit_page_filters_legacy_extra_fields_and_bad_timestamps(app, db_path, clock):
    seed_audit(
        db_path,
        action="password_reset",
        target_type="user",
        created_at="not-a-timestamp",
        before_json='{"password_version": 2, "password_hash": "leak-me"}',
        after_json="not-json",
    )
    client = admin_client(app, db_path)

    resp = client.get("/admin/audit")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "leak-me" not in html and "password_version" in html
    assert "not-a-timestamp" in html and "—" in html
    assert redact.filter_stored("slot", '{"a": 1}') == ""


def test_audit_orders_newest_first_and_reports_truncation(app, db_path, clock):
    seed_audit(db_path, action="booking_create", created_at="2026-11-09T00:00:01Z")
    seed_audit(db_path, action="booking_edit", created_at="2026-11-09T00:00:02Z")
    seed_audit(db_path, action="booking_cancel", created_at="2026-11-09T00:00:03Z")
    client = admin_client(app, db_path)

    html = client.get("/admin/audit").get_data(as_text=True)
    conn = connect(db_path)
    try:
        page = audit_service.list_audit(conn, limit=1)
    finally:
        conn.close()

    assert audit_rows(html) == ["booking_cancel", "booking_edit", "booking_create"]
    assert len(page.entries) == 1 and page.total == 3 and page.truncated

