---
title: 'Story 3.3 锁定与解锁 slot'
type: 'feature'
created: '2026-11-11'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
context: ['project-context.md']
baseline_commit: 'd70757a'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 设备维修、校准的时段仍显示为空闲，学生能提交并占用；管理员也没有任何入口把某个 slot 变成"不能约但不是预约"的状态。

**Approach:** 新增 `GET /admin/equipments/<id>/lock` 页面与 `POST .../lock`、`POST .../unlock`。锁就是 `occupancy` 里 `kind='lock'`、`booking_id IS NULL` 的一行，与预约共用 `uq_occupancy_slot`；服务层 `lock_slots()` / `unlock_slots()` 复用 `insert_occupancy()` 与锁行删除，同一 `write_tx()` 内写 `audit_log`。

## Boundaries & Constraints

**Always:** 锁行只经 `booking_service.py` 写入；冲突只由 `uq_occupancy_slot` 裁决，409 冲突列表在回滚后重查；审计 `action='lock'/'unlock'`、`target_type='equipment'`、`target_id=equipment_id`、`after_json={"slots": [...]}` 与业务写同事务；`@admin_required` 是路由第一行；slot 形状校验只在 `slot_rules.py`；成功 303 回该 slot 所在周。

**Never:** 为锁单独建表、加 `is_locked` 列或改 schema/唯一键；`INSERT OR IGNORE` / `OR REPLACE` / 事务外 check-then-write；在 `web/` 或模板里比较时间、判断状态；解锁删到 `kind='booking'` 的行；做 3.4 的 CSV 导出与审计页；新增运行期依赖。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| LOCK_OK | 10:00 空闲 | 303；该 key 恰 1 行 `kind='lock'`、`booking_id IS NULL` | N/A |
| LOCK_BOOKED | 10:00 已有预约 | 409；原预约行数与 kind 不变、无锁行 | 409 体含 equipment_id 与 slot_start |
| LOCK_DUP | 10:00 已锁定 | 409；仍只有 1 行锁、不新增审计 | N/A |
| UNLOCK_OK | 10:00 已锁定 | 303；该 key 0 行；学生视图 free，可再预约 | N/A |
| UNLOCK_MISSING | 10:00 无锁（空闲） | 404；occupancy 不变 | 解锁预约行同样 404 且预约不动 |
| UNLOCK_PARTIAL | 锁 10:00，请求解锁 10:00+10:30 | 404；10:00 的锁保留（整单原子） | N/A |
| STUDENT_VIEW | 10:00 锁定 | 学生网格 `state == "locked"`；提交该 slot 409；占用行数不变 | N/A |
| AUDIT | 一次锁定 + 一次解锁 | 两条 `lock`/`unlock`，`target_type='equipment'`，`after_json.slots` 含 slot | N/A |
| AUTH | 学生 / 匿名 / 管理员缺 token | 403 / 401 / 400，均不写库 | N/A |
| BAD_SLOT | 非法格式或过去时刻 | 400，不写库 | 锁定只收未来 7 天内的开放窗口 slot |

</frozen-after-approval>

## Code Map

- `src/app/slot_rules.py` — 新增 `validate_lock_slots()`（1+ 个合法、对齐、未来、7 天窗口内、开放时间内；去重保序）与 `validate_unlock_slots()`（仅格式与对齐）；形状规则仍单点在此。
- `src/app/booking_service.py` — 新增 `lock_slots()` / `unlock_slots()`；复用 `_is_slot_clash()`、`_raise_conflict()`、`write_tx()`、`redact.dump_fields("equipment", {"slots": ...})`，不新造写路径。
- `src/data/occupancy_repo.py` — 新增 `delete_lock_rows(conn, equipment_id, slots) -> rowcount`（`kind='lock'` 条件），不改既有函数。
- `src/app/admin_service.py` — 新增 `EquipmentLockView` 与 `build_lock_view()`：设备存在性、缺省日期、`build_slot_grid()` 六态、周一回跳。
- `src/app/slot_service.py` — 仅给 `SlotCell` 加只读属性 `lockable`（free 或 locked），状态判定不动。
- `src/web/admin.py` — 新增 GET 页面与两个 POST；首行 `@admin_required`；只解析表单、映射 303/400/404/409。
- `src/templates/admin_lock.html` — 新建：日期 GET 表单、复用 `_slot_grid.html`、一个表单两个 `formaction` 提交按钮（锁定/解锁）。
- `src/templates/_slot_grid.html` — 增加 `lock_form` 勾选分支（`cell.lockable`），预约分支不变。
- `src/templates/admin_week.html` — 每台设备行加"锁定/解锁"入口，带 `date=view.monday`。
- `tests/test_admin_lock.py` — 新建；先红后绿，HTTP + 只读 SQL 断言。
- 不改：`migrations/`、`tx.py`、`slot_service.py` 状态逻辑、`booking_repo.py`、规划工件。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_admin_lock.py` — 覆盖矩阵、5 条 AC 与重复锁 409 / 解锁缺失 404，先跑出红灯 — R5
- [x] `src/app/slot_rules.py`、`src/data/occupancy_repo.py` — 锁定/解锁校验与锁行删除 — R1/R3
- [x] `src/app/booking_service.py` — 两个用例共用 `write_tx()` 与审计 — R2/R3
- [x] `src/app/admin_service.py`、`src/app/slot_service.py` — 组装锁定页与 lockable — R1
- [x] `src/web/admin.py`、`src/templates/admin_lock.html`、`_slot_grid.html`、`admin_week.html` — 接线与入口 — R1
- [x] `python -m pytest tests/test_admin_lock.py -q` + `python -m pytest -q` — 先红后绿、全量无回归
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` — 3.3 置 `review`，不得 `done` — R6

**Acceptance Criteria:**
- Given 10:00 空闲，when 管理员 POST lock，then 303 且该 key 恰 1 行 `kind='lock'`、`booking_id IS NULL`。
- Given 10:00 已锁定，when 学生刷新并提交该 slot，then 网格 `locked`、提交 409、占用行数不变。
- Given 10:00 已有学生预约，when 管理员锁定，then 409 且原预约行数与 kind 不变。
- Given 10:00 已锁定且无人预约，when 管理员解锁，then 303、该 key 0 行、学生视图 free、学生提交 303。
- Given 一次锁定与一次解锁，when 查 `audit_log`，then 两条 `lock`/`unlock`、`target_type='equipment'`、`after_json.slots` 均含该 slot。
- Given 10:00 已锁定，when 再次锁定，then 409；given 无锁，when 解锁，then 404。

### Review Findings

- [x] [Review][Patch] 解锁 404 文案直接暴露 20 字符 UTC 串，其余管理端文案均为本地 `MM-DD HH:MM`，且测试已把 UTC 形态钉死 [src/app/booking_service.py:270]
- [x] [Review][Patch] 「不能锁定已开始的 slot」分支无断言：唯一过去时段用例 `07:00` 先被开放窗口拦下，把 `<=` 改成 `<` 仍全绿 [src/app/slot_rules.py:122]
- [x] [Review][Patch] `week_monday_for_slots()` 取 `slots[0]` 而非最早 slot，跨周批次回跳周取决于表单顺序 [src/app/admin_service.py:324]
- [x] [Review][Patch] `_render_lock` 的错误分支无测试：非法 `?date=` 的 400 同页兜底、设备不存在/停用的 404 都未被执行（实测非法日期为 400 + 今日网格，非 200）[src/web/admin.py:110]
- [x] [Review][Patch] 锁定页未复用 `.slot-filter`，`.lock-toolbar/.lock-picker/.lock-back/.lock-form` 在 `app.css` 中无任何规则，375px 下日期控件不进入整宽网格 [src/templates/admin_lock.html:7]
- [x] [Review][Patch] 周视图入口的 `date=view.monday` 只被子串断言，删掉参数测试仍绿，管理员会落到“今天”而非所看周 [src/templates/admin_week.html:47]
- [x] [Review][Patch] 解锁路由未做端到端验证：303 目标周与按钮 `formaction` 均无断言；删掉 `formaction` 后“解锁所选”会打到 `/lock` 得 409，17 条测试全绿 [src/web/admin.py:178]
- [x] [Review][Patch] 远未来 slot（如 `9999-12-31T20:00:00Z`）在 `utc_to_local()` 抛 `OverflowError` → 500；窗口检查排在本地时间换算之后 [src/app/slot_rules.py:120]
- [x] [Review][Patch] 多 slot 解锁成功路径无测试：只有单 slot 成功、多 slot 锁定、多 slot 404 原子性 [tests/test_admin_lock.py:307]
- [x] [Review][Patch] `deferred-work.md` 缺 3.3 的 R5 条目：先红后绿不可复核的缺口未像 2.4/3.2 那样登记（3.3 小节已在本轮建好）[_bmad-output/implementation-artifacts/deferred-work.md:109]
- [x] [Review][Defer] 架构契约未同步 3.3 新增面：`architecture.md:60` 与 `project-context.md` 仍写“四个用例 / 仅 `insert_occupancy()` 与 `delete_occupancy()`”，§15.1 缺 `GET /admin/equipments/<id>/lock` 行 [_bmad-output/planning-artifacts/architecture.md:60] — deferred: 改规划工件须人工确认并按 R7 同步 PRD §11

**Rejected**

- `low` spec 自述“5 条 AC”但列了 6 条，且“13 passed / 全量 180”与 17 条、184 条不符 —— 事实成立，但修法是改评审中的 spec 本身，按规则驳回。
- `low` `## Spec Change Log` 为空，10 条 patch 的去向只留在正文散文里 —— 同上，修法是改本 spec。
- `low` Verification 只列命令不记结果 —— 同上，修法是改本 spec。
- `low` `validate_unlock_slots()` docstring 说可清理历史锁，Design Notes 又说“历史锁不提供清理入口” —— 需先由人决定是否允许清理历史锁，函数偏宽松无用户可见损害。
- `low` `_slot_grid.html` 的 aria-label 新增 `cell.label`，改变了学生页与改单页的无障碍名 —— 新名称更完整，修法要加条件分支，无实际损害。
- `false` 改单到已锁 slot 无测试 —— `tests/test_admin_edit_booking.py:471` 的 `test_locked_target_returns_409_and_marks_locked_cell` 已覆盖 409、`data-state="locked"`、零写库；并发 demo 属 2.2。
- `false` POST 到不存在/停用设备返回 404 与 Code Map 不符 —— Code Map 明列 404，且 `build_lock_view()` 抛的正是 `NotFound("设备不存在")`（实测 404）。
- `false` `/admin/week` 把每条锁都算进“异常 slot” —— Story 3.1 的 AC 与 I/O 矩阵 `LOCK_ANOMALY` 明确要求锁定格进异常摘要。
- `low` 锁定页 409 重渲染无 `conflict_scope == "page"` 整页提示 —— 只有冲突行不在当日（伪造或跨日竞态）才出现，页面已有 `role="alert"` 文案列出冲突 slot；修法要加模板分支。
- `low` 请求内重复 slot 被静默去重，而预约路径判 400“必须连续” —— 去重有 docstring 明示目的，改判需产品意图，无用户可见损害。


## Implementation Notes

- 2026-11-11：先写 `tests/test_admin_lock.py`（13 条），首跑 12 failed / 1 passed（学生视图 `locked` 与提交 409 已由 1.3/2.1 覆盖）；实现后 13 passed，全量 180 passed（基线 167）。
- 锁行复用 `insert_occupancy(..., booking_id=None, kind='lock')`；冲突只由 `uq_occupancy_slot` 抛 `IntegrityError`，回滚后 `_raise_conflict()` 重查生成含 `equipment_id`/`slot_start` 的 409 文案。
- 解锁按 `equipment_id + slot_start + kind='lock'` 删除并比对 rowcount；少一行即 404 且 `write_tx()` 整单回滚，`booking` 行不受影响。
- `SlotCell.lockable` 只在服务层判定（free / locked），模板只按布尔值渲染；周视图设备行新增“锁定/解锁”入口。
- 自定决策：锁定只收未来 7 天内、开放窗口内的对齐 slot；解锁只校验格式与对齐；一页两按钮用 `formaction` 区分锁定/解锁。
- 本运行时子代理使用隔离工作树，无法与主工作树共享 TDD 红灯证据，故按 step-03 的直接实现分支在主工作树完成。
- 2026-11-11 评审收口：回跳周改为按已写入 slot 推导；`lockable` 排除冲突格，409 重渲染不再让管理员原地重提交；解锁 404 列出请求 slot；补 7 天窗口提示与 aria 标签；新增跨周重定向、混合批次原子性、GET 鉴权与 `/unlock` CSRF 用例（17 passed）。

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Route |
| --- | --- | --- |
| BH-01 成功 303 用表单 date 而非写入 slot 的周 | low | patch：新增 `week_monday_for_slots()`，回跳周按已写入 slot 推导 |
| BH-02 锁定无 8 格上限 | false | 锁不是预约，整天锁定是合法诉求；intent 未设上限 |
| BH-03 一页两按钮可混合勾选 | false | 混合选择必然命中用户要求的 404/409；页面已指导按状态分按钮 |
| BH-04 重复锁 409 复用预约文案 | low | 驳回：区分文案需按行来源分支，收益不足 |
| BH-05 解锁 404 不列 slot | low | patch：404 文案附请求 slot |
| BH-06 设备不存在/停用状态混用 | low | 驳回：仅伪造停用 id 可达，最终仍是 404 |
| BH-07 `week_monday_for_day` 重复日期归一 | low | patch：随 BH-01 删除，只保留一个归一入口 |
| BH-08 `_render_lock` 对任意 Validation 重取今天 | low | 驳回：同一设备配置错误会再次抛出，不会被掩盖 |
| BH-09 历史/窗口外锁无 UI 清理入口 | low | 驳回：历史锁失活，无功能影响；合成格子超出本 Story |
| BH-10 页面未写 7 天锁定窗口 | low | patch：提示补窗口与过去时段限制 |
| BH-11 锁定页硬编码图例 | false | 与周视图/改单页一致；多余项不可达但无害 |
| BH-12 周视图入口固定 `date=monday` | low | patch：补 `aria-label`；周一为周默认入口 |
| BH-13 勾选框 aria 未带状态 | low | patch：aria-label 加 `cell.label` |
| BH-14 矩阵缺设备/非法日期/重渲染行 | false | 修法是改 spec，按规则驳回 |
| BH-15 Spec 日志与决策编号 | false | 同上 |
| BH-16 sprint-status 仍是 in-progress | low | patch：收尾置 `review` |
| BH-17 架构路由表无 GET 锁定页 | false | 3.2 的 GET 改单页同样未入表；只读页不违反写路径契约 |
| BH-18 “@admin_required 路由第一行”措辞 | false | 指函数体首行；装饰器顺序正确 |
| BH-19 “不改 slot_service”与新增 lockable | false | 修法是改 spec |
| BH-20 303 Location 无断言 | medium | patch：补本日与跨周 Location 断言 |
| BH-21 仅 lock 路由测了 CSRF | medium | patch：补 `/unlock` 缺 token 400 |
| BH-22 closed_past 无勾选未断言 | low | patch：锁定页断言 08:00 无勾选 |
| BH-23 校验函数无单元测试 | low | defer：HTTP 已覆盖，登记为后续加固 |
| BH-24 红灯证据未归档 | false | 修法是改 spec；R5 红灯已在会话内实际跑出 |
| EC-01 409 重渲染仍可勾选冲突格 | medium | patch：`lockable` 排除 `conflicted`，并补重渲染断言 |
| EC-02 过去/窗口外锁无 UI 清理 | low | 驳回：同 BH-09 |
| EC-03 303 周与 slot 不一致 | low | patch：同 BH-01 |
| EC-04 停用设备重渲染丢视图 | low | 驳回：同 BH-06 |
| EC-05 claim：303 回 slot 所在周 | medium | patch：同 BH-01/BH-20 |
| VG-01 成功回跳的周未被测试锁定 | medium | patch：同 BH-20 |
| VG-02 混合空闲/已约批次无零写入测试 | medium | patch：新增 409 后零锁行、零审计断言 |
| VG-03 GET 鉴权与 /unlock CSRF 未测 | medium | patch：补 401/403 与缺 token 400 |
| VG-04 重复 slot 去重未被测试锁定 | low | defer：表单每格一个值，正常流程不可达 |

## Design Notes

锁页与预约页的区别只有"哪些格可勾选"：`SlotCell.lockable` 在服务层判定，模板只按布尔值渲染。解锁按 `equipment_id + slot_start + kind='lock'` 删除并核对 rowcount；rowcount 不足即 404 并整单回滚，避免"解了一半"。锁只收未来 slot，历史锁自然失活、不提供清理入口。

## Verification

**Commands:**
- `python -m pytest tests/test_admin_lock.py -q` — 先红后绿。
- `python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_story33_full` — 全量回归（基线 167）。
