---
title: 'Story 2.4 连续多 slot 选择与改单边界'
type: 'feature'
created: '2026-11-11'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 1
context: []
baseline_commit: 'ca904276d84e3efe313650d6b4d777f761c9fdba'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 创建预约已有形状校验，但改单仍会复制第二份规则；且“先插新行、再删旧行”会在目标与自身旧集合相交时撞上自己的唯一键，把成功改单误报成 409。

**Approach:** 在 `src/app/slot_rules.py` 用 `validate(..., mode="create"|"edit")` 单点承载全部形状/窗口规则，仅 edit 额外执行 2 小时截止；在 `booking_service.edit_booking()` 的单个 `write_tx()` 内先删旧 occupancy、再插新 occupancy、更新同一 booking 并写审计。本 Story 只做规则内核与服务层，HTTP 路由与表单留给 3.2。

## Boundaries & Constraints

**Always:** 规则只在 `slot_rules.validate()` 实现一次；create 与 edit 共用同一套检查；edit 的 2 小时截止同时约束原预约首 slot 与目标首 slot；冲突只由 `uq_occupancy_slot` 裁决；改单固定顺序 SELECT booking → DELETE 旧行 → INSERT 新行 → UPDATE booking → 审计；失败整单回滚，原 occupancy 按 `(equipment_id, slot_start, kind, booking_id)` 逐行不变；booking_id 与 id 不变，updated_at 严格递增。

**Never:** 第二条校验路径或复制连续性判断；先插后删；事务外 check-then-write；`INSERT OR IGNORE` / `OR REPLACE`；把外键等 IntegrityError 伪装成 409；改 migrations、唯一键或 CHECK；实现 3.2 路由/表单；新增运行期依赖。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 规则矩阵 | 合法连续 / 中断 / 9 个 / 非对齐 / 开放窗口外 / 首格超 7 天 | create 与 edit 结果一致：合法通过，非法 `Validation` | 400（web 层，3.2） |
| 换设备 | 改单请求换 `equipment_id` | `Validation`；booking 行与 occupancy 行都不变 | 400 |
| edit 截止 | 目标首格距 now 1h59 | create 通过；edit `Validation` | 400 |
| 自身重叠 | 旧 14:00–15:00，改到 14:30–15:30 | 成功；该 booking_id 恰 3 行新 slot；id 不变 | N/A |
| 他人冲突 | 目标含他人 booking 或 lock | `Conflict`；原占用逐行不变 | 409 |
| 形状失败 | 改单目标 9 个或有间隙 | `Validation`；原占用逐行不变 | 400 |
| 原预约临期 | 原首格距 now 1h59 | `Validation`；原占用逐行不变 | 400 |
| 成功改单 | 新旧集合有交集 | 无重复 key；该 booking_id 行数等于新集合大小 | N/A |
| 单点调用 | 先创建再改单，spy `slot_rules.validate` | mode 序列恰为 `["create", "edit"]` | N/A |
| 时间戳 | 改单前后 booking 行 | `id` 相同，`updated_at` 字典序严格更大 | N/A |

</frozen-after-approval>

## Code Map

- `src/app/slot_rules.py` -- 将 `validate_slots()` 收敛为 `validate(..., *, mode, current_first_slot=None)`；create/edit 共用全部检查。
- `src/app/booking_service.py` -- 创建路径改调 `slot_rules.validate(..., mode="create")`；新增 `edit_booking()`，单事务内先删后插；换设备请求直接 `Validation`（改单只改时间）。
- `src/data/occupancy_repo.py` -- 追加 `delete_occupancy()`、`list_for_booking()`，并让 `select_taken()` 可排除被改预约自身。
- `src/data/booking_repo.py` -- 追加 `update_booking()`，更新 equipment_id 与 updated_at，不改 id。
- `src/core/timeutil.py` -- 追加 `strictly_later_utc()`，保证同一秒内改单 updated_at 仍严格递增。
- `tests/test_slot_rules.py` -- 新增本 Story 全部测试；服务层直接构造预约，不接 HTTP。
- 不改：`migrations/`、`src/web/`、`src/templates/`、planning artifacts。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_slot_rules.py` -- 先写矩阵、自身重叠、冲突回滚、形状失败、临期、单点 spy、时间戳测试并跑出红灯 -- R5
- [x] `src/app/slot_rules.py` -- 单点实现 create/edit 与 edit 截止 -- R1
- [x] `src/data/occupancy_repo.py`、`src/data/booking_repo.py` -- 增加删除/查询/更新仓储函数，不控制事务 -- R2
- [x] `src/core/timeutil.py` -- 增加严格递增 UTC 工具 -- R4
- [x] `src/app/booking_service.py` -- 新增同日单事务改单用例与 409 映射 -- R2/R3
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 2.4 置 `review` -- R6

**Acceptance Criteria:**
- Given 规则矩阵七类用例，when 分别以 create/edit 调用 `slot_rules.validate`，then 结果与 EXPECTED_MATRIX 一致，仅 2h 截止用例在 edit 下失败。
- Given 旧预约占 3 个 slot 且目标与旧集合相交，when 改单，then 成功、booking_id 不变、恰 3 行新 slot。
- Given 目标含他人预约或锁定，when 改单，then `Conflict` 且 occupancy 逐行不变（kind/booking_id 含在内）。
- Given 目标 9 个或有间隙，when 改单，then `Validation` 且 occupancy 逐行不变。
- Given 原预约首 slot 距 now 1h59，when 改单，then `Validation` 且 occupancy 逐行不变。
- Given 成功改单，when 检查 key 分布，then 无重复 key 且该 booking_id 行数等于新集合大小。
- Given 先创建再改单，when spy `slot_rules.validate`，then mode 序列为 `["create", "edit"]`。
- Given 成功改单前后 booking 行，when 比较，then `id` 相同且 `updated_at` 严格递增。

## Implementation Notes

HTTP 303/400/409 的映射属于 Story 3.2；本 Story 以服务层“无异常 / Validation / Conflict”为等价契约。

红灯：`tests/test_slot_rules.py` 9 failed，均为缺少 `slot_rules.validate`、`booking_service.edit_booking`、`occupancy_repo.delete_occupancy` 的行为失败；无夹具或环境错误。

绿灯：`tests/test_slot_rules.py` 9 passed；全量 `130 passed`。

实现决定：edit 的 2 小时截止同时检查原预约首 slot 与目标首 slot；改单在同一 `write_tx()` 内严格先 `DELETE` 后 `INSERT`；冲突回滚后重查时排除被改预约自身的旧行，避免把自身 slot 报进 409；`updated_at` 经 `strictly_later_utc()` 保证同一秒内仍严格递增。

本仓库渲染的 workflow 未配置 review-prompts，故无独立评审层可跑；上述证据与源码 diff 由实现方自检。

## Review Triage Log

| Finding | Verdict | Route |
| --- | --- | --- |
| 无独立评审层（review-prompts 不存在） | — | 自检；无 finding 可登记 |

## Verification

**Commands:**
- `python -m pytest tests/test_slot_rules.py -q` -- 先红（断言失败），实现后全绿。
- `python -m pytest -q` -- 全量回归全绿。

### Review Findings

评审：2026-11-11，四个独立评审层（blind-hunter / edge-case-hunter / verification-gap / acceptance-auditor）并行，基线 `ca904276`，范围 `ca904276..1aad2d6`。

**Decision（已由人工裁定）**

- 2026-11-11 裁定：`sprint-status.yaml` 里 Story 2.3 的 `done` 与 `spec-2-3-cancel-booking.md` 的 `in-review` 均为人工修改，R6 未违反；以 `sprint-status.yaml` 为准，不回退。
- 2026-11-11 裁定：「跨设备」= 禁止改单换设备，设备不同须取消后重新预约，改单只改时间。原实现允许 E1→E2 属缺陷。
- 2026-11-11 裁定：`epics.md` 2.4 的 AC 改为服务层契约（无异常 / `Validation` / `Conflict`），HTTP `303/400/409` 的断言归 Story 3.2；`PRD.md` §11 的 Story/Test 列不变。

**Patch（已全部应用）**

- [x] [Review][Patch] 改单写路径的审计与顺序无断言 [src/app/booking_service.py:183] — 已补 `test_successful_edit_writes_one_booking_edit_audit_row`（actor/action/target 与 before/after 的 `slots`）、`test_failed_edit_writes_no_audit_row`；顺序 spy 扩到 `write_tx → delete → insert → update → audit` 五步。
- [x] [Review][Patch] 改单换设备未被拒绝 [src/app/booking_service.py:145] — `equipment_id != booking["equipment_id"]` 时抛 `Validation`；矩阵 7 类收敛为 6 类形状规则，新增 `test_edit_to_another_equipment_is_validation_and_keeps_every_row` 覆盖第 7 类。
- [x] [Review][Patch] `mode="edit"` 缺 `current_first_slot` 时静默跳过原预约 2 小时截止 [src/app/slot_rules.py:73] — `validate()` 现要求 edit 必传、create 不得传，否则 `ValueError`；矩阵与截止用例同步传参。

**Defer**

- [x] [Review][Defer] 溯源未同步且 FR-7 的 ADR 集合不一致 [_bmad-output/planning-artifacts/PRD.md:361] — deferred: 修法需改规划工件（PRD/epics），R7 要求人工确认后同一改动完成；`PRD.md:361` 有 2.3 的日期确认行而 2.4 没有，`PRD.md` FR-7 行写 ADR-002/003/005，`epics.md` 2.4 写 ADR-001/005。
- [x] [Review][Defer] R5 红灯证据无法从改动复核 [_bmad-output/implementation-artifacts/spec-2-4-slot-rules-edit.md:76] — deferred: 单 commit `1aad2d6` 同时含测试与实现，`9 failed` 只有自述；需要开发者提供先红后绿的运行记录才能定论。

**Rejected**

- `false` — Story 2.3 被置 `done` 违反 R6：人工裁定该状态由其本人修改，R6 不成立。
- `false` — 未知 `mode` 抛裸 `ValueError` 会经 web 层变成 500：`mode` 只由本仓库调用方以字面量传入，用户输入不可达，不构成可达缺陷。
- `false` — `delete_occupancy` 的 `kind = 'booking'` 与 `list_for_booking` 无 kind 过滤不一致，会把有效改单报成 404：`migrations/001_init.sql:41-42` 的 CHECK 强制 `kind='lock'` 必须 `booking_id IS NULL`，两集合恒等。
- `false` — `edit_booking` 三个 `NotFound` 与 `update_booking(...) != 1` 不可达是缺陷：同一 `BEGIN IMMEDIATE` 内 `get_by_id` 已成功、行必然存在；不可达路径上的显式失败不是缺陷。
- `false` — 409 文案不区分 lock 与他人预约：契约只要求 409 体列出 `equipment_id` 与 `slot_start`。
- `false` — 409 冲突列表在事务外重查可能过期：`project-context.md` 明确要求 ROLLBACK 之后重新查询，属既定设计。
- `false` — 矩阵测试无法区分是哪条规则失败：AC 的断言就是结果码相等，测试与 AC 同构。
- `low` — 复用 `CANCEL_LEAD_HOURS` 让 FR-6 与 FR-7 耦合：同模块同阈值 2 小时，拆常量只增接口面不增正确性。
- `low` — `strictly_later_utc` 同秒分支会把 `updated_at` 推到 `now + 1s`：1 秒偏移，无消费者依赖 `updated_at <= now`。
- `low` — `list_for_booking` 与 `list_slots_for_booking` 重复：列投影不同且都是只读查询，不减少出错面。
- `low` — 矩阵缺重复 slot 用例：`[14:00, 14:00]` 已被连续性检查拒绝。
- 不立案 — `spec-2-4:82-88` 称 `review-prompts` 不存在（实际目录下有两个提示文件）：修复方式是改被评审的 spec 本身，故不立案；本次评审已补做四个独立评审层。
- 不立案 — 3.2 需接手 `admin_required` 与 `current_first_slot` 的交接未落到文字：修复方式是改被评审的 spec 本身；已在此记录为 3.2 的必接项：路由第一行 `@admin_required`，且 `edit_booking()` 不接受换设备。