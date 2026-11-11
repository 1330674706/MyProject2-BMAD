# Epic 3 Context: 管理员运维

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

让管理员在周一用不超过 10 分钟完成本周对账：打开即本周，冲突、锁定与异常直接在格子上可见；能按学号定位学生及其预约，进而处理改单与锁定；最终能导出 CSV 归档并从只读日志追溯操作。系统不提供第二套管理员专用表格，也不允许管理员绕过学生预约所遵守的同一唯一约束。

## Stories

- Story 3.1: 管理员本周视图与按学号检索
- Story 3.2: 管理员改单
- Story 3.3: 锁定与解锁 slot
- Story 3.4: 自然周 CSV 导出与追加式操作日志

## Requirements & Constraints

- 本周视图按自然周展示预约，范围是本地周一 00:00 起、下周一 00:00 止，左闭右开；上一周周日 23:30 的 slot 不得混入本周。
- 页面必须让冲突、锁定、改单等异常有可见标记，且锁定/预约格的状态来自统一 slot 视图。
- 管理员可按学号检索学生并看到其预约；精确学号优先，同时支持前缀匹配。查不到时返回 200 空结果，不得 404 或 5xx。
- 管理员可见学生学号与预约归属；学生侧响应不得泄露其他学生的学号或预约归属信息。
- 所有 `/admin/*` 路由先做认证与授权：未登录 401，已登录学生 403；权限判断不进入模板。
- NFR-3：375 px 与 1280 px 下核心页面不得出现横向滚动，表格需可自动断言不溢出。

## Technical Decisions

- 服务端渲染，无 SPA、无 JSON UI 接口、无前端校验副本；成功写操作 303，失败按语义返回状态码。
- 学生日视图与管理员周视图必须复用同一个 `_slot_grid.html` 局部模板，格子的 `data-state` 只能由 `app/slot_service.py` 的六态计算：`free`、`booked_by_self`、`booked_by_other`、`locked`、`closed_past`、`closed_window`。模板只渲染传入值，不比较时间、不判断冲突。
- slot 是派生量，不建 slot 表；只存 `occupancy` 行，锁定与预约共用 `(equipment_id, slot_start)` 唯一键空间。
- 所有时刻存 20 字符 UTC 文本；自然周边界由 `core/timeutil.py` 计算，查询使用 `>= ? AND < ?`，禁止 `BETWEEN` 与本地时间入库。
- 本轮为只读视图与检索：不得插入、更新或删除任何 `occupancy` 行；不得为展示而改变锁或预约。
- 业务规则只在服务层；`web/` 只解析查询参数与映射状态码，`templates/` 只渲染视图对象，SQL 只在 `data/` 且参数化。
- 管理员读取预约归属时可联查 `user`，但响应中只暴露业务需要的学号；内部自增 id、密码哈希、会话 token 一律不出现。
- 响应式实现优先使用现有 CSS 与语义化表格；若宽表在 375 px 下溢出，应在组件容器内提供受控滚动，且测试断言页面根节点无横向溢出。

## UX & Interaction Patterns

- 默认打开当前自然周；`?week=` 可切换到相邻周，页面应明确显示周范围。
- 周视图以设备 × 日期/时段组织，格子沿用学生日视图的状态文案与视觉语义；异常有独立、可检索的标记元素。
- 检索表单只提交学号；结果为空时展示空态而非错误页。
- 表格在窄屏可读、可操作，不横向撑破 viewport。

## Cross-Story Dependencies

- 依赖 Story 1.3 的六态视图与 `_slot_grid.html`，以及 Story 2.1 的预约/占用数据。
- Story 3.2 的改单与 Story 3.3 的锁定必须复用同一周视图入口与状态模型；Story 3.4 的导出与日志依赖本周边界和审计表。
- 周视图的只读检索为后续改单、锁定提供定位入口，但本 Story 不实现任何写操作。
