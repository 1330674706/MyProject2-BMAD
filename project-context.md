<!-- bmad:context -->
<!-- Verified 2026-11-09 against 2d80a4f; working tree has uncommitted edits to epics.md and decision-log.md. Managed by bmad-project-context: edits inside this block are replaced on refresh. Keep local additions outside the markers. -->

## 实验室设备预约系统（MyProject2）

学生与管理员预约实验室设备 30 分钟 slot 的单机 Web 应用。Python 3.12 + Flask 3 + SQLite + Jinja2 + pytest，单进程、单文件库 `data/lab.db`、服务端渲染。规划与构建契约在 `_bmad-output/planning-artifacts/`：`PRD.md`（FR/NFR、§11 溯源）、`architecture.md`（ADR-001..005、§16 禁止表）、`epics.md`（3 Epic / 12 Story）。架构是构建契约；文档冲突时以 `architecture.md` 为准，并按 R7 同步 §11。

## 硬规则（违反即退回；不得以"为了跑通/更简单"为由豁免）

- R1 业务规则只在服务层 `src/app/` 实现：slot 形状校验只在 `src/app/slot_rules.py`，slot 状态只在 `src/app/slot_service.py`；`src/web/` 只解析表单并映射状态码，`src/templates/` 只渲染传入的视图对象——路由或模板出现任何校验、时间比较、冲突判断分支即违规。
- R2 所有写操作必须经 `src/data/tx.py` 的 `write_tx()`（`BEGIN IMMEDIATE`）执行；仓储函数不得 `BEGIN`/`COMMIT`/`ROLLBACK`，不得用 `with conn:` 自开事务，也不得在事务外写库。
- R3 冲突只由 `uq_occupancy_slot (equipment_id, slot_start)` 唯一约束裁决：禁止事务外 check-then-write；事务内预检只允许生成 409 文案，不得作为放行/拒绝依据；禁止 `INSERT OR IGNORE`、`OR REPLACE`、`ON CONFLICT DO NOTHING`。
- R4 时刻一律以 20 字符 UTC 文本 `YYYY-MM-DDTHH:MM:SSZ` 存库，`Asia/Shanghai` 转换只在 `src/core/timeutil.py`；例外仅 `equipment.open_start/open_end`（本地 `HH:MM` 墙钟）。其他文件出现 `datetime.now(`、手工拼接时间或 `+08:00` 字符串即违规。
- R5 每个 Story 先写能失败的测试再写实现：测试文件取 `epics.md` 该 Story 的 `tests/test_*.py`，AC 的 `→ assert ...` 必须逐条落成断言；先实现后补测试、或测试从未红过即违规。
- R6 Story 状态只能由人改：AI 不得把 `sprint-status.yaml` 的 `development_status`（生成后）中任何 story 置为 `done`（`epic-*` 同理），最多置 `review`；也不得在未获人工确认时宣称某 Story 已完成。
- R7 改动 `PRD.md`、`architecture.md`、`epics.md` 任一处，必须在同一改动中同步 `PRD.md` §11 溯源表（FR → ADR → Story → Test）；漏同步即视为文档漂移，改动不成立。
- R8 新增任何运行期依赖前，先在 `architecture.md` 补一条 ADR（决定、被否决备选、回指 FR/NFR），且不得触碰 §16 禁止表（React/任何 SPA、MySQL/PostgreSQL、Redis、消息队列、WebSocket/SSE）；先改约束，再写代码。

## 关键落点

- 入口：`python -m src.serve`（`src/serve.py`）；应用工厂 `app.py`；种子 `python -m src.seed`。
- 唯一写入口：`src/app/booking_service.py` 的四个用例（创建/改单/锁定/取消）→ `src/data/occupancy_repo.py` 的 `insert_occupancy()` / `delete_occupancy()`；其他模块直接 INSERT/DELETE `occupancy` 即越界。
- 状态码唯一映射点：`src/web/errors.py`；脱敏唯一入口：`src/core/redact.py`（字段白名单，不用黑名单过滤 `password`）。
- 约束原文：`architecture.md` §4 不变量、§5 ADR-001、§9 ADR-005、§11 一致性约定、§16 禁止表；Story 与 AC：`epics.md`；溯源：`PRD.md` §11。
- 上列 `src/` 路径来自 `architecture.md` §13，代码尚未落地；首次 refresh 以实际文件为准。

## 运行与验证

- 启动：`python -m src.serve`，单进程 `threaded=True`；`GET /health` 返回 200 是"服务可用"的唯一判据。
- 测试：`pytest -q`；并发证据另跑 `python -m tests.concurrency_demo`，输出归档到 `evidence/`。
- 必需环境变量：`LAB_SECRET_KEY`（≥32 字节）、`LAB_DEFAULT_PASSWORD`（≥8 位）；缺失必须启动失败，不得加默认值或回退。
- 版本：Python 3.12.x、Flask 3.1.3、Jinja2 3.1.6、Werkzeug 3.1.3、itsdangerous 2.2.0、pytest 8.4.2、SQLite ≥3.24、tzdata ≥2024.1（Windows）；依赖只从 `requirements.txt` 装。
- 代码落地前，以上命令是 `architecture.md` §15 的契约而非已验证事实。

## 与默认不同的约定

- slot 是派生量：不建 `slot` 表，只存被占用的 `occupancy` 行；`booking` 不存时间段，取消 = 删除 `booking` 行（`ON DELETE CASCADE` 带走占用行）。
- 审计与业务写同一事务提交；`audit_log` 只追加，无 UPDATE/DELETE、无编辑路由。
- `409` 响应体必须列出冲突的 `equipment_id` 与 `slot_start`。
- 学生只能取消自己的 booking（`owner_id` 不符 → 403），不能改约；管理员走独立 `/admin/*`，不在学生路由里加角色 `if`。
- `@login_required` / `@admin_required` 是路由第一行；权限判断不进模板；角色与 `password_version` 每请求回库核对。
- SQL 只出现在 `src/data/`，一律参数化；`data` 不得 import `web`/`app`；每请求独立连接（`flask.g`），禁止模块级复用连接。
- 时间列禁止 `DEFAULT CURRENT_TIMESTAMP` / `datetime('now')`，时间戳由应用传参；自然周用半开区间 `>= ? AND < ?`，不用 `BETWEEN`。
- CSV 固定 `utf-8-sig`、六列顺序、一行一个 slot；只导 `kind='booking'`；排除密码、token、内部自增 id。
- 运行期依赖只限 §12 清单：不引入 ORM、前端工具链/Node、Docker、缓存或任务队列客户端。

## 已知陷阱

- 改单"先插后删"会撞上自己的旧 `occupancy` 行抛 `IntegrityError`，用户看到"你占用了自己的 slot"的 409；必须先删旧行再插新行。
- 延迟事务（`BEGIN DEFERRED`）在 WAL 下先读后写会 `SQLITE_BUSY_SNAPSHOT`，且中途不能安全重试；写事务只能 `BEGIN IMMEDIATE`。
- 409 的冲突列表必须在 `ROLLBACK` 之后重新查询，否则会把本事务的脏写算进冲突。
- `except IntegrityError: return 409` 会把外键等错误伪装成业务冲突；只捕获唯一键冲突。
- 取消只删 `occupancy` 不删 `booking`，会让"取消后改单"把已取消预约复活；按 `booking_id` 写占用前必须先确认 `booking` 行存在。
- 存本地时间或 `+08:00` 字符串会让同一物理 slot 出现两种字符串，唯一键失效（ADR-005 备选 C）。

## 常见 AI 越界行为（看到自己或他人准备这么做，停手并回报）

- [ ] 在 `src/web/` 或 `src/templates/` 写 `if` 判冲突、算 slot 状态、比较时间 → 违反 R1
- [ ] 在仓储或服务里 `conn.execute("BEGIN ...")`、`conn.commit()`、`with conn:` → 违反 R2
- [ ] 先 `SELECT` 判空再 `INSERT`，或把裸 `INSERT` 改成 `OR IGNORE`/`REPLACE` → 违反 R3
- [ ] 用 `datetime.now()`、`strftime` 拼时间，或存带 `+08:00` 的字符串 → 违反 R4
- [ ] 先写实现再补测试，或改测试断言去迎合实现 → 违反 R5
- [ ] 把 `sprint-status.yaml` 的 story 改成 `done`，或回复里宣布"Story 已完成" → 违反 R6
- [ ] 改了 PRD/架构/故事却没动 §11 溯源表 → 违反 R7
- [ ] 直接 `pip install` 新库、引入 ORM/React/Redis/Docker/Flask-Login，或跳过 ADR → 违反 R8
- [ ] 为让测试通过而删 CHECK、改唯一键、关 `foreign_keys`、放宽 30 分钟对齐 → 违反 R3 与 §4 不变量
- [ ] 给 `booking` 加 `start_slot`/`end_slot`，或给 `slot` 建表、加软删除 `status` 列 → 违反 §4 不变量
- [ ] 在模板里做时间比较或日期加减（展示格式化必须走约定过滤器）→ 违反 R1、R4
- [ ] 给 `LAB_SECRET_KEY` 或默认密码写 fallback 值让本地跑起来 → 违反运行约定
- [ ] 用 `BETWEEN` 查自然周，或把 slot 结束时间交给客户端传 → 违反 CSV 导出约定
<!-- /bmad:context -->
