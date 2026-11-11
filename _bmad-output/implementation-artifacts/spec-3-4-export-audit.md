---
title: 'Story 3.4 自然周 CSV 导出与追加式操作日志'
type: 'feature'
created: '2026-11-11'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
context: ['project-context.md']
baseline_commit: '947c41d'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 管理员还没有可归档的一周清单，也没有一处能倒查“谁在什么时候做了什么”；导出若原样输出 UTC 或混入锁定/已取消行，周表就无法作为唯一的人工归档。

**Approach:** 新增 `GET /admin/export?week=` 生成 UTF-8 BOM 的六列 CSV（一行一个 slot，只导 `kind='booking'`），新增 `GET /admin/audit` 只读渲染审计日志；周界、slot 结束时刻与本地墙钟全部经 `core/timeutil.py`，审计 JSON 读取时再经 `core/redact.py` 白名单过滤。

## Boundaries & Constraints

**Always:** 表头精确为 `设备,slot 开始,slot 结束,学号,booking_id,状态`；`utf-8-sig`、`\n` 换行；slot 结束由服务端按 30 分钟推算；自然周为本地周一 00:00 起、右端开区间；只导 `kind='booking'`；审计页 GET-only，无编辑/删除路由；`@admin_required` 是路由第一行；不改 1.x/2.x/3.x 既有行为。

**Never:** `BETWEEN`、客户端传结束时间、导出锁定行或已取消预约、导出内部自增 id；响应体出现明文密码、`password_hash`、session 或 csrf token；给 `/admin/audit` 加写路由或页面表单；改 schema/迁移、改 `slot_service` 状态判定、新增运行期依赖；在 `web/` 或模板做时间比较。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| EXPORT_FIVE | 周内 5 条 booking 占用行 | BOM 开头，6 行（表头 + 5） | N/A |
| EXPORT_MULTI | 3-slot + 1-slot 预约 | 表头精确；同一 `booking_id` 占 3 行；结束 = 开始 + 30 分钟 | N/A |
| EXPORT_CANCELLED | 一条预约已取消 | 该 `booking_id` 出现 0 次 | N/A |
| WEEK_BOUNDARY | 本地周一 00:00 与上周日 23:30 | 分别只出现在各自周 | N/A |
| LOCK_EXCLUDED | 周内 1 锁 + 2 预约 | 数据行 2；锁定 slot 不在“slot 开始” | N/A |
| EMPTY_WEEK | 周内无预约 | 仅表头一行 | N/A |
| BAD_WEEK | 非法周参数 | 400，不生成文件 | `Validation → 400` |
| AUDIT_FIVE | 预约/取消/改单/锁定/重置密码 | 五类 action 各 ≥ 1；actor/target/created_at 非空 | N/A |
| AUDIT_READONLY | `PUT` / `DELETE /admin/audit` | 均 405；页面无表单与写入口 | N/A |
| REDACTION | 导出体与日志页完整响应 | 明文密码、全部 `password_hash` 命中 0 | N/A |
| RESET_AUDIT_KEYS | 一次重置密码 | before/after 仅 `password_version` | N/A |
| AUTH | 学生 / 匿名访问两个 GET | 403 / 401，均不写库 | `Forbidden / Unauthorized` |

</frozen-after-approval>

## Code Map

- `src/core/timeutil.py` — 新增 `add_minutes_utc()`：slot 结束时刻的唯一算法；既有的 `week_bounds_utc()` 提供本地自然周半开区间。
- `src/core/redact.py` — 新增 `filter_stored()`：读取既有审计 JSON 时按同一字段白名单再过滤，非法/非字典返回空串。
- `src/data/booking_repo.py` — 新增 `list_week_export_rows()` 与 `LIST_WEEK_EXPORT`：`kind='booking'`、半开区间、按 slot 排序，带设备名与学号。
- `src/data/audit_repo.py` — 新增 `list_recent()`（倒序 + `LIMIT`，左连 `user` 取学号）与 `count_all()`；不新增任何写语句。
- `src/app/export_service.py` — 新建：`build_week_export()` 产出 `ExportFile(filename, body, row_count)`；`csv.writer` 固定 `lineterminator="\n"`，`encode("utf-8-sig")`。
- `src/app/audit.py` — 新建：`AuditEntry` / `AuditPage` / `list_audit()`；动作与对象中文标签、本地时间展示、`—` 占位都在服务层算好。
- `src/web/admin.py` — 新增 `GET /admin/export` 与 `GET /admin/audit`，首行 `@admin_required`；只做参数透传、周参数 400 映射与 `text/csv` 附件头。
- `src/templates/admin_audit.html` — 新建只读表格，`data-audit-action` / `data-audit-actor` 供验收定位；无表单、无按钮。
- `src/templates/admin_week.html` — 周导航下加“导出本周 CSV”“操作日志”两个只读入口。
- `tests/test_export_audit.py` — 新建 12 个用例，覆盖矩阵全部行与 9 条 AC；先红后绿。
- 不改：`migrations/`、`tx.py`、`slot_service.py`、`booking_service.py`、`auth_service.py`、既有 1.x/2.x/3.x 测试。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_export_audit.py` — 先写 9 条 AC 对应断言并跑出红灯（7 failed / 2 passed），再补矩阵行 — R5
- [x] `src/core/timeutil.py`、`src/core/redact.py` — slot 结束算法与读取侧白名单 — R4/NFR-4
- [x] `src/data/booking_repo.py`、`src/data/audit_repo.py` — 只读参数化 SQL，半开区间 — R1/R2
- [x] `src/app/export_service.py`、`src/app/audit.py` — CSV 与日志视图服务 — FR-8
- [x] `src/web/admin.py`、`admin_audit.html`、`admin_week.html` — GET-only 路由与只读页面 — FR-8
- [x] 全量回归 `python -m pytest -q` — 209 passed；本 Story 17 passed

**Acceptance Criteria:**
- Given 周内 5 条 booking 占用行, when 导出, then 响应以 BOM 开头且非空行数为 6
- Given 3-slot 与 1-slot 预约, when 导出, then 表头精确且 3-slot 预约占 3 行共享 `booking_id`
- Given 一条预约已取消, when 导出, then 该 `booking_id` 不出现
- Given 本地周一 00:00 与上周日 23:30, when 分别导出两周, then 各归其周
- Given 1 锁 + 2 预约, when 导出, then 数据行 2 且锁定行不出现
- Given 五类动作, when 打开日志页, then 五类 action 齐全且每条字段完整
- Given 只读日志页, when 发送 PUT 与 DELETE, then 均 405
- Given 导出体与日志页, when 检索明文密码与哈希, then 命中 0
- Given 一次重置密码, when 读取该审计行, then before/after 仅含 `password_version`

## Implementation Notes

- 导出 SQL 在 `booking_repo` 内 JOIN `booking`/`user`/`equipment`，`kind='booking'` 与 `booking_id IS NOT NULL` 双条件；锁定行天然没有 `booking` 行，不会进入结果。
- `week_bounds_utc()` 已把本地周一 00:00 转成 UTC 半开区间，导出与周视图共用，跨周边界不再另算。
- 审计页展示的 `before_json` / `after_json` 先 `filter_stored()` 再渲染：即便历史行混入白名单外字段，也不会出现在响应体。
- 自定决策：日志默认显示最近 200 条并显示总数与截断提示；动作标签在服务层映射，模板不做分支；导出文件名 `bookings-YYYY-MM-DD.csv`。
- 自定决策：CSV 单元格中和换行与 `= + - @` 公式前缀，保证“一行一个 slot”且 Excel 不执行注入公式。
- 自定决策：导出不写 `audit_log`——`action` 枚举被 CHECK 冻结，新增 `export` 需迁移与 ADR，登记为 defer；`ExportFile` 不保留无读者的 `row_count`。
- 评审收口（2026-11-11）：`filter_stored()` 遇到未知 `target_type` 返回空串；历史 `created_at` 非法时原样展示而非 500；周参数错误改用 `timeutil` 原文，区分“格式错”与“越界”；审计行补 `data-audit-actor-label/created-at` 锚点；周视图入口文案改为“导出该周 CSV”；补导出下载头、入口链接、排序/截断、公式注入与历史脏数据用例。
- 本 Story 的 TDD 红灯在实现前实际跑出（`tests/test_export_audit.py` 7 failed / 2 passed），实现后 17 passed；全量 209 passed。

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Route |
| --- | --- | --- |
| BH-01 审计页 target_id 是 uuid，未解析成学号/设备 | low | defer：需要额外 JOIN 与新的展示契约，登记后续 |
| BH-02 200 条上限无翻页/筛选 | low | defer：PRD 未要求分页，登记为后续加固 |
| BH-03 `filter_stored()` 无测试，直通实现也全绿 | medium | patch：补历史行/坏 JSON 用例 |
| BH-04 未知 `target_type` 触发 `KeyError` → 500 | medium | patch：`.get()` + 未知即返回空串 |
| BH-05 “已取消不导出”用裸 DELETE 造状态 | medium | patch：改走 `booking_service.cancel_booking()` |
| BH-06 CSV 公式注入与换行拆行 | medium | patch：`_csv_cell()` 中和换行与 `= + - @` 前缀 |
| BH-07 入口文案“导出本周”与实际周不符 | low | patch：改为“导出该周 CSV” |
| BH-08 审计 JSON 里仍是 UTC 原串 | false | 审计快照按原样留存；本地化只约束事件时间列与导出 |
| BH-09 导出动作未留痕 / `row_count` 无读者 | low | defer（action 枚举被 CHECK 冻结）；patch：删除 `row_count` |
| BH-10 AUTH/BAD_WEEK/下载头矩阵行只验一半 | medium | patch：补计数不变、无 `Content-Disposition`、mimetype/filename 断言 |
| BH-11 周参数映射复制且越界被报成格式错 | low | patch：改用 `Validation(str(error))` |
| BH-12 展示字段无锚点、零断言 | medium | patch：补 `data-audit-*` 与可见值断言 |
| BH-13 新入口无 CSS | low | patch：补 `.week-actions` 与 `.audit-table code` |
| BH-14 第 7 份测试脚手架 | low | defer：仓库级测试夹具重构，不在本 Story |
| EC-01 公式注入 | medium | patch：同 BH-06 |
| EC-02 状态恒为“有效”，与周视图异常标记不同 | false | 架构 §10.1 固定状态集合只有“有效” |
| EC-03 非法 `created_at` 让整页 500 | medium | patch：展示失败原样返回 |
| EC-04 Spec 写 201 passed 与实测不符 | low | patch：更新为 209 passed |
| VG-01 读取侧白名单从未被真正触发 | medium | patch：同 BH-03 |
| VG-02 操作人/本地时间/变更列零断言 | medium | patch：同 BH-12 |
| VG-03 排序、LIMIT、truncated 未验证 | medium | patch：补倒序与 `limit=1` 用例 |
| VG-04 下载 mimetype 与附件名未验证 | medium | patch：补头断言 |
| VG-05 周视图两个新入口未验证 | medium | patch：补 href 断言 |

## Design Notes

导出是纯读路径，不经过 `write_tx()`；唯一需要“算”的量是 slot 结束时刻，放在 `timeutil.add_minutes_utc()`，避免任何文件手工拼时间。日志页同样是纯读：`audit_repo` 只提供 SELECT，页面没有表单，Flask 对未注册的 PUT/DELETE 自然返回 405，不需要额外分支。

## Verification

**Commands:**
- `python -m pytest tests/test_export_audit.py -q` — 先红（7 failed）后绿（17 passed）。
- `python -m pytest -q` — 全量回归 209 passed。
