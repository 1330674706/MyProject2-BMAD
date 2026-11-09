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
## D-007 2026-11-09 接受 CONCERNS 门禁，逐条裁定 7 条顾虑

- 类型：实质修改（不是否决）
- 触发：`bmad-sprint-planning` 实现就绪检查，结论 CONCERNS（可开工，7 条顾虑，其中 2 条落在 Sprint 1）
- 智能体建议：CONCERNS 放行，Sprint 1 顺序 1.1 → 1.2 → 1.4 → 1.3 → 2.1 → 2.2。
- 判断与依据：7 条里只有 1 条会在写代码时直接失败——ADR-004 正文写 `action='reset_password'`，而 §10.2 的 CHECK 与 Story 3.4 的 AC 都是 `password_reset`，DDL 会当场拒绝插入；另 3 条是文档漂移（FR-2 归属只列 1.2、Story 1.2 元数据漏 ADR-003、architecture §18 仍写「PRD §11 需补 ADR-005」）；1 条是 Story 内前向依赖（3.3 最后一条 AC 测 CSV 导出，导出在 3.4 才交付）；剩下 2 条不需要动文档（1.2/1.3 的 AC 用测试夹具直接造占用行；3.2 用第三个学生当观察者即可）。因笔误打回重跑整个规划，成本远高于直接改 5 处。
- 结果：当场改 5 处——architecture §8.1 的 action 名改为 `password_reset`；architecture §18 第 3 条标记为已回写；PRD §11 FR-2 的 Story 列补 1.4 与 `tests/test_ops_startup.py`；epics 1.2 元数据补 ADR-003；epics 3.3 末条 CSV 断言迁入 3.4。AC 总数保持 88 条、Story 仍 12 条，sprint-status.yaml 未重排。留待开工前的 2 条：1.2/1.3 用夹具造数、2.2 补「两个冲突 slot 都在 409 响应里」的断言（FR-5 要求返回全部冲突）。
- 验证计划：1.1 的 build 首次跑 `pytest` 时确认重置密码写入 `action='password_reset'` 不触发 CHECK 约束；3.4 完成后确认「锁定行不出现在导出中」由 `tests/test_export_audit.py` 单独覆盖。
- 证据：`evidence/D-007_2026-11-09-chat-gate-concerns.png`——规划对话中 Codex 给出 CONCERNS 结论与 7 条顾虑的那一屏；书面侧佐证为 `sprint-status.yaml` 的 `sprints`、`development_status` 块与本轮 5 处文档改动。
## D-008 2026-11-09 独立复审发现 P0，裁定修 9 条、暂不修 10 条

- 类型：实质修改（不是否决）
- 触发：Story 1.1 完成后新开对话跑 `bmad-code-review`，复审给出 19 条发现（4 条 P1、15 条 P2，其中 F1 判 P0）
- 智能体建议：按 19 条全量修复后再进入下一条 Story。
- 判断与依据：19 条里只有 F1（匿名 CSRF 只验签名、不与客户端绑定，别人自取的 token 可替受害者提交登录表单）是安全缺陷，且现场 30 秒可演示；F2 违反 R2 硬规则、评审必查；F3/F4 是 AC 缺断言，属于「测试没测到」而不是「功能没做」；F7/F8/F9/F11/F12 是后续 Story 会踩的坑（2.2 的 409 裁决依赖 F8 的错误分类，2.1 首次写审计会踩 F9）。其余 10 条（枚举与限流、非 ASCII token 500、错误码查表、入参上界、测试加强、1.4 的 serve.py）不在核心演示路径上，4 周内修的收益低于风险。
- 结果：修复范围定为 9 条——F1 改 double-submit（独立 `csrf` cookie，不用 session，否则 401 会带出 session cookie 撞 AC3）、F2 包进 `write_tx()`、F3/F4 补断言、F7 重置目标限 `student`、F8 改判 `sqlite_errorname`、F9 白名单补 `booking`/`equipment`、F11 `.gitignore` 补 `data/`、F12 删模板 `minlength`。暂不修的 10 条记入 retrospective「已知未修」。
- 验证计划：修完 `pytest -q` 全绿，且新增「另一客户端用自己 token → 400」用例；`sprint-status.yaml` 保持 1.1 = review。
- 证据：`evidence/D-008_2026-11-09-chat-review-findings.png`——复审对话中「审查结论 + R1–R8 核对 + P0/P1 列表」那一屏。
## D-009 2026-11-09 否决改用 HTTPS + `__Host-` Cookie，按已接受风险处置

- 类型：否决
- 触发：Story 1.1 增量复审，指出 double-submit 在 HTTP 下 cookie 可被注入，建议改 `Secure=True` + `__Host-` 前缀
- 智能体建议：把 CSRF cookie 改为 `Secure=True` 并加 `__Host-` 前缀，或把 token 绑到会话标识。
- 判断与依据：`Secure=True` 与 `__Host-` 都强制要求 HTTPS，而首版是校园网 HTTP——ADR-004 明确 `Secure=False`，PRD §7.3 已把「无 HTTPS、无证书」列为接受风险。照建议改，Cookie 在 HTTP 下不会下发，登录直接不能用：用一个必然坏掉的功能换一个需要中间人或子域才能触发的理论风险，不成立。
- 结果：不改代码；ADR-004 §8.1 的 CSRF 条目按实际实现（匿名 double-submit + 登录后转会话）重写，并把注入风险写成「已接受」，注明改 HTTPS 时同步启用 `Secure=True` 与 `__Host-`。复审第 2 条（登录失败不带 session cookie）确认通过，无动作。
- 验证计划：`tests/test_auth_login.py` 的 CSRF 用例保持全绿；演示时用 HTTP 访问，若评审问起，指 ADR-004 的残余风险段。
- 证据：本条无对话截图。可倒查：`architecture.md` §8.1 CSRF 条目、`PRD.md` §7.3 已接受风险清单、`tests/test_auth_login.py` 的 CSRF 用例。

## D-010 2026-11-09 Story 1.4 只交付三件事，管理员种子记入 deferred

- 类型：实质修改（缩小 Story 交付面）
- 触发：`bmad-build` Story 1.4 启动时，用户明确「交付三件事，只做这三件」，与 `epics.md` 的 7 条 AC（含管理员种子、单 .db、复制库）不完全一致
- 智能体建议：严格按用户给出的三项交付：一条命令启动 + `/health`、设备 CSV 幂等导入、不新增依赖且不做容器/守护/备份；管理员种子、README、复制库断言不实现
- 判断与依据：用户指令优先于规划文档；把管理员种子塞进本轮会把「运维部署」扩成「账号初始化」，且需要新增 actor 语义。`sprint-status.yaml` 只能置 `review`（R6），由人工决定是否补做；三项之外的发现全部可追溯地记入 `deferred-work.md`，不静默丢弃
- 结果：新增 `src/serve.py`、`src/web/health.py`、`src/seed.py`、`seed/equipment.csv`，改 `app.py`、`config.py`、`equipment_repo.py`、`equipment_service.py`；种子复用 1.2 窗口校验、单事务 upsert、变更写审计；未碰 2.1 与 `occupancy`
- 验证计划：`tests/test_ops_startup.py` 先红后绿（7 → 16 passed），全量 73 passed；`python -m src.serve` 缺任一必需 env 时非 0 退出且不监听
- 证据：`_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md` 的 Implementation Notes 与 Review Triage Log；`deferred-work.md` 的 6 条待办
