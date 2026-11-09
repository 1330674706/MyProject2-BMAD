-- 001_init.sql —— 架构 §5.1 D1 与 §10.2 的建表原文；由 PRAGMA user_version 驱动。
-- 时刻列一律由应用传入 20 字符 UTC 文本，禁止 DEFAULT CURRENT_TIMESTAMP。

CREATE TABLE user (
    id               TEXT PRIMARY KEY,
    student_no       TEXT NOT NULL UNIQUE,
    role             TEXT NOT NULL CHECK (role IN ('student', 'admin')),
    password_hash    TEXT NOT NULL,
    password_version INTEGER NOT NULL DEFAULT 1,
    active           INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at       TEXT NOT NULL
);

CREATE TABLE equipment (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    open_start TEXT NOT NULL,
    open_end   TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE booking (
    id           TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL REFERENCES user(id) ON DELETE RESTRICT,
    equipment_id TEXT NOT NULL REFERENCES equipment(id) ON DELETE RESTRICT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE occupancy (
    equipment_id TEXT NOT NULL
        REFERENCES equipment(id) ON DELETE RESTRICT,
    slot_start   TEXT NOT NULL
        CHECK (length(slot_start) = 20
               AND slot_start GLOB
                   '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:00Z'),
    kind         TEXT NOT NULL CHECK (kind IN ('booking', 'lock')),
    booking_id   TEXT REFERENCES booking(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    CONSTRAINT uq_occupancy_slot UNIQUE (equipment_id, slot_start),
    CHECK ((kind = 'booking' AND booking_id IS NOT NULL)
        OR (kind = 'lock'    AND booking_id IS NULL))
);

CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY,
    actor_id    TEXT NOT NULL,
    action      TEXT NOT NULL CHECK (action IN (
                  'register','login_fail','booking_create','booking_cancel','booking_edit',
                  'lock','unlock','password_reset','user_deactivate','equipment_update')),
    target_type TEXT NOT NULL CHECK (target_type IN ('booking','equipment','user')),
    target_id   TEXT NOT NULL,
    before_json TEXT,
    after_json  TEXT,
    created_at  TEXT NOT NULL,
    CHECK (before_json IS NOT NULL OR after_json IS NOT NULL)
);

CREATE INDEX idx_booking_owner ON booking(owner_id);
CREATE INDEX idx_occupancy_booking ON occupancy(booking_id);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);
CREATE INDEX idx_audit_actor ON audit_log(actor_id, created_at DESC);