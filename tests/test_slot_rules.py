"""Story 2.4 验收测试：create/edit 共用规则与改单替换语义。

本 Story 只交付规则内核与服务层；HTTP 303/400/409 映射留给 Story 3.2。
每条 AC 经 `slot_rules.validate()` 或 `booking_service.edit_booking()` 观察，
失败后的 occupancy 用只读 SQL 按 `(equipment_id, slot_start, kind, booking_id)`
逐行比对。
"""

from __future__ import annotations

import json

from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest

from src.app import booking_service, slot_rules
from src.core.errors import Conflict, Validation
from src.core.timeutil import local_to_utc
from src.data import audit_repo, booking_repo, occupancy_repo
from src.data.db import connect

NOW = "2030-01-01T02:00:00Z"
EDIT_NOW = "2030-01-01T02:05:00Z"
DAY = "2030-01-01"
USER_ID = "u1"
ADMIN_ID = "admin1"
OTHER_ID = "u2"
BOOKING_ID = "b1"
EQUIPMENT_ID = "E1"
OTHER_EQUIPMENT_ID = "E2"


def slot_at(day, hhmm):
    return local_to_utc(datetime.fromisoformat(f"{day}T{hhmm}:00"))


def local_slots(day, start_hhmm, count):
    hour, minute = (int(part) for part in start_hhmm.split(":"))
    start = datetime.fromisoformat(f"{day}T00:00:00") + timedelta(hours=hour, minutes=minute)
    return [local_to_utc(start + timedelta(minutes=30 * index)) for index in range(count)]


def equipment(equipment_id=EQUIPMENT_ID, open_start="08:00", open_end="22:00"):
    return {
        "id": equipment_id,
        "name": f"设备{equipment_id}",
        "open_start": open_start,
        "open_end": open_end,
        "active": 1,
    }


@pytest.fixture
def db(app, db_path):
    conn = connect(db_path)
    conn.executemany(
        "INSERT INTO user (id, student_no, role, password_hash, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        [
            (USER_ID, "2025001", "student", "x", NOW),
            (ADMIN_ID, "admin", "admin", "x", NOW),
            (OTHER_ID, "2025002", "student", "x", NOW),
        ],
    )
    conn.execute(
        "INSERT INTO equipment (id, name, open_start, open_end, active) VALUES (?, ?, ?, ?, 1)",
        (EQUIPMENT_ID, "设备E1", "08:00", "22:00"),
    )
    conn.execute(
        "INSERT INTO equipment (id, name, open_start, open_end, active) VALUES (?, ?, ?, ?, 1)",
        (OTHER_EQUIPMENT_ID, "设备E2", "08:00", "22:00"),
    )
    conn.commit()
    yield conn
    conn.close()


def insert_booking(
    conn,
    *,
    booking_id=BOOKING_ID,
    owner_id=USER_ID,
    equipment_id=EQUIPMENT_ID,
    slots,
    created_at=NOW,
    updated_at=NOW,
):
    conn.execute(
        "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (booking_id, owner_id, equipment_id, created_at, updated_at),
    )
    conn.executemany(
        "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
        " VALUES (?, ?, 'booking', ?, ?)",
        [(equipment_id, slot_start, booking_id, created_at) for slot_start in slots],
    )
    conn.commit()


def add_other_booking(conn, slot_start):
    conn.execute(
        "INSERT INTO booking (id, owner_id, equipment_id, created_at, updated_at)"
        " VALUES ('b2', ?, ?, ?, ?)",
        (OTHER_ID, EQUIPMENT_ID, NOW, NOW),
    )
    conn.execute(
        "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
        " VALUES (?, ?, 'booking', 'b2', ?)",
        (EQUIPMENT_ID, slot_start, NOW),
    )
    conn.commit()


def add_lock(conn, slot_start):
    conn.execute(
        "INSERT INTO occupancy (equipment_id, slot_start, kind, booking_id, created_at)"
        " VALUES (?, ?, 'lock', NULL, ?)",
        (EQUIPMENT_ID, slot_start, NOW),
    )
    conn.commit()


def sorted_rows(conn):
    return [
        tuple(row)
        for row in conn.execute(
            "SELECT equipment_id, slot_start, kind, booking_id FROM occupancy"
            " ORDER BY equipment_id, slot_start, kind, booking_id"
        )
    ]


def booking_row(conn, booking_id=BOOKING_ID):
    return conn.execute("SELECT * FROM booking WHERE id = ?", (booking_id,)).fetchone()


def audit_count(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]


def n_occ_for(conn, booking_id=BOOKING_ID):
    return conn.execute(
        "SELECT COUNT(*) AS n FROM occupancy WHERE booking_id = ?", (booking_id,)
    ).fetchone()["n"]


def outcome(case, mode):
    equipment_row, slots = case
    options = {"current_first_slot": local_slots(DAY, "16:00", 1)[0]} if mode == "edit" else {}
    try:
        slot_rules.validate(equipment_row, slots, NOW, mode=mode, **options)
    except Validation:
        return "Validation"
    return "ok"


CASES = [
    ("legal", (equipment(), local_slots(DAY, "14:00", 3)), "ok"),
    ("gap", (equipment(), [slot_at(DAY, "14:00"), slot_at(DAY, "15:00")]), "Validation"),
    ("nine", (equipment(), local_slots(DAY, "14:00", 9)), "Validation"),
    ("misaligned", (equipment(), [slot_at(DAY, "14:15")]), "Validation"),
    ("outside_window", (equipment(), local_slots("2030-01-02", "07:30", 1)), "Validation"),
    ("beyond_7d", (equipment(), local_slots("2030-01-08", "10:30", 1)), "Validation"),
]
EXPECTED_MATRIX = [
    (name, mode, expected)
    for name, _case, expected in CASES
    for mode in ("create", "edit")
]


def test_create_and_edit_share_rule_matrix_except_edit_deadline():
    actual = [
        (name, mode, outcome(case, mode))
        for name, case, _expected in CASES
        for mode in ("create", "edit")
    ]
    assert actual == EXPECTED_MATRIX


def test_two_hour_deadline_applies_only_to_edit():
    soon = [slot_at(DAY, "12:00")]
    now_119 = "2030-01-01T02:01:00Z"

    try:
        slot_rules.validate(equipment(), soon, now_119, mode="create")
        create_result = "ok"
    except Validation:
        create_result = "Validation"
    try:
        slot_rules.validate(
            equipment(), soon, now_119, mode="edit", current_first_slot=slot_at(DAY, "20:00")
        )
        edit_result = "ok"
    except Validation:
        edit_result = "Validation"

    assert (create_result, edit_result) == ("ok", "Validation")


def test_edit_overlapping_own_slots_replaces_three_rows_without_conflict(db):
    old_slots = local_slots(DAY, "14:00", 3)
    new_slots = local_slots(DAY, "14:30", 3)
    insert_booking(db, slots=old_slots, updated_at=NOW)
    before = booking_row(db)

    result = booking_service.edit_booking(
        db, ADMIN_ID, BOOKING_ID, EQUIPMENT_ID, new_slots, now=NOW
    )

    after = booking_row(db)
    rows = sorted_rows(db)
    duplicates = db.execute(
        "SELECT equipment_id, slot_start, COUNT(*) AS n FROM occupancy"
        " GROUP BY equipment_id, slot_start HAVING COUNT(*) > 1"
    ).fetchall()
    assert result == BOOKING_ID
    assert rows == [(EQUIPMENT_ID, slot_start, "booking", BOOKING_ID) for slot_start in new_slots]
    assert n_occ_for(db) == len(new_slots) == 3
    assert duplicates == []
    assert after["id"] == before["id"] == BOOKING_ID
    assert after["updated_at"] > before["updated_at"]


@pytest.mark.parametrize("blocked_by", ["other_booking", "lock"])
def test_edit_conflict_rolls_back_and_keeps_every_original_row(db, blocked_by):
    old_slots = local_slots(DAY, "14:00", 3)
    new_slots = local_slots(DAY, "14:30", 3)
    insert_booking(db, slots=old_slots)
    conflict_slot = new_slots[-1]
    if blocked_by == "other_booking":
        add_other_booking(db, conflict_slot)
    else:
        add_lock(db, conflict_slot)
    before = sorted_rows(db)

    with pytest.raises(Conflict) as raised:
        booking_service.edit_booking(
            db, ADMIN_ID, BOOKING_ID, EQUIPMENT_ID, new_slots, now=EDIT_NOW
        )

    assert sorted_rows(db) == before
    assert raised.value.conflict_slots == (conflict_slot,)
    assert n_occ_for(db) == 3


def test_edit_nine_slots_or_gap_is_validation_and_keeps_every_original_row(db):
    old_slots = local_slots(DAY, "14:00", 3)
    insert_booking(db, slots=old_slots)
    before = sorted_rows(db)

    failures = []
    for bad_slots in (
        local_slots(DAY, "14:00", 9),
        [slot_at(DAY, "14:00"), slot_at(DAY, "15:00")],
    ):
        try:
            booking_service.edit_booking(
                db, ADMIN_ID, BOOKING_ID, EQUIPMENT_ID, bad_slots, now=EDIT_NOW
            )
        except Validation:
            failures.append("Validation")
        assert sorted_rows(db) == before

    assert failures == ["Validation", "Validation"]


def test_edit_existing_booking_starting_in_119_minutes_is_validation(db):
    old_slots = local_slots(DAY, "14:00", 1)
    insert_booking(db, slots=old_slots)
    before = sorted_rows(db)
    now_119 = "2030-01-01T04:01:00Z"

    with pytest.raises(Validation):
        booking_service.edit_booking(
            db, ADMIN_ID, BOOKING_ID, EQUIPMENT_ID, local_slots(DAY, "16:00", 1), now=now_119
        )

    assert sorted_rows(db) == before


def test_edit_delete_happens_before_insert_inside_one_write_tx(db, monkeypatch):
    insert_booking(db, slots=local_slots(DAY, "14:00", 3))
    calls = []
    real_delete = occupancy_repo.delete_occupancy
    real_insert = occupancy_repo.insert_occupancy
    real_update = booking_repo.update_booking
    real_audit = audit_repo.insert_audit
    real_write_tx = booking_service.write_tx

    def delete_spy(conn, booking_id):
        calls.append(("delete", conn.in_transaction))
        return real_delete(conn, booking_id)

    def insert_spy(conn, equipment_id, slots, booking_id, kind, *, created_at):
        calls.append(("insert", conn.in_transaction))
        return real_insert(conn, equipment_id, slots, booking_id, kind, created_at=created_at)

    def update_spy(conn, **kwargs):
        calls.append(("update", conn.in_transaction))
        return real_update(conn, **kwargs)

    def audit_spy(conn, **kwargs):
        calls.append(("audit", conn.in_transaction))
        return real_audit(conn, **kwargs)

    @contextmanager
    def tx_spy(conn):
        calls.append(("write_tx", conn.in_transaction))
        with real_write_tx(conn):
            yield conn

    monkeypatch.setattr(occupancy_repo, "delete_occupancy", delete_spy)
    monkeypatch.setattr(occupancy_repo, "insert_occupancy", insert_spy)
    monkeypatch.setattr(booking_repo, "update_booking", update_spy)
    monkeypatch.setattr(audit_repo, "insert_audit", audit_spy)
    monkeypatch.setattr(booking_service, "write_tx", tx_spy)

    booking_service.edit_booking(
        db, ADMIN_ID, BOOKING_ID, EQUIPMENT_ID, local_slots(DAY, "14:30", 3), now=EDIT_NOW
    )

    assert calls == [
        ("write_tx", False),
        ("delete", True),
        ("insert", True),
        ("update", True),
        ("audit", True),
    ]


def test_create_and_edit_each_call_validate_once_with_their_mode(db, monkeypatch):
    modes = []
    real_validate = slot_rules.validate

    def spy(*args, **kwargs):
        modes.append(kwargs["mode"])
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(slot_rules, "validate", spy)

    booking_id = booking_service.create_booking(
        db, USER_ID, EQUIPMENT_ID, [slot_at(DAY, "16:00")], now=NOW
    )
    booking_service.edit_booking(
        db, ADMIN_ID, booking_id, EQUIPMENT_ID, [slot_at(DAY, "17:00")], now=EDIT_NOW
    )

    assert modes == ["create", "edit"]


def test_edit_to_another_equipment_is_validation_and_keeps_every_row(db):
    old_slots = local_slots(DAY, "14:00", 3)
    insert_booking(db, slots=old_slots)
    before_rows = sorted_rows(db)
    before_booking = booking_row(db)

    with pytest.raises(Validation):
        booking_service.edit_booking(
            db,
            ADMIN_ID,
            BOOKING_ID,
            OTHER_EQUIPMENT_ID,
            local_slots(DAY, "16:00", 1),
            now=EDIT_NOW,
        )

    assert sorted_rows(db) == before_rows
    assert booking_row(db)["equipment_id"] == before_booking["equipment_id"]
    assert n_occ_for(db) == 3
    assert audit_count(db) == 0


def test_successful_edit_writes_one_booking_edit_audit_row(db):
    old_slots = local_slots(DAY, "14:00", 3)
    new_slots = local_slots(DAY, "14:30", 3)
    insert_booking(db, slots=old_slots)

    booking_service.edit_booking(
        db, ADMIN_ID, BOOKING_ID, EQUIPMENT_ID, new_slots, now=EDIT_NOW
    )

    rows = db.execute(
        "SELECT actor_id, action, target_type, target_id, before_json, after_json"
        " FROM audit_log ORDER BY id"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert (row["actor_id"], row["action"], row["target_type"]) == (
        ADMIN_ID,
        "booking_edit",
        "booking",
    )
    assert row["target_id"] == BOOKING_ID
    assert json.loads(row["before_json"])["slots"] == old_slots
    assert json.loads(row["after_json"])["slots"] == new_slots


def test_failed_edit_writes_no_audit_row(db):
    insert_booking(db, slots=local_slots(DAY, "14:00", 3))

    with pytest.raises(Validation):
        booking_service.edit_booking(
            db, ADMIN_ID, BOOKING_ID, EQUIPMENT_ID, local_slots(DAY, "14:00", 9), now=EDIT_NOW
        )

    assert audit_count(db) == 0
