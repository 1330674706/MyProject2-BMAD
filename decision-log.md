## D-001 2026-11-04 将任意区间预约改为 30 分钟固定 slot

- 类型：实质修改（不是否决）
- 触发：Product Brief 评审，第 1 轮
- 智能体建议：任意起止，按区间重叠判定冲突；理由是更灵活。
- 判断与依据：依据 NFR-1 和 2 人 2 周约束；SQLite 无 exclusion constraint，任意区间需要事务锁 + 重叠查询，测试成本高；固定 30 分钟 slot 可用 (equipment_id, slot_start) 唯一约束直接消灭双预约。
- 结果：修改 Brief 第 5/6/7 节；PRD 的 FR-4/FR-5 按 slot 写；ADR-001 用唯一约束。
- 验证计划：待 Story 2.2 完成后跑两线程并发测试，断言恰好一个成功、一个 409。
- 证据：evidence/D-001_2026-11-04_brief-slot-decision.png
