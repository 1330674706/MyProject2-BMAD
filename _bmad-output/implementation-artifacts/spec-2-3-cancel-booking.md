---
title: 'Story 2.3 我的预约与取消'
type: 'feature'
created: '2026-11-10'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
context: []
baseline_commit: '629225bc61f1ea6215d88095981d6e7644479a5e'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 学生还没有一个页面能看到自己的预约，也不能在计划变化时把整张预约释放掉；缺少取消路径意味着 slot 一旦被占就永远是"没人敢动的死记录"。

**Approach:** 新增 `GET /bookings/mine` 列出当前学生自己的预约与取消入口，新增 `POST /bookings/<id>/cancel`：在首个 slot 开始前至少 2 小时、且预约属于本人时，同一事务内删除 `booking` 行（`ON DELETE CASCADE` 带走 `occupancy`）并写入 `booking_cancel` 审计；先写红测试再实现。

## Boundaries & Constraints

**Always:** 取消 = 删 `booking` 行，占用行由级联删除，不得软删除、不得只改状态位、不得留孤儿 `occupancy`；只能取消自己的预约，`owner_id` 不符返回 403；审计与被删行同事务，`action='booking_cancel'`，`before_json` 记被删 slot 列表，`after_json` 为空，序列化走 `core/redact.py`；取消后同一组 slot 任何人（含原主）都能重新预约；重复取消返回 404 且不写审计；业务规则只在 `src/app/`，写操作只经 `write_tx()`，时刻只用 20 字符 UTC；先写 `tests/test_cancel_booking.py` 并跑出断言红，再写实现转绿。

**Never:** 软删除 / `status='cancelled'` / 部分唯一索引；`booking` 表存时间段；改 `occupancy` DDL 或唯一约束；在路由/模板里做时间比较或归属判断；做 2.4 改单或 3.x 管理员功能；新增运行期依赖；把任何 Story 置 `done`。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 我的预约 | A 有 2 条、B 有 1 条 | 页面只出现 A 的 2 个 booking_id | 200 |
| 窗口内取消 | 首 slot 距 now 2h01m，本人 | 303；booking 行 0、occupancy 行 0；审计 1 条 | N/A |
| 窗口外取消 | 首 slot 距 now 1h59m，本人 | 400；booking/occupancy 不变；不写审计 | 400 |
| 取消他人 | A 持有会话取消 B 的预约 | 403；B 的记录不变；不写审计 | 403 |
| 不存在 / 已取消 | 同一 id 二次取消 | 404；审计条数不变 | 404 |
| 释放后可约 | A 取消 3 格后 | grid 三格 `free`；C 约 1 格、A 约另 1 格均 303 | N/A |
| 审计内容 | 取消成功 | `before_json["slots"]` = 排序后的被删 slot；`after_json IS NULL` | N/A |

</frozen-after-approval>

## Code Map

- `tests/test_cancel_booking.py` -- 新增：逐条覆盖上表与 epics Story 2.3 全部 AC。
- `src/app/slot_rules.py` -- 追加 `CANCEL_LEAD_HOURS = 2` 与 `validate_cancellable(first_slot, now)`；窗口规则唯一落点。
- `src/app/booking_service.py` -- 追加 `list_my_bookings()`（返回只读视图对象）与 `cancel_booking()`（用例持有事务）。
- `src/data/booking_repo.py` -- 追加 `get_by_id()`、`list_by_owner()`、`delete_by_id()`；参数化 SQL，不控制事务。
- `src/data/occupancy_repo.py` -- 追加 `list_slots_for_booking()`（按 slot_start 升序）；不改既有 SQL。
- `src/web/bookings.py` -- 追加两个路由：`GET /bookings/mine`、`POST /bookings/<id>/cancel`；只解析参数与 `validate_csrf()`。
- `src/templates/bookings_mine.html` -- 新增：渲染传入视图对象，`data-booking-id` 供测试读取。
- `src/templates/base.html` -- 追加"我的预约"入口。
- 不改：`migrations/001_init.sql`（DDL 已支持级联）、`src/core/redact.py`（白名单已含所需字段）、`src/web/errors.py`。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_cancel_booking.py` -- 先写全部 AC 断言并跑出红灯（断言失败，非 ImportError）-- R5
- [x] `src/app/slot_rules.py` -- 2 小时截止校验 -- R1
- [x] `src/data/booking_repo.py`、`src/data/occupancy_repo.py` -- 查询与删除原语 -- R2
- [x] `src/app/booking_service.py` -- 列表视图与取消用例（删 booking + 审计同事务）-- ADR-001 D5
- [x] `src/web/bookings.py`、`src/templates/bookings_mine.html`、`src/templates/base.html` -- 路由与只读渲染 -- R1
- [x] `_bmad-output/planning-artifacts/epics.md`、`PRD.md` -- 审计字段与架构一致化并同步 §11 -- R7
- [x] `_bmad-output/implementation-artifacts/sprint-status.yaml` -- 2.3 置 `review` -- R6

**Acceptance Criteria:**
- Given A 有 2 条预约、B 有 1 条，when A 请求 `GET /bookings/mine`，then 200 且页面 booking_id 集合恰为 A 的 2 个。
- Given 首个 slot 距 now 2h01m，when `POST /bookings/<id>/cancel`，then 303、booking 行 0、occupancy 行 0。
- Given 首个 slot 距 now 1h59m，when 取消，then 400 且 booking=1、occupancy=3。
- Given A 取消 B 的预约，when 提交，then 403 且 B 的 booking=1、occupancy=3。
- Given A 刚释放 3 个 slot，when C 刷新 grid 并提交其中 1 个，then 三格 `free` 且 C 返回 303；原主 A 预约另一格也 303。
- Given 同一 id 已取消一次，when 再次取消，then 404 且审计条数不变。
- Given 取消成功，when 读该 target_id 最新审计，then `action == "booking_cancel"`、`json.loads(before_json)["slots"] == sorted(slots)`、`after_json IS NULL`。

## Implementation Notes

- 红灯：`tests/test_cancel_booking.py` 首次运行 `7 failed`，全部因 `/bookings/mine` 与 `/bookings/<id>/cancel` 尚不存在（断言失败，非 ImportError）；实现后 `7 passed`。
- 绿灯：`python -m pytest -q -p no:cacheprovider` → `118 passed`（含并发/启动/视图全量回归）。
- 取消用例在 `write_tx()` 内取 `now_utc()`、查归属、取 slot、删 `booking`、写审计；`occupancy` 由 `ON DELETE CASCADE` 带走，仓储无事务控制。
- 校验顺序固定为：不存在 → 404；`owner_id` 不符 → 403；首 slot 不足 2 小时 → 400。403 优先于窗口判断，避免泄露他人预约的可取消性。
- 审计 `before_json` 写 `{id, owner_id, equipment_id, slots}`（`slots` 按 `slot_start` 升序），`after_json` 为 `NULL`；与 `architecture.md` §5.1 D5、§10.2 一致，已同步 epics Story 2.3 AC 与 PRD §11。
- 测试环境因沙箱禁止写系统临时目录，运行时把 `TEMP`/`TMP` 指向工作区内忽略目录，并加 `-p no:cacheprovider`。
- 复审（blind / edge / verification 三层）：23 组发现全部落表；14 组属实并已修复（状态三态、匿名导航、审计快照补时间戳、审计归属与条数断言、CSRF/403 优先级/2h 等号/页面状态与本地时间断言、无障碍小修），3 组转入 `deferred-work.md`，6 组判 false 或拒绝（不可达路径、窗口内跨年、既有规模下的 N+1/读撕裂）。
- 复审后：`tests/test_cancel_booking.py` 10 passed；全量 `121 passed`。Story 仍为 `review`，等待人工确认（R6）。

## Spec Change Log

## Review Triage Log

| # | 发现（来源） | 判定 | 处置 |
|---|---|---|---|
| 1 | `status_label` 把所有不可取消都写成“首 slot 前不足 2 小时”，已开始的预约被误标（blind #1 / edge #3） | medium：真实误导 | patch：新增 `cancel_status` 三态（cancellable / started / past_deadline），页面分别显示“可取消 / 已开始 / 已过取消截止” |
| 2 | 取消成功无提示（blind #2） | false：303 后列表已无该行，PRG 即结果确认；PRD 未要求 flash | 不改 |
| 3 | 零 occupancy 的 booking 变永久垃圾（blind #3） | false：创建必写 ≥1 条 occupancy，取消删 booking；该状态无路径可达 | 不改 |
| 4 | 匿名页面也渲染导航，点进去 401（blind #4） | low：每次登录都会遇到 | patch：`base.html` 仅在 `g.get('user')` 时渲染导航 |
| 5 | 页面无登出入口（blind #5） | low：1.1 起就存在的缺口，非本 Story 引入 | defer |
| 6 | 取消路由缺 CSRF / 匿名访问测试（blind #6 / verify #1） | medium：删掉 `validate_csrf()` 仍全绿 | patch：新增缺 token 400 且不写库用例 |
| 7 | 2 小时等号边界未测（blind #7 / verify #6） | medium：`<` 改 `<=` 仍全绿 | patch：新增恰好 2h → 303 用例 |
| 8 | 并发取消未测（blind #8） | maybe-false / low：FR-6 与 AC 未要求，需进程级栅栏另建测试 | defer |
| 9 | 列表顺序无断言，文档声称倒序但同秒按 uuid 排（blind #9 / verify #7） | low：FR/AC 未规定顺序 | defer |
| 10 | 审计快照缺 `created_at` / `updated_at`，与 D5“整张快照”不符（blind #10 / edge #6） | medium：删行后无法还原生命周期 | patch：`before_json` 增补两字段（白名单已允许） |
| 11 | 审计断言未校验 actor / target_type / 条数（blind #11 / verify #5） | medium：重复写或错归属仍全绿 | patch：成功=1、400=0、403=0，并校验 actor/target_type |
| 12 | 重编译的 epic 上下文丢失 401/400、uuid、时间戳等契约（blind #12 / edge #5） | low：后续 Story 可能少读约束 | patch：补回两条精简约束 |
| 13 | `validate_cancellable` 与 §11“create/edit 两模式”矛盾（blind #13） | false：取消截止是窗口规则，§11 的 create/edit 描述的是形状校验；两者同处 `slot_rules.py` | 不改 |
| 14 | 2 小时常量三处硬编码（blind #14） | low：改截止时间会漏文案 | patch：状态文案与异常消息由 `CANCEL_LEAD_HOURS` 生成 |
| 15 | 时段格式丢年份/星期，且视图只留展示串（blind #15 / verify #4） | false：7 天窗口内不可能出现跨年同 MM-DD；展示串经本地时区转换正确。但“本地时间被渲染”缺断言 → 属实 | patch：断言页面含 `01-01 12:00` 且不含原始 UTC 串；格式不改 |
| 16 | `/bookings/mine` N+1 且无上限（blind #16） | low：约 40 名学生规模，改批量查询新增公开面 | 拒绝：非日常可感知，修复超出最小改动 |
| 17 | 测试模块 docstring 声称“只经公开入口”，但用 SQL 播种/断言（blind #17） | low：表述不精确 | patch：docstring 改为“HTTP 触发 + 只读 SQL 断言 + 直接 INSERT 播种” |
| 18 | 表格缺 `scope`/`caption`、按钮同名、disabled 对比度低（blind #18） | low：NFR 未要求无障碍，但改动很小 | patch：`th scope="col"`、按钮 `aria-label`、disabled 背景改 `#6b7280` |
| 19 | 传入 naive datetime 会 TypeError→500（edge #1） | false：所有调用方只传 20 字符 UTC 文本 | 不改 |
| 20 | 连接未开 `foreign_keys` 会留孤儿 occupancy（edge #2） | false：`src/` 唯一连接入口 `data/db.connect()` 固定开启；seed 也走它 | 不改 |
| 21 | 列表两条 SELECT 之间被取消会渲染幽灵行（edge #4） | low：读快照撕裂，窗口极窄；修复需重构为单条 JOIN | 拒绝：非日常可感知，修复超出最小改动 |
| 22 | 403 应先于窗口判断但无测试（verify #2） | medium：交换顺序仍全绿，会泄露他人预约可取消性 | patch：新增“窗口内取消他人 → 403”用例 |
| 23 | 页面状态/按钮、时段本地化无断言（verify #3 / #4） | medium：改坏 `cancellable` 或展示仍全绿 | patch：列表用例解析行 HTML，断言状态文案、`disabled`、本地时间 |

## Verification

**Commands:**
- `python -m pytest tests/test_cancel_booking.py -q` -- 先红（断言失败），实现后全绿
- `python -m pytest -q` -- 全量回归全绿
