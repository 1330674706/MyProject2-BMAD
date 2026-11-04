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
- 证据：evidence/D-002_2026-11-04-architecture-reject-spa.png（架构 §7.2/§7.3 与 §16 同屏），原始讨论见 `_bmad-output/planning-artifacts/architecture/reviews/review-tech.md`。
