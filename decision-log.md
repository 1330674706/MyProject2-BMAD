## D-001 2026-11-04 将任意区间预约改为 30 分钟固定 slot

- 类型：实质修改（不是否决）
- 触发：Product Brief 评审，第 1 轮
- 智能体建议：任意起止，按区间重叠判定冲突；理由是更灵活。
- 判断与依据：依据 NFR-1 和 2 人 2 周约束；SQLite 无 exclusion constraint，任意区间需要事务锁 + 重叠查询，测试成本高；固定 30 分钟 slot 可用 (equipment_id, slot_start) 唯一约束直接消灭双预约。
- 结果：修改 Brief 第 5/6/7 节；PRD 的 FR-4/FR-5 按 slot 写；ADR-001 用唯一约束。
- 事后验证：成立。Story 2.2 的 C1–C3 与 100 轮实测给出直接证据——C1/C2 各 100 轮全部「1 成功 + 1 冲突」，C3 删掉唯一约束后每轮出现 2 次成功，说明胜负确实由数据库裁决而不是应用层判断（`evidence/story-2.2_2026-11-10_pytest-concurrency.txt`）。
- 验证计划：待 Story 2.2 完成后跑两线程并发测试，断言恰好一个成功、一个 409。
- 证据：evidence/D-001_2026-11-04_brief-slot-decision.png

## D-002 2026-11-04 否决 React SPA + JSON API，改为服务端渲染

- 类型：否决
- 触发：架构设计第 1 轮，ADR-003「表现层」的备选 A（`architecture.md` §7.2）
- 智能体建议：前端独立构建的 React / Vue SPA，`/api/*` 返回 JSON，浏览器端保存 slot 状态再整包提交。
- 判断与依据：三条硬约束同时不成立——(1) 只有 8 条 FR、2 名开发者，SPA 的收益接近零；(2) NFR-2 要求「一条命令启动」，引入 React 就要 Node 工具链与构建产物，启动从 `python -m src.run` 变成「先 build 再 serve」；(3) FR-5 要求冲突返回 409 并标出具体 slot，服务端渲染天然能带错误回原页面，SPA 还得另造一套错误协议。另外客户端再实现一遍连续性 / 1–8 上限 / 7 天窗口，必然与后端规则漂移。
- 结果：ADR-003 定为 Jinja + 表单 POST + 303 PRG；`architecture.md` §7.2 另外否决 HTMX/Alpine（B）、`fetch` 轮询（C）、客户端状态管理（D）；§16「明确不引入」把 React、MySQL、Redis、消息队列、WebSocket 列为禁止技术，出现即视为范围蔓延。
- 事后验证：成立。后面 9 个 Story 都只有一个进程，`python -m src.serve` 起来就能用，没有一次前后端联调，也没装过 Node。215 条测试全在 pytest 里跑完。
- 验证计划：Story 1.3 完成后确认 `python -m src.run` 一条命令起服务、`pytest -q` 全程不触发 Node 或前端构建；`tests/test_responsive_smoke.py` 用无 JS 的 HTTP 客户端跑通占用视图。
- 证据：本条无对话截图（该否决发生在架构产出的备选表里，当时未留图）。可倒查的书面证据：`architecture.md` §7.2 备选 A、§7.3 否决理由、§16 禁止技术表，以及评审记录 `architecture/reviews/review-tech.md`。

## D-003 2026-11-05 故事拆分由 11 条改为 12 条，新增 2.4 连续多 slot 与改单边界

- 类型：实质修改（不是否决）
- 触发：`bmad-create-epics-and-stories` 第 1 轮，E2 只拆出 2.1、2.2、2.3 三条（合计 11 条）
- 智能体建议：改单（edit）的规则校验与 3.2 管理员改单路由一起实现，E2 保持 3 条故事。
- 判断与依据：改单有一个 create 场景永远测不到的失败模式——把 `14:00–15:00` 改到 `14:30–15:30` 时新旧集合相交，若实现成「先插后删」，`uq_occupancy_slot` 会在自己的旧行上抛 `IntegrityError`，用户看到「你占用了自己的 slot」的 409；2.1 的前置条件全是「目标集合与库内占用不相交」，天然覆盖不到。另外两条：改单失败的原子性断言对象是「原集合逐行不变」，与创建失败的「新增 0 行」不是同一件事，`write_tx()` 边界最容易在这里写错；若把 edit 分支拖到 3.2，2.1 到 3.2 之间会出现只有 create 被执行、edit 被复制成第二份校验的窗口，正是 ADR-003 §7.3 D 要挡的规则分叉。
- 结果：E2 补为 2.1–2.4，全项目 3 Epic / 12 Story / 88 条 AC；2.4 只交付 `app/slot_rules.validate(mode="create"|"edit")` 与服务层替换语义，3.2 只接路由与表单，消除「3.2 才能测 2.4」的倒挂；依赖图所有边均为小号→大号。
- 事后验证：成立。2.4 自己把 `validate(mode="create"|"edit")` 做完了，先红后绿 9 条；3.2 直接调 `edit_booking()` 接路由，规则没有复制第二份，也没出现「要等 3.2 才能测 2.4」的情况。
- 验证计划：2.4 的 6 组 AC 全部带 `→ assert ...`，Story 2.4 完成后跑 `pytest tests/test_slot_rules.py`，其中「改到与自身旧集合相交」用例必须返回 303 且 `booking_id` 不变、「目标含他人占用」用例必须返回 409 且原 `occupancy` 逐行相等。
- 证据：本条无对话截图。可倒查的书面证据：`epics.md` 第 2.4 节「为什么 2.4 值得独立成 Story」5 条理由、文末「PRD §11 回写记录（2026-11-05 已同步）」，以及 PRD §11 表内 FR-4/FR-7 行已并入 2.4。

## D-004 2026-11-09 Story 1.4 只交付三件事，管理员种子记入 deferred

- 类型：实质修改（缩小 Story 交付面）
- 触发：`bmad-build` Story 1.4 启动时，用户明确「交付三件事，只做这三件」，与 `epics.md` 的 7 条 AC（含管理员种子、单 .db、复制库）不完全一致
- 智能体建议：严格按用户给出的三项交付：一条命令启动 + `/health`、设备 CSV 幂等导入、不新增依赖且不做容器/守护/备份；管理员种子、README、复制库断言不实现
- 判断与依据：用户指令优先于规划文档；把管理员种子塞进本轮会把「运维部署」扩成「账号初始化」，且需要新增 actor 语义。`sprint-status.yaml` 只能置 `review`（R6），由人工决定是否补做；三项之外的发现全部可追溯地记入 `deferred-work.md`，不静默丢弃按验收面切：种子导入属 FR-2，一条命令启动属 NFR-2，管理员账号不在其中任何一条里。
- 结果：新增 `src/serve.py`、`src/web/health.py`、`src/seed.py`、`seed/equipment.csv`，改 `app.py`、`config.py`、`equipment_repo.py`、`equipment_service.py`；种子复用 1.2 窗口校验、单事务 upsert、变更写审计；未碰 2.1 与 `occupancy`
- 事后验证：一半对。延后是对的，管理员种子后来只改了 3 处、加了 3 条测试就补齐。但当时只是口头记了一笔，没写进 `deferred-work.md`，差点彻底漏掉，是 3.4 之后复查捞回来的。延后可以，漏登记不行。
- 验证计划：`tests/test_ops_startup.py` 先红后绿（7 → 16 passed），全量 73 passed；`python -m src.serve` 缺任一必需 env 时非 0 退出且不监听
- 证据：`_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md` 的 Implementation Notes 与 Review Triage Log；`deferred-work.md` 的 6 条待办

## D-007 2026-11-09 接受 CONCERNS 门禁，逐条裁定 7 条顾虑

- 类型：实质修改（不是否决）
- 触发：`bmad-sprint-planning` 实现就绪检查，结论 CONCERNS（可开工，7 条顾虑，其中 2 条落在 Sprint 1）
- 智能体建议：CONCERNS 放行，Sprint 1 顺序 1.1 → 1.2 → 1.4 → 1.3 → 2.1 → 2.2。
- 判断与依据：7 条里只有 1 条会在写代码时直接失败——ADR-004 正文写 `action='reset_password'`，而 §10.2 的 CHECK 与 Story 3.4 的 AC 都是 `password_reset`，DDL 会当场拒绝插入；另 3 条是文档漂移（FR-2 归属只列 1.2、Story 1.2 元数据漏 ADR-003、architecture §18 仍写「PRD §11 需补 ADR-005」）；1 条是 Story 内前向依赖（3.3 最后一条 AC 测 CSV 导出，导出在 3.4 才交付）；剩下 2 条不需要动文档（1.2/1.3 的 AC 用测试夹具直接造占用行；3.2 用第三个学生当观察者即可）。因笔误打回重跑整个规划，成本远高于直接改 5 处。
- 结果：当场改 5 处——architecture §8.1 的 action 名改为 `password_reset`；architecture §18 第 3 条标记为已回写；PRD §11 FR-2 的 Story 列补 1.4 与 `tests/test_ops_startup.py`；epics 1.2 元数据补 ADR-003；epics 3.3 末条 CSV 断言迁入 3.4。AC 总数保持 88 条、Story 仍 12 条，sprint-status.yaml 未重排。留待开工前的 2 条：1.2/1.3 用夹具造数、2.2 补「两个冲突 slot 都在 409 响应里」的断言（FR-5 要求返回全部冲突）。
- 事后验证：成立。7 条顾虑里 2 条真的发生了：1.2、1.3 要提前造占用行，3.3 最后一条 AC 前向依赖 3.4。因为开工前登记过，两条都没卡住冲刺，也没有一条变成意外。
- 验证计划：1.1 的 build 首次跑 `pytest` 时确认重置密码写入 `action='password_reset'` 不触发 CHECK 约束；3.4 完成后确认「锁定行不出现在导出中」由 `tests/test_export_audit.py` 单独覆盖。
- 证据：`evidence/D-007_2026-11-09-chat-gate-concerns.png`——规划对话中 Codex 给出 CONCERNS 结论与 7 条顾虑的那一屏；书面侧佐证为 `sprint-status.yaml` 的 `sprints`、`development_status` 块与本轮 5 处文档改动。

## D-008 2026-11-09 独立复审发现 P0，裁定修 9 条、暂不修 10 条

- 类型：实质修改（不是否决）
- 触发：Story 1.1 完成后新开对话跑 `bmad-code-review`，复审给出 19 条发现（4 条 P1、15 条 P2，其中 F1 判 P0）
- 智能体建议：按 19 条全量修复后再进入下一条 Story。
- 判断与依据：19 条里只有 F1（匿名 CSRF 只验签名、不与客户端绑定，别人自取的 token 可替受害者提交登录表单）是安全缺陷，且现场 30 秒可演示；F2 违反 R2 硬规则、评审必查；F3/F4 是 AC 缺断言，属于「测试没测到」而不是「功能没做」；F7/F8/F9/F11/F12 是后续 Story 会踩的坑（2.2 的 409 裁决依赖 F8 的错误分类，2.1 首次写审计会踩 F9）。其余 10 条（枚举与限流、非 ASCII token 500、错误码查表、入参上界、测试加强、1.4 的 serve.py）不在核心演示路径上，4 周内修的收益低于风险。批准的三条分别落在 FR-1（登录与重置）、NFR-4（脱敏白名单）、NFR-2（启动脚本）的验收面上，另外 10 条不改变任何 FR/NFR 的可观察行为。
- 结果：修复范围定为 9 条——F1 改 double-submit（独立 `csrf` cookie，不用 session，否则 401 会带出 session cookie 撞 AC3）、F2 包进 `write_tx()`、F3/F4 补断言、F7 重置目标限 `student`、F8 改判 `sqlite_errorname`、F9 白名单补 `booking`/`equipment`、F11 `.gitignore` 补 `data/`、F12 删模板 `minlength`。暂不修的 10 条记入 retrospective「已知未修」。
- 事后验证：成立。F1 改成独立 `csrf` cookie 的 double-submit 之后，3.1 到 3.4 四个 Story 再没因为 CSRF 返工，也没再出现「401 带出 session cookie」。
- 验证计划：修完 `pytest -q` 全绿，且新增「另一客户端用自己 token → 400」用例；`sprint-status.yaml` 保持 1.1 = review。
- 证据：`evidence/D-008_2026-11-09-chat-review-findings.png`——复审对话中「审查结论 + R1–R8 核对 + P0/P1 列表」那一屏。

## D-009 2026-11-09 否决改用 HTTPS + `__Host-` Cookie，按已接受风险处置

- 类型：否决
- 触发：Story 1.1 增量复审，指出 double-submit 在 HTTP 下 cookie 可被注入，建议改 `Secure=True` + `__Host-` 前缀
- 智能体建议：把 CSRF cookie 改为 `Secure=True` 并加 `__Host-` 前缀，或把 token 绑到会话标识。
- 判断与依据：`Secure=True` 与 `__Host-` 都强制要求 HTTPS，而首版是校园网 HTTP——ADR-004 明确 `Secure=False`，PRD §7.3 已把「无 HTTPS、无证书」列为接受风险。照建议改，Cookie 在 HTTP 下不会下发，登录直接不能用：用一个必然坏掉的功能换一个需要中间人或子域才能触发的理论风险，不成立。
- 结果：不改代码；ADR-004 §8.1 的 CSRF 条目按实际实现（匿名 double-submit + 登录后转会话）重写，并把注入风险写成「已接受」，注明改 HTTPS 时同步启用 `Secure=True` 与 `__Host-`。复审第 2 条（登录失败不带 session cookie）确认通过，无动作。
- 事后验证：没验证到。整个学期系统都跑在 `127.0.0.1`，没有跨站场景，所以这条否决的代价一直没暴露。这不能算证明对了，只能算没踩到。
- 验证计划：`tests/test_auth_login.py` 的 CSRF 用例保持全绿；演示时用 HTTP 访问，若评审问起，指 ADR-004 的残余风险段。
- 证据：本条无对话截图。可倒查：`architecture.md` §8.1 CSRF 条目、`PRD.md` §7.3 已接受风险清单、`tests/test_auth_login.py` 的 CSRF 用例。

## D-010 2026-11-09 复审 12 条只批 3 条，7 天窗口由「首格」改为「逐格」

- 类型：实质修改（不是否决）
- 触发：Story 2.1 独立复审给出 12 条发现（2 条 P1、10 条 P2，无 P0），建议按优先级全修
- 智能体建议：先由规划裁决 F1 的两套 7 天语义，再补 F2 的 409 测试，F3/F4/F6 一并处理。
- 判断与依据：只有 3 条影响演示路径——F1 写入只看首格、页面逐格判定，同一 slot 一页说不能约、接口却接受，评审一试就中；F2 的 409 分支一条测试都没有，而 2.2 整个故事讲的就是 409；F5 用事务前快照拼文案，可能列出已不存在的冲突行，改一行即可。其余 9 条（事务外取 now 的 1 秒漂移、Unicode 数字正则、`database is locked` 映射、倒序提交、隐藏 date 不校验、400 重渲染丢网格、预检多一次查询、常量重复定义、红灯未归档）都落在边界时序或体验细节，不进入 4 周内的演示与答辩路径。7 天窗口本身是 FR-4 的验收项，冲突时返回全部 slot 是 FR-5 的要求，逐格判定同时满足两条。
- 结果：F1 选「逐格判定」这一侧——网格已是逐格，改写入侧更省事且与用户直觉一致；PRD FR-4 由「首个 slot 的开始时间在未来 7 天内」改为「每个 slot 的开始时间都在未来 7 天内（首格不得早于当前时刻）」，验收项同步改为「任一 slot 超 7 天返回 4xx」。F2 补 3 条断言级测试（第 3 格冲突整单不变、3 个 lock 冲突全部列出、冲突在第 5 格时前 4 格未落库）。F5 删除 `or pre_conflicts`，冲突列表只取 ROLLBACK 后的重查结果，重查为空时返回通用文案。其余 9 条记入 `deferred-work.md`。
- 事后验证：成立。改成逐格判定之后，7 天窗口的断言全过，3.1 的周视图和 3.2 的跨周改单都没再出窗口边界的问题。
- 验证计划：修完 `pytest -q` 全绿且新增 3 条 409 用例；临时库手工构造「第 3 格已占」确认 `(booking, occupancy)` 计数不变。
- 证据：`evidence/D-010_2026-11-09-chat-triage-2-1.png`——本轮对话中「为什么只修这 3 条」与 PRD 措辞改动同屏；书面侧为 `PRD.md` FR-4 修改前后文本、`deferred-work.md` 的 9 条记录。

## D-011 2026-11-11 否决「改单可以换设备」的实现选择

- 类型：否决
- 触发：Story 2.4 复审的三个待决策项之一——矩阵里「跨设备」用例用 E2 的开放窗口凑失败原因，而 `edit_booking()` 实际允许 E1 的预约改成 E2 的 slot 并成功
- 智能体建议：先确认 AC 原意；若「跨设备」指换设备，则当前实现与 AC 期望的 `Validation` 相反，需要人工裁决走哪边。
- 判断与依据：换设备不是「改时间」，是换了另一个物理资源——新设备有独立的开放窗口、独立的占用集合与独立的维护责任，把它做成一次 UPDATE 会让审计里一条 `booking_edit` 同时改时间与设备，事后追责说不清是谁把谁的机时挪走了。取消再重约虽然多两步，但每一步都可审计、都可被学生看见。首版只有 4 周，把一个组合操作拆成两个已实现的操作，比新增一条跨设备替换语义更省。改单能力由 FR-7 定义，occupancy 的键空间由 ADR-001 固定；换设备等于让 `(equipment_id, slot_start)` 跨设备迁移，超出 FR-7 的授权。
- 结果：`edit_booking()` 在事务内、`validate` 之前比对 `equipment_id`，不同即 `Validation`（400），不改设备；`slot_rules` 的用例矩阵去掉「跨设备」形态，新增 `test_edit_to_another_equipment_is_validation_and_keeps_every_row`（断言 booking/occupancy 逐行不变、审计 0 条）。epics 2.4 的 AC 同步为服务层契约，并注明 HTTP `303/400/409` 由 3.2 承接；`PRD.md` §11 的 FR-7 行补 `ADR-001`。
- 事后验证：成立。3.2 提交换设备会返回 400，`test_edit_to_another_equipment_is_validation_and_keeps_every_row` 断言 booking 和 occupancy 一行没变、审计 0 条。也没出现「先删旧再插新把原预约弄丢」。
- 验证计划：`pytest -q` 133 passed；3.2 接路由后再验证页面层换设备返回 400 而不是 500。
- 证据：`evidence/D-011_2026-11-11-chat-2-4-decisions.png`（复审提出三个待决策）与 `evidence/D-011_2026-11-11-chat-2-4-decisions-reply.png`（我给出的三条判断）两帧。

## D-012 2026-11-11 否决「新增 display_name 列」，改为一律只显示学号

- 类型：否决
- 触发：Story 3.1 规划检查点时，Codex 指出 `user` 表只有 `student_no`、没有姓名，给出 A（新增 nullable `display_name` + 注册页收姓名 + 迁移版本 2 + 回写 Story 1.1）、B（只显示学号）、C（用「学生 + 学号」充当展示名）三个选项
- 智能体建议：推荐 A，理由是「字面上的姓名要求不满足」。
- 判断与依据：`PRD.md` 的 FR-7 只写「可按学号检索学生并进入其预约」，全文没有姓名要求；「姓名与学号」是我在 3.1 的指令里多写的一句，不是需求。为一个 PRD 没有的字段改 schema、加迁移版本、回写已完成并复审过的 Story 1.1，还要连带改注册页与 `user_version` 断言，代价与收益不成比例，且会引出「姓名是否唯一、能否重名」一类新问题。C 同样否决：把「学生 2025001」当展示名，会让审计与导出里出现看着像真名的假姓名，追责时比没有姓名更糟。
- 结果：按 B 实现，管理员页面只展示学号；spec 删掉姓名要求，不新增列、不改迁移、不回写 1.1。将来若确需姓名，加一个 nullable 列即可，属增量而非返工。
- 事后验证：成立。3.1 上线后检索、周视图、改单页都只用学号，没有一处需要「这是谁」的返工，也没人再提加姓名。
- 验证计划：3.1 的检索用例断言返回学号；`migrations/` 仍只有 001，`PRAGMA user_version` 不变。
- 证据：`evidence/D-012_2026-11-11-chat-3-1-name-options.png`（A/B/C 三选项）与 `evidence/D-012_2026-11-11-chat-3-1-reject-schema-change.png`（选 B、否决 A 与 C）两帧。

## D-013 2026-11-11 否决「400 分支丢弃已提交选择」的驳回结论

- 类型：否决
- 触发：Story 3.2 复审给出 1 条待决、9 条 patch、2 条 defer，其中「`_render_edit` 的 Validation 分支不传 `selected_slots`」被首轮判为驳回（BH-08），理由写作「规则只固定 409」
- 智能体建议：维持现状（选项 3），接受首轮裁定，本轮登记为 defer。
- 判断与依据：400 的语义是「填错了改一下」，不是「你不该填」；清空等于让用户重勾 8 个格子，而同一页面 409 却保留选择，两套行为用户分不清。「规则只固定 409」是把文档的沉默当成许可——文档没写不代表可以少做。验收看的是可用性，不是条文覆盖度。这是 FR-7 的一面：改单失败时不该让用户重选一遍。
- 结果：选方案 1，`_render_edit` 的两个异常分支（Validation 与日期回退）都回传 `selected_slots`、`conflicted_slots`，与 409 统一为「一律保留提交态，冲突格额外标红」；`app.css` 的选中描边加 `:not(.is-conflict)`，保证冲突格仍是红色实线。同一轮另修 9 条 patch（`editable` 语义外溢、跨周 303、409 响应体字段等），2 条 defer 记入 `deferred-work.md`。
- 事后验证：成立。3.2 的 409 和 400 都留住了已勾选的 slot，冲突格还是红实线。本轮 9 条 patch 合进去以后 19 passed，选择没丢。
- 验证计划：`tests/test_admin_edit_booking.py` 19 passed（新增跨周改单与 409 字段断言）；全量 167 passed。
- 证据：`evidence/D-013_2026-11-11-chat-3-2-render-edit-options.png`（三个选项）与 `evidence/D-013_2026-11-11-chat-3-2-reject-bh08.png`（选 1 并说明理由）两帧。

## D-014 2026-11-11 否决「上线前直接加邮件提醒」和 `.ics` 桥接

- 类型：否决
- 触发：实验 B（范围变更）。课程要求模拟一次临上线前的变更，用 `bmad-correct-course` 评估「预约成功后自动发邮件提醒」，产出 `_bmad-output/implementation-artifacts/experiment-B-impact.md`，给了 A、B、C 三个方案。
- 智能体建议：推荐 B，排到 v2。如果客户坚持上线前要有动作，先做 `.ics` 日历文件顶着。只有三个条件同时成立才走 A：上线能推后两周以上、校园 SMTP 中继确认可用、产品负责人同意改 NFR-2。
- 判断与依据：影响分析自己就摆出三个冲突。第一，`user` 表没有邮箱列，要发信得先加列再补录 40 个学生，等于回头改已经验收的 1.1。第二，客户说的「三种触发加一次提醒」其实是四个事件（创建、取消、改单、开始前 2 小时），全都落在已经交付的 `write_tx()` 上，在事务里发信就是把外部 IO 塞进事务边界。第三，PRD §6 和 §7.2 写了「不做通知」，NFR-2 写了「不依赖外部服务」，这两条不是能顺手推翻的实现细节。`.ics` 那条也不行，它是个新导出能力，会跟 3.4 刚验收的 CSV 导出并成第二份契约。
- 结果：采用 B，只登记不执行。A 和 C 里的 `.ics` 部分否掉。`deferred-work.md` 新增「Deferred to v2: 邮件提醒」，写清三个重启条件；`experiment-B-impact.md` §12 记了同一份裁决。不加 FR-9、FR-10，不动 PRD、architecture、epics 正文，不改代码，不动 `sprint-status.yaml`。
- 验证计划：`git status` 里不该出现 `PRD.md`、`architecture.md`、`epics.md`，也不该出现 `src/` 和 `tests/`；§16 没碰；12 个 Story 状态不变；`pytest -q` 还是 209 passed。
- 事后验证：还没到验证点。封版前没人再提邮件提醒，`deferred-work.md` 里那三个重启条件一条都没触发。这条只是把外部依赖挡在范围外，暂时没有可观察的后果。
- 证据：`evidence/D-014_2026-11-11-chat-correct-course-request.png`（变更请求原文）、`evidence/D-014_2026-11-11-chat-correct-course-options.png`（A/B/C 对比表）、`evidence/D-014_2026-11-11-chat-reject-email.png`（否掉 A 与 `.ics` 的回复）。

## D-015 2026-11-11 实验 A 改用等价小任务，不重跑真实 Story

- 类型：否决
- 触发：实验 A 设计阶段。讲义要求 X 走完整路径、Y 只口述需求，还要求「X 与 Y 必须难度相当，并在报告里给出判断理由」。
- 智能体建议：X 拿已经交付的真实 Story（比如 2.3 我的预约与取消）重跑一遍完整路径，Y 在干净副本里用一句话重做同一个 Story。做的是同一件事，可比性最强。
- 判断与依据：重跑不可控。要在工作区里复制整个仓库，再删掉 `_bmad-output/`、`project-context.md`、`AGENTS.md` 才够得上 Y 的条件，删漏一样对照组就废了。Y 的实现会覆盖已经验收的 `booking_service.py` 和 `web/bookings.py`，跟封版前的仓库状态打架。2.3 有 10 个测试、跨 3 个模块，重跑一次的时间我们出不起。等价小任务的交付面、函数签名、6 条 AC 都逐字相同，可比性来自构造，不靠运气。不影响任何 FR/NFR 的验收：实验代码不进 `src/`，`pytest -q` 仍 209 passed，FR-1..FR-8 的证据链不变。
- 结果：用 `format_slot_range` 做等价任务。X 读 `project-context.md` 加故事卡，Y 只有一句需求；同一人、同一天、同一模型、同一条评审提示词；X 的产物先归档到 `_expA/X/`，再让 Y 从空目录开始。等价性论证和全部指标写在 `experiment-A-record.md` 第 2、3 节。
- 验证计划：两组交付面必须完全一致，都只新增 `src/core/slotfmt.py` 和 `tests/test_slotfmt.py`；归档后 `git status` 干净；`pytest -q` 回到 209 passed。
- 事后验证：一半。等价性站得住，两组都自己写完了 6 条 AC，X 用了 3 分 16 秒，Y 自纠 1 次，难度确实相当。但对照组不干净：仓库根的 `AGENTS.md` 强制 Y 读 `project-context.md`，它实际拿到了 R1–R8 和既有代码。所以这个实验只能说明「需求规格有用」，说不了「规划整体有用」，详见 `experiment-A-record.md` §8.5。
- 证据：两组产物在 `_expA/X/`、`_expA/Y/`；`evidence/expA_2026-11-11_chat-X-prompt.png`、`evidence/expA_2026-11-11_chat-Y-selfcontext.png`；两组评审回复原文见对话记录。

## D-016 2026-11-11 实验 A 结论：规划买的是「错误能被人裁决」，故事卡得跟模块边界对齐

- 类型：实质修改（否掉了「简化故事卡」的建议）
- 触发：实验 A 结果出来之后。X 组（有 PRD、架构、R1–R8、故事卡）和 Y 组（一句话需求）的评审发现条数一样，都是 5 条，但性质不同。Y 那 5 条里有 2 条是把「非法输入必须拒绝」做成了空串和静默合并，还有 3 处测试缺 `pytest.raises`；X 那 5 条是 `core/` 里复刻了 slot 校验、时间格式重复，没有一条是语义反转。
- 智能体建议：倾向「两组打平，规划性价比不高」，建议后面简化故事卡，只留 AC 列表。
- 判断与依据：打平的是数量，不是后果。Y 那种语义反转如果按 12 个故事等比出现，等于 12 处该 409 的地方静默放行，而 NFR-1 的验收口径是「并发 100 轮双预约 0 成功」，一条静默容错就能让它归零。另一头，X 之所以也违反 R1，是因为故事卡自己强制 `src/core/slotfmt.py`，又把「连续加 30 分钟对齐」写进 AC5，跟 R1「slot 语义属于 `src/app/`」正面撞上。有上下文的一方会老实执行一份错规格，这比没规格更危险。所以要改的是卡片写法，不是把卡片砍掉。
- 结果：不简化故事卡，加一条硬要求：交付落点必须和 `architecture.md` §13 的模块边界一致，AC 不许要求下游模块干上游的活。`experiment-A-story-card.md` 原样留着当反例。`format_slot_range` 不并进生产，两组都没接调用方，接进去等于给 R1 类问题开口子；只在 `deferred-work.md` 记一条「时间格式三处重复（`admin_service._slot_label`、`booking_service._slot_display`、`SlotCell.local_time`），v2 收敛到 `timeutil`」。
- 验证计划：`pytest -q` 回到 209 passed（实验代码全在 `_expA/`，不进生产）；`git status` 干净；12 个 Story 状态不变；以后再有 Story，卡片里的 Code Map 要逐行对上 `architecture.md` §13。
- 事后验证：还没到验证点。12 个 Story 都交付完了，封版前不会再开新 Story，这条「卡片要和模块边界对齐」没机会被检验。留作 v2 的开工规则，`experiment-A-story-card.md` 原样留着当反例。
- 证据：`_bmad-output/implementation-artifacts/experiment-A-record.md`（第 5、6、7 节是缺陷对照与归因，第 8 节是「乘 12 个故事」的回答）；两组评审回复原文见对话记录。

## D-017 2026-11-11 封版：v1 范围冻结，32 条 deferred 不逐条补

- 类型：实质修改（缩小交付面，否掉「顺手都修掉」）
- 触发：封版前盘点。12 个 Story 全 `done`，`deferred-work.md` 累计 32 条没做完的，剩下的时间只够写 README 和录 10 分钟演示。
- 智能体建议：逐条裁决这 32 条，把「不费事」的都补掉，理由是反正都是小改动。
- 判断与依据：按讲义第 33 页的产物清单，这 32 条绝大多数是新增能力或者提高证据可复核性，没有一条落在 PRD §11 那 8 行溯源链上。不补它们，FR-1 到 FR-8 的「FR → ADR → Story → Test」照样走得通，NFR-1 的并发证据和 NFR-2 的一条命令启动也都成立。反过来，两份必交产物还是空的，这个风险比那 32 条大得多。还有一条补不了：R5 的「先红后绿」证据要重跑测试，重跑会覆盖已经归档的证据文件和时间戳，是用新证据盖旧证据，反而多出一处不一致。
- 结果：v1 冻结，只做三件事。一是把已经做完的 4 条从清单归档：管理员种子、7 天窗口改逐格（D-010）、`PRD.md` §11 与 `epics.md` 的 FR-2 表述（D-007）、架构里「四个用例 / 只有两个 occupancy helper / §15.1 缺路由」（今天已修）。二是其余全部顺延 v2，不逐条裁决。三是 README 单列一节「已知未做」指向 `deferred-work.md`，让取舍看得见。另外否掉两项：顺手补文档措辞，不影响任何验收链；补 no-op 审计守卫，会新开一条没有行为的写路径，跟 R3「写 occupancy 只有一个入口」相冲。
- 验证计划：封版后 `git log` 不再出现 `src/` 的功能性改动；`pytest -q` 保持 209 passed；README 的「已知未做」跟 `deferred-work.md` 的未完成条目对得上；10 分钟录屏覆盖并发 409 和 FR→ADR→Story→Test 两条链。
- 事后验证：还没到验证点。封版后没有迭代了，能检验的只有一条：README 和录屏在交之前写完，「已知未做」那一节没漏项。
- 证据：`_bmad-output/implementation-artifacts/deferred-work.md`（32 条原文，封版头已标归档）。
