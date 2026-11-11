- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 补 README 的单条启动命令、环境变量表与 seed 说明。
  evidence: 本次用户明确只交付三件事，文档不在范围内；Story 1.4 AC1 的「README 中的命令」目前只有终端命令本身可用。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 实现 `LAB_ADMIN_USER` / `LAB_ADMIN_PASSWORD` 管理员种子并补 AC7 测试。
  evidence: 用户本次明确不交付管理员账号种子；`sprint-status.yaml` 置 review 而非 done，留待人工决定是否补做。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 补「数据目录恰好 1 个 .db」与「复制 .db 到新路径后 occupancy 计数一致」两条 Story AC 的断言。
  evidence: 两条不在用户本次三件事内；且 WAL 下非优雅停止后只复制 `.db` 可能丢最后提交，需先 `VACUUM INTO` 或连同 `-wal`/`-shm` 一起复制（architecture 评审 M-11）。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 让 `/health` 的数据库异常返回 503 而不是 Flask 默认 500，并避免每次探活都写一条 INFO 日志。
  evidence: architecture §15.1 只要求「可用时返回 200」，未规定异常状态；单机 40 人规模下 500 已能表达不可用，日志量可接受。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 拒绝表头正确但零数据行的 seed 文件，并校验 `equipment_id` 的字符/长度。
  evidence: 空清单按「幂等导入 0 台」处理是当前明确语义；architecture §11 允许可读 slug，但未给格式约束，新增规则需先改规划文档。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 统一 `PRD.md` §11 与 `epics.md` 关于 FR-2 是否由 Story 1.4 承载的表述。
  evidence: 规划文档自相矛盾，属文档漂移；按 R7 修文档需同一改动同步 §11，不在本次代码交付范围。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-create-booking.md`
  summary: 409 响应重渲染同一 slot 页面、保留已选 slot 并标出冲突项。
  evidence: architecture ADR-003 与 epics AR-3 要求 409 同页重渲染；epics 把冲突 UI 与原子性验收分配给 Story 2.2，2.1 只建立 409 写路径与完整冲突列表。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-create-booking.md`
  summary: 统一 7 天窗口语义：校验器只看首格，slot 网格逐格标记 `closed_window`。
  evidence: PRD FR-4 写的是「首个 slot 的开始时间在未来 7 天内」，而 `slot_service` 逐格判断；跨格差异需规划确认后再改校验器或网格。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-1-create-booking.md`
  summary: 由服务端派生成功后的跳转日期，或拒绝与所提交 slot 不一致的隐藏 `date`。
  evidence: 隐藏 `date` 只影响 303 落点，不影响写入的 slot 集合；修复需让用例返回预约日期，属 2.3/2.4 页面整合范围。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-review-fixes.md`
  summary: 把 `architecture.md` §5.4 L3 的“同一个运行中的服务进程”改成“两个服务进程”，并同步 `PRD.md` §11。
  evidence: 本次按复审要求把 L3 改成两个 `src.serve` 进程（不同 `LAB_PORT`、同一库），比原文更强；改规划文档须按 R7 同一改动同步 §11，需人工确认后执行，故未在本次代码改动内完成。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-review-fixes.md`
  summary: 更新 `spec-2-2-conflict-atomicity.md` 里 L3 的描述与旧证据，使其不再声称“进程内 make_server + 整体写事务区间相交”。
  evidence: 该文件是已 `done` 的历史记录，本次复审修复改动的是同一批测试与 `tx.py` trace 字段；改写历史 spec 属于人工确认范围。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-review-fixes.md`
  summary: 让 `db.initialize()` 在多个服务进程同时首次启动同一个全新库时不会撞 `table already exists`。
  evidence: `apply_migrations()` 在 `write_tx()` 之外读 `PRAGMA user_version`，两个进程同时启动全新库时后到者会重复执行 DDL；并发用例都先用 `prepare_database()` 预置库，故不受影响，但真实现场同时起两个进程仍会触发。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-review-fixes.md`
  summary: `python -m src.serve` 在端口被占用等 `application.run()` 抛错时也应打印“启动失败：…”并返回 2。
  evidence: 现有 `except` 只包住 `create_app()`，`application.run()` 的 `OSError` 仍会打 traceback 并以 1 退出；这是 1.4 启动契约的既有缺口，不在本次五条复审修复范围内。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-2-review-fixes.md`
  summary: 409 整页提示时给提交过但无法定位的格子加“未验证”标记，而不是只显示 free。
  evidence: 复审意见认为 page 作用域下提交的 slot 仍按 `free` 渲染、缺少可操作线索；六态枚举是 1.3/3.1 的共同契约，新增第七种视觉状态需先改 `epics.md` 并经人工确认，故本次只保留整页提示与网格。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-cancel-booking.md`
  summary: 为页面补登出入口，并让匿名页面不再渲染仅登录后可达的导航。
  evidence: `POST /logout` 自 1.1 起就没有模板引用，属既有缺口；本次只修了匿名导航 401（`base.html` 按 `g.user` 渲染）。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-cancel-booking.md`
  summary: 证明并发取消同一 `booking_id` 恰有一次 303、一次 404 且只写 1 条审计。
  evidence: FR-6 与 Story 2.3 AC 只要求重复取消 404 与不写审计，未要求并发证据；需要 `Barrier` 双进程驱动，超出本 Story 测试范围。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-3-cancel-booking.md`
  summary: 明确“我的预约”的排序契约并写成断言（含同秒创建的次序）。
  evidence: `LIST_BY_OWNER` 按 `created_at DESC, id` 排序，而 `created_at` 只到秒，同秒创建时退化为 uuid 顺序；FR-6 与 AC 均未规定顺序，需规划确认后再固化。

## Deferred from: code review of spec-2-4-slot-rules-edit.md (2026-11-11)

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-slot-rules-edit.md`
  summary: 同步 `PRD.md` §11 的 2.4 日期确认行，并对齐 FR-7 的 ADR 集合（§11 行写 ADR-002/003/005，`epics.md` 2.4 写 ADR-001/005）。
  evidence: 改规划工件须按 R7 在同一改动同步 §11 并经人工确认；本次代码改动内未执行。

- source_spec: `_bmad-output/implementation-artifacts/spec-2-4-slot-rules-edit.md`
  summary: 补齐 Story 2.4 先红后绿的运行证据，使 R5 可复核。
  evidence: 单个 commit `1aad2d6` 同时包含测试与实现，spec 中 `9 failed` 的红灯记录只有自述，无法从仓库历史复核。

## Deferred from: code review of spec-3-2-admin-edit-booking.md (2026-11-11)

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-admin-edit-booking.md`
  summary: 让 `epics.md` Story 3.2 的目标与 `PRD.md` FR-7 的能力描述和 D-011 一致（改单只改时段，不换设备）。
  evidence: `epics.md:591` 仍写“改到另一台设备”，`PRD.md:183` 写“可修改预约的设备或 slot 集合”；两者与 `decision-log.md` D-011 相反。本次未改规划工件，按 R7 需人工确认后在同一改动同步 `PRD.md` §11。

- source_spec: `_bmad-output/implementation-artifacts/spec-3-2-admin-edit-booking.md`
  summary: 在按学号检索结果表里也提供改单入口。
  evidence: `admin_users.html` 的预约行与周视图同源（`StudentSearch.bookings`），但目前只有周视图有“改单”链接；是否扩大入口属人工范围决定，补测试时在 `/admin/users` 断言即可。
