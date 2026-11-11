"""Story 3.1 验收测试：管理员本周视图与按学号检索。

行为经公开入口（`GET /admin/week`、`GET /admin/users` 与学生 `GET /slots`）观察；
设备/用户/预约直接 INSERT 播种，只读断言通过 SQLite 快照比较。
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from src.core.timeutil import local_to_utc

PASSWORD_HASH = generate_password_hash("P@ssw0rd-lab")
NOW = "2026-11-09T00:00:00Z"  # 本地周一 08:00
ADMIN_ID = "a" * 32
STUDENT_A = "b" * 32
STUDENT_B = "c" * 32
STUDENT_C = "d" * 32


@pytest.fixture
def clock(monkeypatch):
    def fixed_now():
        return NOW

    from src.app import slot_service

    monkeypatch.setattr(slot_service, "now_utc", fixed_now)


def connect(db_path):
    conn = sqlite3.connect(str(db_path))
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
        conn.commit()
    finally:
        conn.close()


def seed_equipment(db_path, equipment_id="E1", name=None, open_start="08:00", open_end="22:00"):
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO equipment (id, name, open_start, open_end, active) VALUES (?, ?, ?, ?, 1)",
            (equipment_id, name or f"设备{equipment_id}", open_start, open_end),
        )
        conn.commit()
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
    updated_at=None,
):
    updated_at = updated_at or created_at
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (booking_id, owner_id, equipment_id, created_at, updated_at),
        )
        conn.executemany(
            "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
            " VALUES (?, ?, 'booking', ?, ?)",
            [(equipment_id, utc_at(day, hhmm), booking_id, created_at) for hhmm in times],
        )
        conn.commit()
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
        conn.commit()
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


def ids(html):
    return re.findall(r'data-booking-id="([^"]+)"', html)


def cells(html):
    return re.findall(r'data-state="([^"]+)" data-slot="([^"]+)"', html)


def grid_block(html, equipment_id, day):
    pattern = (
        r'<div class="week-grid"[^>]*data-grid-equipment="' + re.escape(equipment_id)
        + r'"[^>]*data-grid-day="' + re.escape(day) + r'"[^>]*>(.*?)</div>'
    )
    match = re.search(pattern, html, re.S)
    assert match is not None, f"周视图缺少 {equipment_id}/{day} 的格子容器"
    return match.group(1)


def week_cells(html, equipment_id, day):
    return cells(grid_block(html, equipment_id, day))


def cell_block(html, equipment_id, day, slot_start):
    block = grid_block(html, equipment_id, day)
    match = re.search(
        r"<li\b[^>]*data-slot=\"" + re.escape(slot_start) + r"\"[^>]*>.*?</li>",
        block,
        re.S,
    )
    assert match is not None, f"{equipment_id}/{day} 缺少 {slot_start} 的格子"
    return match.group(0)


def css_rule(css, selector):
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match is not None, f"缺少 {selector} 规则"
    return re.sub(r"\s+", " ", match.group(1))


def snapshot(db_path):
    conn = connect(db_path)
    try:
        return {
            "booking": [
                tuple(row)
                for row in conn.execute(
                    "SELECT id, owner_id, equipment_id, created_at, updated_at FROM booking ORDER BY id"
                ).fetchall()
            ],
            "occupancy": [
                tuple(row)
                for row in conn.execute(
                "SELECT equipment_id, slot_start, kind, booking_id, created_at FROM occupancy"
                " ORDER BY equipment_id, slot_start"
                ).fetchall()
            ],
            "audit": [
                tuple(row)
                for row in conn.execute(
                    "SELECT id, actor_id, action, target_type, target_id, before_json, after_json, created_at"
                    " FROM audit_log ORDER BY id"
                ).fetchall()
            ],
        }
    finally:
        conn.close()


def test_week_boundary_separates_sunday_2330_from_monday_0000(app, db_path, clock):
    seed_equipment(db_path, open_start="00:00", open_end="23:30")
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(
        db_path,
        booking_id="1" * 32,
        owner_id=STUDENT_A,
        day="2026-11-08",
        times=["23:30"],
    )
    seed_booking(
        db_path,
        booking_id="2" * 32,
        owner_id=STUDENT_A,
        day="2026-11-09",
        times=["00:00"],
    )
    client = admin_client(app, db_path)

    previous = client.get("/admin/week?week=2026-11-02")
    current = client.get("/admin/week?week=2026-11-09")
    previous_ids = set(ids(previous.get_data(as_text=True)))
    current_ids = set(ids(current.get_data(as_text=True)))

    assert (previous.status_code, current.status_code) == (200, 200)
    assert previous_ids.isdisjoint(current_ids)
    assert "2" * 32 in current_ids
    assert "1" * 32 in previous_ids


def test_week_renders_all_open_slots_and_distinct_booking_ids(app, db_path, clock):
    seed_equipment(db_path, open_start="08:00", open_end="10:00")
    seed_user(db_path, STUDENT_A, "2025001")
    days = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15"]
    booking_ids = []
    for index, day in enumerate(days):
        booking_id = f"{index + 1:032d}"
        booking_ids.append(booking_id)
        seed_booking(
            db_path,
            booking_id=booking_id,
            owner_id=STUDENT_A,
            day=day,
            times=["08:00"] if index % 2 == 0 else ["08:30"],
        )
    client = admin_client(app, db_path)

    resp = client.get("/admin/week?week=2026-11-09")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert len(re.findall(r'data-state="', html)) == 28
    cell_booking_ids = set()
    for day in days:
        cell_booking_ids |= set(
            re.findall(r'data-booking-id="([^"]+)"', grid_block(html, "E1", day))
        )
    assert cell_booking_ids == set(booking_ids)
    assert set(booking_ids) <= set(ids(html))


def test_locked_and_cross_equipment_overlap_render_anomaly_markers(app, db_path, clock):
    seed_equipment(db_path, "E1")
    seed_equipment(db_path, "E2")
    seed_user(db_path, STUDENT_A, "2025001")
    lock_slot = utc_at("2026-11-11", "16:00")
    seed_lock(db_path, slot_start=lock_slot)
    seed_booking(db_path, booking_id="1" * 32, owner_id=STUDENT_A, times=["14:00"], equipment_id="E1")
    seed_booking(db_path, booking_id="2" * 32, owner_id=STUDENT_A, times=["14:00"], equipment_id="E2")
    client = admin_client(app, db_path)

    resp = client.get("/admin/week?week=2026-11-09")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    lock_block = cell_block(html, "E1", "2026-11-11", lock_slot)
    assert 'data-state="locked"' in lock_block
    assert "已锁定" in lock_block
    assert f'data-anomaly-slot="{lock_slot}"' in html

    overlap_slot = utc_at("2026-11-11", "14:00")
    for equipment_id in ("E1", "E2"):
        block = cell_block(html, equipment_id, "2026-11-11", overlap_slot)
        assert 'data-anomaly="1"' in block
        assert "跨设备重叠" in block
    assert "2025001" in cell_block(html, "E1", "2026-11-11", overlap_slot)


def test_search_exact_precedes_prefix_and_unknown_is_empty(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_user(db_path, STUDENT_C, "20250010")
    seed_booking(db_path, booking_id="1" * 32, owner_id=STUDENT_A, times=["14:00"])
    seed_booking(db_path, booking_id="2" * 32, owner_id=STUDENT_A, day="2026-11-12", times=["14:00", "14:30"])
    seed_booking(db_path, booking_id="3" * 32, owner_id=STUDENT_C, times=["16:00"])
    client = admin_client(app, db_path)

    exact = client.get("/admin/users?student_no=2025001")
    prefix = client.get("/admin/users?student_no=202500")
    missing = client.get("/admin/users?student_no=9999999")

    assert exact.status_code == 200
    assert set(ids(exact.get_data(as_text=True))) == {"1" * 32, "2" * 32}
    assert set(ids(prefix.get_data(as_text=True))) == {"1" * 32, "2" * 32, "3" * 32}
    assert missing.status_code == 200
    assert ids(missing.get_data(as_text=True)) == []


def test_admin_week_requires_admin_and_login(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    student = app.test_client()
    login_as(student, STUDENT_A)
    anonymous = app.test_client()

    assert (student.get("/admin/week").status_code, anonymous.get("/admin/week").status_code) == (403, 401)
    assert (
        student.get("/admin/users?student_no=2025001").status_code,
        anonymous.get("/admin/users?student_no=2025001").status_code,
    ) == (403, 401)


def test_week_grid_reuses_student_day_cell_structure(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_user(db_path, STUDENT_B, "2025002")
    seed_booking(db_path, booking_id="1" * 32, owner_id=STUDENT_B, times=["14:00"])
    admin = admin_client(app, db_path)
    student = app.test_client()
    login_as(student, STUDENT_A)

    week_html = admin.get("/admin/week?week=2026-11-09").get_data(as_text=True)
    day_html = student.get("/slots?equipment_id=E1&date=2026-11-11").get_data(as_text=True)

    assert week_cells(week_html, "E1", "2026-11-11") == cells(day_html)


def test_student_slot_view_does_not_leak_owner_identity_or_booking_id(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_user(db_path, STUDENT_B, "2025002")
    seed_booking(db_path, booking_id="1" * 32, owner_id=STUDENT_B, times=["14:00"])
    student = app.test_client()
    login_as(student, STUDENT_A)

    html = student.get("/slots?equipment_id=E1&date=2026-11-11").get_data(as_text=True)

    assert "2025002" not in html
    assert "data-booking-id=" not in html
    assert "data-owner-student-no=" not in html


def test_week_and_search_are_read_only(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id="1" * 32, owner_id=STUDENT_A, times=["14:00"])
    seed_lock(db_path, slot_start=utc_at("2026-11-11", "16:00"))
    client = admin_client(app, db_path)
    before = snapshot(db_path)

    assert client.get("/admin/week?week=2026-11-09").status_code == 200
    assert client.get("/admin/users?student_no=2025001").status_code == 200

    assert snapshot(db_path) == before


def test_bad_week_returns_400(app, db_path, clock):
    client = admin_client(app, db_path)

    for value in ("not-a-week", "2026-W54", "9999-12-31"):
        assert client.get(f"/admin/week?week={value}").status_code == 400


def test_week_table_css_binds_overflow_guards_to_week_selectors(app, db_path, clock):
    seed_equipment(db_path)
    client = admin_client(app, db_path)

    html = client.get("/admin/week?week=2026-11-09").get_data(as_text=True)
    css = (Path(app.static_folder) / "app.css").read_text(encoding="utf-8")

    assert 'class="week-table-scroll"' in html
    assert 'class="week-table"' in html

    scroll_rule = css_rule(css, ".week-table-scroll")
    assert "width: 100%" in scroll_rule
    assert "max-width: 100%" in scroll_rule
    assert "overflow-x: auto" in scroll_rule

    table_rule = css_rule(css, ".week-table")
    assert "width: 100%" in table_rule
    assert "table-layout: fixed" in table_rule

    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if ".week-table" not in selectors:
            continue
        for value in re.findall(r"min-width:\s*([^;]+);", body):
            assert value.strip() == "0", f"{selectors.strip()} 设置了 min-width: {value}"

    narrow = css[css.index("@media (max-width: 720px)"):]
    assert ".week-table," in narrow
    assert "display: block" in narrow


def test_week_defaults_to_current_week_and_accepts_iso_and_midweek(app, db_path, clock):
    client = admin_client(app, db_path)

    for url in ("/admin/week", "/admin/week?week=2026-W46", "/admin/week?week=2026-11-11"):
        resp = client.get(url)
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "2026-11-09 至 2026-11-15" in html
        assert 'href="/admin/week?week=2026-11-02"' in html
        assert 'href="/admin/week?week=2026-11-16"' in html


def test_edited_booking_is_marked_in_grid_and_both_tables(app, db_path, clock):
    seed_equipment(db_path)
    seed_user(db_path, STUDENT_A, "2025001")
    slot = utc_at("2026-11-11", "14:00")
    seed_booking(
        db_path,
        booking_id="1" * 32,
        owner_id=STUDENT_A,
        times=["14:00"],
        updated_at="2026-11-10T00:00:00Z",
    )
    client = admin_client(app, db_path)

    week_html = client.get("/admin/week?week=2026-11-09").get_data(as_text=True)
    search_html = client.get("/admin/users?student_no=2025001").get_data(as_text=True)

    block = cell_block(week_html, "E1", "2026-11-11", slot)
    assert 'data-anomaly="1"' in block
    assert "已改单" in block
    assert week_html.count("已改单") >= 2
    assert "已改单" in search_html


def test_search_marks_cross_equipment_overlap(app, db_path, clock):
    seed_equipment(db_path, "E1")
    seed_equipment(db_path, "E2")
    seed_user(db_path, STUDENT_A, "2025001")
    seed_booking(db_path, booking_id="1" * 32, owner_id=STUDENT_A, times=["14:00"], equipment_id="E1")
    seed_booking(db_path, booking_id="2" * 32, owner_id=STUDENT_A, times=["14:00"], equipment_id="E2")
    client = admin_client(app, db_path)

    html = client.get("/admin/users?student_no=2025001").get_data(as_text=True)

    assert html.count("跨设备重叠") == 2


def test_search_reports_prefix_truncation(app, db_path, clock):
    for index in range(51):
        seed_user(db_path, f"{index:032x}", f"2025{index:03d}")
    client = admin_client(app, db_path)

    html = client.get("/admin/users?student_no=2025").get_data(as_text=True)

    assert 'data-truncated="1"' in html
    assert "仅显示前 50 人" in html


def test_lock_outside_open_window_still_surfaces_in_anomaly_summary(app, db_path, clock):
    seed_equipment(db_path, open_start="08:00", open_end="10:00")
    lock_slot = utc_at("2026-11-11", "16:00")
    seed_lock(db_path, slot_start=lock_slot)
    client = admin_client(app, db_path)

    html = client.get("/admin/week?week=2026-11-09").get_data(as_text=True)

    assert f'data-anomaly-slot="{lock_slot}"' in html
    assert "窗口外锁定" in html