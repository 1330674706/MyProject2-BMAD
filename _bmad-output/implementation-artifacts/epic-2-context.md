# Epic 2 Context: 预约与并发

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Epic 2 把“看到空闲”变成“真正占住”：学生一次提交同一设备 1–8 个连续 slot，要么整单写入，要么一行不写；两个请求同时抢同一 slot 时，由数据库唯一约束而不是代码执行次序裁决；改单只更换占用集合，规则与创建一致。成功标准：合法提交生成 1 条预约与 N 条共享 `booking_id` 的占用；形状非法或越界请求写入 0 行；任一 slot 冲突整单 409 并列出全部冲突位置；并发下同一 key 最多 1 行。

## Stories

- Story 2.1: 提交连续 slot 预约
- Story 2.2: 冲突整单原子拒绝与并发裁决
- Story 2.3: 我的预约与取消
- Story 2.4: 连续多 slot 选择与改单边界

## Requirements & Constraints

- 单次预约只能是同一设备的 1–8 个连续 slot；slot 边界对齐本地 `:00` / `:30`，每格 30 分钟。
- 首个 slot 必须尚未开始，且开始时间在未来 7 天内；9 个 slot、非连续、跨设备或设备不存在、非对齐、已开始、超出窗口均返回 400，且本次写入 0 条占用与 0 条预约。
- 提交必须来自已登录学生并携带有效 CSRF token：未登录 401，缺 token 400。
- 任一 slot 已被预约或锁定，整单 409；响应体逐一列出每个冲突的 `equipment_id` 与 `slot_start`；不产生部分写入。
- 冲突只能由 `occupancy` 上的命名唯一约束裁决；先查后写只可用于组织 409 文案，不能决定放行或拒绝；禁止静默忽略或覆盖冲突。
- 取消即删除 `booking` 行并由级联带走占用；`booking` 不存时间段、不存取消状态；slot 是派生量，不建 slot 表。
- 学生只能取消自己的预约且不能改约；管理员走独立路由，改单与学生预约共用同一约束与写入口。
- 所有时刻以 20 字符 UTC 文本存储，本地时区转换只在一个核心模块完成。

## Technical Decisions

- 分层单体的依赖方向固定为 `web → app → data → SQLite`；SQL 只在数据层且参数化；模板只渲染传入的只读视图对象。
- 写操作统一经立即写事务入口；事务归用例层，仓储函数不 BEGIN / COMMIT / ROLLBACK，审计与业务写同事务提交。
- `occupancy` 以 `(equipment_id, slot_start)` 为业务主键，命名 UNIQUE 约束覆盖预约与锁定；`kind='booking'` 必须有 `booking_id`，`kind='lock'` 必须为空。
- 冲突以 `IntegrityError` 形式在 INSERT 语句处立即抛出；只捕获唯一键冲突，外键等错误不得伪装成 409；回滚后重新查询冲突集合再组织文案，避免把本事务脏写计入冲突。
- 页面采用服务端渲染，表单 POST 后 303 重定向；slot 多值提交；无 JSON 接口、无前端框架。
- 预约 `id` 为 `uuid4().hex`；时间戳由应用传参，不使用数据库默认时间。

## UX & Interaction Patterns

- 学生在某设备某日的 slot 表格中勾选连续格并一次提交；已占用、已锁定、已开始、超出窗口的格不可勾选。
- 成功后回到该设备该日视图，刚提交的格立即显示为“我的预约”；校验失败显示可读错误，不产生任何占用。
- 冲突页面明确列出哪些格已失效，学生可返回重新选择。

## Cross-Story Dependencies

- Story 2.1 建立预约写入内核（用例 → 事务 → 占用仓储）与 `slot_rules` 形状校验，2.2 在此基础上验证冲突与并发，2.4 复用同一规则以 `mode=edit` 处理改单。
- Story 2.3 的取消依赖 2.1 建立的事务/仓储边界；3.2 管理员改单与 3.3 锁定必须复用同一唯一约束与写入口。
- 依赖 Epic 1 的设备开放时间、slot 派生与六态视图契约。
