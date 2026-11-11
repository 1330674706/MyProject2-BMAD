---
title: 'Story 3.1 管理员本周视图与按学号检索'
type: 'feature'
created: '2026-11-11'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: ['project-context.md']
baseline_commit: '4f20f96'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 管理员没有本周总览或按学号定位学生预约的入口；异常只能导出后肉眼比对。

**Approach:** 新增只读 `/admin/week` 与 `/admin/users?student_no=`。周视图按 Asia/Shanghai 自然周逐设备逐日调用 `slot_service.build_slot_grid()`，继续用 `_slot_grid.html` 渲染六态；管理员归属与异常元数据由新 `admin_service.py` 附加。全程不写 `occupancy`。

## Boundaries & Constraints

**Always:** 六态只在 `slot_service.py` 判定；周视图复用 `_slot_grid.html`，不另造格子；`/admin/*` 第一行 `@admin_required`；自然周用本地周一 00:00 至下周一 00:00 的 UTC 半开区间 `>= ? AND < ?`；检索精确优先、再前缀、查无结果 200 空列表；管理员可含学号与 `booking_id`，学生响应不得含他人学号或 `booking_id`；只读，不调用 `write_tx()`；SQL 只在 `data/` 且参数化。

**Decision（2026-11-11，人工裁定）:** 采用 B，不新增姓名字段、不改 schema、不回写 Story 1.1；管理员页只展示学号。`week` 接受 `YYYY-MM-DD`（该周内任意一天）或 `YYYY-Www`，缺省为当前周；非法值 400。

**Never:** 第二套格模板；在 `web/` 或 `templates/` 写时间、状态或冲突判断；改唯一键/CHECK/迁移版本；实现改单、锁定、导出或审计；新增运行期依赖；把学生身份写进学生页面或会话。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| WEEK_BOUNDARY | 周日 23:30 与周一 00:00 各一条 | 相邻周集合不相交 | N/A |
| WEEK_CELLS | 设备 08:00–10:00，整周 | 28 格，booking_id 去重为 7 | N/A |
| LOCK_ANOMALY | 16:00 锁定；14:00 跨设备重叠 | 锁定格 + 异常标记含 slot_start | N/A |
| SEARCH | 2025001 有 2 条，另有 20250010 | 精确只返回 2 条；前缀返回全部 | 200 |
| SEARCH_MISS | 9999999 不存在 | 空列表 | 200 |
| AUTH | 学生 / 匿名访问周视图 | 拒绝 | 403 / 401 |
| GRID_REUSE | 同设备同日两视图 | `(data-state, data-slot)` 一致 | N/A |
| PII | 学生看他人预约 | 无他人学号/booking_id | N/A |
| READ_ONLY | 打开周视图并检索前后 | occupancy 逐行不变 | N/A |
| BAD_WEEK | `week=not-a-week` | 不查询、不渲染 | 400 |
| RESPONSIVE | 375 / 1280 px | 容器不溢出，窄屏纵向 | N/A |

</frozen-after-approval>

## Code Map

- `src/core/timeutil.py` — 新增 `week_bounds_utc()`，返回周一本地日期与 UTC 半开区间。
- `src/data/occupancy_repo.py`、`booking_repo.py`、`user_repo.py` — 新增参数化只读周查询、按 owner 查询、精确优先的前缀学号检索（转义 `%_\\`）。
- `src/app/slot_service.py` — `SlotCell` 增加可选 booking_id、owner_student_no、anomaly、anomaly_label；状态逻辑不动。
- `src/app/admin_service.py` — 新建：逐设备逐日复用 `build_slot_grid()` 并附加归属/异常；异常含锁定、改单、同学生同 slot 跨设备重叠；返回只读检索结果。
- `src/web/admin.py` — 新增两个只读 GET，第一行 `@admin_required`，只解析参数与映射 400。
- `src/templates/_slot_grid.html` — 仅字段存在时输出 `data-booking-id`、`data-owner-student-no`、`data-anomaly-slot`。
- `src/templates/admin_week.html`、`admin_users.html`、`base.html`、`src/static/app.css` — 复用局部模板、检索结果、宽页与 720 px 纵向断点。
- `tests/test_admin_week_view.py` — 新建，先红后绿。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_admin_week_view.py` — 先写矩阵全部测试并跑出红灯 — R5
- [x] `src/core/timeutil.py`、`src/data/*_repo.py` — 周界与只读查询 — R1/R2/R4
- [x] `src/app/slot_service.py`、`src/app/admin_service.py` — 复用六态并组装 — 状态单点
- [x] `src/web/admin.py`、模板与 CSS — 接线、复用格子、响应式 — R1/NFR-3
- [x] `tests/test_admin_week_view.py` + `python -m pytest -q` — 全绿无回归
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` — 3.1 置 `review`，不得 `done` — R6

**Acceptance Criteria:**
- Given 周一 00:00 与上周周日 23:30 各一条，when 取相邻两周，then booking_id 集合不相交且周一这条只在本周。
- Given 本周 7 条 booking 占用，when 打开周视图，then 格数等于开放时间内 slot 数且 booking_id 去重为 7。
- Given 16:00 锁定且存在跨设备重叠，when 打开周视图，then 锁定格可见且异常标记含 slot_start。
- Given 2025001 有 2 条预约，when 精确检索，then 200 且 booking_id 集合等于这 2 条。
- Given 学号不存在，when 检索，then 200 且空列表。
- Given 学生与匿名用户，when 访问 `/admin/week`，then 403 与 401。
- Given 同设备同日，when 对比两种视图，then `(data-state, data-slot)` 序列一致。
- Given 学生看他人预约，when 检查响应，then 无他人学号或 `data-booking-id`。
- Given 打开周视图并检索，when 对比前后 occupancy，then 逐行不变。
- Given 375/1280 两档，when 检查 HTML/CSS，then 周表不超出页面且窄屏纵向。

## Implementation Notes

- 红灯证据：`tests/test_admin_week_view.py` 先落盘并运行，得到 `9 failed, 1 passed`；失败为 `/admin/week`、`/admin/users` 未注册及周表缺失。
- 绿灯证据：本 Story `15 passed`；全量 `148 passed`（基线 133）。
- 姓名：按人工裁定采用 B，未改 schema、未改 Story 1.1；管理员页只展示学号。
- 周参数：接受 `YYYY-MM-DD`（该周内任意一天）与 `YYYY-Www`，缺省当前周；非法值映射 400。
- 周视图：`admin_service` 逐设备逐日调用 `slot_service.build_slot_grid()`，再用 `dataclasses.replace()` 附加 `booking_id`、`owner_student_no`、`anomaly`、`anomaly_label`；模板只渲染传入字段。
- 异常：锁定、`updated_at != created_at` 的改单、同一学生同一 slot 跨设备重叠；均由服务层给出标记。
- 异常摘要：显示“设备名（ID）+ 本地时间”；未落入任何格子的窗口外锁定也补进摘要，避免数据不可见。
- 检索：前缀命中超过 50 人时返回 `truncated` 并在页面提示；检索结果与周视图一致地标注“跨设备重叠”。
- 入口：格子内学号链接到 `/admin/users?student_no=`；标题为“周视图”并提供“回到本周”。
- 只读：两个 GET 未调用 `write_tx()`；测试在请求前后比较 booking/occupancy/audit 快照。
- 响应式：`.week-table-scroll` 使用 `max-width:100%; overflow-x:auto`，`.week-table` 使用 `table-layout:fixed`；720px 以下整表转纵向块。测试按选择器抽取规则块断言，并禁止 `.week-table*` 出现非 0 `min-width`。

## Spec Change Log

## Review Triage Log

三路评审（Blind Hunter / Edge Case Hunter / Verification Gap）共 33 条；逐条核实后按根因处置，`patch` 已在本次收尾落地。

| ID | 来源 | 发现 | 判定 | 核实与处置 |
|---|---|---|---|---|
| BH-01 | Blind Hunter | `sprint-status.yaml` 仍为 `in-progress`，与 spec 的 `review` 要求不符 | medium | 属实；收尾置 `review`，未置 `done`。→ patch |
| BH-02 | Blind Hunter | 管理员无法从界面到达 `/admin/*` | false | `src/web/catalog.py:19` 为管理员注入 `admin_url`，`equipments.html:5` 渲染“设备维护”；登录后 `/equipments` → 设备维护 → 本周视图链路完整。 |
| BH-03 | Blind Hunter | 格子内学号是纯文本，未带 `?student_no=` 进入检索 | low | 属实；`_slot_grid.html` 仅在管理员才拿到的 `owner_student_no` 上包检索链接，不新增格子判断。→ patch |
| BH-04 | Blind Hunter | 检索无法区分“学号不存在”和“学生存在但无预约” | false | 两种情况下文案都是“没有找到该学号的预约”，字面为真；I/O 矩阵只要求 200 空列表。前缀结果平铺是当前设计。 |
| BH-05 | Blind Hunter | 前缀检索静默截断 50 人 | medium | 属实；`search_by_student_no()` 改为 `limit+1` 探测并返回 `(rows, truncated)`，页面提示“仅显示前 50 人”。→ patch |
| BH-06 | Blind Hunter | `list_for_owners` 无上限或日期过滤 | low | 返回全部历史是审计语义，不会产生错误结果；加分页会扩大接口面。→ 驳回 |
| BH-07 | Blind Hunter | `student_no` 无长度校验，超长查询仍 200 | low | 管理员专用只读参数化 `LIKE`，未展示可利用后果；不加新校验面。→ 驳回 |
| BH-08 | Blind Hunter | 检索状态硬编码 `_booking_status(edited, False)` | medium | 属实；同一 booking 周视图标“跨设备重叠”、检索却显示“正常”。改为按该学生预约行计算重叠键。→ patch |
| BH-09 | Blind Hunter | “已改单”由 `updated_at != created_at` 推断，不可审计 | false | 唯一更新路径 `booking_repo.update_booking` 就是改单；该比较正是本 Story 约定的改单信号，每次改单本就应作为异常展示。 |
| BH-10 | Blind Hunter | 异常摘要显示原始 UTC，且无设备标识 | medium | 属实；改为 `AnomalySlot(slot_start, label)`，摘要显示“设备名（ID）+ 本地时间”，`data-anomaly-slot` 保留 UTC 便于定位。→ patch |
| BH-11 | Blind Hunter | 图例未覆盖“已改单/跨设备重叠/已锁定” | low | 每个格子自带中文异常文案，图例缺失不产生误解。→ 驳回 |
| BH-12 | Blind Hunter | 标题固定“本周视图”，无“回到本周” | low | 属实；标题改为“周视图”并新增“回到本周”链接。→ patch |
| BH-13 | Blind Hunter | 页面无预约/锁定/异常汇总计数 | low | AC 未要求计数；预约表与异常摘要已提供可核对信息。→ 驳回 |
| BH-14 | Blind Hunter | 响应式测试未真正约束 `.week-table-scroll` | medium | 属实；`max-width:100%` 可被 `.table-scroll` 满足。测试改为抽取 `.week-table-scroll`/`.week-table` 规则块逐条断言，并禁止 `.week-table*` 规则出现非 0 `min-width`。→ patch |
| BH-15 | Blind Hunter | `ids()` 同时匹配预约表，异常计数被摘要 `<li>` 满足 | medium | 属实；改为在 `week-grid` 块内读取 `data-booking-id`，并对 E1/E2 的具体格子断言 `data-anomaly="1"` 与文案。→ patch |
| BH-16 | Blind Hunter | 缺少 `/admin/users` 401/403、ISO 周、非法周、上/下周等覆盖 | medium | 属实；补齐 `/admin/users` 鉴权、缺省周/`2026-W46`/周中日期、`2026-W54`/`9999-12-31` 400、上/下周 href、截断提示测试。→ patch |
| BH-17 | Blind Hunter | `SlotCell` 携带归属字段，模板无角色守卫，靠调用方传 `None` | false | 学生路径由 `build_slot_grid()` 产出且这些字段默认 `None`，`test_student_slot_view_does_not_leak_owner_identity_or_booking_id` 已验证；模板加角色判断反而违反 R1。 |
| BH-18 | Blind Hunter | `WeekDay.grid: object`、`WeekView.days` 重复日期、周查询选了未用列 | low | 类型标注与少量冗余列，无行为分叉；`days` 与 `WeekDay` 当前同源计算。→ 驳回 |
| BH-19 | Blind Hunter | 新增 CSS 用硬编码色值、`.week-table-scroll` 与 `.table-scroll` 重复、窄屏丢表格语义、无粘性表头 | low | 纯样式/可访问性打磨，修复需重构或补 ARIA 结构，超出本 Story 最小改动。→ 驳回 |
| BH-20 | Blind Hunter | 设备窗口收窄后，窗口外的锁定行在格子和异常摘要里都消失 | medium | 属实；`_assert_window_covers_occupancy` 只拦未来占用，历史锁定可落在窗口外。改为把未出现在任何格子的锁定行补进异常摘要并标注“窗口外锁定”。→ patch |
| BH-21 | Blind Hunter | 每设备每天重复调用 `build_slot_grid`，存在 N+1 查询 | low | 属实；但单页数据量小、`build_slot_grid` 是六态唯一入口，改预加载会动共享契约，收益不足。→ 驳回 |
| EC-01 | Edge Case Hunter | `week=9999-12-31` 触发 `OverflowError` 返回 500 | medium | 属实；`week_bounds_utc()` 统一把日期溢出转成 `ValueError`，路由映射 400，并加测试。→ patch |
| EC-02 | Edge Case Hunter | 检索结果把真实跨设备重叠报成“正常” | medium | 与 BH-08 同因；同一修复。→ patch |
| EC-03 | Edge Case Hunter | 前缀命中超过 50 人时静默给部分结果 | medium | 与 BH-05 同因；同一修复。→ patch |
| EC-04 | Edge Case Hunter | 异常摘要用 UTC 时间，管理员会看错 slot | medium | 与 BH-10 同因；同一修复。→ patch |
| EC-05 | Edge Case Hunter | 窗口收窄后窗口外锁定既不在格子也不在异常列表 | medium | 与 BH-20 同因；同一修复。→ patch |
| EC-06 | Edge Case Hunter | 任务声称 3.1 置 `review`，跟踪文件仍是 `in-progress` | medium | 与 BH-01 同因；收尾置 `review`。→ patch |
| VG-01 | Verification Gap | `/admin/users` 的 401/403 合同未被测试 | medium | 已由变异实验证实：删掉 `@admin_required` 后全量仍绿。补匿名 401、学生 403 断言（与 BH-16 同批）。→ patch |
| VG-02 | Verification Gap | 缺省当前周、`YYYY-Www`、周中日期与上/下周链接未被测试 | medium | 已证实变异不红。补三种输入同范围断言及 `week=2026-11-02`/`2026-11-16` href（与 BH-16 同批）。→ patch |
| VG-03 | Verification Gap | “已改单”标记完全没有测试 | medium | 已证实把 `edited_ids` 置空仍 10 passed。新增 `updated_at` 晚于 `created_at` 的预约，断言格子、预约表与检索表都显示“已改单”。→ patch |
| VG-04 | Verification Gap | 跨设备重叠断言被 16:00 锁定满足，未证明重叠标记 | medium | 已证实 `overlap_keys = set()` 仍 10 passed。改为对 E1/E2 的 14:00 格子分别断言 `data-anomaly="1"` 与“跨设备重叠”。→ patch |
| VG-05 | Verification Gap | 375/1280 只做 CSS 文本 grep，未绑定周表选择器 | medium | 属实；已按 BH-14 收窄到 `.week-table-scroll`/`.week-table` 规则并禁止非 0 `min-width`。受“不新增运行期依赖”约束，仍未做真实浏览器布局测量。→ patch |
| VG-06 | Verification Gap | 异常摘要渲染原始 20 字符 UTC | medium | 与 BH-10 同因；同一修复。→ patch |

## Design Notes

`build_slot_grid()` 产生唯一可信六态；`admin_service` 再按 `(equipment_id, slot_start)` 附加预约元数据，模板从不自行判断状态。异常标记由服务层给出布尔值与文案。

## Verification

**Commands:**
- `python -m pytest tests/test_admin_week_view.py -q` — 先红后绿。
- `python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_story31` — 全量回归。
