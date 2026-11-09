---
status: reviewed
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/PRD.md
  - _bmad-output/planning-artifacts/architecture.md
  - decision-log.md
created: 2026-11-04
updated: 2026-11-04
---

# 实验室设备预约系统 — Epic Breakdown

## Overview

本文把 `PRD.md`（8 条 FR / 4 条 NFR，status: reviewed）与 `architecture.md`（ADR-001 至 ADR-005，status: final）拆成 **3 个 Epic / 12 个 Story**，每条 AC 都写成"一次请求 + 一个可断言结果"的形式，可以直接翻译成一条 pytest 断言。

三条拆分原则：

- **Story 之间只允许向前依赖。** 每个 Story 的前置 Story 编号必然更小，不存在"等 3.2 写完 2.4 才能测"的倒挂。
- **AC 只写可观测事实。** 状态码、行数、集合相等、字节前缀、索引形状。不写"体验良好""响应及时""界面清晰"。
- **规则只有一个落点。** slot 形状校验只在 `app/slot_rules.py`，slot 状态只在 `app/slot_service.build_grid()`，事务只在 `data/tx.py`，状态码只在 `web/errors.py`（architecture §11）。

## 硬约束核对

| 约束 | 实际 | 结果 |
| --- | --- | --- |
| Epic 数 = 3 | E1 / E2 / E3 | ✅ |
| Story 数 = 12 | 4 + 4 + 4 | ✅ |
| 单 Story ≤ 1 天 | 最大 1 天（M） | ✅ |
| AC 可转 pytest 断言 | 每条 AC 附 `→ assert ...` | ✅ |
| 标注 FR / NFR / ADR / 前置 | 见 Story 索引与各 Story 元数据块 | ✅ |

## Story 索引

| Story | 标题 | FR | NFR | ADR | 前置 | 预估 | 测试文件 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1.1 | 学号注册、登录与管理员重置默认密码 | FR-1 | NFR-4 | ADR-004 | — | M（0.75 天） | `tests/test_auth_login.py` |
| 1.2 | 设备清单、开放时间维护与 slot 派生 | FR-2 | — | ADR-002、ADR-005 | 1.1 | M（0.75 天） | `tests/test_equipment_catalog.py` |
| 1.3 | 逐 slot 占用状态视图 | FR-3 | NFR-3 | ADR-003、ADR-005 | 1.1、1.2 | M（0.75 天） | `tests/test_slot_view.py` |
| 1.4 | 单文件部署、一条命令启动与种子导入 | FR-2（种子） | NFR-2 | ADR-002 | 1.2 | S（0.5 天） | `tests/test_ops_startup.py` |
| 2.1 | 提交连续 slot 预约 | FR-4 | — | ADR-001、ADR-003、ADR-005 | 1.2、1.3 | M（0.75 天） | `tests/test_create_booking.py` |
| 2.2 | 冲突整单原子拒绝与并发裁决 | FR-5 | NFR-1 | ADR-001 | 2.1 | M（1 天） | `tests/test_booking_concurrency.py` |
| 2.3 | 我的预约与取消 | FR-6 | — | ADR-001、ADR-005 | 2.1 | S（0.5 天） | `tests/test_cancel_booking.py` |
| 2.4 | 连续多 slot 选择与改单边界 | FR-4、FR-7 | — | ADR-001、ADR-005 | 2.1 | M（1 天） | `tests/test_slot_rules.py` |
| 3.1 | 管理员本周视图与按学号检索 | FR-7、FR-3 | NFR-3 | ADR-003、ADR-005 | 1.3、2.1 | M（0.75 天） | `tests/test_admin_week_view.py` |
| 3.2 | 管理员改单 | FR-7 | — | ADR-001、ADR-003 | 2.4、3.1 | S（0.5 天） | `tests/test_admin_edit_booking.py` |
| 3.3 | 锁定与解锁 slot | FR-7 | — | ADR-001、ADR-003 | 2.2、3.1 | S（0.5 天） | `tests/test_admin_lock.py` |
| 3.4 | 自然周 CSV 导出与追加式操作日志 | FR-8 | NFR-4 | ADR-002、ADR-005 | 3.1、3.2、3.3 | M（1 天） | `tests/test_export_audit.py` |

## Requirements Inventory

### Functional Requirements

- **FR-1 学号密码账号**：学号全局唯一注册并登录；管理员可重置为默认密码；无找回；重置后旧会话失效。
- **FR-2 设备清单与开放时间**：管理员维护设备与每日开放时间（默认 08:00–22:00）；据此派生对齐 :00/:30 的 30 分钟 slot；收窄窗口致已有预约越界时 409 且原配置不变。
- **FR-3 占用状态视图**：按设备与日期读库渲染逐 slot 状态；打开或刷新即最新；无推送、无轮询。
- **FR-4 提交连续 slot 预约**：同设备连续 1–8 个 slot，单一事务写入；对齐、开放时间内、7 天窗口全部校验。
- **FR-5 冲突原子拒绝**：任一 slot 已被占用或锁定则整单 409 并返回全部冲突，写入 0 行。
- **FR-6 我的预约与取消**：只看自己的预约；首个 slot 前 ≥ 2 小时可取消整单，slot 立即释放并写日志。
- **FR-7 管理员周视图、检索、改单与锁定**：本周视图标记异常；按学号检索；改单/取消/锁定/解锁与学生预约共用同一唯一约束。
- **FR-8 导出与操作日志**：自然周 CSV（UTF-8 BOM、六列固定、一行一 slot）；追加式操作日志覆盖五类动作。

### NonFunctional Requirements

- **NFR-1 并发正确性**：同 key 并发提交恰好一次成功；`(equipment_id, slot_start)` 占用行数 ≤ 1；120 轮全过。
- **NFR-2 可运维**：单个 SQLite 文件承载全部数据；运行时无外部依赖；一条命令启动；`GET /health` = 200。
- **NFR-3 响应式与零安装**：375px / 1280px 浏览器直接完成主流程，无横向滚动，无客户端安装。
- **NFR-4 凭据安全**：仅存加盐哈希；响应、页面、日志、CSV 中明文密码命中数为 0。

### Additional Requirements

来自 `architecture.md`，不新增功能，只固定实现契约：

- **AR-1（ADR-001）**：`uq_occupancy_slot UNIQUE (equipment_id, slot_start)` 是唯一裁决者；五条写路径（创建、改单、锁定、解锁、取消）共用 `insert_occupancy`；`write_tx()` 用 `BEGIN IMMEDIATE`；禁用 `INSERT OR IGNORE`；冲突以 `IntegrityError` 上浮映射 409。
- **AR-2（ADR-002）**：单文件 `data/lab.db`，stdlib `sqlite3`，`migrations/*.sql` 按 `PRAGMA user_version` 幂等补齐；PRAGMA 含 `foreign_keys=ON`、`journal_mode=WAL`、`busy_timeout=1000`。
- **AR-3（ADR-003）**：服务端渲染 + 表单 POST + 303 PRG；slot 用复选框多值提交；409 重渲染同一页面并标出冲突；无 JSON API、无前端构建。
- **AR-4（ADR-004）**：签名 Cookie 会话（`uid`/`role`/`pv`），`werkzeug.security` 加盐哈希，重置密码递增 `password_version` 使旧会话失效。
- **AR-5（ADR-005）**：所有时刻存 20 字符 UTC 文本；转换只在 `core/timeutil.py`；自然周用半开区间，禁用 `BETWEEN`；禁用 `DEFAULT CURRENT_TIMESTAMP`。
- **AR-6（§10.1/§10.2）**：CSV 六列固定、`utf-8-sig`、一行一 slot；审计 `before_json`/`after_json` 只写 `core/redact.py` 白名单字段；日志只追加。

### UX Design Requirements

无独立 UX 文档（`_bmad-output/planning-artifacts/` 下无 `ux-designs/`）。界面质量只由 **NFR-3** 约束，其可自动断言的部分落在 Story 1.3（viewport meta、`@media (max-width: 480px)`）与 Story 3.1（周视图复用 `_slot_grid.html`）；375/1280 人工截图作为 Demo 证据，不进 pytest。

### FR Coverage Map

| 需求 | 覆盖 Story |
| --- | --- |
| FR-1 | 1.1 |
| FR-2 | 1.2、1.4 |
| FR-3 | 1.3、3.1 |
| FR-4 | 2.1、2.4 |
| FR-5 | 2.2、3.3 |
| FR-6 | 2.3 |
| FR-7 | 2.4、3.1、3.2、3.3 |
| FR-8 | 3.4 |
| NFR-1 | 2.2 |
| NFR-2 | 1.4 |
| NFR-3 | 1.3、3.1 |
| NFR-4 | 1.1、3.4 |

## Epic List

| Epic | 名称 | 目标 | Story |
| --- | --- | --- | --- |
| E1 | 账号与设备发现 | 一个学生能注册、登录、看到设备与真实 slot 状态；管理员能把设备与开放时间配对到现实 | 1.1 – 1.4 |
| E2 | 预约与并发 | 一次提交占住 1–8 个连续 slot；冲突在数据库层被裁决；改单边界只有一套规则 | 2.1 – 2.4 |
| E3 | 管理员运维 | 周一 10 分钟内扫完本周、改单、锁定、导出、查日志 | 3.1 – 3.4 |

## Epic 1: 账号与设备发现

**目标**：一个学生能在 30 秒内注册、登录、看到某台设备某天的真实 slot 状态；管理员能把"这台设备每天几点开门"如实写进系统，并且不会因为改配置悄悄破坏已有预约。

**覆盖**：FR-1、FR-2、FR-3；NFR-2、NFR-3、NFR-4。
**约束**：ADR-002（单文件 SQLite）、ADR-003（服务端渲染）、ADR-004（签名会话 + 密码版本号）、ADR-005（UTC 定长存储）。

### Story 1.1: 学号注册、登录与管理员重置默认密码

As a 学生 / 管理员,
I want 用学号自助注册并登录，遗忘密码时由管理员重置为系统默认密码,
So that 不用等审批、不用找回邮件就能进入系统，且重置后旧设备上的会话立刻失效。

**元数据**：FR-1；NFR-4；ADR-004；前置：无；预估：M（0.75 天）；测试：`tests/test_auth_login.py`

**Acceptance Criteria:**

**Given** 学号 `2025001` 已注册
**When** 用同一学号再次 `POST /register`
**Then** 返回 409，且 `user` 表中该学号行数为 1
→ `assert resp.status_code == 409 and count_user("2025001") == 1`

**Given** 已注册学号与正确密码
**When** `POST /login` 提交正确凭据
**Then** 返回 303 且 `Location` 指向 `/equipments`，响应 `Set-Cookie` 同时含 `HttpOnly`、`SameSite=Lax`、`Path=/`
→ `assert resp.status_code == 303 and "/equipments" in resp.headers["Location"] and "HttpOnly" in c and "SameSite=Lax" in c`

**Given** 已注册学号
**When** `POST /login` 提交错误密码
**Then** 返回 401，且客户端未获得会话 Cookie
→ `assert resp.status_code == 401 and "session" not in client.cookie_jar`

**Given** 浏览器无会话 Cookie
**When** 依次请求 `GET /equipments` 与 `GET /slots?equipment_id=E1&date=2026-11-05`
**Then** 两个响应均为 401
→ `assert [r.status_code for r in (a, b)] == [401, 401]`

**Given** 学生已登录且持有会话，管理员已登录
**When** 管理员 `POST /admin/users/<id>/reset-password`
**Then** 返回 303；学生旧会话的下一个请求返回 401；用 `LAB_DEFAULT_PASSWORD` 登录返回 303；`password_version` 恰好 +1
→ `assert (reset.status_code, old_next.status_code, new_login.status_code, pv_after - pv_before) == (303, 401, 303, 1)`

**Given** 应用已注册全部路由
**When** 枚举 `app.url_map`
**Then** 不存在含 `forgot` 或 `recover` 的路由；重置密码是唯一相关路由且 methods 为 `{POST}`
→ `assert {r.rule for r in app.url_map.iter_rules() if "forgot" in r.rule or "recover" in r.rule} == set() and app.url_map["/admin/users/<id>/reset-password"].methods == {"POST"}`

**Given** 两个账号设置同一明文密码 `P@ssw0rd-lab`
**When** 读取两行 `password_hash` 并扫描注册、登录、重置的全部响应体与 stdout
**Then** 两个哈希互不相等、均不等于明文，且明文在响应与日志中出现 0 次
→ `assert h1 != h2 and "P@ssw0rd-lab" not in (h1 + h2 + bodies + stdout)`

**备注**：重置权限是管理员能力，但密码版本号失效逻辑属于 ADR-004 的核心，必须与登录同批验证；否则 1.1 之后没人再碰 `pv`，回归没有落点。

### Story 1.2: 设备清单、开放时间维护与 slot 派生

As a 管理员 / 学生,
I want 维护每台设备的名称与每日开放时间，并让系统据此派生 30 分钟 slot,
So that 学生看到的每一个可约格都对应设备真实可用的时间，而不是管理员手工画的格子。

**元数据**：FR-2；ADR-002、ADR-005；前置：1.1；预估：M（0.75 天）；测试：`tests/test_equipment_catalog.py`

**Acceptance Criteria:**

**Given** 设备开放时间设为 `09:00–12:00`
**When** 调用 `build_grid()` 取该设备某一天的 slot
**Then** 恰好 6 个 slot，本地时刻序列为 `09:00, 09:30, 10:00, 10:30, 11:00, 11:30`
→ `assert [utc_to_local(s).strftime("%H:%M") for s in grid] == ["09:00","09:30","10:00","10:30","11:00","11:30"]`

**Given** 同一设备开放时间改为 `08:00–22:00`
**When** 再次调用 `build_grid()`
**Then** 恰好 28 个 slot，首个本地 `08:00`、末个本地 `21:30`
→ `assert len(grid) == 28 and first == "08:00" and last == "21:30"`

**Given** 设备已有预约占用 `15:00` 与 `15:30`
**When** 管理员把开放时间收窄为 `08:00–15:00`
**Then** 返回 409，`equipment` 行的 `open_end` 仍为改前的值，`occupancy` 行数不变
→ `assert resp.status_code == 409 and open_end_after == open_end_before and occupancy_count() == n_before`

**Given** 提交 `open_start = 09:15`
**When** 管理员保存开放时间
**Then** 返回 400，`equipment.open_start` 不变
→ `assert resp.status_code == 400 and open_start_after == "09:00"`

**Given** 提交 `open_start = 18:00`、`open_end = 09:00`
**When** 管理员保存开放时间
**Then** 返回 400，行不变
→ `assert resp.status_code == 400 and (open_start_after, open_end_after) == ("09:00", "12:00")`

**Given** 已登录学生
**When** `GET /equipments`
**Then** 返回 200，响应体包含该设备的 `name`、`open_start`、`open_end` 三个值；同一请求去掉 Cookie 后返回 401
→ `assert (authed.status_code, anon.status_code) == (200, 401) and all(v in authed.text for v in (name, "09:00", "12:00"))`

**Given** 设备开放时间为 `08:00–22:00`
**When** 检查派生出的 slot 集合
**Then** `07:30` 与 `22:00` 都不在集合内，集合最小值为本地 `08:00`
→ `assert "07:30" not in local_times and "22:00" not in local_times and min(local_times) == "08:00"`

### Story 1.3: 逐 slot 占用状态视图

As a 学生,
I want 选好设备与日期就看到每个 slot 当前是空闲、被别人占了、还是被锁定,
So that 我在提交之前就知道能不能约，而不是到场才发现。

**元数据**：FR-3；NFR-3；ADR-003、ADR-005；前置：1.1、1.2；预估：M（0.75 天）；测试：`tests/test_slot_view.py`

**Acceptance Criteria:**

**Given** 学生 A 已预约 `14:00`，学生 B 已预约 `14:30`
**When** A 刷新 `GET /slots?equipment_id=E1&date=D`
**Then** `14:00` 的 `cell.state == "booked_by_self"`，`14:30` 的 `cell.state == "booked_by_other"`
→ `assert (grid["14:00"].state, grid["14:30"].state) == ("booked_by_self", "booked_by_other")`

**Given** 当前本地时间为 `T`，`T` 之前的 slot 存在
**When** 取当天 grid
**Then** 所有 `slot_start < now` 的格 `state == "closed_past"`
→ `assert all(c.state == "closed_past" for c in grid if c.start < now_utc())`

**Given** 首个 slot 开始时间晚于 `now + 7 天`
**When** 取该格
**Then** `state == "closed_window"`
→ `assert grid[far_slot].state == "closed_window"`

**Given** 管理员已锁定 `16:00`
**When** 学生刷新页面
**Then** `16:00` 的 `state == "locked"`
→ `assert grid["16:00"].state == "locked"`

**Given** 任意一天的 grid
**When** 收集全部 `cell.state`
**Then** 取值集合是 `{free, booked_by_self, booked_by_other, locked, closed_past, closed_window}` 的子集，且模板输出的 `data-state` 属性数等于格数
→ `assert set(states) <= SIX_STATES and html.count('data-state=') == len(grid.cells)`

**Given** `GET /slots` 的响应
**When** 检查响应头与页面脚本
**Then** 无 `Upgrade` 头、无 `text/event-stream`、页面源码不含 `EventSource` 与 `setInterval`
→ `assert "Upgrade" not in resp.headers and "EventSource" not in resp.text and "setInterval" not in resp.text`

**Given** 用桩 grid 渲染 `_slot_grid.html`，其中 3 个格 `state="locked"`
**When** 统计渲染结果
**Then** `data-state="locked"` 出现 3 次，且未出现任何由模板自行推导出的其他状态值
→ `assert out.count('data-state="locked"') == 3 and out.count("data-state=") == 3`

**Given** 任意核心页面
**When** 检查 HTML 与 `static/app.css`
**Then** HTML 含 `<meta name="viewport"` 且 `width=device-width`；CSS 含 `@media` 与 `max-width: 480px`
→ `assert 'width=device-width' in html and "@media" in css and "max-width: 480px" in css`

**备注**：375/1280 的"无横向滚动"由人工截图取证（NFR-3 通过标准），pytest 只断言可静态判定的 viewport 与断点存在。

### Story 1.4: 单文件部署、一条命令启动与种子导入

As a 管理员 / 学生技术负责人,
I want 在一台新机器上执行 README 里的单条命令就得到可访问的服务，并导入设备与管理员账号,
So that 部署不需要装数据库、不依赖外网，也不会因为种子文件出错留下半套数据。

**元数据**：FR-2（种子导入）；NFR-2；ADR-002；前置：1.2；预估：S（0.5 天）；测试：`tests/test_ops_startup.py`

**Acceptance Criteria:**

**Given** 干净目录、已装运行时、无外网出口
**When** 执行 README 中的单条启动命令
**Then** 进程监听 `LAB_PORT`，`GET /health` 返回 200
→ `assert wait_for_port(port, 10) and requests.get(f"{base}/health").status_code == 200`

**Given** 服务运行并写入过预约
**When** 列出数据目录
**Then** 目录内 `.db` 文件恰好 1 个（`-wal` / `-shm` 不计入）
→ `assert len([p for p in data_dir.iterdir() if p.suffix == ".db"]) == 1`

**Given** 已完成 5 条预约的服务已停止
**When** 把该 `.db` 复制到另一目录并以 `LAB_DB_PATH` 指向它重启
**Then** `SELECT COUNT(*) FROM occupancy` 与原库相等
→ `assert count_occupancy(new_db) == count_occupancy(old_db) == 5`

**Given** 环境变量缺 `LAB_SECRET_KEY`
**When** 启动服务
**Then** 进程以非 0 退出码结束，且端口未被监听
→ `assert proc.returncode != 0 and not port_in_use(port)`

**Given** `seed/equipment.csv` 有 3 行设备
**When** 连续执行两次 `python -m src.seed`
**Then** 两次退出码均为 0，`equipment` 行数为 3（按 `equipment_id` upsert，不重复插入）
→ `assert (r1.returncode, r2.returncode, count_equipment()) == (0, 0, 3)`

**Given** `seed/equipment.csv` 第 3 行缺 `open_start`
**When** 执行 `python -m src.seed`
**Then** 退出码非 0，stdout 含行号 `3`，`equipment` 行数为 0（整文件回滚）
→ `assert proc.returncode != 0 and "3" in proc.stdout and count_equipment() == 0`

**Given** 环境变量 `LAB_ADMIN_USER` / `LAB_ADMIN_PASSWORD` 已设置
**When** 执行 `python -m src.seed`
**Then** `role='admin'` 的用户恰好 1 行，且该账号可成功登录
→ `assert count_users(role="admin") == 1 and login(admin_user, admin_pw).status_code == 303`

## Epic 2: 预约与并发

**目标**：一次提交完整占住 1–8 个连续 slot，或者一行都不写；两个人在同一秒点同一个 slot 时，数据库而不是代码次序决定谁赢；改单只换集合，不换规则。

**覆盖**：FR-4、FR-5、FR-6（并交付 FR-7 的规则内核）；NFR-1。
**约束**：ADR-001（唯一约束裁决 + `BEGIN IMMEDIATE`）、ADR-003（表单多值提交 + 303）、ADR-005（UTC 瞬时比较）。

### Story 2.1: 提交连续 slot 预约

As a 学生,
I want 一次勾选同一设备连续的 1–8 个 slot 并提交,
So that 我占住的是一整段时间，而不是逐个 slot 反复提交、中途被人插队。

**元数据**：FR-4；ADR-001、ADR-003、ADR-005；前置：1.2、1.3；预估：M（0.75 天）；测试：`tests/test_create_booking.py`

**Acceptance Criteria:**

**Given** 设备开放 `08:00–22:00`，`14:00` 起 8 个连续 slot 全空闲
**When** `POST /bookings` 提交这 8 个 `slot` 值
**Then** 返回 303；`booking` 新增 1 行；`occupancy` 新增 8 行；这 8 行的 `booking_id` 只有 1 个不同值
→ `assert resp.status_code == 303 and n_booking() == 1 and n_occ() == 8 and len({r.booking_id for r in occ_rows}) == 1`

**Given** 同样 8 个 slot 再追加第 9 个连续 slot
**When** `POST /bookings`
**Then** 返回 400，`booking` 与 `occupancy` 新增均为 0
→ `assert resp.status_code == 400 and (n_booking(), n_occ()) == (before, before)`

**Given** 提交 `14:00` 与 `15:00`（间隔 60 分钟，不连续）
**When** `POST /bookings`
**Then** 返回 400，写入 0 行
→ `assert resp.status_code == 400 and n_occ_delta() == 0`

**Given** 提交本地 `14:15`（非 `:00/:30` 对齐）
**When** `POST /bookings`
**Then** 返回 400，写入 0 行
→ `assert resp.status_code == 400 and n_occ_delta() == 0`

**Given** 首个 slot 已经开始
**When** `POST /bookings`
**Then** 返回 400，写入 0 行
→ `assert resp.status_code == 400 and n_occ_delta() == 0`

**Given** 首个 slot 开始时间为 `now + 7 天 + 30 分钟`
**When** `POST /bookings`
**Then** 返回 400；同一用例改为 `now + 7 天 - 30 分钟` 时返回 303
→ `assert (far.status_code, near.status_code) == (400, 303)`

**Given** 表单 `equipment_id` 与所提交 slot 所属设备不一致，或 `equipment_id` 在库中不存在
**When** `POST /bookings`
**Then** 返回 400，写入 0 行
→ `assert resp.status_code == 400 and n_occ_delta() == 0`

**Given** 未登录用户，或已登录但表单缺 `csrf_token`
**When** `POST /bookings`
**Then** 分别返回 401 与 400，写入 0 行
→ `assert (anon.status_code, no_csrf.status_code) == (401, 400) and n_occ_delta() == 0`

**Given** 一次成功的 8-slot 提交
**When** 同一学生随后 `GET /slots` 该设备该日
**Then** 这 8 个格的 `state` 全部为 `booked_by_self`
→ `assert {grid[s].state for s in submitted} == {"booked_by_self"}`

### Story 2.2: 冲突整单原子拒绝与并发裁决

As a 学生 / 学生技术负责人,
I want 冲突时整单被拒并告诉我哪几个 slot 没了，两个请求同时到达时只有一个能成功,
So that 我不必担心"部分占了、部分没占"，也不必相信任何进程内的锁。

**元数据**：FR-5；NFR-1；ADR-001（§5.4 L1–L5）；前置：2.1；预估：M（1 天）；测试：`tests/test_booking_concurrency.py`

**Acceptance Criteria:**

**Given** 新建库并应用迁移
**When** 读取 `PRAGMA index_list('occupancy')` 与 `PRAGMA index_info('sqlite_autoindex_occupancy_1')`
**Then** 唯一索引恰好 1 行且 `unique=1`、`origin='u'`、`partial=0`，列序为 `(equipment_id, slot_start)`
→ `assert (idx.unique, idx.origin, idx.partial) == (1, "u", 0) and [c.name for c in cols] == ["equipment_id", "slot_start"]`

**Given** 4 个连续 slot 中第 3 个已被他人占用
**When** 提交整组 4 个
**Then** 返回 409；响应体含该 `slot_start` 与该 `equipment_id`；`booking` 与 `occupancy` 新增均为 0
→ `assert resp.status_code == 409 and conflict_slot in resp.text and (n_booking_delta(), n_occ_delta()) == (0, 0)`

**Given** 同一学生已成功预约一组 slot
**When** 原样再次提交同一组
**Then** 第二次返回 409，该 `booking_id` 的 `occupancy` 行数仍为原值
→ `assert second.status_code == 409 and n_occ_for(booking_id) == n_before`

**Given** 每个 slot 起两个独立进程（非同一连接），`Barrier(2)` 后同时 POST 同一 key
**When** 重复 100 轮
**Then** 每轮 `{303: 1, 409: 1, 5xx: 0}`，`SQLITE_BUSY` 计数为 0，新连接 `COUNT(*) == 1`，两侧 `BEGIN IMMEDIATE` 持锁区间相交
→ `assert all(r.ok and r.claimed for r in rounds) and rounds_ok == 100`

**Given** 同一 key 起 10 个并发请求
**When** 重复 20 轮
**Then** 每轮 303 恰 1 个、409 恰 9 个、5xx 为 0
→ `assert all(r == (1, 9, 0) for r in codes) and len(codes) == 20`

**Given** 全部并发轮次结束后
**When** 执行 `SELECT equipment_id, slot_start, COUNT(*) FROM occupancy GROUP BY 1,2 HAVING COUNT(*) > 1`
**Then** 结果为空集
→ `assert conn.execute(dup_sql).fetchall() == []`

**Given** 把预检短路为恒返回空（约束保留）
**When** 重跑 100 轮
**Then** 仍全部满足"1 成功 + 1 冲突"（C2）
→ `assert mutation_c2_rounds_ok == 100`

**Given** 同时删除唯一约束并把预检短路
**When** 重跑 100 轮
**Then** 出现恰好 2 次成功的轮次（C3），证明真正裁决者是约束
→ `assert mutation_c3_two_success_rounds > 0`

**Given** 任意 409 响应
**When** 检查响应体与状态码
**Then** 不含 `Traceback`，且状态码不落在 5xx
→ `assert "Traceback" not in resp.text and resp.status_code < 500`

**备注**：L4 的 C2/C3 是这套测试的"真值表"，缺了它们，一个换成"先查后写"的实现也能全绿。C3 必须同时删约束与短路，只删其一会得到假阴性（architecture §5.4）。

### Story 2.3: 我的预约与取消

As a 学生,
I want 在一个页面看完自己的预约并在允许窗口内整单取消,
So that 计划变化时 slot 立刻回到池子里，而不是变成一条没人敢动的死记录。

**元数据**：FR-6；ADR-001（D5：取消即删行）、ADR-005；前置：2.1；预估：S（0.5 天）；测试：`tests/test_cancel_booking.py`

**Acceptance Criteria:**

**Given** 学生 A 有 2 条预约、学生 B 有 1 条预约
**When** A 请求 `GET /bookings/mine`
**Then** 返回 200，页面出现的 `booking_id` 集合恰好等于 A 的 2 个
→ `assert set(rendered_booking_ids(resp)) == set(a_booking_ids) and len(a_booking_ids) == 2`

**Given** 预约首个 slot 距现在 2 小时 01 分
**When** `POST /bookings/<id>/cancel`
**Then** 返回 303；该 `booking` 行数为 0；该 `booking_id` 的 `occupancy` 行数为 0
→ `assert resp.status_code == 303 and n_booking(id) == 0 and n_occ_for(id) == 0`

**Given** 预约首个 slot 距现在 1 小时 59 分
**When** `POST /bookings/<id>/cancel`
**Then** 返回 400，`booking` 与 `occupancy` 行数均不变
→ `assert resp.status_code == 400 and (n_booking(id), n_occ_for(id)) == (1, 3)`

**Given** 学生 A 持有会话，预约属于学生 B
**When** A `POST /bookings/<b_id>/cancel`
**Then** 返回 403，B 的 `booking` 与 `occupancy` 行数不变
→ `assert resp.status_code == 403 and (n_booking(b_id), n_occ_for(b_id)) == (1, 3)`

**Given** 学生 A 刚取消成功的 3 个 slot
**When** 学生 C 刷新该日 grid 并提交其中 1 个 slot
**Then** 三个格 `state == "free"`，C 的提交返回 303
→ `assert {grid[s].state for s in freed} == {"free"} and c_submit.status_code == 303`

**Given** 同一个 `booking_id` 已取消一次
**When** 再次 `POST /bookings/<id>/cancel`
**Then** 返回 404
→ `assert second_cancel.status_code == 404`

**Given** 取消成功
**When** 查询 `audit_log` 该 `target_id` 的最新一行
**Then** `action == "booking_cancel"`，`after_json["slots"]` 等于被取消的 3 个 `slot_start`（排序后）
→ `assert row.action == "booking_cancel" and json.loads(row.after_json)["slots"] == sorted(slots)`

### Story 2.4: 连续多 slot 选择与改单边界

As a 学生 / 管理员,
I want 系统用同一套规则判断"这组 slot 合不合法"——无论是我新提交，还是管理员把我的预约改到另一组,
So that 我不会遇到"前端说可以、提交说不行"，也不会在改单时撞上自己旧记录造成的 409。

**元数据**：FR-4、FR-7（规则面）；ADR-001、ADR-005；前置：2.1；预估：M（1 天）；测试：`tests/test_slot_rules.py`

**Acceptance Criteria:**

**Given** 一个参数化用例矩阵：连续合法 / 中断 / 9 个 / 非对齐 / 超出开放窗口 / 首 slot 超 7 天 / 跨设备
**When** 分别以 `mode="create"` 与 `mode="edit"` 调用 `app.slot_rules.validate()`
**Then** 同一个用例在两种 mode 下的结果码完全一致（合法→通过，非法→`Validation`），除"2 小时截止"只对 edit 生效
→ `assert [(c, m, outcome(case, m)) for c in cases for m in ("create","edit")] == EXPECTED_MATRIX`

**Given** 已有预约占 `14:00–15:00`（3 个 slot，含 `14:30`）
**When** 管理员把该预约改到 `14:30–15:30`（与自身旧集合有交集）
**Then** 返回 303（不是 409）；该 `booking_id` 的 `occupancy` 恰为 3 行新 slot；`booking_id` 不变
→ `assert resp.status_code == 303 and occ_set(booking_id) == new_set and len(new_set) == 3`

**Given** 目标集合中包含被他人预约或被锁定的 slot
**When** 执行改单
**Then** 返回 409；原 `occupancy` 集合按 `(equipment_id, slot_start, kind, booking_id)` 排序后逐行相等
→ `assert resp.status_code == 409 and sorted_rows(occ_before) == sorted_rows(occ_after)`

**Given** 目标集合为 9 个 slot，或两个 slot 之间隔了 30 分钟以上
**When** 执行改单
**Then** 返回 400（不是 409），原集合不变
→ `assert (nine.status_code, gap.status_code) == (400, 400) and sorted_rows(occ_before) == sorted_rows(occ_after)`

**Given** 预约首个 slot 距现在 1 小时 59 分
**When** 执行改单
**Then** 返回 400，原集合不变
→ `assert resp.status_code == 400 and sorted_rows(occ_before) == sorted_rows(occ_after)`

**Given** 一次成功改单
**When** 统计该 `equipment_id` 的 key 分布
**Then** `GROUP BY equipment_id, slot_start HAVING COUNT(*) > 1` 为空，且该 `booking_id` 行数等于新集合大小
→ `assert conn.execute(dup_sql).fetchall() == [] and n_occ_for(booking_id) == len(new_set)`

**Given** 创建路径与改单路径各调用一次校验
**When** 用 spy 包裹 `slot_rules.validate`
**Then** 两次调用的 `mode` 分别为 `"create"` 与 `"edit"`，且没有其他模块自行实现连续性判断
→ `assert [c.kwargs["mode"] for c in spy.call_args_list] == ["create", "edit"]`

**Given** 一次成功改单前后的 `booking` 行
**When** 比较两行
**Then** `id` 相同，`updated_at` 的字典序严格大于改单前的值
→ `assert after.id == before.id and after.updated_at > before.updated_at`

#### 为什么 2.4 值得独立成 Story

1. **它有一个只在 edit 场景出现的失败模式：与自己的唯一键相撞。** 学生把 `14:00–15:00` 改到 `14:30–15:30` 时，新旧集合有交集。若实现成"先插新行、再删旧行"，`uq_occupancy_slot` 会在自己的旧行上抛 `IntegrityError`，用户看到"你占用了自己的 slot"这种荒谬 409。Story 2.1 的用例永远测不到它——2.1 的所有前置都是"目标集合与库内既有占用不相交"。
2. **它的原子性断言对象不同。** 创建失败断言的是"新增 0 行"（2.1/2.2 已覆盖）；改单失败断言的是"原集合逐行不变"（architecture §5.4 L5 明确单列一条）。后者要求"先删后插全部在一个事务内、失败整单回滚"，是 `write_tx()` 边界最容易写错的地方。
3. **它防止规则分叉，而分叉已经写在 ADR-003 的否决理由里。** 若把 edit 分支留给 3.2 再写，2.1 之后到 3.2 之间会出现一段"只有 create 分支被执行"的窗口，edit 分支要么是死代码、要么被顺手复制成第二份校验——正是 ADR-003 §7.3 D 要挡的"前端允许、后端 400"的同构问题。
4. **尺寸理由。** 5 条形状规则 × 2 个 mode 的边界矩阵，加上"有交集 / 无交集 / 部分保留"三组写入路径，本身就是一天。塞进 2.1 会把 2.1 从 M 推成 L，违反"单 Story ≤ 1 天"。
5. **它在 E2 交付、在 E3 消费。** 2.4 只交付 `slot_rules` 的 edit 能力与服务层替换语义，用测试夹具直接构造预约；3.2 才接路由与表单。这样 3.2 只剩 S 的厚度，也不产生"3.2 才能测 2.4"的倒挂。

## Epic 3: 管理员运维

**目标**：管理员周一早上打开本周视图，10 分钟内看清冲突、锁定与改单，处理例外、导出存档、查得到谁在什么时候改了什么。

**覆盖**：FR-7、FR-8、FR-1（重置的运维视角）；NFR-1、NFR-3、NFR-4。
**约束**：ADR-001（五条写路径共用唯一约束）、ADR-002、ADR-003（周视图复用 `_slot_grid.html`）、ADR-005（自然周半开区间）。

### Story 3.1: 管理员本周视图与按学号检索

As a 管理员,
I want 打开就是本周、异常（冲突/锁定）在格子上直接可见，并能按学号找到某个学生的预约,
So that 我不必导出 Excel 再肉眼比对，也不必在群里问"这是谁约的"。

**元数据**：FR-7、FR-3；NFR-3；ADR-003、ADR-005；前置：1.3、2.1；预估：M（0.75 天）；测试：`tests/test_admin_week_view.py`

**Acceptance Criteria:**

**Given** 周一 `00:00`（Asia/Shanghai）有一个 slot，上一周周日 `23:30` 也有一个 slot
**When** 分别请求 `GET /admin/week?week=W-1` 与 `week=W`
**Then** 两个页面出现的 `booking_id` 集合不相交，周一 `00:00` 的预约只出现在 `W`
→ `assert set(ids(prev_week)).isdisjoint(ids(this_week)) and mon_booking_id in ids(this_week)`

**Given** 本周有 7 条 `kind='booking'` 的占用行
**When** `GET /admin/week`
**Then** 页面渲染的格数为该周内落在开放时间内的 slot 数，且 `data-booking-id` 去重后为 7 个
→ `assert len(set(re.findall(r'data-booking-id="([^"]+)"', resp.text))) == 7`

**Given** 管理员已锁定 `16:00`，学生 `14:00` 的预约与另一设备存在时间重叠提示
**When** 打开本周视图
**Then** `16:00` 格 `data-state="locked"`，异常标记元素数量 ≥ 1 且含该 `slot_start`
→ `assert 'data-state="locked"' in resp.text and conflict_marker_count(resp) >= 1`

**Given** 学生 `2025001` 有 2 条预约
**When** `GET /admin/users?student_no=2025001`
**Then** 返回 200，列表中的 `booking_id` 集合等于该学生的 2 个
→ `assert resp.status_code == 200 and set(ids(resp)) == set(student_booking_ids)`

**Given** 学号 `9999999` 不存在
**When** 同一检索接口被调用
**Then** 返回 200 且列表为空，状态码不在 5xx
→ `assert resp.status_code == 200 and ids(resp) == []`

**Given** 已登录学生（`role='student'`）与未登录用户
**When** 请求 `GET /admin/week`
**Then** 分别返回 403 与 401
→ `assert (student.status_code, anon.status_code) == (403, 401)`

**Given** 本周视图与学生日视图的渲染
**When** 检查两者 HTML 的格结构
**Then** 两者的 `data-state` 取值集合与 `_slot_grid.html` 渲染结果一致（同一模板）
→ `assert extract_cells(week_html) == extract_cells(day_html)`

### Story 3.2: 管理员改单

As a 管理员,
I want 把某条预约整体改到另一台设备或另一组连续 slot,
So that 学生私下来换时段时，系统里留下的是唯一正确的那条记录，而不是两张都像真的表。

**元数据**：FR-7；ADR-001、ADR-003；前置：2.4、3.1；预估：S（0.5 天）；测试：`tests/test_admin_edit_booking.py`

**Acceptance Criteria:**

**Given** 目标 `15:00` 已被他人占用
**When** 管理员 `POST /admin/bookings/<id>/edit`
**Then** 返回 409；该 `booking_id` 的 `occupancy` 排序后逐行等于改前；`booking_id` 不变
→ `assert resp.status_code == 409 and sorted_rows(before) == sorted_rows(after) and booking_id_after == booking_id_before`

**Given** 目标集合合法且空闲
**When** 管理员提交改单
**Then** 返回 303；`audit_log` 新增 1 行且 `action == "booking_edit"`，`before_json["slots"]` 与 `after_json["slots"]` 分别等于改前/改后集合
→ `assert resp.status_code == 303 and row.action == "booking_edit" and json.loads(row.after_json)["slots"] == sorted(new_set)`

**Given** 一次成功改单
**When** 统计全库 key 分布
**Then** 无重复 `(equipment_id, slot_start)`，且该 `booking_id` 行数等于新集合大小
→ `assert conn.execute(dup_sql).fetchall() == [] and n_occ_for(booking_id) == len(new_set)`

**Given** 改单把 `14:00` 改为 `16:00`（同设备）
**When** 学生随后刷新日视图
**Then** `14:00` 格 `state == "free"`，`16:00` 格 `state == "booked_by_other"`
→ `assert (grid["14:00"].state, grid["16:00"].state) == ("free", "booked_by_other")`

**Given** 已登录学生
**When** 该学生 `POST /admin/bookings/<id>/edit`
**Then** 返回 403，原 `occupancy` 不变
→ `assert resp.status_code == 403 and sorted_rows(before) == sorted_rows(after)`

### Story 3.3: 锁定与解锁 slot

As a 管理员,
I want 把某台设备的某些 slot 直接锁住或解锁,
So that 设备维修、校准这类"不能约但不是预约"的状态不会被学生当成空闲格。

**元数据**：FR-7；ADR-001（D1 锁定行共用键空间、D5 共用写入路径）、ADR-003；前置：2.2、3.1；预估：S（0.5 天）；测试：`tests/test_admin_lock.py`

**Acceptance Criteria:**

**Given** `10:00` 空闲
**When** 管理员 `POST /admin/equipments/<id>/lock`
**Then** 返回 303；该 key 的 `occupancy` 恰 1 行，`kind == "lock"` 且 `booking_id IS NULL`
→ `assert resp.status_code == 303 and len(rows) == 1 and rows[0].kind == "lock" and rows[0].booking_id is None`

**Given** `10:00` 已锁定
**When** 学生刷新页面并 `POST /bookings` 提交该 slot
**Then** 该格 `state == "locked"`，提交返回 409，`occupancy` 行数不变
→ `assert grid["10:00"].state == "locked" and submit.status_code == 409 and n_occ() == n_before`

**Given** `10:00` 已有学生预约
**When** 管理员尝试锁定
**Then** 返回 409，原预约的 `occupancy` 行数与该行 `kind` 均不变
→ `assert resp.status_code == 409 and n_occ_for(booking_id) == 1 and occ_kind(booking_id) == "booking"`

**Given** `10:00` 已锁定且无人预约
**When** 管理员 `POST /admin/equipments/<id>/unlock`
**Then** 返回 303；该 key 行数为 0；学生视图 `state == "free"`；学生提交返回 303
→ `assert resp.status_code == 303 and n_occ_key() == 0 and grid["10:00"].state == "free" and submit.status_code == 303`

**Given** 一次锁定与一次解锁
**When** 查询 `audit_log`
**Then** 两条记录 `action` 分别为 `lock`、`unlock`，`target_type == "equipment"`，`after_json["slots"]` 均包含该 `slot_start`
→ `assert [(r.action, r.target_type) for r in rows] == [("lock","equipment"), ("unlock","equipment")] and all(slot in json.loads(r.after_json)["slots"] for r in rows)`

**Given** 本周存在 1 条锁定行与 2 条预约行
**When** 管理员导出该周 CSV
**Then** CSV 数据行数为 2，锁定行不出现在导出中
→ `assert len(csv_data_rows) == 2 and lock_slot_local not in [r["slot 开始"] for r in csv_rows]`

### Story 3.4: 自然周 CSV 导出与追加式操作日志

As a 管理员,
I want 导出一周的预约清单为 CSV，并查看谁在什么时候做了什么,
So that 周表能作为唯一的人工归档，出问题时也追得到源头。

**元数据**：FR-8；NFR-4；ADR-002、ADR-005；前置：3.1、3.2、3.3；预估：M（1 天）；测试：`tests/test_export_audit.py`

**Acceptance Criteria:**

**Given** 指定自然周内有 5 条 `kind='booking'` 的占用行
**When** `GET /admin/export?week=W`
**Then** 响应体以 `b"\xef\xbb\xbf"` 开头，按 `\n` 切分后共 6 行（表头 + 5）
→ `assert body.startswith(b"\xef\xbb\xbf") and len([l for l in body.decode("utf-8-sig").splitlines() if l]) == 6`

**Given** 一条 3-slot 预约与一条 1-slot 预约
**When** 导出该周
**Then** 表头精确等于 `设备,slot 开始,slot 结束,学号,booking_id,状态`；3-slot 预约占 3 行且 `booking_id` 相同
→ `assert header == "设备,slot 开始,slot 结束,学号,booking_id,状态" and len([r for r in rows if r["booking_id"] == bid]) == 3`

**Given** 一条预约已取消
**When** 导出取消前所在的周
**Then** 该 `booking_id` 在 CSV 中出现 0 次
→ `assert cancelled_bid not in {r["booking_id"] for r in rows}`

**Given** 周一 `00:00`（本地）的 slot 与上一周周日 `23:30` 的 slot
**When** 分别导出 `W` 与 `W-1`
**Then** 周一 `00:00` 只出现在 `W` 的 CSV 中，`W-1` 行数不含它
→ `assert mon_slot in rows(W) and mon_slot not in rows(W-1)`

**Given** 依次完成预约、取消、改单、锁定、重置密码五类动作
**When** `GET /admin/audit`
**Then** 五类 `action` 各有 ≥ 1 条，且每条 `actor_id`、`target_type`、`target_id`、`created_at` 均非空，`before_json` 或 `after_json` 至少一个非空
→ `assert {"booking_create","booking_cancel","booking_edit","lock","password_reset"} <= {r.action for r in rows} and all(r.actor_id and (r.before_json or r.after_json) for r in rows)`

**Given** 日志页只读
**When** 对 `/admin/audit` 发送 `PUT` 与 `DELETE`
**Then** 两者均返回 405
→ `assert (put.status_code, delete.status_code) == (405, 405)`

**Given** 导出文件与日志页的完整响应体
**When** 检索 `LAB_DEFAULT_PASSWORD` 的值与任一用户 `password_hash`
**Then** 命中数均为 0
→ `assert plain_pw not in body and all(h not in body for h in hashes)`

**Given** 一次重置密码动作
**When** 读取该条审计记录
**Then** `before_json` 与 `after_json` 只含 `password_version` 键，不含任何密码值
→ `assert set(json.loads(r.before_json)) == {"password_version"} and set(json.loads(r.after_json)) == {"password_version"}`

## 跨 Story 依赖图

```text
1.1 ──> 1.2 ──> 1.3 ──> 2.1 ──> 2.2 ──> 3.3
          │       │       ├────> 2.3        │
          │       │       └────> 2.4 ──> 3.2 ┤
          └──> 1.4                            └──> 3.4
                     1.3 ─────────────────────> 3.1 ──> 3.2 / 3.3
```

- 无倒挂：每条边的箭头方向都是小号 → 大号。
- 3.4 的测试直接构造库内数据，因此即使 3.2/3.3 的 UI 有调整，导出契约的断言不受影响。

## PRD §11 回写记录（2026-11-05 已同步）

下表 8 项已于 2026-11-05 全部回写 `PRD.md` §11（FR-2 至 FR-8 行、NFR 测试索引、抽查示例）。本节保留作变更记录：改了什么、为什么改，可在评审时逐行倒查。

| # | PRD §11 当前写法 | 应改为 | 原因 |
| --- | --- | --- | --- |
| 1 | FR-2 → Story `1.2、1.4`；Test `tests/test_equipment_catalog.py` | FR-2 → Story `1.2`；Test `tests/test_equipment_catalog.py`；ADR 列补 `ADR-005` | 1.4 改为 NFR-2 的部署与种子故事，不再承载 FR-2；开放时间收窄的 409 并入 1.2 |
| 2 | FR-3 → Story `1.3`；Test `tests/test_slot_view.py` | FR-3 → Story `1.3、3.1`；Test `tests/test_slot_view.py`、`tests/test_admin_week_view.py` | 周视图复用 `_slot_grid.html`，同一状态生产者出现第二个消费者 |
| 3 | FR-4 → Story `2.1`；Test `tests/test_create_booking.py` | FR-4 → Story `2.1、2.4`；Test `tests/test_create_booking.py`、`tests/test_slot_rules.py` | 新增 2.4，形状规则以 `mode=create/edit` 单点实现 |
| 4 | FR-5 → Story `2.2`；Test `tests/test_booking_concurrency.py` | FR-5 → Story `2.2、3.3`；Test 追加 `tests/test_admin_lock.py` | 锁定与学生预约共用 `(equipment_id, slot_start)`，锁定冲突也是 FR-5 的拒绝语义 |
| 5 | FR-7 → Story `3.1、3.2`；Test `tests/test_admin_edit_lock.py` | FR-7 → Story `2.4、3.1、3.2、3.3`；Test `tests/test_slot_rules.py`、`tests/test_admin_week_view.py`、`tests/test_admin_edit_booking.py`、`tests/test_admin_lock.py` | `test_admin_edit_lock.py` 一拆三：周视图/检索、改单、锁定各自独立可测；规则内核前移到 2.4 |
| 6 | FR-8 → Story `3.3、3.4`；Test `tests/test_export_audit.py` | FR-8 → Story `3.4`；Test `tests/test_export_audit.py` | 3.3 改为锁定/解锁；导出与日志合并到 3.4 一个故事，避免同一测试文件跨两个 Story |
| 7 | NFR-3 → `tests/test_responsive_smoke.py` + 375/1280 人工截图 | NFR-3 → `tests/test_slot_view.py`（viewport + 断点断言）+ `tests/test_admin_week_view.py`；人工截图保留 | 无独立 `test_responsive_smoke.py`；可自动断言的部分落在 1.3 与 3.1 |
| 8 | NFR-4 → `tests/test_auth_password_hash.py` | NFR-4 → `tests/test_auth_login.py`（哈希与明文扫描）+ `tests/test_export_audit.py`（导出/日志脱敏） | 原计划文件名未落地；哈希断言与登录同批验证才有回归价值 |

另有两处非表内差异，建议一并写入 PRD §11 正文：

- **FR-1 的 Story 归属**：重置密码留在 1.1（与 `password_version` 失效同批验证），不单独占 E3 名额；PRD 表内 FR-1 行无需改动，但正文"管理员重置"不再作为 3.x 的独立交付项。
- **抽查示例**：`FR-7 → ADR-002/003 → Story 3.1/3.2 → tests/test_admin_edit_lock.py` 需改为 `FR-7 → ADR-001/002/003 → Story 2.4/3.1/3.2/3.3 → tests/test_slot_rules.py、test_admin_week_view.py、test_admin_edit_booking.py、test_admin_lock.py`；`FR-5 → Story 2.2 → tests/test_booking_concurrency.py` 保持有效。
