## D-001 2026-11-04 将任意区间预约改为 30 分钟固定 slot

- 类型：实质修改（不是否决）
- 触发：Product Brief 评审，第 1 轮
- 智能体建议：任意起止，按区间重叠判定冲突；理由是更灵活。
- 判断与依据：依据 NFR-1 和 2 人 2 周约束；SQLite 无 exclusion constraint，任意区间需要事务锁 + 重叠查询，测试成本高；固定 30 分钟 slot 可用 (equipment_id, slot_start) 唯一约束直接消灭双预约。
- 结果：修改 Brief 第 5/6/7 节；PRD 的 FR-4/FR-5 按 slot 写；ADR-001 用唯一约束。
- 验证计划：待 Story 2.2 完成后跑两线程并发测试，断言恰好一个成功、一个 409。
- 证据：evidence/D-001_2026-11-04_brief-slot-decision.png

## D-002 2026-11-04 否决 React SPA + JSON API，改为服务端渲染

- 类型：否决
- 触发：架构设计第 1 轮，ADR-003「表现层」的备选 A（`architecture.md` §7.2）
- 智能体建议：前端独立构建的 React / Vue SPA，`/api/*` 返回 JSON，浏览器端保存 slot 状态再整包提交。
- 判断与依据：三条硬约束同时不成立——(1) 只有 8 条 FR、2 名开发者，SPA 的收益接近零；(2) NFR-2 要求「一条命令启动」，引入 React 就要 Node 工具链与构建产物，启动从 `python -m src.run` 变成「先 build 再 serve」；(3) FR-5 要求冲突返回 409 并标出具体 slot，服务端渲染天然能带错误回原页面，SPA 还得另造一套错误协议。另外客户端再实现一遍连续性 / 1–8 上限 / 7 天窗口，必然与后端规则漂移。
- 结果：ADR-003 定为 Jinja + 表单 POST + 303 PRG；`architecture.md` §7.2 另外否决 HTMX/Alpine（B）、`fetch` 轮询（C）、客户端状态管理（D）；§16「明确不引入」把 React、MySQL、Redis、消息队列、WebSocket 列为禁止技术，出现即视为范围蔓延。
- 验证计划：Story 1.3 完成后确认 `python -m src.run` 一条命令起服务、`pytest -q` 全程不触发 Node 或前端构建；`tests/test_responsive_smoke.py` 用无 JS 的 HTTP 客户端跑通占用视图。
- 证据：本条无对话截图（该否决发生在架构产出的备选表里，当时未留图）。可倒查的书面证据：`architecture.md` §7.2 备选 A、§7.3 否决理由、§16 禁止技术表，以及评审记录 `architecture/reviews/review-tech.md`。

## D-003 2026-11-05 故事拆分由 11 条改为 12 条，新增 2.4 连续多 slot 与改单边界

- 类型：实质修改（不是否决）
- 触发：`bmad-create-epics-and-stories` 第 1 轮，E2 只拆出 2.1、2.2、2.3 三条（合计 11 条）
- 智能体建议：改单（edit）的规则校验与 3.2 管理员改单路由一起实现，E2 保持 3 条故事。
- 判断与依据：改单有一个 create 场景永远测不到的失败模式——把 `14:00–15:00` 改到 `14:30–15:30` 时新旧集合相交，若实现成「先插后删」，`uq_occupancy_slot` 会在自己的旧行上抛 `IntegrityError`，用户看到「你占用了自己的 slot」的 409；2.1 的前置条件全是「目标集合与库内占用不相交」，天然覆盖不到。另外两条：改单失败的原子性断言对象是「原集合逐行不变」，与创建失败的「新增 0 行」不是同一件事，`write_tx()` 边界最容易在这里写错；若把 edit 分支拖到 3.2，2.1 到 3.2 之间会出现只有 create 被执行、edit 被复制成第二份校验的窗口，正是 ADR-003 §7.3 D 要挡的规则分叉。
- 结果：E2 补为 2.1–2.4，全项目 3 Epic / 12 Story / 88 条 AC；2.4 只交付 `app/slot_rules.validate(mode="create"|"edit")` 与服务层替换语义，3.2 只接路由与表单，消除「3.2 才能测 2.4」的倒挂；依赖图所有边均为小号→大号。
- 验证计划：2.4 的 6 组 AC 全部带 `→ assert ...`，Story 2.4 完成后跑 `pytest tests/test_slot_rules.py`，其中「改到与自身旧集合相交」用例必须返回 303 且 `booking_id` 不变、「目标含他人占用」用例必须返回 409 且原 `occupancy` 逐行相等。
- 证据：本条无对话截图。可倒查的书面证据：`epics.md` 第 2.4 节「为什么 2.4 值得独立成 Story」5 条理由、文末「PRD §11 回写记录（2026-11-05 已同步）」，以及 PRD §11 表内 FR-4/FR-7 行已并入 2.4。
