# 架构文档独立评审：`architecture.md`

| 项 | 值 |
| --- | --- |
| 被评审文件 | `_bmad-output/planning-artifacts/architecture.md` |
| 评审基线 | 2026-11-04 14:33:29，617 行，47,810 字节，SHA256 `2092F9996C5A7B1CF9F733E35AC162672D51AB08E144D6D9C91F0117C2495483` |
| 评审类型 | 架构评审（只评审，不改交付物） |
| 评审视角 | 下一层独立实现者：两人分别按本文写代码，能否写出不兼容的系统 |
| 上游 | `PRD.md`、`product-brief.md`、`prds/prd-MyProject2-2026-11-04/addendum.md`、`decision-log.md`(D-001) |
| 技术栈锁 | Python 3.12 + Flask 3 + SQLite + Jinja2 + pytest（禁 React/MySQL/Redis/MQ/WebSocket） |
| 评审日期 | 2026-11-04 |

> 说明：本文档在评审过程中被作者更新过一次（14:31 → 14:33，新增 §5.5 与 §11 四行）。下列行号以 **14:33 基线**为准；引用格式 `architecture.md:NN` 省略文件名，`PRD.md:NN` 指上游 PRD。若文档再次变动，行号需重新对齐（建议在文首固定 `revision` 字段）。

---

## 0. 结论（Verdict）

**有条件不通过。** 五条 ADR 选的是对的方向，否决理由站得住，14:33 版新增的 §5.5 也补上了三条非 occupancy 写路径的事务边界。但文档仍有**同一份文档内部互相矛盾的硬规则**（事务归属、四态归属、错误映射），按字面实现必然分叉；ADR-001 的"并发证明"按字面**无法执行**，且两个负向对照在逻辑上不成立——它证明不了自己声称证明的东西。

判定：**不可直接作为 Story 拆分的唯一依据**。修完 C-01 ~ C-05 与 H-01/H-02 后可放行（约 6 处规则改写 + 1 张契约表，不需要重写文档）。

评分（自评 /10）：

| 维度 | 分 | 说明 |
| --- | --- | --- |
| 边界与运行拓扑 | 7 | §15 罕见地完整，但启动命令与目录树不一致、`-wal` 与备份口径打架 |
| 依赖方向 | 6 | 四条规则可执行，但规则 2 与 ADR-003 正面冲突 |
| 跨单元契约唯一性 | 4 | `claim_slots` 是全文唯一给出函数体的契约，而它自相矛盾；路由/模板契约缺席 |
| 事务边界 | 4 | 14:33 版有改善（§5.5），但 occupancy 主路径仍无解 |
| 并发裁决 | 5 | 裁决点选对了，证明设计不可执行 |
| 数据形状 | 4 | 时间格式很扎实；`user.active`、审计前后值、booking 生命周期三处缺失 |
| 错误映射 | 5 | 单点映射的思路对，表本身漏项且与示例代码冲突 |
| 安全 | 5 | ADR-004 主体正确，CSRF/失效语义实际无人负责 |
| 可验证性 | 6 | 有变异测试意识（少见的好），但对照 B 恒不成立 |
| Deferred 纪律 | 7 | 每条都有触发条件；但 7 个"必须现在定"的项既不在 ADR 也不在 Deferred |
| 部署运维 | 7 | NFR-2 落地得不错；缺时钟、文件权限、优雅关闭 |
| 上游可追溯 | 5 | FR-7 标记、FR-8 前后值等验收答不出来 |

---

## 1. 评审方法：好架构文档清单

判据只有一条（与文档 §1 自述 `:36-38` 一致）：**两个人分别实现下一层，会不会做出不兼容的选择？** 基于此拆成 12 项可检查条件。

| # | 检查项 | 结果 | 证据 |
| --- | --- | --- | --- |
| C1 | 边界与运行拓扑单一、可执行 | 部分 | `:551-579` 完整；但 `:558` 的 `python -m src.serve` 在 `:517-532` 目录树中不存在 |
| C2 | 依赖方向可机械检查 | 通过 | `:55-60`（`web→app→data`，SQL 只在 `data/`） |
| C3 | 每个跨单元契约有唯一 owner | **不通过** | 5 张表中 3 张无 owner 规则；路由表缺席；`_slot_grid.html` 入参契约缺席（`:328`） |
| C4 | 事务边界显式（谁 BEGIN/COMMIT/嵌套） | **不通过** | `:127-146` 内建 COMMIT，与 `:182-183` 的多表原子写互斥 |
| C5 | 并发裁决单点且可被负向证明 | 部分 | 裁决点正确（`:93`），证明链不成立（`:232`、`:245-247`） |
| C6 | 共享数据形状唯一（时刻/ID/枚举/状态） | **不通过** | `:434-441` 缺 `active`；`:463-470` 缺前后值；booking 无生命周期 |
| C7 | 错误→状态码单一映射且无遗漏 | 部分 | `:85` 漏 `NotFound`；`:143-145` 与 `:170-174` 冲突 |
| C8 | 安全控制有 owner 与失效语义 | 部分 | `:356-367` 主体好；CSRF 跨两个 ADR、措辞不一致 |
| C9 | 每条规则被违反时测试能抓到 | 部分 | `:209-259` 有设计，但 `:245-246` 的对照恒不成立 |
| C10 | Deferred 只含可延后项 | 部分 | `:593-609` 每条有触发条件；但 7 个必需项既不在 ADR 也不在 Deferred |
| C11 | 运行/部署/备份/恢复闭环 | 部分 | `:296` 与 NFR-2 的"停止后复制 .db"口径冲突；无时钟/权限/优雅关闭 |
| C12 | 上游 FR/NFR 逐条可追溯 | 部分 | `:534-549` 覆盖 12 项，但 3 条验收语义无落点 |

---

## 2. 发现清单

严重度定义：**critical** = 按字面实现必然产生错误数据或不可实现；**high** = 两个合规实现会不兼容，且验收测试抓不到；**medium** = 会产生分歧但代价可控；**low** = 表述/一致性问题。

### 2.1 Critical

#### C-01 `claim_slots()` 自持事务，使 FR-4 / FR-7 的"多表原子写"无法按 ADR 实现

- **位置**：`architecture.md:127-146`（`BEGIN IMMEDIATE` → `COMMIT` 全部在函数内） vs `:182-183`（学生创建 = `INSERT booking` + N 条 `INSERT occupancy`；改单 = `DELETE` + `INSERT` + `UPDATE booking`） vs `:60`（规则 4：occupancy 只能经 `claim_slots`/`release_slots` 写）
- **问题**：三条规则同时成立时无解。`booking` 行必须与 occupancy 行同事务提交（`:493` 也这么要求），但 `claim_slots` 在插入 occupancy 后**自己 COMMIT**。
- **两个合规实现**：
  - 实现甲（照抄 D2）：`INSERT booking` → `claim_slots()`。冲突时 occupancy 回滚，**booking 行已提交**，留下一条 0 个 slot 的孤儿预约，直接违反 FR-5"本次请求写入 0 条"（`PRD.md:156`）。
  - 实现乙（保原子性）：外层 `BEGIN IMMEDIATE` 后调用 `claim_slots()` → 内层 `BEGIN` 抛 `OperationalError: cannot start a transaction within a transaction` → 500。为绕开，乙把 `claim_slots` 拆成"不提交"的两个函数——**违反规则 4 与 D2 的"唯一允许的形状"**。
- **附加影响**：`:229` 新增的"拓扑 B 直接调用 `claim_slots()`"依赖当前签名；若按本条的改法调整事务归属，拓扑 B 的定义与断言要同步改，否则测试会在改造后悄悄失效。
- **可执行改法**：把事务归属提到用例层：

```python
# app/booking_service.py
def claim_slots(conn, *, equipment_id, slots, booking_id, kind, created_at):
    """调用方必须在 BEGIN IMMEDIATE 事务内调用；本函数不 BEGIN、不 COMMIT、不 ROLLBACK。
    冲突时抛 Conflict（不自行回滚），由用例统一回滚。"""
```

  并在 ADR-001 增一条硬规则："**事务边界只属于 `app/` 的用例函数；`data/` 与 `claim_slots`/`release_slots` 永不调用 `BEGIN`/`COMMIT`/`ROLLBACK`**"。D2 示例改为用例级伪代码（`with write_txn(conn):`），`IntegrityError` 只在用例层捕获一次。

#### C-02 D2 的示例代码与 D4 的错误映射表互相矛盾

- **位置**：`architecture.md:143-145` vs `:170-174`
- **问题**：D2 的 `except sqlite3.IntegrityError:` 捕获**所有** IntegrityError 并一律 `raise Conflict`（→409）。D4 明写"其他（外键、CHECK）→ 400，**不得吞成 409**"，而 `booking_id` 与 `kind` 的 CHECK（`:109-110`）、`equipment_id` 外键（`:100`）都属于"其他"。同时 D2 **完全不处理** `OperationalError: database is locked`，而 D4 要求"重试 3 次→503"。
- **两个合规实现**：甲粘 D2（CHECK 违规返回 409，busy 返回 500）；乙实现 D4（CHECK 违规 400，busy 重试后 503）。两者都"遵守 ADR-001"，但对同一输入给出 3 种状态码，且甲的 500 直接违反 NFR-1 的 0×5xx。
- **可执行改法**：给出唯一异常分类函数并强制复用：

```python
def classify(exc: sqlite3.IntegrityError) -> type:
    if exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE":
        return Conflict
    return Validation          # FK / CHECK / NOT NULL -> 400
```

  同时在 D2 加 `except sqlite3.OperationalError`（仅 `SQLITE_BUSY`/`SQLITE_LOCKED`）分支，与 D4 的重试策略写在同一处，避免两份。

#### C-03 审计表缺"变更前后值"，FR-8 验收不可满足，且文档对自身来源的引述是错的

- **位置**：`architecture.md:463-470`（字段只有 `actor_id/action/target_type/target_id/created_at`） vs `:477`（"字段沿用 addendum A.5"） vs `addendum.md:34`（A.5 含 `before_json`、`after_json`） vs `PRD.md:202`（"日志各有对应条目，字段包含操作人、动作、对象、**变更前后值**、时间戳"）
- **问题**：不是风格问题，是**上游验收项无法通过**。更严重的是 `:477` 声称"沿用 A.5"，而 A.5 明确有前后值——事实性错误，会让实现者以为已对齐。另外 `target_type='equipment'` 的锁定动作无法记录"锁了哪些 slot"，`target_id` 只能放设备 id → FR-7"每次锁定/解锁均写入操作日志"实际只记了"锁过这台设备"。`:367` 新增的"重置密码原子写"同样要写 `before_json/after_json`，否则日志只有"重置了"，没有"从什么变成什么"。
- **两个合规实现**：甲按 `:463-470` 建表并把 slot 列表塞进 `target_id`（`equipment_id|slot1,slot2`），乙加 `payload_json` 列——审计日志的读取端（FR-8 的日志页）互不兼容。
- **可执行改法**：审计表固定为

```sql
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  actor_id TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('register','login_fail','booking_create','booking_cancel',
                                          'booking_edit','lock','unlock','password_reset','user_deactivate')),
  target_type TEXT NOT NULL CHECK (target_type IN ('booking','equipment','user')),
  target_id TEXT NOT NULL,
  before_json TEXT,          -- 无前态时为 NULL
  after_json  TEXT,          -- 无后态时为 NULL
  created_at  TEXT NOT NULL CHECK (length(created_at)=20),
  CHECK (before_json IS NOT NULL OR after_json IS NOT NULL)
);
```

  并把 `action` 定为封闭枚举。删掉 `:477` 的错误引述，改为逐字段对照表。

#### C-04 `booking` 没有生命周期标记，取消后成为不可判定的僵尸，且能被改单"复活"

- **位置**：`architecture.md:449-455`（BOOKING 无 `status`/`cancelled_at`） vs `:185`（取消 = `DELETE` occupancy + `INSERT audit_log`，**不删 booking**） vs `:475`（"我的预约"由 occupancy 反查）
- **问题**：取消后 `booking` 行仍在、occupancy 为 0。于是"该预约是否已取消"在库里**没有任何可判定依据**：它与"创建失败残留"（C-01）"数据被外部删改"三种状态在数据层无法区分。
- **两个合规实现**：
  - 学生取消路径：删 occupancy + 写审计，`booking` 不动（照 `:185`）。
  - 管理员改单路径：按 `:183` `DELETE 旧 + INSERT 新 + UPDATE booking`。它只按 `booking_id` 找行，**没有任何规则要求它先确认该预约未被取消**。
  - 于是"取消 → 改单"这一串行序列会把已取消的预约**重新写回 N 条 occupancy**，两条请求都返回成功、都写审计，事后审计里同时有 cancel 与 edit，无法判断最终状态。完全符合所有 ADR 字面要求。
- **可执行改法**：任选其一并写进 ADR-001（建议前者，代价最小）：
  - 方案 1：`booking` 加 `state TEXT NOT NULL CHECK (state IN ('active','cancelled'))` + `cancelled_at TEXT`。取消改为 `UPDATE booking SET state='cancelled', cancelled_at=? WHERE id=? AND state='active'`，**断言 rowcount==1**，否则 404/409；改单同样带 `AND state='active'`。
  - 方案 2：取消时直接 `DELETE FROM booking`（occupancy 靠 `ON DELETE CASCADE` 一并删），但此时 `:185` 的"删 occupancy + 写日志"需改为"删 booking"，且 `:106` 的级联行为要重新审视（见 M-03）。
  - 无论哪种，都要补一条规则：**"任何按 booking_id 写 occupancy 的路径，必须在同一事务内重新断言该 booking 处于 active"**。

#### C-05 模板是否允许判定 slot 状态：§2 规则 2 与 ADR-003 正面对立

- **位置**：`architecture.md:58`（"`templates/` 只消费路由传入的只读视图对象，**不查库、不算占用状态**"） vs `:328`（"`_slot_grid.html` … slot 的四态…**只有一处判定逻辑**"）
- **问题**：两句话对"四态由谁算"给出相反答案，而 §2 自称"违反即视为架构缺陷"。这不是措辞问题：它决定了 `_slot_grid.html` 的入参形状，进而决定学生日视图（FR-3，`:540`）与管理员周视图（FR-7，`:544`）能否共用同一个局部模板。
- **两个合规实现**：甲在 `slot_service` 算好 `state` 枚举传模板（违反 `:328` 的字面归属，符合 `:58`）；乙把 occupancy 行与 `now` 传模板、在 Jinja 里算（违反 `:58`，符合 `:328`）。二者共用同一个 `_slot_grid.html` 时必然冲突；若各写一个，FR-3 的"锁定后显示已锁定"与 FR-7 的"锁定态可点解锁"会在两个页面漂移。
- **可执行改法**：保留 `:58`（模板不判），把 `:328` 改写为"四态判定只在 `app/slot_service.build_grid()` 一处，`_slot_grid.html` 只渲染传入的 `state` 字符串"，并补一张入参契约表（见 §3 的 Pair A）。

### 2.2 High

#### H-01 并发测试的成功码与 ADR-003 冲突；拓扑 B 没有对应断言

- **位置**：`architecture.md:232`（"10 并发断言 1×2xx、9×409"）、`:235`（"2xx 响应数 == 1"） vs `:329`（成功一律 **303** See Other） vs `:229`（拓扑 B 直接调用 `claim_slots()`，根本没有 HTTP 状态码）
- **问题 1**：成功路径按 ADR-003 返回 303，不是 2xx。文档没说测试是否跟随重定向。甲 `allow_redirects=False` 数首跳 → 303 被计为失败；乙 `allow_redirects=True` → 计为 200 通过。同一份"证据"两种口径，而 NFR-1 的验收原文（`PRD.md:216`）用的也是"2xx"。
- **问题 2**：`:233` 已修正上一版"每轮 +1 天越过 7 天窗口"的缺陷（改为专用测试设备 + 30 分钟递增，100 轮跨约 2 天）——这条修得好。但 `:232-239` 的断言集合是**为 HTTP 拓扑写的**，`:229` 的拓扑 B 没有 HTTP，`1×2xx/1×409` 在那一组无意义；文档未给拓扑 B 的断言（应为"1 次成功返回 + 1 次抛 `Conflict`，且无 `OperationalError`"）。
- **可执行改法**：断言改为显式集合 `{303} × 1`、`{409} × 1`，并注明"客户端不跟随重定向，303 的 Location 另行 GET 一次且断言 200"；为拓扑 B 单列一组断言（成功返回/`Conflict` 异常计数）；同步修改 `PRD.md:216` 的措辞或在本文注明"2xx 指 303 之后的最终 200"。

#### H-02 并发测试存在结构性假阳性：重叠未被证明，两个负向对照都不成立

- **位置**：`architecture.md:230`（`Barrier(2).wait()`）、`:245-247`（对照 A/B/C）
- **问题**：
  1. **重叠未被证明**：栅栏只保证"同时开始发请求"，不保证两个请求的 `claim_slots` 时间区间相交。而"1×成功 + 1×409"恰好也是**完全串行**两次请求的结果。断言集合没有区分"并发"与"顺序"的能力 → 主证据与被测性质无关。
  2. **对照 A（共用连接必须失败）会因错误的理由失败**：共用一个 `sqlite3.Connection` 时，第二个线程的 `BEGIN IMMEDIATE` 抛 `cannot start a transaction within a transaction`（或 `check_same_thread` 报错）→ 500 → "测试失败"成立，但它失败的原因与"并发被串行化"毫无关系。这个对照无法区分"测试无效"与"实现有 bug"。
  3. **对照 B（只删约束）恒不成立**：`claim_slots` 自带预检（`:131-134`），删掉 `uq_occupancy_slot` 后第二个请求的预检仍会读到已提交行并返回 409 → **永远不会出现"某轮 2 个 2xx"**。作者会看到对照 B"失败"，从而误以为"证明有效"，实际上该对照证明的是它自己不可能成功。
  4. **对照 C（短路预检）在同进程下无判别力**：若并发本来就是假的，因果断预检而依靠约束的路径在串行下也全绿。
- **可执行改法**（三条缺一不可）：
  - **确定性交错测试（主证据，替代 HTTP）**：两连接手工排序——A `BEGIN IMMEDIATE` + INSERT（不提交）；B `BEGIN IMMEDIATE` 断言 `SQLITE_BUSY`；A `COMMIT`；B 重试 `INSERT` 断言 `IntegrityError`；B `ROLLBACK`；断言行数 == 1。这条不依赖调度，可 100% 复现。
  - **重叠证明**：测试配置下在 `claim_slots` 入口加 `TEST_CLAIM_HOLD_MS`（非测试环境为 0），断言两侧 `BEGIN IMMEDIATE` 的单调时钟区间相交；不相交则该轮判"未验证"并计失败。
  - **对照 B'**：删约束 **且** 短路预检 → 必须出现 2 次成功；单独删约束不算变异。对照 A 改为"共用连接 + 断言不产生 500 且两个请求都成功"，才是有意义的反例。

#### H-03 NFR-1 的"0 × 5xx"与 D4 允许的 503 互斥，且重试预算无上界推导

- **位置**：`architecture.md:174`（"仍失败返回 503，且 NFR-1 判该轮失败"） vs `:237`（"5xx 响应数 == 0，`SQLITE_BUSY` 计为失败"） vs `:232`（10 并发 × 20 轮）
- **问题**：ADR 自己允许了一个必然导致验收失败的结果。10 并发写同一 key，`busy_timeout=5000` + "重试 3 次 × 50ms" 的最坏等待 ≈ 5s + 3×5s + 150ms ≈ 20s（每次重试都会重新等满 `busy_timeout`），远超客户端与测试超时；而单次事务只有毫秒级，说明预算设计没有依据。
- **可执行改法**：把预算写成可推导的形式并作为架构约束：单事务上限 ≤ 20ms（用测试断言），10 并发最坏排队 200ms，`busy_timeout=1000` 已足够；重试仅针对 `BEGIN IMMEDIATE` 失败且最多 2 次、退避 20/50ms，总预算 ≤ 1.2s < 客户端超时。三条数字写进 D3/D4，并用 `test_booking_latency_p99` 守住。若不接受该推导，则必须把 NFR-1 的 0×5xx 降级——但不能两者都留。

#### H-04 `user.active` 被 ADR-004 使用，但数据模型里不存在

- **位置**：`architecture.md:364`（"比较 `pv == user.password_version` 且 `user.active`"） vs `:434-441`（USER 字段：`id/student_no/role/password_hash/password_version/created_at`）
- **问题**：`PRD.md:302` 写明"靠管理员注销误注册账号兜底"，但注销在模型层没有落点。三种合规实现：甲加 `active INTEGER NOT NULL DEFAULT 1`；乙加 `deactivated_at TEXT`；丙直接 `DELETE FROM user`（并踩上 `booking.owner_id` 外键与审计缺失）。三者的"停用后旧 Cookie 是否失效"行为各不相同（丙因查不到用户 401；甲的 `active=0` 也 401；乙若把 `deactivated_at IS NULL` 写反则返 200）。
- **可执行改法**：USER 增加 `active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))` 与 `deactivated_at TEXT`（同事务写），并规定"`@login_required` 判定顺序：用户不存在 → 401；`active=0` → 401；`pv` 不匹配 → 401"。

#### H-05 `booking.equipment_id` 与 `occupancy.equipment_id` 是两个事实源，改单时更新哪边未定

- **位置**：`architecture.md:452`（BOOKING 有 `equipment_id`）、`:457`（OCCUPANCY 也有）、`:183`（改单只写"`UPDATE booking`"，未说更新哪些列）、`:83`（"occupancy 是唯一事实源"仅限定 slot 范围）
- **问题**：改单允许换设备（`PRD.md:183`"修改预约的设备或 slot 集合"）。此时必须同时改两处，但没有任何规则要求。实现甲只更新 occupancy（因为"occupancy 是事实源"），`booking.equipment_id` 停滞在旧值；实现乙只更新 booking，occupancy 停在旧设备上。
- **后果**：CSV 的"设备"列（`PRD.md:201`，取 booking）与"我的预约"（取 occupancy）显示不同设备；更糟的是甲的实现下 `occupancy.equipment_id=E2` 而 `booking.equipment_id=E1`，任何走 booking→occupancy join 的查询都会出现跨设备的空结果。
- **可执行改法**：二选一并写死——(a) 删除 `booking.equipment_id`（设备归属只由 occupancy 决定，booking 只保留 owner/时间戳）；或 (b) 保留但规定"改单必须在同一事务内 `UPDATE booking SET equipment_id=?` **且** 断言 `SELECT DISTINCT equipment_id FROM occupancy WHERE booking_id=?` 恰为 1 行且等于该值"。推荐 (a)，并加 `test_booking_equipment_consistency`。

#### H-06 改单与创建的校验规则没有唯一 owner，FR-4 与 FR-7 必然各写一份

- **位置**：`architecture.md:489`（"校验只在 `app/` 做一次"）、`:541`（FR-4 → `booking_service`）、`:544`（FR-7 → `admin_service`）、`:349`（"规则只能有一份，在 `app/` 层"）
- **问题**：`:489` 只说"在 `app/` 做一次"，但 `booking_service` 与 `admin_service` **都在 `app/` 下**——这句话没有排除两处各写一份，反而像是允许。连续性、≤8 个、`:00/:30` 对齐、开放时间内、7 天窗口、2 小时截止这 6 条规则，在两个 service 里各实现一次仍然完全合规。`PRD.md:189` 又要求"改单后的 slot 集合仍须连续且不超过 8 个；开始前 2 小时限制同样适用"——架构从未把这句话落到某个函数上。
- **典型分叉**：学生创建禁止"已开始"的 slot（`PRD.md:148`）；改单的 2 小时规则若由 `admin_service` 自行实现，很容易只判"首个 slot 距现在 > 2h"，从而允许把预约改到**已经过去的** slot（只要整段都在过去，`now - first > 2h` 恒成立）。一条预约被搬进历史，周视图与 CSV 立刻出现"未来不可见、过去可见"的脏数据。
- **可执行改法**：定义唯一校验器并写进 §13 模块表：

```python
# app/slot_rules.py —— 唯一校验入口，booking_service 与 admin_service 都必须调用
def validate_slot_set(*, equipment, slot_starts, actor, now_utc, mode):
    """actor: 'student' | 'admin'; mode: 'create' | 'edit'"""
```

  规则固定 6 条，且**明确 admin 不是"绕过 2 小时/7 天"的例外**；若要给管理员开后门，必须在 ADR 里写出来（`:187` 只否认了"强制覆盖冲突"，没说时间窗）。

#### H-07 锁定与预约共用键空间是对的，但"取消+锁定"没有单事务形态，lock 行也没有身份

- **位置**：`architecture.md:105-110`（`kind`/`booking_id` 的 CHECK）、`:121`（共用键空间）、`:184`（锁定 = `INSERT`/`DELETE` `kind='lock'`）
- **问题（4 个具体洞）**：
  1. **"把某时段关掉"在已有人预约时是复合操作**：必须"取消预约 + 锁定 slot"。ADR 只提供两个独立事务，`:187` 又禁止"强制覆盖"。于是实现甲写成两次请求（取消 → 锁定），中间窗口学生可抢；实现乙在 `admin_service` 里写一个复合事务（先删 occupancy 再插 lock 行），**这一路径不经过 `claim_slots`，违反 `:60`**。两者都合规。
  2. **lock 行无分组**：一次"锁定 08:00–12:00"写 8 行，仅共享 `created_at`；解锁 4 行就产生半个锁，审计也无法表达"这是一次锁定动作"。
  3. **lock 行无 actor**：`occupancy` 没有 `created_by`，锁定是谁做的只能去 audit 里猜。
  4. **解锁的 DELETE 条件未对称约束**：`:184` 只说删 `kind='lock'` 行；若实现写成 `DELETE FROM occupancy WHERE equipment_id=? AND slot_start IN (...)`（漏 `kind`），会**删掉学生的预约行**且不写审计——正是"共用键空间"最危险的失败模式。
- **可执行改法**：
  - 增加 `lock_group_id TEXT`（一次锁定动作一个 uuid）与 `created_by TEXT`；解锁以 group 为单位，`DELETE ... WHERE lock_group_id=? AND kind='lock'`。
  - 规定"关停某时段"为**单个用例** `admin_service.close_slots(equipment_id, slots, reason)`：单事务内删除该设备该组 slot 上的全部 occupancy（预约与锁）+ 写审计 + `INSERT kind='lock'`，并注明这是规则 4 的**唯一例外**，且必须由 `claim_slots`/`release_slots` 组合实现而非裸 SQL。
  - 加对称测试：解锁后断言 `SELECT COUNT(*) FROM occupancy WHERE kind='booking'` 不变。

#### H-08 开放时间收缩的校验有规则了，但缺时间边界与"不可见占用"的处理

- **位置**：`architecture.md:267`（§5.5：缩短开放时间时"查出该设备已有占用中、但不再落在新开放区间内的 occupancy 行；有则整体拒绝"） vs `PRD.md:121`
- **问题**：14:33 版新增的 §5.5 补上了"有则整体拒绝，409，不自动迁移"的语义——这是实质进步。仍缺三件事：
  1. **时间边界未定**：扫"全部历史"还是"从今天起"？扫全部 → 管理员永远改不了历史设备的开放时间（台账上总有过去的合法预约）；只扫未来 → 历史行留在库里，而网格由 open hours 派生 slot，这些行**不会渲染**，成为不可见但继续阻塞的占用（学生看不到占用却总 409，无法自查）。
  2. **409 的响应体未要求列出越界 slot**，与 FR-5 的 409 契约（`PRD.md:158`）不一致。
  3. **"不自动迁移"之后没有下一步**：管理员被拒后必须手工取消/改单（`PRD.md:334`），但没有规则说明"先取消再保存"这个复合操作的顺序，也没有提示性视图。
- **可执行改法**：在 §5.5 写死：扫描区间 `slot_start >= 本地今天 00:00`；历史越界行在网格上渲染为"已占用（窗口外）"，不得静默隐藏；409 响应体列出全部越界 `(equipment_id, slot_start)`；并在 §14 的 FR-2 行（`:539`）挂上 §5.5。

#### H-09 CSRF 与会话失效并未被 ADR-004 覆盖（它只是被提到）

- **位置**：`architecture.md:366`（ADR-004 只有一行"会话内生成随机 token，模板注入隐藏字段，POST 校验"） vs `:333`（ADR-003："与会话内 token 做**常量时间比较**，失败返回 400"） vs `:354`（ADR-004 的 Binds 只有 FR-1/NFR-2/NFR-4）
- **问题**：CSRF 的**归属**在两个 ADR 之间摇摆，两处措辞不一致（一处有"常量时间/400"，一处没有），且五个关键语义全部未定：
  1. **校验顺序**：CSRF 在 `@login_required` 之前还是之后？若在前，未登录 POST 返回 400，违反 `PRD.md:104`"未登录返回 401"；若在后，无会话时 401。两个实现都能自称合规。
  2. **是否与用户绑定/是否轮换**：登录、重置密码（`pv` 递增）、登出时是否换 token？不换 → 存在登录 CSRF 与旧 token 复用。
  3. **会话失效的覆盖面**：`pv` 只覆盖"重置密码"，未覆盖"停用账号后请求进行中"、"角色变更"、"登出后重放"。`:490` 只解决了"越权 403"，没解决"失效时机"。
  4. **`session.permanent` 未规定**：`PERMANENT_SESSION_LIFETIME=12h`（`:361`）只在 `session.permanent = True` 时生效；不设则退化为"关浏览器即失效"，12 小时的绝对过期承诺是假的。两个实现一个设一个不设，行为差一个数量级。
  5. **401 与 403 的分工**：`:365` 说 `@admin_required` → 非管理员 403，但**匿名**访问 `@admin_required` 是 401 还是 403 未定（学生看到"请登录"还是"无权"，测试断言会差一个状态码）。
- **可执行改法**：把这五点写成 ADR-004 的编号子项（R1…R5），并把 `:333` 的 CSRF 段落删除、改为"见 ADR-004 R3"，保证单一出处。

### 2.3 Medium

| ID | 位置 | 问题 | 改法 |
| --- | --- | --- | --- |
| M-01 | `:102-104`、`:327` | `slot_start` 的 CHECK 只保证"20 字符形状"：分钟位是两位数字，`10:17` 能通过；月份/日期也不校验（`2026-13-45T99:99:00Z` 通过 GLOB）。"对齐 :00/:30"只活在应用层。锁路径若不做同样校验，会写入一个网格永不渲染、学生永不可约的 key | CHECK 收紧：`substr(slot_start,15,2) IN ('00','30')`，并加 `date(slot_start) IS NOT NULL` |
| M-02 | `:398`、`:445-446`、`:423` | `open_start`/`open_end` 是**墙钟时刻**，不是瞬时，却套用了 ADR-005"每个时刻 20 字符"的说法；格式（`08:00` 还是 `08:00:00`）与"是否本地时间"均未定。`test_time_format` 声称"所有时间列匹配 20 字符"，若 `open_start` 是 5 字符则该断言自相矛盾；若排除它又没有白名单 | 明确：`open_start/open_end` 是 `HH:MM` 本地墙钟文本（5 字符），**不属于** ADR-005 的"时刻"；`test_time_format` 改为显式白名单 `[occupancy.slot_start, booking.created_at, booking.updated_at, user.created_at, audit_log.created_at]` 逐列断言。另定"开放时间不是 30 分钟整数倍"的处理（建议要求输入必须对齐，否则 400） |
| M-03 | `:106` | `booking_id ... ON DELETE CASCADE` 造出**第二条 occupancy 写路径**：任何 `DELETE FROM booking` 都会绕过 `claim_slots`/`release_slots` 静默删除占用行且不写审计，直接违反 `:60` 的规则 4 | 若采纳 C-04 方案 2（取消即删 booking），把审计与删除固定在同一用例内并加测试"任意 DELETE booking 必伴随 1 条 audit"；若采纳方案 1，去掉 CASCADE 改 `RESTRICT`，让"删 booking"在物理上不可能 |
| M-04 | `:297` vs `:494` | `GET /health` 要求返回 200，而 §11 规定"路由第一行加 `@login_required`/`@admin_required`"。健康检查会拿到 401/302，NFR-2 的启动断言（`PRD.md:226`）直接失败 | `:494` 加免鉴权清单：`/health`、`/login`、`/register`、`/static/*`；并把这些路由写进路由表 |
| M-05 | `:295` | 迁移只说"按序号执行 + `user_version` 记录到第几号"，未规定"单个迁移的 DDL 与 `user_version` 递增在同一事务"。半途失败会留下"表已建、版本没升"或"版本升了、表没建" | 写死"每个迁移文件 = 一个事务：`BEGIN IMMEDIATE` → DDL → `PRAGMA user_version = n` → `COMMIT`"，启动时断言 `user_version` ≤ 可用迁移数 |
| M-06 | `:159-164`、`:295` | `PRAGMA journal_mode = WAL` 是**库级持久设置**，却放在每请求连接上。已为 WAL 时通常是 no-op，但当另一连接持有排他锁时该 PRAGMA 可能返回 `database is locked`，等于给只读页面（FR-3）凭空加了一个失败面 | 移到启动/迁移阶段执行一次；每请求连接只保留 `foreign_keys`、`busy_timeout`、`synchronous` |
| M-07 | `:145`、`:152` | 409 的冲突列表在 `ROLLBACK` 之后重查。若触发冲突的那一行在此期间被取消，重查结果**不含肇事 slot**；若别人又提交了新行，列表里混入无关 slot。违反 `PRD.md:158` | 在 `IntegrityError` 之前先记录本次尝试写入的 slot 集合，409 响应 = 本次尝试 ∩ 回滚后实际被占，空交集时回退为"整组列出" |
| M-08 | `:544`、`PRD.md:186` | FR-7 要求"本周视图…**冲突**、锁定、改单异常有可见标记"。但唯一约束使"冲突"在数据层**不可能存在**（提交时即被拒），"改单异常"没有任何字段承载 | 在 §14 改写：周视图三类标记 = 锁定（`kind='lock'`）、改单（`booking.updated_at > booking.created_at`）、开放时间冲突（occupancy 落在当前 open hours 之外）。删掉"冲突"标记并回写 PRD |
| M-09 | `:85`、`:59`、`:365` | 错误映射表列了 `Conflict/Unauthorized/Forbidden/Validation`，但 §2 规则 3 还引入了 `NotFound`，映射表**没有它**；CSRF 失败也归 400，与 `Validation` 同码不可区分；匿名访问 `@admin_required` 的 401/403 仍未定（`:490` 只定义了"越权 403"） | 映射表补 `NotFound → 404`、`CsrfError → 400`；明确"匿名 → 401，已登录非管理员 → 403"；页面路由未登录是否 302 也要一句话定死 |
| M-10 | `:491`、`PRD.md:201` | 14:33 版已固定 CSV 的 BOM 与列序（好），但仍未定"slot 开始/结束"用 UTC 还是北京时间、"状态"列的取值集合（`active`/`已预约`/`有效`）。CSV 是唯一归档手段，格式漂移会直接损坏对账可比性 | 写死：时间列按 `Asia/Shanghai` 渲染为 `YYYY-MM-DD HH:MM`（与 `:487` 的页面口径一致），状态固定为 `已预约`；加 `test_export_csv_header_and_rows` |
| M-11 | `:558`、`:517-532`、`:296`、`:579` | 部署节 5 个缺口：(1) `python -m src.serve` 在目录树里不存在；(2) `app.py` 在根而 `templates/` 在 `src/` 下，`template_folder`/`static_folder` 未指定，两人会一个 404；(3) `:296` 警告"不要漏 -wal"，而 NFR-2 验收要求"停止服务后复制 .db"——非优雅停止时 `-wal` 仍在，只复制 `.db` 会丢最近提交；(4) 无"主机时钟必须同步（NTP）"前提，而 2 小时截止/7 天窗口/已开始判定**全部**依赖本机时钟；(5) `data/lab.db` 含学号与密码哈希，文件权限未规定 | 补 `src/serve.py`；把 `create_app(template_folder="src/templates", static_folder="src/static")` 写进 §13；NFR-2 的复制步骤改为"先 `VACUUM INTO` 或复制 `.db` + `-wal` + `-shm` 三者"；加"部署前提：主机启用 NTP"；加"`data/` 权限 700" |
| M-12 | `:267` vs `:271` | §5.5 内部自相矛盾：`:267` 要求"查出…有则整体拒绝"（先查后拒），`:271` 却说"先让数据库判定…不要为它们各写一套'先查一下'"。开放时间收缩**没有对应的数据库约束可依赖**，必须查——照 `:271` 写的实现者会以为该路径可以省掉查询 | `:271` 改为"注册/重置密码先让数据库判定；开放时间收缩是唯一需要先查再写的路径，因为它没有可依赖的约束" |
| M-13 | `:233`、`:232` | 并发测试改用"专用测试设备 + 30 分钟递增"解决了 7 天窗口问题，但引入新前提：该设备的 `00:00–23:30` 开放时间与"1 台设备 100 轮 × 2 请求"会在 `occupancy` 留下 100 行测试数据，且拓扑 A 走的仍是生产校验（含"未来 7 天"）。文档未说明测试库是临时库还是生产库、如何清理 | 明确"并发测试一律在临时库上跑（`LAB_DB_PATH` 指向 tmp），结束后删除"，并在 `:257` 的证据留存里注明库路径 |
| M-14 | `:490` vs `PRD.md:262` | §11 新增行写"学生只能改/取消自己的 `booking`"，但 PRD §6 明确"不提供学生直接改约：改期只能取消后重新预约；改单是管理员能力"。这条一致性约定等于凭空给了一个 PRD 里不存在的学生改单能力，照它实现会多出一组路由与越权判定 | 改为"学生只能取消自己的 booking（不改约）；管理员走独立路由"，并与 §14 的 FR-6 行（`:543`）一致 |

### 2.4 Low

| ID | 位置 | 问题 | 改法 |
| --- | --- | --- | --- |
| L-01 | `:38` | "其余进**第 9 节** Deferred"，而 §9 是 ADR-005，Deferred 在 §17。前向引用错位会让读者以为 Deferred 已被 ADR 取代 | 改为"第 17 节" |
| L-02 | `:509` vs `:98-114`、`:120` | §12 说需要"支持 `STRICT` 与部分索引"，但 DDL 未用 `STRICT`，且 `:120` 明确**不用**部分索引。这是从否决方案里残留的表述 | 删除"`STRICT` 与部分索引"，改为"需支持命名 UNIQUE 约束与 `GLOB` CHECK（SQLite ≥ 3.24）" |
| L-03 | `:485` | "路由用复数资源名（`/bookings`、`/equipment`）"——`/equipment` 不可数，示例与规则不符；且全文无路由清单 | 示例改 `/equipments` 或把规则改为"集合资源用复数，不可数名词除外"；至少补一张 6 行路由表（方法/路径/鉴权/写哪张表） |
| L-04 | `:332` | 提到"用户输入（备注、设备名）不得使用 safe 过滤器"，但 `BOOKING` 无 `note` 字段 | 要么删掉"备注"，要么在 BOOKING 加 `note TEXT CHECK (length(note) <= 200)` |
| L-05 | `:172` | 用异常消息文本 `"UNIQUE constraint failed: occupancy.equipment_id, occupancy.slot_start"` 判定冲突，依赖 SQLite 文案（随版本可能变，且一旦加列就失效） | 改用 `exc.sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE"`，并用 `exc.sqlite_errorcode` 区分 |
| L-06 | `:477`、`:604`、`:616` | 审计日志"不清理、不分页、无索引"，而 `:604` 只按"单周记录 > 5000 行"触发分页。审计表是唯一单调增长的表，FR-8 的日志页会线性退化 | 现在就加 `CREATE INDEX idx_audit_created ON audit_log(created_at DESC)`，并把分页触发条件改为"审计表 > 20000 行" |
| L-07 | `:579` vs `:293` | `:579` 说"断电后重启即恢复"，`:293` 说 `synchronous=NORMAL` 下"断电时可能丢失最后几个已提交事务"。前者是承诺，后者是事实，两句并置会让读者误判持久性等级 | 改为"断电后库不损坏、可恢复到最后一次 checkpoint；最后若干已提交事务可能丢失（已接受）" |


---

## 3. 对抗性攻击：三对"完全合规但不兼容"的下级单元

构造约束：每一对的两个单元**都不违反任何一条 ADR 的字面要求**，且都能通过文档现有测试。若某一对能被现有测试抓到，则说明该测试是有效的（此处三对都抓不到）。

### Pair A — 共享数据形状冲突：`_slot_grid.html` 的两种入参

| | 单元 A：学生日视图 | 单元 B：管理员周视图 |
| --- | --- | --- |
| 模块 | `web/slots.py` + `app/slot_service.py`（FR-3，`:540`） | `web/admin.py` + `app/admin_service.py`（FR-7，`:544`） |
| 路由 | `GET /slots?equipment_id=…&date=…` | `GET /admin/week?week=…` |
| 读的表 | `equipment`、`occupancy` | `equipment`、`occupancy`、`booking`、`user` |
| 遵守的条款 | `:58`（模板不算占用态）→ 在 service 里算好 `state`，传 `slots=[{start, state}]` | `:328`（四态判定只在 `_slot_grid.html`）→ 传 `occupancy_rows` + `now`，在 Jinja 里算 |
| 互不兼容点 1 | 枚举只有 `free/booked/locked/closed` | 模板需要 `locked_by_admin`（可点"解锁"）；A 的枚举没有该维度 |
| 互不兼容点 2 | `now` 由 service 取一次 `now_utc()`，全页一致 | `now` 由模板过滤器取，一页 28 个 cell 各取一次，跨秒时会自行分裂 |
| 互不兼容点 3 | 传入的 `start` 是 UTC 20 字符 | 模板按本地 `HH:MM` 字符串做字典序比较 `slot_start >= now`（UTC 串 vs 本地串）→ 边界全错 |
| 现有测试能否发现 | 否。`test_slot_view.py` 与 `test_admin_edit_lock.py` 各测各的，模板是"同一份文件"这件事没有任何契约测试 | 同左 |
| 崩溃后的表现 | 同一个 slot 在 14:00 边界上，学生页显示"可预约"、管理员页显示"不可预约"，两边都"通过了自己的验收" | 同左 |

**修复**：定义唯一契约（可粘贴）：

```python
# app/slot_service.py —— 唯一四态生产者（FR-3 与 FR-7 共用）
SlotState = Literal["free", "booked_by_self", "booked_by_other", "locked", "closed_past", "closed_window"]
def build_grid(*, equipment, local_date, viewer_id, role, now_utc: str) -> GridVM: ...
```

`_slot_grid.html` 只判断 `cell.state` 是否等于某值，**不做任何比较运算**；模板契约（变量名、枚举值、是否可编辑）列为 §11 的一张表。

### Pair B — 同一实体两个所有者："这张预约还在不在"

| | 单元 A：取消用例 | 单元 B：周视图 / 导出 |
| --- | --- | --- |
| 模块 | `app/booking_service.release_slots()`（`:543`） | `app/admin_service.week_view()`、`app/export_service.csv()`（`:544`、`:545`） |
| 入口 | `POST /bookings/<id>/cancel` | `GET /admin/week`、`GET /admin/export.csv` |
| 遵守的条款 | `:185`（只删 occupancy + 写 audit，不碰 booking）、`:475`（occupancy 反查） | `:475`（"由 occupancy 反查"）+ `:452`（BOOKING 有 equipment_id）+ `PRD.md:201`（CSV 列取 booking_id 与设备） |
| 事实源 | 认为"occupancy 有行 ⇒ 预约存在" | 认为"booking 有行 ⇒ 预约存在"（周视图要显示 booking_id 与设备，join 起点必须是 booking） |
| 串行后的结果 | 取消后 occupancy = 0，booking 仍在 | 周视图/CSV 列出该 booking：booking_id 有值、slot 列表为空、设备有值 |
| 谁对 | PRD 说"已取消不导出"（`PRD.md:201`） | 但 A 的实现没有留下任何"已取消"标记，B 无法过滤 |
| 现有测试能否发现 | 否。`test_cancel_booking.py` 只断言"occupancy 行数 = 0"；`test_export_audit.py` 用新数据跑，不会先取消再导出 | 同左 |
| 附加损伤 | 若 B 用 `LEFT JOIN occupancy`，会导出一行"设备=显微镜、slot 开始=NULL"的 CSV 行，直接破坏"CSV 是唯一可信归档"这一 SM 前提 | 同左 |

**修复**：C-04 的 `booking.state`。并写一条归属规则："`booking` 拥有身份与生命周期，`occupancy` 拥有时段；**任何查询在判断'该预约是否有效'时只允许读 `booking.state`，在判断'它占了哪些 slot'时只允许读 `occupancy`**"。

### Pair C — 两条互相矛盾的状态变更路径

| 路径 | 学生取消 | 管理员改单 |
| --- | --- | --- |
| 模块 | `booking_service.release_slots()`（`:543`） | `admin_service.edit_booking()`（`:544`） |
| 路由 | `POST /bookings/<id>/cancel` | `POST /admin/bookings/<id>/edit` |
| 事务 | `DELETE occupancy WHERE booking_id=?` + audit（`:185`） | `DELETE 旧 + INSERT 新 + UPDATE booking`（`:183`） |
| 前置校验 | 首 slot 前 ≥ 2h、owner 匹配（2h 规则只在 `:401` 出现，无函数落点） | **文档未要求任何校验**（`:183` 的动作列里没有校验项） |
| 遵守的条款 | ADR-001 D5、ADR-003、`:493` | ADR-001 D5、`:187`（不强制覆盖冲突） |

**矛盾 1：顺序敏感，两种顺序都"成功"。**

- 序列 ①（学生先）：取消提交 → occupancy=0，booking 存活 → 管理员改单：`DELETE 0 行` + `INSERT N 行` + `UPDATE booking` → 成功。**已取消预约复活**，两个操作各写一条审计，没有任何 409/400。
- 序列 ②（管理员先）：改单把 slot 从 S 挪到 S′ → 学生取消：删 S′ → 成功。结果正确。
- 同一对操作、同一对输入，结果取决于谁先提交，且两条路径都返回 303。`booking_id` 不变、`occupancy` 最终形状不同。

**矛盾 2：两条路径对同一条时间规则的解释不同。**

- 学生取消被 2 小时规则挡住（`PRD.md:172`），但架构只说"用 UTC 瞬时比较"（`:401`），没说谁在哪个事务里判。
- 管理员改单没有这条规则（`:183` 未列，`PRD.md:189` 那句"同样适用"没有落点，见 H-06）。管理员把预约改到 **1 小时前**也能成功（不存在"首个 slot 在过去"的检查）。
- 结果：学生无法取消、管理员却能把同一条预约搬到过去。两条路径都 100% 符合 ADR 字面。

**修复**：三件事一起做——(1) `booking.state` 状态机（C-04）；(2) 所有变更路径统一走 `slot_rules.validate_slot_set(..., mode=...)`，并显式写"admin 不豁免 2h/7d"（H-06）；(3) 每个变更用例都必须 `UPDATE booking SET updated_at=? WHERE id=? AND state='active'` 并断言 `rowcount==1`，否则 409（"该预约已被取消"）。补对抗测试：`test_cancel_then_edit_rejected` 与 `test_edit_then_cancel_ok`。

---

## 4. 重点怀疑对象的逐项回答

### 4.1 ADR-001 的并发证明"真能证明"吗？

**不能。** 它证明的是"最终状态只有 1 行"，而这一性质**在完全串行的两次请求下同样成立**；同时两个负向对照都不成立（H-02）。四处具体原因：

1. 重叠未证明（栅栏在 HTTP 之前，`:230`，见 H-02.1）。
2. 因 `BEGIN IMMEDIATE` 串行化，生产路径的 409 **永远来自预检**（`:131-134`），`IntegrityError` 分支在正常运行中几乎不可达 → 主证据考察的是预检，而不是被声称的约束。真正考察约束的只有对照 C，而 C 在没有真实并发时必然全绿。
3. 对照 B 恒不成立（删约束后预检仍 409，`:246`）→ 作者会误判为"对照有效"。
4. 测试口径自相矛盾：成功码是 303 不是 2xx（`:235` vs `:329`，H-01）。`:233` 已修掉"第 8 轮越过 7 天窗口"的问题——这条修得对，但它只解决了四层里最表面的一层。

**一个真能证明的最小替代**（建议直接替换 `:209-259`）：

| 层 | 内容 | 断言 |
| --- | --- | --- |
| L1 结构 | `PRAGMA index_list` / `index_info` | 存在 `unique=1, origin='u'`，列序 `(equipment_id, slot_start)` |
| L2 确定性交错 | 两连接手工排序：A 持写锁不提交 → B `BEGIN IMMEDIATE` → A 提交 → B 插入 | B 得到 `SQLITE_BUSY`；B 重试插入得到 `SQLITE_CONSTRAINT_UNIQUE`；最终 1 行。**不依赖调度** |
| L3 重叠证明 | 测试钩子 `TEST_CLAIM_HOLD_MS` + 记录 `BEGIN IMMEDIATE` 的单调时钟区间 | 两区间相交；不相交则该轮判"未验证"并计失败 |
| L4 端到端 | 真实 HTTP + 303/409 口径固定 | 1×303、1×409、0×5xx、该 key 1 行、该 booking_id N 行 |
| L5 变异 | 删约束 **且** 短路预检；另做"共用连接"反例 | 变异后必须 2 次成功；共用连接下必须 2 次成功且 0×5xx（证明串行化确实发生） |

### 4.2 多 slot 原子性证明是否足够？

**不够。** 现有 Layer 4（`:251-255`）只覆盖"提交时第 3 个已被占 → 409 + 0 行"，缺三件事：

- **并发下的整组拒绝**：`10 请求 × 4 连 slot` 只断言"成功数 = 行数/4"，无法排除部分写入（部分写会让该式出现非整数，但四舍五入或整除去尾时会被吞掉）。应改为逐 booking 断言：每个成功响应的 `booking_id` 在 occupancy 中恰好 4 行、slot 连续、且与请求体完全相等。
- **`executemany` 部分插入的回滚**：必须显式断言 `booking` 表行数不变 **且** 该 `booking_id` 有 0 行，而不只是"总行数不变"（C-01 的孤儿 booking 就是这样漏过的）。
- **同一请求内的重复 slot**（`slot=A&slot=A`）：`executemany` 会在第 2 行触发唯一冲突 → 409。PRD 未定义，属于"同一请求自冲突"。应明确"提交前去重后数量不等 → 400"或"按 409 处理"，否则两实现一个 400 一个 409。

### 4.3 管理员改单与取消的事务边界

三条都必须补（当前一条都没有）：

1. **归属**：事务由 `app/` 用例开启（C-01），`claim_slots`/`release_slots` 不开关事务。`:261-271` 的 §5.5 只覆盖了三条**不写 occupancy** 的路径，主路径仍是空白。
2. **2 小时/7 天/连续性校验必须在事务内、且在读取 occupancy 之后执行**；否则存在 TOCTOU：读到首 slot 在 3 小时后 → 管理员改到 1 小时后 → 学生取消仍通过。`:493` 只规定了"写在一个事务"，没规定"读与判也在同一个事务"。
3. **状态断言**：`UPDATE booking … WHERE state='active'` + `rowcount==1`（C-04 / Pair C）。

### 4.4 锁定与预约共用键空间有漏洞吗？

**有，5 个**：lock 行无分组、无 actor；"取消+锁定"没有单事务形态；解锁的 DELETE 条件没有"必须带 `kind='lock'`"的对称测试；锁定不校验 slot 对齐/开放时间（M-01），可写入永不渲染的 key；**锁定跨多 slot 的原子性**未写（`:184` 只写了单条 INSERT 的失败后果），逐条插入中途失败会留下半个锁。详见 H-07。

### 4.5 UTC 文本唯一键与 slot 生成是否自洽？

**基本自洽，边角有 3 个洞**：

1. `slot_start` 的 CHECK 只锁定"20 字符形状"，不锁对齐、不锁真实日期（M-01）→ "同一物理 slot 只有一种字符串"成立，但"字符串一定是合法 slot"不成立。
2. `open_start/open_end` 是本地墙钟，格式未定，且被 ADR-005 的"每个时刻 20 字符"（`:394`）整体表述吞掉（M-02）→ 派生 slot 的**输入**形状没定，输出再严格也没用。
3. `now` 的截断规则未定：比较 `slot_start >= now_utc` 时（`:401`），`now` 是 `2026-11-05T06:00:00.437Z`（26 字符）还是截断到秒？同一秒内的边界行为两种实现不同（"该 slot 刚开始"是否可约）。应在 `core/timeutil.now_utc()` 写死"返回秒级截断的 20 字符"。

### 4.6 CSRF / 会话失效是否被 ADR-004 覆盖？

**没有。** 见 H-09 的五点。一句话总结：ADR-004 定义了"登录态怎么存"和"口令怎么失效"，但没有定义"**请求是否可被伪造**"与"**失效发生在请求中途时怎么处理**"。CSRF 的规则寄居在 ADR-003 的一句话里（`:333`），与 ADR-004 的措辞不一致（一处有常量时间比较 + 400，一处没有）。14:33 版新增的"重置密码原子写"（`:367`）解决了日志与密码的一致性，但没有解决 CSRF 归属与失效时机。

---

## 5. Deferred 审查

### 5.1 "本应现在就定"却既不在 ADR 也不在 Deferred 的 7 项

| 项 | 为什么必须现在定 | 关联发现 |
| --- | --- | --- |
| 预约的生命周期状态（取消后如何判定） | 决定 `booking` 表的形状与所有读路径，晚改要动迁移与全部查询 | C-04、Pair B/C |
| 审计日志的 `before_json/after_json` | 决定 FR-8 能否验收；晚加列会让已写日志不可回溯 | C-03 |
| 锁定的分组标识与操作者 | 决定解锁粒度与审计可读性，晚加要重写锁定用例 | H-07 |
| 开放时间收缩扫描的时间边界 | FR-2 的显式验收项，且决定是否会留下不可见占用 | H-08 |
| CSRF token 的生命周期（绑定/轮换/顺序） | 安全控制，事后补会改所有表单与装饰器 | H-09 |
| 迁移的原子性（DDL 与 `user_version` 同事务） | 半迁移状态的恢复策略，事后无法补救 | M-05 |
| 单条路径的校验归属（`slot_rules`） | 决定 FR-4 与 FR-7 是否共用一套规则 | H-06 |

### 5.2 现有 Deferred 条目本身是否合理

11 条（`:599-609`）全部**可以延后**，没有一条是"伪装成延后的必需项"。两处需要微调：

- `:602`（区间预约）理由自洽，但应补一句"前提是 `occupancy` 的 `slot_start` 永远对齐 30 分钟"——否则未来叠加区间视图时，M-01 的非对齐行会成为脏数据。
- `:604`（分页）与 `:616`（审计不清理）组合起来会让日志页线性退化（L-06）。分页仍可延后，但索引不能延后。

---

## 6. 运行/部署维度审查

**结论：这是全文第二好的部分**（`architecture.md:551-579`），覆盖了单进程、WAL 本地磁盘前提、环境变量、启动顺序、健康检查、备份方式、明确不引入 Docker/守护。14:33 版在 `:293` 补了 `synchronous=NORMAL` 的持久性代价，是加分项。仍缺 6 项：

1. **进程形态未定名**：`:558` 用 `python -m src.serve` + `threaded=True`，实际就是 Werkzeug 开发服务器。应显式写"首版接受 dev server，40 人规模可接受；并发写超阈值则迁移 waitress（纯 Python，不违反栈锁）"——否则读者会以为已经选定了 WSGI。
2. **优雅关闭与 `-wal`**：`:294` 说"正常关闭时 checkpoint 后消失"，`:296` 又警告别漏 `-wal`，`:579` 说"断电后重启即恢复"。三句之间缺少"非优雅关闭时如何判定数据完整性"。
3. **主机时钟**：2 小时/7 天/已开始三个判定全靠本机墙钟，但 §15 没有"NTP 必须开启"的部署前提，也没有登记为风险。
4. **文件权限**：`data/lab.db` 含学号 + scrypt 哈希，实验室共用机器上默认权限可能被任何登录用户读取。`:492` 的脱敏只保护日志与导出，不保护库文件本身。
5. **端口与防火墙**：`:575` 默认 `0.0.0.0:5000`，宿舍可达的前提是校园网放行 5000。应写成部署检查项。
6. **首启无管理员**：`/health` 200 不等于可用（可能还没有管理员账号）。应补"`/health` 200 且 `SELECT COUNT(*) FROM user WHERE role='admin'` ≥ 1"，否则忘记跑 seed 时所有页面 403，而健康检查是绿的。

---

## 7. 与上游的可追溯性缺口（会影响验收，不只是文档一致性）

| FR/NFR | 上游验收 | 架构落点 | 判定 |
| --- | --- | --- | --- |
| FR-2 第 5 条 | 缩短开放时间致越界 → 409，原配置不变（`PRD.md:121`） | `:267` 有规则，缺时间边界 | 部分（H-08） |
| FR-7 第 1 条 | 周视图"冲突、锁定、改单异常有可见标记"（`PRD.md:186`） | 无数据源 | **不可满足**（M-08） |
| FR-8 第 3 条 | 日志含"变更前后值"（`PRD.md:202`） | `:463-470` 无对应列 | **不可满足**（C-03） |
| FR-6 第 1 条 | "我的预约"含"状态"（`PRD.md:170`） | 无枚举 | 未定义（C-04） |
| NFR-1 | 0×5xx、120 轮全部通过 | `:174` 允许 503 | **自相矛盾**（H-03） |
| NFR-2 | 停止服务后复制 .db 数据一致（`PRD.md:228`） | `:296` 要求带 `-wal` | **口径冲突**（M-11） |
| NFR-4 | 明文命中数 0（`PRD.md:247`） | `:492` 脱敏白名单（新增，好）；缺库文件权限 | 部分（M-11） |

另：`:617` 已自认"PRD §11 溯源表缺 ADR-005 一行"——这条应在交付前修掉，而不是记在"待确认"里。`status: final` 与"上游表尚未同步"不能同时成立。

---

## 8. 最小修复集（按顺序，共 9 处）

1. `:124-146` + `:168-176`：改写 D2，把事务归属交给用例层；`claim_slots`/`release_slots` 声明"不开关事务"；异常分类用 `sqlite_errorname`，补齐 `OperationalError` 分支（C-01、C-02）。
2. `:178-187` + `:261-271`：D5 表增加"事务内必须重新断言 `booking.state='active'`"与"校验必须在事务内"两列；修正 §5.5 内部矛盾（M-12）。
3. `:425-479`：数据模型补 `user.active`、`booking.state/cancelled_at`、`audit_log.before_json/after_json`、`occupancy.lock_group_id/created_by`；删除 `booking.equipment_id`（或加一致性断言）（C-03、C-04、H-04、H-05、H-07）。
4. `:58` / `:328`：统一"四态只由 `slot_service.build_grid()` 产出"，补 §11 模板契约表（C-05、Pair A）。
5. `:209-259`：用 §4.1 的 L1–L5 替换现有四层证明；303/409 口径固定；对照 B 改为"删约束 + 短路预检"；为拓扑 B 单列断言（H-01、H-02、M-13）。
6. `:154-166` + `:168-176`：写出 busy 预算推导（单事务 ≤ 20ms、`busy_timeout=1000`、重试 2 次、总预算 ≤ 1.2s），使 0×5xx 可证（H-03）。
7. 新增 `app/slot_rules.py` 一节：6 条校验的唯一入口，`mode=create|edit`，admin 不豁免；同步改 `:489`、`:541`、`:544`（H-06、Pair C）。
8. `:351-367`：ADR-004 补 R1–R5（CSRF 绑定/轮换/顺序、`session.permanent`、401/403 分工、失效覆盖面），删除 `:333` 的重复表述（H-09）。
9. `:481-496` + `:534-549` + `:551-579`：补路由表（含 `/health` 与免鉴权清单）、`src/serve.py`、`template_folder`、NTP 前提、文件权限、健康检查含 admin 存在性；修 `:490` 的学生改约、`:38` 节号、`:509` STRICT、`:477` A.5 引述（M-04、M-09、M-11、M-14、L-01、L-02）。

---

## 9. 值得保留的部分（返修时不要丢掉）

- **ADR 的"被否决备选 + 逐条回指 FR/NFR"**：`:189-207`、`:300-316`、`:335-349`、`:369-385`、`:405-419` 是全文质量最高的部分，尤其"否决 A 的理由是它在单线程手工测试中永远通过"（`:202`）——这是评审者最需要的那句话。
- **"slot 是派生量 / occupancy 是唯一事实源"两条不变量**（`:82-83`）：它们才是真正的架构决定，比任何选型都重要。
- **`:118-122` 的"约束五条硬性要求"**：把"命名约束 / 列序 / 非部分索引 / 共用键空间 / 定长文本"写成了可断言项，非常具体。
- **`:241-249` 的变异测试意识**：方向完全正确（虽然对照 B 的实现不成立），只需修正而不是推翻。
- **`:261-271` 的 §5.5**：把"不写 occupancy 但有事务边界"的路径单独拎出来，是本轮修订最有价值的新增；只需修正 `:271` 的一句过度概括。
- **`:293` 对 `synchronous=NORMAL` 的代价说明**：把"接受什么风险"写清楚，比默认值本身重要。
- **`:551-579` 的运维边界**：明确写"不做进程守护/日志轮转/自动备份"并给出理由，比含糊地"暂不实现"好得多。
