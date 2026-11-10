---
title: 'Story 2.2 冲突整单原子拒绝与并发裁决'
type: 'feature'
created: '2026-11-10'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '3ce30e57ac1f0aa1530346f7062fc9ee9f9a0f1b'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.1 已让冲突走 409，但"约束才是裁决者"没有任何可复现证明：没有 L1–L5 分层证据，`now` 在写事务外取，`BEGIN IMMEDIATE` 抢锁失败会冒泡成 500，409 也只回一行错误而不重渲染格子。评审无法从代码判断"换成先查后写"会不会一样全绿。

**Approach:** 新增 `tests/test_booking_concurrency.py` 承载 L1–L5 五层证明与 C1–C3 真值表，新增现场脚本 `tests/concurrency_demo.py`；`write_tx()` 对 `BEGIN IMMEDIATE` 的忙等做有限重试并映射 503，同时提供仅测试可见的持锁区间追踪；把 `now_utc()` 移入事务；409 同页重渲染并标出冲突格。

## Boundaries & Constraints

**Always:** 唯一裁决者只能是 `uq_occupancy_slot`；事务内预检只生成 409 文案，不得决定放行或拒绝；写入口唯一（用例 → `write_tx()` → `insert_occupancy()`）；409 体列出每个冲突的 `equipment_id` 与 `slot_start`；时刻只经 `src/core/timeutil.py` 取用并存 20 字符 UTC；先写测试跑到断言红，再写实现转绿；测试只经公开入口（HTTP 或用例函数）观察行为。

**Never:** 进程内锁 / 文件锁；事务外 check-then-write；`INSERT OR IGNORE`、`OR REPLACE`、`ON CONFLICT DO NOTHING`；删或改 CHECK、唯一键、`foreign_keys`；为跑通改测试断言；把 2.3 / 2.4 / 3.x 功能做进来；改 planning artifacts（若改则须同步 PRD §11）；新增运行期依赖。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| L1 结构 | 新建库并迁移 | 唯一索引恰 1 条：`unique=1`、`origin='u'`、`partial=0`，列序 `(equipment_id, slot_start)` | N/A |
| L2 确定性交错 | A 持写锁插入未提交 → B `BEGIN IMMEDIATE` → A COMMIT → B 重试 INSERT | B 首次在 1 s 内 `SQLITE_BUSY`；重试后 `SQLITE_CONSTRAINT_UNIQUE`；新连接 `COUNT=1` | 断言 `sqlite_errorname` |
| L3 双进程 | 2 个 spawn 进程 `Barrier(2)` 后同时 POST 同一组 3 slot | `303` 与 `409` 各 1；该组占用行数 = 3；无重复 key；两侧写事务区间相交 | 无 5xx |
| L4 C1 | 约束 + 预检 | 每轮 1 成功 1 冲突 | N/A |
| L4 C2 | 约束 + 预检短路 | 每轮仍 1 成功 1 冲突 | N/A |
| L4 C3 | 删约束 + 预检短路 | 每轮成功次数必须 `== 2`（显式断言） | N/A |
| L5 原子性 | 8 连中第 5 格已被占 | 409 含该 slot 与 equipment；前 4 格 0 行、booking 新增 0 | 不写库 |
| 重复提交 | 同一学生原样再提交已成功的一组 | 409；该 `booking_id` 占用行数不变 | 不写库 |
| 抢锁失败 | 外部连接持写锁 | 重试 2 次（20/50 ms）后 503，不 500 | 503 |
| now 位置 | 正常提交 | `now_utc()` 被调用时本事务已持有写锁 | N/A |
| 409 页面 | 任一 slot 冲突 | 同页重渲染该设备该日网格，冲突格带标记，原选择仍勾选 | 409 |

</frozen-after-approval>

## Code Map

- `tests/test_booking_concurrency.py` -- 新增：L1–L5 + C1–C3 + 三条边界断言（本 Story 唯一测试文件）。
- `tests/concurrency_demo.py` -- 新增：`python -m tests.concurrency_demo` 现场脚本；共用 HTTP 客户端、进程池栅栏、轮次执行器；不依赖 pytest。
- `tests/__init__.py` -- 新增空包标记，使 `python -m tests.concurrency_demo` 与 spawn 子进程可按模块名导入。
- `src/data/tx.py` -- 追加 `BEGIN IMMEDIATE` 有限重试、忙耗尽映射 `Unavailable`、仅测试生效的持锁时长与区间追踪（默认全关）。
- `src/app/booking_service.py` -- 把 `now_utc()` 移入 `write_tx()`；409 分支逻辑不变。
- `src/app/slot_service.py` -- `SlotCell` 增加只读 `conflicted` / `selected` 标记；`build_slot_grid()` 透传冲突与已选集合。
- `src/web/bookings.py` -- 409 时重建网格并重渲染 `slots.html`。
- `src/templates/_slot_grid.html` -- 渲染 `data-conflict` 与已选项（只消费视图对象）。
- 不改：`migrations/001_init.sql`、`src/app/slot_rules.py`、`src/data/occupancy_repo.py` 的 SQL、`src/web/errors.py` 的状态码映射、planning artifacts。

## Tasks & Acceptance

**Execution:**
- [x] `tests/concurrency_demo.py`、`tests/__init__.py` -- 写 HTTP 客户端 / 栅栏进程 / 轮次执行器与命令行入口 -- 让 L3 有可复用、可现场重放的驱动
- [x] `tests/test_booking_concurrency.py` -- 先写 L1–L5、C1–C3、三条边界断言并跑出断言红灯 -- R5
- [x] `src/data/tx.py` -- `BEGIN IMMEDIATE` 忙重试 2 次（20/50 ms）→ `Unavailable`；`TEST_CLAIM_HOLD_MS` 与 `LAB_TX_TRACE_DIR` 默认关闭 -- D4、L3 重叠证明
- [x] `src/app/booking_service.py` -- `now_utc()` 移入事务 -- 边界一
- [x] `src/app/slot_service.py`、`src/web/bookings.py`、`src/templates/_slot_grid.html` -- 409 同页重渲染 -- AR-3
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 2.2 置 `review` -- R6

**Acceptance Criteria:**
- Given 新建库并迁移，when 读 `PRAGMA index_list('occupancy')` 与 `index_info('sqlite_autoindex_occupancy_1')`，then 唯一索引恰 1 条且 `(unique, origin, partial) == (1, 'u', 0)`，列序为 `(equipment_id, slot_start)`。
- Given 4 连中第 3 格已被他人占用，when 提交整组，then 409、响应含该 `slot_start` 与 `equipment_id`、`booking` 与 `occupancy` 新增均为 0。
- Given 已成功预约一组 slot，when 原样再次提交，then 409 且该 `booking_id` 的 `occupancy` 行数仍为原值。
- Given 两个 spawn 进程 `Barrier(2)` 后同时 POST 同一 key，when 跑完全部轮次，then 每轮 `{303: 1, 409: 1, 5xx: 0}`、新连接 `COUNT(*) == 1`、两侧 `BEGIN IMMEDIATE` 区间相交。
- Given 同一 key 起 10 个并发请求，when 重复 20 轮，then 每轮 303 恰 1 个、409 恰 9 个、5xx 为 0。
- Given 全部并发轮次结束，when 按 `(equipment_id, slot_start)` 分组，then `HAVING COUNT(*) > 1` 为空集。
- Given 把预检短路为恒返回空（约束保留），when 重跑 C2 轮次，then 仍每轮 1 成功 1 冲突。
- Given 同时删除唯一约束并把预检短路，when 重跑 C3 轮次，then 每轮 `assert 成功次数 == 2`。
- Given 第 5 格冲突，when 提交整组 8 格，then 409 且前 4 格一行都不存在。
- Given 任意 409 响应，when 检查响应体，then 不含 `Traceback` 且状态码 `< 500`。
- Given 外部连接持有写锁，when 提交预约，then 有限重试后 503 而非 500。
- Given 提交预约，when `now_utc()` 被调用，then 本事务已持有写锁（不能在事务外取好再传入）。

## Implementation Notes

红灯（实现前）：`5 failed, 11 passed`，全部为断言失败，无 ImportError——缺写事务区间记录（L3 相交证明）、409 页未标记冲突格、忙锁冒泡 500、`now_utc()` 仍在事务外。

绿灯：`tests/test_booking_concurrency.py` 16 passed；全量 `107 passed`。C1 `successes=100 conflicts=100 / 100 轮`；C2 同 C1；C3 `successes=200 conflicts=0 / 100 轮，每轮=2`。L3 双进程 100 轮全为 `{303, 409}`，200 条写事务区间 100/100 相交；10 并发 20 轮全部 `1×303 + 9×409`；全库无重复 key。

实现决定：`write_tx()` 首试沿用连接配置的 1000 ms `busy_timeout`，两次重试只退避（20/50 ms）并在重试期间把 `busy_timeout` 置 0，最坏总等待 ≈1.07 s（落在 D4 的 1.2 s 内），耗尽或 COMMIT 遇忙一律 `Unavailable`（503）。`LAB_TX_TRACE_DIR` / `TEST_CLAIM_HOLD_MS` 未设置时零开销，生产不会设置。`Conflict` 增带 `conflict_slots`（仅槽位文本），409 页据此标记 `data-conflict="1"` 并保留原选择；六个 slot 状态不变。

2.1 复审遗留的「409 重渲染并标出冲突」由本 Story 关闭（`deferred-work.md` 中该条保持原样不改写）。

本仓库渲染的 workflow 未配置 review layers，故 step-04 无独立评审子代理可跑；上述证据与源码 diff 由实现方自检。

## Spec Change Log

## Review Triage Log

## Verification

**Commands:**
- `python -m pytest tests/test_booking_concurrency.py -q` -- 先红（断言失败，非 ImportError），实现后全绿。
- `python -m tests.concurrency_demo` -- 输出 1×303 + 1×409、0×5xx、`COUNT=1`，退出码 0。
- `python -m pytest -q` -- 全量回归全绿。
