---
title: 'Story 2.2 复审修复：真双进程、锁区间证据与两处回归'
type: 'bugfix'
created: '2026-11-10'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '82197c6c06debfda9119e07260cdea73aba916a4'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.2 复审发现五处证据缺口：L3 的"双进程"其实是 pytest 进程内的 `make_server`，测不出跨进程行为；锁区间断言用的是 `write_tx` 整体 enter–exit，任何实现都会相交，等于恒真；`src/serve.py` 漏捕 `AppError`（含 `Unavailable`），1.4 的"启动失败返回 2、不打 traceback"被破坏；`write_tx` 的 COMMIT 抛非 `OperationalError` 时既不回滚也被记成 `commit`；409 后重查为空时渲染的是全 `data-conflict="0"`、看不出发生冲突的空白页。

**Approach:** L3 改为启动两个真实 `python -m src.serve` 进程（不同 `LAB_PORT`、同一 `data/lab.db`）；`tx.py` 分别记录等锁与持锁区间，断言改为"输家等锁区间 ∩ 赢家持锁区间"，并用一次进程内互斥锁变异证明该断言会失败；`serve.py` 补 `AppError`；COMMIT 失败显式回滚并记 `commit_failed`；409 重查为空时改为整页冲突提示并保留网格与原选择。

## Boundaries & Constraints

**Always:** 唯一裁决者仍是 `uq_occupancy_slot`；写入口唯一（用例 → `write_tx()` → `insert_occupancy()`）；409 体仍列 `equipment_id` 与 `slot_start`；时刻仍只经 `src/core/timeutil.py`；`tests/test_booking_concurrency.py` 先红后绿；`sprint-status.yaml` 的 `2-2` 保持 `review`。

**Never:** 在 pytest 进程内起被测服务；进程内锁/文件锁进入生产路径；`INSERT OR IGNORE`/`OR REPLACE`/`ON CONFLICT DO NOTHING`；改 CHECK、唯一键、`foreign_keys`；动 C3 的手写表定义、合并 C1/C2、给 503 加日志；改 planning artifacts；新增运行期依赖。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| L3 真双进程 | 两个 `src.serve` 进程、不同端口、同一 db，Barrier 后同发一组 3 slot | 每轮恰好 1×303 + 1×409、0×5xx；该组 occupancy 行数 = 3；全库无重复 key | N/A |
| 锁区间 | 同轮两条 trace | 输家 `[lock_request, lock_acquired]` 与赢家 `[lock_acquired, lock_released]` 相交 | 不相交即判失败 |
| 变异自检 | 临时在 `write_tx` 内加进程内互斥锁后重跑 | 上述重叠断言必须失败（证明非恒真） | 变异后仍绿即判失败 |
| 启动失败 | `create_app()` 抛 `AppError`（如 `Unavailable`） | 打印"启动失败：…"，返回码 2，无 traceback | 退出码 2 |
| COMMIT 失败 | COMMIT 抛 `IntegrityError` | 显式 ROLLBACK，trace `outcome == commit_failed`，无残留事务 | 原异常冒泡 |
| 409 重查为空 | 命中唯一约束但重查无行 | 整页冲突提示 + 保留网格与原选择，不出现全 `data-conflict="0"` 空白页 | 409 |
| 正常网格页 | `GET /slots`，无冲突无选择 | 逐格 `data-conflict="0"`，且不出现整页提示或“提交未完成” | N/A |

</frozen-after-approval>

## Code Map

- `tests/concurrency_demo.py` -- `start_server()`（进程内 `make_server`）替换为 `start_servers()`：`subprocess` 起 N 个 `python -m src.serve`，`/health` 200 后返回；新增 `free_port()`、`lock_wait_interval()`、`lock_hold_interval()`、`intervals_overlap(a, b)` 元组版；`run_phase()` 不再改本进程 `os.environ`（trace/持锁时长经子进程 env 传入）。
- `tests/test_booking_concurrency.py` -- 复用上述助手；新增启动失败与 COMMIT 失败两条回归，409 空白页改为整页提示。
- `src/data/tx.py` -- trace 增 `lock_request_ns` / `lock_acquired_ns` / `lock_released_ns`，保留 `enter_ns` / `exit_ns`；COMMIT 失败显式 ROLLBACK 且记 `commit_failed`；BEGIN 失败也要留 trace。
- `src/serve.py` -- `except` 增 `AppError`，统一打印"启动失败：…"并返回 2。
- `src/app/slot_service.py` -- `SlotGrid` 增只读 `conflict_scope`（`cells` / `page` / `none`），由冲突与已选集合派生。
- `src/templates/_slot_grid.html`、`src/templates/slots.html` -- 仅消费视图字段：`page` 作用域不输出逐格 `data-conflict`，改为整页冲突提示。
- 不改：`migrations/001_init.sql`、`src/web/errors.py` 状态码映射、C1/C2/C3 的表重建脚本、planning artifacts。

## Tasks & Acceptance

**Execution:**
- [x] `tests/concurrency_demo.py` -- 真双进程启动器 + 锁区间助手 -- L3 需跨进程证据
- [x] `tests/test_booking_concurrency.py` -- 改 L3、补启动失败/COMMIT 失败/409 空白页用例并跑红 -- R5
- [x] `src/data/tx.py` -- 等锁/持锁区间与 `commit_failed` -- B、D
- [x] `src/serve.py` -- 捕 `AppError` 返回 2 -- C
- [x] `src/app/slot_service.py`、`src/templates/_slot_grid.html`、`src/templates/slots.html` -- 409 整页提示 -- E

**Acceptance Criteria:**
- Given 两个真实 `src.serve` 进程指向同一库，when 两客户端 Barrier 后同发同一组 slot，then 每轮恰 1×303 + 1×409 且 0×5xx。
- Given 全部轮次结束，when 数该组 occupancy 行数并按 `(equipment_id, slot_start)` 分组，then 行数等于一组 slot 数且 `HAVING COUNT(*) > 1` 为空。
- Given 每轮两条 trace，when 比较输家等锁区间与赢家持锁区间，then 必须相交。
- Given 临时在 `write_tx` 内插入进程内互斥锁，when 重跑重叠断言，then 必须失败。
- Given `create_app()` 抛 `AppError`，when 跑 `src.serve.main()`，then 返回 2 且输出以"启动失败："开头、不含 traceback。
- Given COMMIT 抛 `IntegrityError`，when 退出 `write_tx`，then 连接不在事务中且 trace `outcome == commit_failed`。
- Given 409 且重查为空，when 渲染，then 出现整页冲突提示、网格仍在、原选择仍勾选，且无 `data-conflict="0"`。

## Implementation Notes

**红灯（实现前）**：新增三条用例全部断言失败（E 页面仍是 `data-conflict="0"` 一屏、C 的 `Unavailable` 直接冒出 `serve.main()`、D 的 `in_transaction` 仍为 `True`），无 ImportError；L3 在改助手前仍跑旧进程内服务。

**绿灯**：`tests/test_booking_concurrency.py` 20 passed；全量 111 passed；`python -m tests.concurrency_demo` 2 并发 100/100 轮 `{303, 409}`、trace 200 条来自 2 个服务进程、等锁/持锁区间相交 100/100，10 并发 20/20 轮 `1×303 + 9×409`，全库无重复 key。

**B 的变异自检（已执行并还原）**：单服务进程、2 客户端 × 20 轮、`TEST_CLAIM_HOLD_MS=50`。原实现 `overlaps=20/20`；把 `write_tx` 包进模块级 `threading.Lock`（先拿锁再记 `lock_request_ns`）后 `overlaps=0/20`，而同轮状态码仍是 `{303, 409}`——说明旧式"整体区间相交"断言会继续全绿，新断言不是恒真。还原后回到 `20/20`。完整记录见 `evidence/story-2.2_2026-11-10_mutation-selfcheck.txt`。

**实现决定**：trace 字段拆成 `enter_ns`（进入 `write_tx`）、`lock_request_ns`（首次 `BEGIN IMMEDIATE` 之前）、`lock_acquired_ns`（`BEGIN IMMEDIATE` 返回成功）、`lock_released_ns`（COMMIT/ROLLBACK 完成之后）、`exit_ns`。输家等锁区间取 `[lock_request_ns, lock_acquired_ns or exit_ns]`，赢家持锁区间取 `[lock_acquired_ns, lock_released_ns]`。`outcome` 只有六种：`commit`、`rollback`、`begin_busy`（抢锁重试耗尽）、`begin_failed`（BEGIN 非忙错）、`commit_busy`（COMMIT 遇忙）、`commit_failed`（其余 COMMIT 失败，含 `IntegrityError`）。`BEGIN` 失败也留一条 trace（旧实现直接丢样本）；`COMMIT` 任何失败都显式 ROLLBACK 并记真实原因，不再产生旧的 `error` 值。

**409 整页提示**：`SlotGrid` 新增只读 `conflict_scope`，按"渲染出来的格子是否真的被标脏"派生（`cells` > `page` > `none`）；冲突 slot 不在当天网格时（隐藏 `date` 与 `slot` 不一致）会退化成 `page`，不再给出零标脏的假清白页。`page` 作用域下网格不输出逐格 `data-conflict`，改由 `slots.html` 渲染 `data-conflict-page="1"` 的整页提示；`cells` 与 `none` 照旧输出 `0`/`1`。提示文案写明"仍然可选的 slot 保留原勾选"——复选框只渲染在仍可选的格子上，不能承诺冲突格也被勾选。路由仍只解析表单与映射状态码，模板只读视图字段。

**评审后补强**：L3 增加"trace 恰好来自 2 个 pid、同轮赢家/输家 pid 不同"的断言（否则单服务进程也能全绿）；新增 `test_plain_slots_page_has_no_conflict_notice` 与逐格 409 页的整页提示反向断言；`test_busy_begin_is_retried_then_mapped_to_unavailable` 增加 `begin_busy` 与 `lock_acquired_ns is None` 断言；证据改用 `pytest -v` 重新生成，变异证据补齐变异 hunk 与单进程理由。

**与架构的偏差（需人工确认）**：`architecture.md` §5.4 L3 写的是"同时 POST 同一 key 到同一个运行中的服务进程"；本次按复审要求改成两个 `src.serve` 进程（不同 `LAB_PORT`、同一库），比原文更强。planning artifacts 未改动（避免 R7 连带改动），若确认应把 §5.4 L3 的措辞改成"两个服务进程"并同步 PRD §11。

**已知限制（非本 Story 范围，均已记入 `deferred-work.md`）**：两个服务进程同时首次启动一个全新库会并发跑迁移，后到者可能撞 `table already exists`（所有并发用例都先用 `prepare_database()` 预置库）；`application.run()` 绑定失败仍会打 traceback；`architecture.md` §5.4 L3 仍写"同一个运行中的服务进程"，与本次实现不一致，需人工确认后连同 PRD §11 一起改。

**追溯**：本次修复的 `src/serve.py` 回归属 Story 1.4 的启动契约（1.4 在 `sprint-status.yaml` 中仍是 `done`）；按 R6 未改动 1.4 的状态，只在此记录。

**证据**：`evidence/story-2.2_2026-11-10_pytest-concurrency.txt`、`..._concurrency-demo.txt`、`..._pytest-full.txt`、`..._mutation-selfcheck.txt`。

## Spec Change Log

（无 bad_spec 回环。）

## Review Triage Log

一轮：blind-hunter 14 条、edge-case-hunter 10 条、verification-gap 2 条主发现 + 2 条附注；去重后按下表裁决。

| 发现 | 裁决 | 处置 |
|------|------|------|
| L3 用两个服务进程与 `architecture.md` §5.4 L3 的措辞不一致 | low（真实，但代码遵循人工复审指令） | defer：已记入 `deferred-work.md`，改架构需按 R7 同步 §11，待人工确认 |
| 旧 spec `spec-2-2-conflict-atomicity.md` 仍写进程内服务与整体区间相交 | low | defer：历史 done 记录，改写需人工确认 |
| `holder_and_waiter` 只把 `commit` 当赢家，`commit_busy` / `commit_failed` 会被误配成输家 | medium | patch：输家收紧为 `rollback`，其余 outcome 直接判失败 |
| `busy` 同时表示 BEGIN 抢锁失败与 COMMIT 遇忙，trace 不可辨 | low | patch：拆成 `begin_busy` / `commit_busy` |
| BEGIN 抛非忙错时 outcome 仍记 `rollback`，却没回滚也没持锁 | low | patch：新增 `begin_failed` |
| 声明 BEGIN 失败也会留 trace，但没有测试 | low | patch：`test_busy_begin_is_retried_then_mapped_to_unavailable` 补 trace 字段断言 |
| 跨进程按 `enter_ns` 配对、记录无轮次标识 | false（Windows/POSIX 上 `monotonic` 全系统一致；记录数已按轮次断言） | 不修；额外加 pid 断言提高确定性 |
| 没有断言两个服务进程都真的处理过请求 | high | patch：L3 断言 trace 恰好来自 2 个 pid，且同轮赢家/输家 pid 不同 |
| `free_port()` 抢端口竞态、`deadline` 复用 | low | patch：每台服务单独计时；端口被抢仍属理论风险 |
| `Popen` 抛错时日志句柄泄漏 | low | patch：失败时关闭句柄 |
| 证据只剩点号，看不出跑了哪些用例 | low | patch：证据改用 `pytest -v` 重新生成 |
| 变异证据不可审计、且用单服务进程 | low（单进程是变异生效的必要条件） | patch：证据补齐变异 hunk、命令与单进程理由 |
| 红灯日志没有归档 | low | 接受：红灯只在实现前存在，spec 已记录断言失败；不伪造红灯 |
| `conflict_scope` 按入参集合判定，冲突 slot 不在网格时给出零标脏的假清白页 | medium | patch：改为按实际标脏的格子判定 |
| page 作用域缺少逐格“未验证”标记 | low | defer：新增第七种视觉状态需先改规划文档 |
| `none` 作用域不再输出 `data-conflict`，正常页丢了属性契约 | low | patch：`cells` 与 `none` 都输出 `0`，仅 `page` 省略 |
| `.conflict-page` 没有样式 | low | patch：补 `app.css` 规则 |
| 409 标题写在模板里，绕开 `errors.py` | false：`errors.py` 拥有状态码映射与错误渲染，标题只是展示文案，错误正文仍来自服务层 | 不修 |
| 1.4 已 done 但其启动契约在 2.2 被修复，没有记录 | low | patch：已写入本 spec 的实现备注 |
| 两个服务进程同时首次启动全新库会并发迁移 | medium | defer：并发用例都先 `prepare_database()`，真实现场问题留给 1.4 范围 |
| 整页提示用例写死 47 格且不验网格是刷新后的状态 | low | patch：补 `booked_by_other` 断言 |
| demo 输出退化成元组列表、丢了 trace 条数 | low | patch：改 URL 列表并打印 trace 条数与 pid |
| COMMIT 抛非 sqlite3 异常时既不回滚也不记 `commit_failed` | low | patch：补 `except BaseException` |
| `application.run()` 绑定失败仍打 traceback | low（既有缺口，非本次引入） | defer：已记入 `deferred-work.md` |
| 正常 `/slots` 与逐格 409 页没有反向断言，整页提示可能误挂到所有页面 | medium | patch：新增 `test_plain_slots_page_has_no_conflict_notice` 与逐格页反向断言 |
| 只给 `selectable` 的格子渲染复选框，提示却说“已保留选择” | medium | patch：提示改为“仍可选的 slot 保留原勾选” |

## Verification

**Commands:**
- `python -m pytest tests/test_booking_concurrency.py -q` -- 先红（断言失败，非 ImportError），修复后全绿
- `python -m tests.concurrency_demo` -- 退出码 0
- `python -m pytest -q` -- 全量回归全绿
