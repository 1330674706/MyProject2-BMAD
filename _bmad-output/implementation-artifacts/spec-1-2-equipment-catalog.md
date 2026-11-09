---
title: 'Story 1.2 设备清单、开放时间维护与 slot 派生'
type: 'feature'
created: '2026-11-09'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'fb98528f90e474b6adc1c60faeb5b69fa235ff03'
context:
  - 'project-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前 `/equipments` 仍是占位页，管理员无法维护设备名称与每日开放时间，系统也没有从开放时间派生 30 分钟 slot 的唯一实现，Story 1.3 的逐 slot 状态视图因此没有可信的时间基座。

**Approach:** 在服务层实现开放时间校验、越界预约拒绝与 `build_grid()` 纯派生；管理员通过 `/admin/equipments` 维护设备，学生通过 `/equipments` 只读设备清单；所有时刻经 `core/timeutil.py` 在本地墙钟与 UTC 定长文本间转换。

## Boundaries & Constraints

**Always:** 业务规则只在 `src/app/`；写设备与审计同事务且只经 `write_tx()`；`open_start/open_end` 是本地 `HH:MM` 墙钟，slot 入库为 20 字符 UTC；操作日志用 `redact` 白名单；`/admin/*` 路由第一行鉴权。

**Never:** 不建 `slot` 表、不改 `occupancy` 约束；不做 1.3 的 slot 状态/`/slots` 视图；不做 1.4 的种子导入；不在路由或模板中比较时间或判断冲突；不引入新运行期依赖。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | `open_start=09:00`、`open_end=12:00` | 当天 6 个 slot，本地 09:00–11:30 | N/A |
| FULL_DAY | `08:00–22:00` | 28 个 slot，本地 08:00–21:30 | N/A |
| NARROW_CONFLICT | 已有 15:00、15:30 占用，收窄为 `08:00–15:00` | 拒绝保存，原配置与占用行不变 | 409 |
| BAD_ALIGNMENT | `open_start=09:15` | 拒绝保存，原配置不变 | 400 |
| BAD_ORDER | `18:00–09:00` | 拒绝保存，原配置不变 | 400 |
| AUTH_BOUNDARY | 学生带会话 / 不带会话 GET `/equipments` | 200 且含设备三字段 / 401 | 401 |

</frozen-after-approval>

## Code Map

- `src/core/timeutil.py` -- 已有 `now_utc()`；补 `local_to_utc()`、`utc_to_local()` 与本地时区常量。
- `src/app/slot_service.py` -- 新建；`build_grid(open_start, open_end, day)` 纯函数，返回 UTC 字符串列表。
- `src/app/equipment_service.py` -- 新建；设备新增、开放时间校验、越界占用预检、`write_tx()` 内更新与审计。
- `src/data/equipment_repo.py` -- 新建；`insert_equipment()`、`list_active()`、`get_by_id()`、`update_window()`，不控制事务。
- `src/web/catalog.py` -- 已有 `catalog` 蓝图；`GET /equipments` 改为渲染真实设备清单，保留 `/slots` 占位给 1.3。
- `src/web/admin.py` -- 已有 `admin` 蓝图；增加设备维护 GET/POST 与 `POST /admin/equipments/<id>/window`。
- `src/templates/equipments.html` -- 新建；学生只读清单。
- `src/templates/admin_equipments.html` -- 新建；新增设备与修改开放时间表单。
- `tests/test_equipment_catalog.py` -- 新建；逐条覆盖上述 AC 与矩阵，必须先红后绿。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_equipment_catalog.py` -- 先写全部 AC 与矩阵测试并运行，确认因缺少实现而失败 -- 满足 R5 的红灯证据。
- [x] `src/core/timeutil.py` -- 增加本地/UTC 双向转换 -- 让 slot 派生不手工拼时间。
- [x] `src/app/slot_service.py` -- 实现 `build_grid()` -- slot 集合唯一派生点。
- [x] `src/data/equipment_repo.py` -- 实现设备参数化 SQL -- SQL 只留在 `src/data/`。
- [x] `src/app/equipment_service.py` -- 实现新增/更新、校验、冲突与审计 -- 业务规则唯一落点。
- [x] `src/web/catalog.py`、`src/web/admin.py` -- 接线路由与状态码 -- 路由只解析表单。
- [x] `src/templates/equipments.html`、`src/templates/admin_equipments.html` -- 渲染传入视图对象 -- 模板不做任何计算。
- [x] `tests/test_equipment_catalog.py` -- 运行至全绿，再跑全量回归 -- 证明实现与旧 Story 兼容。

**Acceptance Criteria:**
- Given 开放时间 `09:00–12:00`，When 调用 `build_grid()`，Then 恰好 6 个 slot，本地序列为 09:00/09:30/10:00/10:30/11:00/11:30 → `assert [utc_to_local(s).strftime("%H:%M") for s in grid] == ["09:00","09:30","10:00","10:30","11:00","11:30"]`
- Given 开放时间改为 `08:00–22:00`，When 再次调用 `build_grid()`，Then 恰好 28 个，首个 08:00、末个 21:30 → `assert len(grid) == 28 and first == "08:00" and last == "21:30"`
- Given 已有 15:00、15:30 占用，When 收窄为 `08:00–15:00`，Then 409 且配置与占用不变 → `assert resp.status_code == 409 and open_end_after == open_end_before and occupancy_count() == n_before`
- Given 提交 `open_start=09:15`，When 保存，Then 400 且配置不变 → `assert resp.status_code == 400 and open_start_after == "09:00"`
- Given 提交 `18:00–09:00`，When 保存，Then 400 且行不变 → `assert resp.status_code == 400 and (open_start_after, open_end_after) == ("09:00", "12:00")`
- Given 已登录学生，When GET `/equipments`，Then 200 且含名称与开放时间；无 Cookie 为 401 → `assert (authed.status_code, anon.status_code) == (200, 401) and all(v in authed.text for v in (name, "09:00", "12:00"))`
- Given 开放时间 `08:00–22:00`，When 检查 slot 集合，Then 07:30 与 22:00 不在集合、最小值为 08:00 → `assert "07:30" not in local_times and "22:00" not in local_times and min(local_times) == "08:00"`

## Implementation Notes

- 红灯基线：`python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_run tests/test_equipment_catalog.py` 为 8 failed；3 条因缺少 `slot_service` / `local_to_utc`，5 条因路由 404 或占位页不含设备字段。
- 绿灯结果：同一命令 8 passed；全量 `python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_run` 为 31 passed。
- 环境说明：沙箱拒绝默认 pytest 临时目录与 `.pytest_cache`，验证命令固定加 `--basetemp=.pytest_tmp_run -p no:cacheprovider`，不改变测试语义。
- 落地调整：`timeutil` 增加 `local_at()` 构造本地时刻，避免 `slot_service` 手工拼时间；保留既有 `catalog` 蓝图承载 `/equipments`，未重命名 Story 1.1 已引用的 endpoint。
- 管理员设备维护页同时支持新增设备与改名/改开放时间；更新与新增审计均在同一 `write_tx()` 内写入 `equipment_update`。
- 复审修复：管理页增加入口与可见名称输入；400/409 重渲染维护页；冲突预检只统计 `slot_start >= now_utc()` 的未来占用；补齐成功保存、权限、CSRF、显式窗口、404 与回滚审计测试。复审红灯 3 条，修复后 19 passed，全量 42 passed。

## Spec Change Log

## Review Triage Log

| 发现 | 判定 | 证据与处置 |
|---|---|---|
| `build_grid()` 未校验 30 分钟对齐与纯 `HH:MM` 格式 | low | 只有 `equipment_service` 校验后的窗口会进入 `build_grid()`；在 `slot_service` 再加形状校验会违反 R1（形状校验归 `slot_rules.py`）。拒绝。 |
| `build_grid()` 对 `None` 抛 `TypeError` | low | 内部纯函数，当前调用方均传字符串，无可达用户路径。拒绝。 |
| `build_grid()` 返回 `list[str]` 与 1.3 六态契约冲突 | low | Story 1.2 AC 明确按 `for s in grid` 取时刻；状态叠加属于 1.3 的 slot 视图范围，本 Story 明确不实现。拒绝为 1.2 缺陷。 |
| 管理员维护页没有页面入口 | medium | 已在 `/equipments` 由路由传入 `admin_url`，模板渲染“设备维护”链接；新增管理员可见、学生不可见断言。已修。 |
| 设备名称只能经隐藏字段回传，界面无法改名 | medium | 维护表已改为可见 `type="text" name="name"` 输入；新增渲染断言。已修。 |
| 失败保存落到通用错误页，丢失设备上下文 | medium | 管理路由捕获 `Validation`/`Conflict` 并用 `render_error(..., admin_equipments.html, equipments=...)` 重渲染同页；新增加载设备名的 400 断言。已修。 |
| 409 文案使用原始 UTC 且冲突列表不封顶 | low | 约定只要求列出 `equipment_id` 与 `slot_start`，原始 UTC 即存储值；可读化属增强，不影响正确性。拒绝。 |
| 新增设备时空窗口字段回退 `08:00–22:00` 而非 400 | false | FR-2 明确“默认 08:00–22:00”；空值取默认是约定行为，显式非法值仍返回 400。 |
| 冲突预检不区分过去/未来，历史占用永久阻止收窄 | high | 仓储查询已改为 `slot_start >= now_utc()`；新增“2020 年占用不阻止收窄”红灯后转绿。已修。 |
| 缺少成功保存、管理页渲染、403/401、CSRF、显式窗口、404、回滚审计测试 | medium | 已新增 11 条回归测试；3 条先红后绿，全量 42 passed。已修。 |
| 测试 helper 与 `test_auth_login.py` 重复 | low | 跨 Story 测试重构，无用户影响，不在 1.2 范围。拒绝。 |
| 测试夹具直接 `commit()` 写 booking/occupancy | false | R2 约束生产写路径；测试夹具直接准备数据不经过应用仓储是正常做法。 |
| 新增设备也记录为 `equipment_update` | false | `audit_log.action` 的 CHECK 没有 create 取值，§10.2 只定义 `equipment_update`；沿用合法枚举。 |
| spec 验证命令、context、红灯日志不完整 | false | 属于 spec 记录问题而非代码缺陷；验证命令已改为沙箱内可执行形式。 |
| 模板硬编码 `08:00`/`22:00` 与服务层默认值重复 | low | 服务端默认仍是唯一裁决；模板值只做预填，不影响校验。拒绝。 |
| `utc_to_local()` 对损坏文本抛 `ValueError`，`ZoneInfo` 导入失败无诊断 | low | DB CHECK 限制 20 字符形状，应用只写合法时刻；`tzdata` 已在依赖中。拒绝。 |
| 新路由遮蔽 `id`、缺少 `provide_automatic_options=False`、400 先于 404 | low | 与既有 `reset_password` 风格一致；先校验窗口再查存在性可接受。拒绝。 |
| 409 测试只断言 `E1`，未验证 slot 与审计回滚 | medium | 已扩展断言 UTC `slot_start` 且 409 不新增审计。已修。 |
| 管理页无法改名（与隐藏字段同源） | medium | 与第 5 条同一根因，已随可见名称输入修复。已修。 |

## Design Notes

`build_grid()` 只负责时间派生，不读取数据库；1.3 再在其上叠加占用状态。管理员新增设备属于 FR-2 的“新增和修改”，最小实现为同一维护页上的新增表单与 `equipment_update` 审计。

## Verification

**Commands:**
- `python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_run tests/test_equipment_catalog.py` -- expected: 19 passed。
- `python -m pytest -q --ignore=_bmad -p no:cacheprovider --basetemp=.pytest_tmp_run` -- expected: 42 passed，无回归。
