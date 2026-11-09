---
title: 'Story 2.1 提交连续 slot 预约'
type: 'feature'
created: '2026-11-09'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: 'a16bf066bbbf43d6beaa71a82f2bdab75951bfef'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 学生目前只能看 slot 状态，无法一次占住同一设备一整段连续时间；逐格提交会产生半成功与中途被插队。

**Approach:** 新增 `POST /bookings` 表单用例：服务层校验 1–8 个连续、对齐、在开放窗口与 7 天窗口内且尚未开始的 slot，随后在单个立即写事务中写 1 条 `booking` 与 N 条共享 `booking_id` 的 `occupancy`。冲突只由唯一约束裁决，失败整单回滚。

## Boundaries & Constraints

**Always:** 形状校验只在 `src/app/slot_rules.py`；写路径唯一：`booking_service.create_booking()` → `write_tx()` → `occupancy_repo.insert_occupancy()`；裸 `INSERT`；时刻只经 `src/core/timeutil.py` 取用与转换，存 20 字符 UTC；409 文案列出全部冲突的 `equipment_id` 与 `slot_start`；校验失败返回 400 且写 0 行；未登录 401、缺 CSRF 400；成功 303 回该设备该日视图。

**Never:** `INSERT OR IGNORE` / `OR REPLACE` / `ON CONFLICT DO NOTHING`；事务外 check-then-write；以预检结果放行或拒绝；把外键等 `IntegrityError` 映射成 409；在 `web/` 或模板做校验、时间比较或冲突分支；给 `booking` 存时间段或状态、建 `slot` 表；实现 2.2 并发测试、2.3 取消、2.4 改单或任何 3.x 功能。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 8 连续空闲 slot | 本地 14:00 起 8 格 | 303；1 booking、8 occupancy、单 `booking_id` | N/A |
| 9 连续 slot | 14:00 起 9 格 | 400；新增 0/0 | 不写库 |
| 非连续 | 14:00 与 15:00 | 400；占用新增 0 | 不写库 |
| 非对齐 | 14:15 | 400；占用新增 0 | 不写库 |
| 已开始 | 首格早于当前时刻 | 400；占用新增 0 | 不写库 |
| 7 天边界 | 首格 now+7d+30min / now+7d-30min | 400 / 303 | 超窗不写库 |
| 设备不符或不存在 | slot 不在该设备窗口 / 未知 id | 400；占用新增 0 | 不写库 |
| 匿名 / 缺 CSRF | 无会话 / 已登录但无 token | 401 / 400；占用新增 0 | 不跨状态码 |
| 成功后看视图 | GET 该设备该日 | 8 格 `booked_by_self` | N/A |

</frozen-after-approval>

## Code Map

- `src/app/slot_rules.py` -- 新增：形状/窗口校验唯一落点，返回规范化 UTC slot 列表。
- `src/app/booking_service.py` -- 新增：用例拥有事务；校验→写 booking→写 occupancy→审计；只捕获唯一键冲突并在回滚后重查冲突集合生成 409。
- `src/data/booking_repo.py` -- 新增：`insert_booking()` 参数化 SQL，不控制事务。
- `src/data/occupancy_repo.py` -- 追加 `insert_occupancy()`（裸 executemany INSERT）与 `select_taken()`（仅用于 409 文案）。
- `src/web/bookings.py` -- 新增：`POST /bookings`，`@login_required` 第一行，解析表单、调用例、映射状态码、303。
- `app.py` -- 注册 `bookings` 蓝图。
- `src/templates/slots.html`、`_slot_grid.html` -- 表单、CSRF、隐藏设备/日期、仅空闲格渲染复选框。
- `src/app/slot_service.py` -- `SlotCell` 增加只读 `selectable` 属性，避免模板判断业务状态。
- `src/web/errors.py`、`src/data/tx.py`、`src/core/timeutil.py` -- 复用，不改语义。
- `tests/test_create_booking.py` -- Story 2.1 九条 AC。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_create_booking.py` -- 先写九条 AC 并跑出断言红灯 -- R5
- [x] `src/app/slot_rules.py` -- 实现形状与窗口校验 -- R1/R4
- [x] `src/data/booking_repo.py`、`src/data/occupancy_repo.py` -- 实现裸 INSERT 与冲突查询 -- R2/R3
- [x] `src/app/booking_service.py` -- 实现事务用例与 409 映射 -- R2/R3
- [x] `src/web/bookings.py`、`app.py`、模板 -- 接通表单与 303 -- R1
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 2.1 置 review -- R6

**Acceptance Criteria:**
- Given 8 个连续空闲 slot，when POST，then 303 且 1 booking / 8 occupancy / 单一 booking_id。
- Given 9 个、非连续、非对齐、已开始、超 7 天、设备不符或不存在，when POST，then 400 且新增 0 行。
- Given 首格 now+7d-30min，when POST，then 303；首格 now+7d+30min 时 400。
- Given 匿名或缺 CSRF，when POST，then 401 / 400 且新增 0 行。
- Given 成功预约，when GET 该设备该日，then 提交的格全为 `booked_by_self`。

## Implementation Notes

红灯：`9 failed`，全部为 404 断言失败；实现后 `tests/test_create_booking.py` 9 passed，全量 85 passed。评审补齐表单/空选择/审计/跳转断言后为 11 passed、全量 87 passed。

冲突路径不读预检结果做分支：事务内 `select_taken()` 仅收集文案素材，随后始终尝试裸 `INSERT`；`IntegrityError` 只接受 `SQLITE_CONSTRAINT_UNIQUE` 且消息指向 `occupancy.equipment_id, occupancy.slot_start`，回滚后重查全部冲突行再抛 `Conflict`。审计 `booking_create` 与预约、占用同事务提交。

设备存在性、开放窗口与 slot 形状在 `write_tx()` 内复核，避免校验后设备窗口被并发收窄；非唯一键的 `SQLITE_CONSTRAINT_*` 按 architecture §5 映射为 `Validation`（400），不伪装成 409。

## Review Triage Log

| Finding | Verdict | Route |
| --- | --- | --- |
| 校验与 `BEGIN IMMEDIATE` 之间设备窗口可变 | medium | patch：设备读取与校验移入事务 |
| 非唯一 `SQLITE_CONSTRAINT_*` 会变成 500 | medium | patch：映射为 `Validation`/400（architecture §5 表格） |
| 写 0 行测试只数 occupancy | low | patch：统一用 `counts()` 前后比对 |
| 空选择可能 `IndexError` 变 500 | low | patch：新增空选择测试钉住 400 |
| 成功用例未断言审计与 303 `Location` | low | patch：成功测试补审计行与跳转断言 |
| 表单复选框从未被测试 | low | patch：新增 GET 表单复选框集合测试 |
| 409 未重渲染同页并保留选择 | low | defer 2.2：AR-3 / 2.2 冲突页职责 |
| 冲突/409 分支无测试 | low | defer 2.2：epics 将 409 原子性与并发证据分配给 2.2 |
| 隐藏 `date` 未校验、仅影响跳转 | low | defer：不影响写入结果 |
| 提交顺序倒序被判不连续 | low | defer：浏览器复选框按 DOM 顺序提交 |
| 7 天窗口：校验看首格、网格逐格 | maybe-false | defer：PRD FR-4 明确「首个 slot 在 7 天内」，差异需规划确认 |
| 409 文案使用 UTC/equipment_id | false | 用户硬要求 #3 明确要求列出 `equipment_id` 与 `slot_start` |
| `clock` fixture 吞 ImportError | false | 为满足「红灯必须是断言失败、不是 ImportError」的用户硬要求 |

## Verification

**Commands:**
- `python -m pytest tests/test_create_booking.py -q` -- expected: 先红（断言失败，非 ImportError），实现后全绿。
- `python -m pytest -q` -- expected: 既有 76 条与新增测试全绿。
