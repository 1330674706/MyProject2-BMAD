---
title: 'Story 1.3 逐 slot 占用状态视图'
type: 'feature'
created: '2026-11-09'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: '443e75f937c5161eec690bc17ce8fb2df4293fb7'
context:
  - 'project-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 1.2 只派生 slot 时间，`/slots` 仍是占位页；学生无法在提交前看到每个 slot 是空闲、本人/他人已约、已锁定，还是因已开始或超出 7 天窗口而不可约。

**Approach:** 在 `src/app/slot_service.py` 用一次读库把开放时间派生结果与 `occupancy` 叠加为六态只读视图对象；`_slot_grid.html` 只渲染 `cell.state`，学生日视图经 `GET /slots?equipment_id=&date=` 输出。状态枚举一次定稿，供 2.1 与 3.1 复用。

## Boundaries & Constraints

**Always:** 六态只允许 `free` / `booked_by_self` / `booked_by_other` / `locked` / `closed_past` / `closed_window`；状态判定只在 `slot_service.py`，模板不比较时间、不判状态、不查库；`occupancy` 读取参数化且只在 `src/data/`；UTC 与 `Asia/Shanghai` 转换只经 `core/timeutil.py`；`/slots` 第一行 `@login_required`；页面保留 viewport 与 480px 断点。

**Never:** 不实现 2.1 的预约提交、复选框或写 `occupancy`；不实现 3.1 的管理员周视图/检索；不新增运行期依赖；不在路由或模板写冲突判断、时间比较或状态映射；不建 `slot` 表。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| SELF_BOOKED | 学生 A 已约 14:00，B 已约 14:30 | A 看到 `booked_by_self` / `booked_by_other` | N/A |
| PAST | slot_start 不晚于当前 UTC | `closed_past`，优先于锁定/预约 | N/A |
| BEYOND_WINDOW | slot_start 晚于 now + 7 天 | `closed_window` | N/A |
| LOCKED | 管理员锁定 16:00 | 学生看到 `locked` | N/A |
| FREE | 窗口内且无占用 | `free` | N/A |
| BAD_EQUIPMENT | 不存在或已停用设备 | 不渲染网格 | 404 |
| BAD_DATE | 非法日期文本 | 不渲染网格 | 400 |
| ANONYMOUS | 无会话 GET /slots | 不渲染网格 | 401 |

</frozen-after-approval>

## Code Map

- `src/app/slot_service.py` -- 保留 1.2 的 `build_grid()` 派生；新增 `SIX_STATES`、`SlotCell`、`SlotGrid` 与 `build_slot_grid()`，按设备/日期/查看者叠加状态。
- `src/data/occupancy_repo.py` -- 新建只读查询，按设备与 slot 区间取 `kind` 与 `booking.owner_id`；不控制事务、不写库。
- `src/core/timeutil.py` -- 补 `add_days()`，避免在服务层手工拼时间或解析 UTC。
- `src/web/catalog.py` -- `/slots` 去掉占位，解析 `equipment_id` / `date`，调用服务并渲染。
- `src/templates/_slot_grid.html` -- 新建共享局部模板；每格输出一次 `data-state`，只读 `cell.state` / `cell.label` / `cell.local_time`。
- `src/templates/slots.html` -- 新建学生日视图：设备选择、日期选择、网格、图例。
- `src/templates/equipments.html` -- 每台设备增加进入日视图的链接。
- `src/static/app.css` -- 补 slot 网格样式与 `@media (max-width: 480px)`。
- `tests/test_slot_view.py` -- 新建；逐条覆盖 AC 与矩阵，先红后绿。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_slot_view.py` -- 先写 AC 与矩阵测试并运行，确认红灯 -- R5 证据。
- [x] `src/core/timeutil.py` -- 增加 `add_days()` -- 7 天窗口不手工拼时间。
- [x] `src/data/occupancy_repo.py` -- 增加按区间只读查询 -- SQL 留在数据层。
- [x] `src/app/slot_service.py` -- 实现六态视图对象与唯一状态判定 -- 1.3/2.1/3.1 共用契约。
- [x] `src/web/catalog.py` -- 接线 `/slots` -- 路由只解析与映射。
- [x] `src/templates/_slot_grid.html`、`slots.html`、`equipments.html`、`src/static/app.css` -- 渲染与响应式 -- 模板只画状态。
- [x] `tests/test_slot_view.py` -- 运行至全绿，再跑全量回归 -- 证明 1.1/1.2 无回归。

**Acceptance Criteria:**
- Given A 已约 14:00、B 已约 14:30，When A 取 grid，Then 两格分别为 `booked_by_self` / `booked_by_other`。
- Given slot_start 早于 now，When 取当天 grid，Then 全部为 `closed_past`。
- Given 首个 slot 晚于 now + 7 天，When 取该格，Then 为 `closed_window`。
- Given 管理员锁定 16:00，When 学生刷新，Then 该格为 `locked`。
- Given 任意一天 grid，When 收集状态，Then 是六态子集且 `data-state=` 数等于格数。
- Given GET /slots 响应，When 检查头与源码，Then 无 Upgrade、无 `text/event-stream`、无 `EventSource`、无 `setInterval`。
- Given 桩 grid 含 3 个 locked 格，When 渲染 `_slot_grid.html`，Then 恰好 3 个 `data-state="locked"`。
- Given 任意核心页与 CSS，When 检查，Then 有 viewport width=device-width、`@media` 与 `max-width: 480px`。

## Implementation Notes

- 红灯证据：`tests/test_slot_view.py` 先落盘并运行，得到 13 failed / 2 passed；失败包含 `SIX_STATES` 缺失、`build_slot_grid()` 缺失、`data-state` 数量不符、CSS 无断点、未知设备仍为 200、非法日期仍为 200。
- `build_grid()` 保持 1.2 的纯派生签名；新增 `build_slot_grid()` 叠加六态。优先级固定为 `closed_past` → `closed_window` → `locked` → `booked_by_self` → `booked_by_other` → `free`。
- `SlotCell` 构造时拒绝六态之外的值；`SIX_STATES` 与 `STATE_LABELS` 作为 2.1、3.1 的共享契约。
- `occupancy_repo.list_for_range()` 一次左连接 `booking` 取 `owner_id`，避免逐格查询；SQL 只在 `src/data/`。
- `/slots` 缺设备返回 400、未知设备返回 404、非法日期返回 400；缺日期默认本地今天；错误重渲染同页并保留筛选上下文。
- 模板只输出 `cell.state` / `cell.label` / `cell.local_time`，每格恰好一次 `data-state`；未加复选框、未写 `occupancy`、未实现 2.1 或 3.1。
- 环境说明：沙箱无法复用或清理 `--basetemp`，每次验证使用新的临时目录。

## Spec Change Log

## Review Triage Log

## Design Notes

状态优先级固定为：`closed_past` → `closed_window` → `locked` → `booked_by_self` → `booked_by_other` → `free`。时间不可约优先于占用原因，避免同一格出现两个责任主体。`build_grid()` 保持 1.2 的纯派生签名不变；视图层新增 `build_slot_grid()` 消费它。

## Verification

**Commands:**
- `python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_story13 tests/test_slot_view.py` -- 实际 15 passed。
- `python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_story13_full` -- 实际 57 passed，无回归。
