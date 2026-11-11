---
title: 'Story 3.2 管理员改单'
type: 'feature'
created: '2026-11-11'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
context: ['project-context.md']
baseline_commit: '09c2380'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 3.1 的周视图只能看不能改；服务层 `edit_booking()` 已具备改单语义，但没有 HTTP 入口把 303/400/409 映射出来，管理员无法在线处理学生私下换时段。

**Approach:** 新增 `GET/POST /admin/bookings/<id>/edit`。GET 复用 `build_slot_grid()` 渲染改单表单（设备只读、可换日期、勾选新时段）；POST 只解析表单并调用 2.4 的 `edit_booking()`。409 在同一请求内按提交的日期与时段重建网格、标出冲突格并保留勾选；成功 303 回原周视图。设备不可更换（D-011）。

## Boundaries & Constraints

**Always:** `@admin_required` 是路由第一行；所有形状/窗口/截止校验只经 `edit_booking()` → `slot_rules.validate()`；写路径只经 `write_tx()`；冲突只由 `uq_occupancy_slot` 裁决；409 的网格在事务回滚后重新查询；成功时 `booking_id` 不变且恰一条 `booking_edit` 审计；周视图与改单页共用 `_slot_grid.html`。

**Never:** 在 `src/web/` 或模板里写时间比较、冲突判断或第二套校验；改单换设备；渲染时直写 `occupancy`；`INSERT OR IGNORE` / `OR REPLACE` / 事务外 check-then-write；改迁移、唯一键或 CHECK；新增运行期依赖；给学生路由加角色分支。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| EDIT_OK | 目标集合合法且空闲 | 303 回 `/admin/week?week=<原周>`；恰一条 `booking_edit` | N/A |
| CONFLICT | 目标含他人预约或锁定 | 409；原 occupancy 逐行不变 | 该 booking_id 行与 id 保持 |
| EQUIPMENT_CHANGE | 提交另一台设备 | 400 | 不是 404/409，行与审计都不变 |
| SELF_OVERLAP | 新旧集合相交（14:00→14:30） | 303；无重复键，行数等于新集合 | N/A |
| RESELECT | 409 重渲染 | 保留提交日期/网格，冲突格 `data-conflict="1"`，空闲的已选格仍 checked | N/A |
| PRESELECT | GET 改单页 | 原时段在网格中带 `data-selected="1"`，摘要展示本地时段 | N/A |
| AUTH | 学生 / 匿名 | 403 / 401 | 不写库 |
| UNKNOWN | 不存在的 booking_id | 404 | N/A |
| MISSING_CSRF | 管理员缺 token | 400 | 不写库 |
| BAD_DATE | `?date=` 非法 | 回到原日期重渲染并提示 | 400 |

</frozen-after-approval>

## Code Map

- `src/app/admin_service.py` — 新增 `BookingEditView`、`build_booking_edit_view()` 与 `booking_week_monday()`：读 booking/occupancy、复用 `build_slot_grid()`，无冲突时把展示作用域归零；原周由首个 slot 推导。
- `src/app/slot_service.py` — `SlotCell` 增加只读属性 `editable`（空闲或本预约已选），让改单页能勾选自己的旧 slot 做顺延。
- `src/web/admin.py` — 新增 GET/POST `/bookings/<id>/edit` 与 `_render_edit()`；第一行 `@admin_required`，只解析表单和映射错误；成功回跳用服务层算出的原周。
- `src/templates/admin_booking_edit.html` — 新建：摘要、返回原周、日期 GET 表单、POST 表单（隐藏 equipment_id/date），复用 `_slot_grid.html`，离格冲突显示整页提示。
- `src/templates/_slot_grid.html` — 勾选条件改为 `cell.editable`；`cell.selected` 输出 `data-selected="1"`；`aria-label` 可用 `slot_action` 覆写。
- `src/templates/admin_week.html` — 预约表新增“操作”列，链到改单页。
- `src/static/app.css` — 为 `data-selected="1"` 增加虚线高亮。
- `tests/test_admin_edit_booking.py` — 新建，先红后绿；播种用户/设备/预约，经 HTTP 与只读 SQL 断言。
- 不改：`booking_service.py`（2.4 已完成）、`slot_rules.py`、`slot_service.py`、`migrations/`、规划工件。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_admin_edit_booking.py` — 覆盖矩阵与 5 条 AC，先跑出 13 failed — R5
- [x] `src/app/admin_service.py` — 组装改单视图并复用六态 — R1
- [x] `src/web/admin.py` — 接线路由与 303/400/409/404 映射 — R1
- [x] `src/templates/admin_booking_edit.html`、`_slot_grid.html`、`admin_week.html` — 表单、选中标记与入口 — R1
- [x] `python -m pytest tests/test_admin_edit_booking.py -q` — 全绿（18 passed）— R5
- [x] `python -m pytest -q` — 全量无回归（166 passed）— R5
- [x] `sprint-status.yaml` — 3.2 置 `review`，不得 `done` — R6

**Acceptance Criteria:**
- Given 15:00 已被他人占用，when 管理员改单，then 409 且该 booking_id 的行与 id 不变。
- Given 目标合法空闲，when 提交，then 303、恰一条 `booking_edit`，before/after 的 slots 分别为旧/新集合。
- Given 一次成功改单，when 统计全库，then 无重复 `(equipment_id, slot_start)` 且该单行数等于新集合大小。
- Given 14:00 改到 16:00，when 另一学生刷新日视图，then 14:00 `free`、16:00 `booked_by_other`。
- Given 学生或匿名，when 访问改单 GET/POST，then 403 / 401 且占用不变。
- Given 提交另一台设备，when 管理员改单，then 400（D-011），行、设备与审计都不变。
- Given 409，when 查看响应，then 保留提交日期与网格，冲突格标出，空闲的已选格仍勾选。

### Review Findings

第二轮独立评审（4 层：Blind Hunter / Edge Case Hunter / Verification Gap / Acceptance Auditor），基线 `09c2380..50dae79`。

- [x] [Review][Decision] `_render_edit` 的异常分支丢弃提交态，且页面把**原始时段**显示为已勾选 — Validation 分支（`src/web/admin.py:96`）不传 `selected_slots`，于是形状错误（不连续、9 格、2 小时截止）的 400 页把旧 slot 勾上，错误文案与已勾状态互相矛盾；日期解析失败的回退分支（`src/web/admin.py:54-62`）又不传 `conflicted_slots`，带冲突的这类请求会渲染出无标记网格。首轮已把“400 丢弃已提交选择”判为驳回（BH-08，理由：契约只固定 409），故此处需人工定夺：保留提交选择 / 全部清空 / 维持现状。 **已定（2026-11-11）：选项 1 — 两个异常分支都回传 selected_slots / conflicted_slots，与 409 保持同一套行为；首轮 BH-08 的驳回理由不成立（规则没写不等于禁止）。**
- [x] [Review][Patch] `SlotCell.editable` 判的是“调用方传入的 selected”，不是“本预约自己的格”，并随共享模板外溢到学生页 [src/app/slot_service.py:67]
- [x] [Review][Patch] 选中态描边覆盖冲突描边：`[data-selected="1"]` 与 `.is-conflict` 同特异性但在后，409 页冲突格丢红色实线轮廓 [src/static/app.css:182]
- [x] [Review][Patch] “303 回原周”没有能区分原周与提交日的测试：唯一 Location 断言里原周与目标同属一周 [tests/test_admin_edit_booking.py:299]
- [x] [Review][Patch] R5 先红后绿证据不可从历史复核（测试与实现同一 commit），且未像 2.4 那样登记到 `deferred-work.md` [_bmad-output/implementation-artifacts/spec-3-2-admin-edit-booking.md:58]
- [x] [Review][Patch] `if not conflicted_slots: replace(..., "none")` 把“冲突列表为空”当成“无冲突”，空 `conflict_slots` 的 409 会渲染一屏 `data-conflict="0"` [src/app/admin_service.py:286]
- [x] [Review][Patch] 改单页图例缺“已选/原时段”键，却列了管理员永远看不到的“我的预约” [src/templates/admin_booking_edit.html:33]
- [x] [Review][Patch] 改单页文案让管理员“取消后重新预约”，但 `/admin/*` 没有任何取消入口 [src/templates/admin_booking_edit.html:14]
- [x] [Review][Patch] `BookingEditView.slots` 是死字段（模板只用 `slots_display`） [src/app/admin_service.py:92]
- [x] [Review][Patch] 409 响应体“必须列出冲突的 `equipment_id` 与 `slot_start`”在本 Story 测试里没有断言（`locked_slot in html` 因每格都带 `data-slot` 而恒真） [tests/test_admin_edit_booking.py:485]
- [x] [Review][Defer] 无变更的改单也会写一条 `booking_edit` 审计 [src/app/admin_service.py:277] — deferred: 服务层（2.4）无 no-op 守卫，本 Story 只接线；预勾原时段让误提交变容易，但不是本改动引入
- [x] [Review][Defer] `PRD.md` FR-7 与 `epics.md` Story 3.2 仍写“可改到另一台设备”，与 D-011 相反 [PRD.md:183] — deferred: 规划工件漂移，已登记，需人工按 R7 同步 §11

Rejected:

- `false` 跨周改单 303 落到旧周是“错周” — 冻结的 Intent/矩阵 EDIT_OK 明确要求回“原周”，代码与契约一致；UX 取舍不属缺陷。
- `false` 模板 `{% if error and view.grid.conflict_scope == "page" %}` 违反 R1 — 只按服务层算出的枚举选横幅，不判冲突；`_slot_grid.html` 的 `cell.conflicted` 自 1.3 起是同一惯例。
- `false` `replace(grid, conflict_scope="none")` 造成双写/文档不一致 — 该调用点就是要清掉“因 selected 非空→page”的哨兵，未给出任何受影响调用方的错误结果。
- `low` 整页冲突横幅只能由 UI 造不出的请求触发（测试伪造了它） — 属防御性分支，无害；改成带冲突日链接需重做入口。
- `low` 400 形状错误（0 格 / 断档 / 9 格 / 2 小时截止）缺 HTTP 级用例 — 规则由 2.4 服务层测试覆盖，路由的 Validation→400 已被换设备与缺 CSRF 两条钉住。
- `low` 成功 303 后无任何确认反馈 — 项目无 flash 设施，补上属新增面。
- `low` `test_week_view_links_to_edit_form_for_each_booking` 只播种 1 条 — 断言的就是“存在入口”，命名夸大不影响保护力。
- `low` slot 标签 `%m-%d %H:%M` 无年份/星期 — 与 2.3/3.1 既有展示约定一致。
- `low` “改单”链接无可区分的无障碍名、`_slot_grid.html` 单行超长 — 纯外观，改动波及每行。
- `low` 日期输入无 min/max、页面不展示 7 天窗口与 2 小时截止 — 在模板算边界即触碰 R4/R1，代价高于收益。
- `false` 测试断言 `"11-11 14:00" in html` 钉住展示文案 — PRESELECT 矩阵要求“摘要展示本地时段”，该断言正是契约本身。
- `false` spec 自身矛盾（`slot_service.py` 既在改动清单又在“不改”清单） / `Spec Change Log` 为空 / AC 计数 5 vs 7 — 修法都是改被测 spec 文本，按规则直接驳回。

## Implementation Notes

- 2026-11-11（第二轮评审收口）：`_render_edit` 的两个异常分支都回传提交集合；`SlotCell.own` + `build_slot_grid(own_slots=)` 把可重选范围收回“本预约自己的占用格”，学生页恢复 free-only；`conflict_pending` 时 409 不再把作用域归零；补 CSS `:not(.is-conflict)`、图例与跨周 303 用例（19 passed / 167 passed）。- 2026-11-11：先写 `tests/test_admin_edit_booking.py`（初版 13 条），在路由未接线时跑出 13 failed（全部 404），实现后转绿；评审补齐后 18 passed。
- 改单页的原时段格子状态是 `booked_by_other`（管理员不是 owner）；`SlotCell.editable` 让本预约的已选格也能勾选，管理员可保留 14:30 顺延到 15:00，而不必整段重选。
- 原周不再由表单回显：`booking_week_monday()` 在写之前从原预约首个 slot 推导周一，扫码/检索进入也能 303 回原周，非法 `week` 不再造成“写入成功但落地 400”。
- 无冲突时 `conflict_scope` 归零；冲突格落在提交日之外时，改单页显示整页冲突提示，不留“看起来没问题”的网格。
- 全量回归：`166 passed`（基线 148 + 新增 18），未改 `booking_service.py` 与 `slot_rules.py`。

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Route |
| --- | --- | --- |
| BH-01 sprint-status 仍是 in-progress | low | patch：收尾置 `review` |
| BH-02 spec 的红灯/AC 计数笔误 | false | 文本笔误，已更正注释；不是代码缺陷 |
| BH-03 epics/PRD 仍写“改到另一台设备” | low | defer：规划工件与 D-011 漂移，需人工按 R7 同步 |
| BH-04 选中态无样式/无图例 | low | patch：补 `data-selected` 虚线样式 |
| BH-05 干净 GET 被标成 page 作用域 | low | patch：无冲突时 `conflict_scope="none"` |
| BH-06 页面未提示 2h/8 格/连续性 | low | 驳回：与创建页一致，修复需新增规则展示 |
| BH-07 周视图对不可改预约也给链接 | low | 驳回：修复需可编辑标志与新分支，超出本 Story |
| BH-08 400 丢弃已提交选择 | low | 驳回：契约只固定 409；换设备时保留选择反而误导 |
| BH-09 矩阵缺 400/锁定形态覆盖 | medium | patch：补锁定、多冲突、离格、只读四类测试 |
| BH-10 缺 week 缺省/只读/冲突全列测试 | medium | patch：week 输入已移除；补只读与多冲突测试 |
| BH-11 week 未校验，写后可能 400 | medium | patch：改为服务层推导原周 |
| BH-12 BAD_DATE 文案泛化 | low | 驳回：共享文案，改动会波及创建页 |
| BH-13 设备停用后改单页 404 | low | 驳回：当前没有停用路由，不可达 |
| BH-14 无返回链接/裸 id/空学号 | low | patch：补返回原周链接；id 是既有展示约定，FK 保证学号 |
| BH-15 改单页 aria-label 仍是“开始预约” | low | patch：`slot_action` 覆写为“改到该时段” |
| BH-16 `admin.py` 文档字符串过时 | low | patch：更新模块说明 |
| BH-17 `BookingEditView.day` 死字段 | low | patch：改为模板使用的 `week_monday` |
| BH-18 baseline 用全 SHA | low | patch：改为短 SHA，与 3.1 一致 |
| VG-01 week 只由伪造请求覆盖 | medium | patch：改为服务层推导并断言 303 目标 |
| VG-02 检索结果无改单入口 | low | defer：范围决定，已登记 |
| VG-03 sprint-status 未到 review | low | patch：同 BH-01 |
| EC-01 非法 week 写后 400 | medium | patch：同 BH-11 |
| EC-02 400 丢选择 | low | 驳回：同 BH-08 |
| EC-03 干净 GET 的 page 作用域 | low | patch：同 BH-05 |
| EC-04 离格冲突无标记 | medium | patch：整页冲突横幅 + 测试 |
| EC-05 本预约旧 slot 不可勾选 | medium | patch：`SlotCell.editable` + 勾选测试 |
| EC-06 sprint-status 声明不符 | low | patch：同 BH-01 |
| EC-07 “409 丢日期/选择” | false | 正常 409 路径已传提交日期与选择；离格由 EC-04 兜底 |
| EC-08 “303 未回原周” | low | patch：已由服务层推导原周，任何入口一致 |

## Design Notes

改单页的设备是只读隐藏字段：换设备不是“改时间”，按 D-011 由服务层抛 `Validation`，HTTP 层只映射 400。原时段在网格里显示为 `booked_by_other`（管理员不是 owner）；`SlotCell.editable` 让“本预约已选且未冲突”的格子也可勾选，因此顺延改单能在页面上完成。409 的网格必须在 `write_tx()` 抛错回滚之后重建，才能看到已提交的真实占用；离格冲突退化为整页横幅。

## Verification

**Commands:**
- `python -m pytest tests/test_admin_edit_booking.py -q` -- 先红（13 failed）后全绿（18 passed）。
- `python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_story32_full2` -- 全量回归 166 passed。
