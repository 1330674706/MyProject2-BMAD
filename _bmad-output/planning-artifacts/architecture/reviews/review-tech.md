# 技术事实核查报告：architecture.md

- 被核查文件：`_bmad-output/planning-artifacts/architecture.md`
- 快照：617 行，SHA256 `2092F9996C5A7B1CF9F733E35AC162672D51AB08E144D6D9C91F0117C2495483`，LastWriteTime 2026-11-04 14:33:29
- 核查时间：2026-11-04
- 核查方式：静态逐条比对 + 本机实测（SQLite 3.51.0 / Flask 3.1.3 / Werkzeug 3.1.3 / Python 3.13.9 / tzdata 2025.2），所有"实测"结论均给出可复现命令或输出
- 核查范围：文档内全部具体技术断言（SQLite、Flask/Werkzeug、Python zoneinfo）、被禁技术混入、版本号一致性
- 未改动被核查文件

> 注意：核查过程中该文件被外部修改过一次（599 行 → 617 行），本报告所有行号均以 617 行版本（上述 SHA256）为准。

## 结论

**总体可信：核心并发方案（唯一约束 + BEGIN IMMEDIATE）在技术上是成立的，但存在 3 处硬错误（IntegrityError 触发时机、会话"绝对过期"、载荷措辞）与 5 处需要收紧的表述，其中"绝对过期，不滑动"会直接导致按文档实现出 12 小时滑动会话。**

## 一、错误（必须修改）

### E-1 第 93 行：`IntegrityError` 不会在 `COMMIT` 时抛出

原文：

> 同一设备同一 30 分钟 slot 在全库最多存在一行占用记录（预约或锁定），第二次写入必然在 `COMMIT` 时报 `IntegrityError`，整单回滚，返回 409。

判定：**错误**。

实测（`isolation_level=None` + `BEGIN IMMEDIATE` + `executemany` 两行，第二行与已有行冲突）：

```
INTEGRITY AT: executemany | UNIQUE constraint failed: occupancy.equipment_id, occupancy.slot_start
COMMIT: 未被执行
```

SQLite 的 UNIQUE 冲突在**语句执行时**立即报错，属于即时（immediate）约束；SQLite 中唯一可声明为 `DEFERRABLE INITIALLY DEFERRED` 的只有外键约束，UNIQUE/CHECK/NOT NULL 都不能延迟到 `COMMIT`。

建议措辞：

> 同一设备同一 30 分钟 slot 在全库最多存在一行占用记录（预约或锁定）。第二次写入会在 `INSERT`（`executemany`）语句处立即抛出 `IntegrityError`——SQLite 的 UNIQUE 冲突不会延迟到 `COMMIT`，可延迟的只有声明为 `DEFERRABLE` 的外键——由 `claim_slots()` 捕获后整单回滚并返回 409。

### E-2 第 361 行：`PERMANENT_SESSION_LIFETIME=12h` 不等于"绝对过期，不滑动"

原文：

> `HttpOnly=True`、`SameSite=Lax`、`Secure=False`（首版校园网 HTTP，风险见 PRD §7.3 已接受）、`PERMANENT_SESSION_LIFETIME=12h`（绝对过期，不滑动）。

判定：**错误**。缺两个必要条件，且默认行为恰好相反。

实测（Flask 3.1.3）：

```
SESSION_REFRESH_EACH_REQUEST 默认 True
login  : Expires=Sat, 05 Dec 2026 06:34:24 GMT
+2s hit: Expires=Sat, 05 Dec 2026 06:34:26 GMT   ← 每次请求顺延，即滑动
```

两个问题：

1. `PERMANENT_SESSION_LIFETIME` 只在 `session.permanent = True` 时生效；否则下发的 Cookie 没有 `Expires`/`Max-Age`，是浏览器会话 Cookie（关浏览器即失效），12 小时配置完全不生效（实测非 permanent 的 `Set-Cookie` 无 `Expires`）。
2. Flask 默认 `SESSION_REFRESH_EACH_REQUEST=True`，每个响应都会重发 Cookie 并把过期时间往后推，是**滑动**过期。要得到绝对过期必须显式 `SESSION_REFRESH_EACH_REQUEST=False`（实测该设置下后续请求不再下发 `Set-Cookie`，过期时间固定为登录时刻 + 12h）。

建议措辞：

> `HttpOnly=True`、`SameSite=Lax`、`Secure=False`（首版校园网 HTTP，风险见 PRD §7.3 已接受）；登录成功后置 `session.permanent = True`，`PERMANENT_SESSION_LIFETIME=timedelta(hours=12)`，并设 `SESSION_REFRESH_EACH_REQUEST=False`。三者缺一不可：少了 `session.permanent` 会退化成浏览器会话 Cookie，少了 `SESSION_REFRESH_EACH_REQUEST=False` 会变成每次请求顺延 12 小时的滑动过期（Flask 默认为 `True`）。

### E-3 第 360 行：载荷描述自相矛盾

原文：

> 仅 `uid`、`role`、`pv`（密码版本号）。不放姓名、学号以外的个人信息，不放任何可用于提权的字段。

判定：**错误（表述）**。"不放姓名、学号以外的个人信息"字面含义是"姓名和学号**可以**放"，与前一句"仅 uid/role/pv"直接矛盾。

建议措辞：

> 仅 `uid`、`role`、`pv`（密码版本号）；不放姓名、学号等任何身份信息，不放任何可用于提权的字段。注意 Flask 会话 Cookie 只做签名、不加密，载荷可被客户端 base64 解码读出，因此上述字段不得当作机密（`role` 已在第 364 行规定以库中值为准，此处保持一致）。

## 二、不准确（建议修改）

| # | 行号 | 原文要点 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| N-1 | 174 | "同一事务最多重试 3 次（间隔 50ms，仅限未提交）" | "仅限未提交"歧义：若把重试理解为"事务内重跑 `executemany`"，在部分行已写入后重试会重复写其它 slot。且 `busy_timeout=5000` 已先等满 5 秒，再补 3×50ms 基本无收益 | 改为："重试只允许发生在 `BEGIN IMMEDIATE` 本身失败时（此时事务尚未开始）；一旦事务内已有写入，只能回滚并由上层重新发起整个用例。busy_timeout 已等待 5 秒，追加重试的实际收益有限，仅作为抖动兜底" |
| N-2 | 500/504 | "本机运行时已核对版本；目标解释器为 Python 3.12" / `Python 3.12.x` | 本机不存在 3.12：`py -0p` 仅有 3.13.9 与 3.10；实测解释器为 3.13.9、SQLite 3.51.0。"已核对"与事实不符 | 改为："本机实测（Python 3.13.9）：Flask 3.1.3 / Werkzeug 3.1.3 / Jinja2 3.1.6 / itsdangerous 2.2.0 / pytest 8.4.2 / tzdata 2025.2 / SQLite 3.51.0。目标解释器锁定 Python 3.12.x，需在 3.12 环境复跑一次版本核对后再签字" |
| N-3 | 509 | "SQLite 3.37+（随 CPython 3.12 提供…）" | 仅 Windows 的 CPython 自带 `sqlite3.dll`；Linux/macOS 链接系统 `libsqlite3`，可能低于 3.37（如 Debian 11 为 3.34） | 改为："SQLite ≥ 3.37（Windows 上随 CPython 3.12 附带；Linux/macOS 链接系统 libsqlite3，需在启动时断言 `sqlite3.sqlite_version_info >= (3,37,0)`；3.37 起支持 `STRICT`，部分索引自 3.8 起）" |
| N-4 | 579 | "断电后重启即恢复" | 与第 293 行"断电时可能丢失最后几个已提交事务"存在张力，容易被读成"已提交即不丢" | 改为："断电后重启可正常打开且库保持一致；受 `synchronous=NORMAL` 影响，最后若干个已提交事务可能回退（见 ADR-002），数据兜底是管理员每周导出的 CSV" |
| N-5 | 615 | "改这一项只影响 `PERMANENT_SESSION_LIFETIME`" | 不完整；要维持绝对过期还需 `SESSION_REFRESH_EACH_REQUEST=False`（见 E-2） | 改为："改这一项需同时调整 `PERMANENT_SESSION_LIFETIME` 与 `SESSION_REFRESH_EACH_REQUEST=False`（保持绝对过期），不影响其他 ADR" |

## 三、逐条判定总表

判定说明：**正确** = 与实测/官方语义一致；**正确（需补充）** = 结论成立但边界条件未写明，照抄会踩坑；**不准确** = 方向对但表述会误导；**错误** = 与事实相反。

| # | 行号 | 断言 | 判定 | 证据 / 说明 |
| --- | --- | --- | --- | --- |
| T-01 | 93 | 唯一冲突在 `COMMIT` 时报 `IntegrityError` | **错误** | 见 E-1；实测在 `executemany` 处即抛出 |
| T-02 | 118 | `PRAGMA index_list` 对命名 UNIQUE 约束返回 `unique=1`、`origin='u'` | 正确（需补充） | 实测 `[(0,'sqlite_autoindex_occupancy_1',1,'u',0)]`：`origin='u'`、`unique=1`、`partial=0` 均成立。但**索引实名是 `sqlite_autoindex_occupancy_1`，不是 `uq_occupancy_slot`**；该自动索引在 `sqlite_master.sql` 中为 `NULL`，不能按约束名去 `sqlite_master` 里查 DDL |
| T-03 | 119 | `PRAGMA index_info` 可证明列序 `(equipment_id, slot_start)` | 正确 | 实测 `[(0,0,'equipment_id'),(1,1,'slot_start')]`，第 3 列（`r[2]`）即列名，文档中的取法正确；`index_info` 不返回隐式 rowid 列（那是 `index_xinfo`） |
| T-04 | 120 | 普通唯一索引、非部分索引 | 正确 | `PRAGMA index_list` 第 5 列为 `partial=0` |
| T-05 | 122 | 唯一性即文本相等，格式必须唯一 | 正确 | 文本列 + `BINARY` 默认排序规则，逐字节比较 |
| T-06 | 150 | WAL 下延迟事务先读后写，升级写锁返回 `SQLITE_BUSY`，且不可安全重试 | 正确 | 实测：连接 A `BEGIN`+`SELECT` → 连接 B 提交写入 → A 再 `INSERT` 得 `OperationalError: database is locked`（`sqlite_errorname=SQLITE_BUSY_SNAPSHOT`），**等待 0.00s**，`busy_timeout` 对此不生效。`BEGIN IMMEDIATE` 在进入时取写锁，确实规避 |
| T-07 | 152 | 冲突列表在 `ROLLBACK` 之后重查 | 正确 | 失败语句前已写入的行仍留在事务内，回滚后重查才只反映对手已提交的行 |
| T-08 | 159-163 | `connect(isolation_level=None)` + 四条 PRAGMA | 正确（需补充） | `isolation_level=None` 才能手动 `BEGIN IMMEDIATE`；`PRAGMA busy_timeout=5000` 是毫秒。**Python `sqlite3.connect()` 的 `timeout` 参数就是同一机制（秒），默认 5.0**（实测默认 `PRAGMA busy_timeout` 即 5000），因此本行 PRAGMA 与默认值等价、属显式冗余而非冲突；两者不要设成不同值 |
| T-09 | 166 | 连接不共享是多线程下正确工作的前提 | 正确 | Python `sqlite3` 默认 `check_same_thread=True`，跨线程复用会直接报错；每请求一连接是推荐形态 |
| T-10 | 172 | 冲突消息为 `UNIQUE constraint failed: occupancy.equipment_id, occupancy.slot_start` | 正确（需补充） | 实测消息**逐字一致**。但依赖消息文本较脆，建议同时/改为判断 `e.sqlite_errorname == 'SQLITE_CONSTRAINT_UNIQUE'`，并仍以列名子串区分是本约束而非 `user.student_no` |
| T-11 | 174 | 锁忙重试 3 次（间隔 50ms，仅限未提交） | 不准确 | 见 N-1 |
| T-12 | 195 / 204 | `INSERT OR IGNORE` 静默跳过、只写入部分 slot、接口仍成功 | 正确 | 实测 `executemany` 3 行（含 1 行冲突）：`rowcount=2`，库中新增 2 行，无异常。补充：`OR IGNORE` 同时吞掉 NOT NULL / CHECK 违反（外键违反不会被忽略），比文档描述的危害更大 |
| T-13 | 151 | 绝不 `OR REPLACE`（会静默覆盖） | 正确 | 实测 `REPLACE` 先删除冲突行再插入：`rowid` 由 1 变 5。补充：还会触发该行的 DELETE 触发器、改变 rowid、并对 NOT NULL 违反用 DEFAULT 顶替，属"删除+插入"而非"更新" |
| T-14 | 102-104 | `CHECK (length(...)=20 AND ... GLOB '[0-9]...Z')` 写法有效 | 正确（需补充） | 语法有效且能挡住小写 `z`、错长度；**但不校验日历合法性**：实测 `2026-99-99T99:99:00Z`、`2026-13-45T88:77:00Z`、`2026-11-05T24:00:00Z` 全部被接受。CHECK 只保证"形状"，真实日期合法性仍须在 `app/` 层校验（与第 489 行"校验只在 `app/` 做一次"一致，建议在 ADR-005 明写此边界） |
| T-15 | 402 | `DEFAULT CURRENT_TIMESTAMP` 产出 `YYYY-MM-DD HH:MM:SS` | 正确 | 空格分隔、无 `T`、无 `Z`，与 20 字符约定冲突，会违反 CHECK |
| T-16 | 全文 / 476 | 未使用 `WITHOUT ROWID` | 正确 | 全文无 `WITHOUT ROWID`。该表无 `PRIMARY KEY`，若加 `WITHOUT ROWID` 会直接报 `PRIMARY KEY missing on table`；保持 rowid 表是正确的 |
| T-17 | 361 | `PERMANENT_SESSION_LIFETIME=12h` 即绝对过期 | **错误** | 见 E-2 |
| T-18 | 360 | "不放姓名、学号以外的个人信息" | **错误（表述）** | 见 E-3 |
| T-19 | 363 | Werkzeug 3 的 `generate_password_hash()` 默认 scrypt | 正确 | 实测输出前缀 `scrypt:32768:8:1`（Werkzeug 3.1.3）。`check_password_hash()` 会按存储串前缀自动识别算法，无需显式传 method |
| T-20 | 403 | Windows 上 `zoneinfo` 需显式安装 `tzdata` | 正确 | Windows 无 IANA 时区库；本机 `zoneinfo.TZPATH` 指向 `…/share/zoneinfo`，即由 `tzdata` wheel 提供（已装 2025.2）。不装则 `ZoneInfo("Asia/Shanghai")` 抛 `ZoneInfoNotFoundError` |
| T-21 | 293 | WAL + `synchronous=NORMAL`：不损坏库，但断电可能丢最后几个已提交事务 | 正确 | 与 SQLite 官方语义一致，**未夸大**：WAL+NORMAL 保证一致性/不损坏，但可能回退最近提交；应用崩溃不影响已提交事务。补充：`FULL` 的代价是每次提交一次 fsync，"仍在毫秒级"在 SSD 成立、机械盘可能到 10ms 量级 |
| T-22 | 579 | 断电后重启即恢复 | 不准确 | 见 N-4 |
| T-23 | 281/294 | `-wal`/`-shm` 是运行期临时文件，正常关闭 checkpoint 后消失 | 正确 | 最后一个连接正常关闭时会 checkpoint 并删除（除非 `SQLITE_FCNTL_PERSIST_WAL`）。注意进程被 kill 时它们会残留，下次打开自动恢复，不影响结论 |
| T-24 | 296 | `VACUUM INTO` 可做在线快照；不可只复制 `.db` 而忽略 `-wal` | 正确 | `VACUUM INTO`（3.27+）在单个读事务内生成一致快照；只拷主库文件会丢 WAL 中未 checkpoint 的提交 |
| T-25 | 298 | WAL 放 SMB/NFS 会损坏或不可用 | 正确 | WAL 依赖共享内存与 POSIX 文件锁，官方明确不支持网络文件系统；措辞"损坏或直接不可用"略强但方向正确 |
| T-26 | 384 | Asia/Shanghai 常年 +08:00、无夏令时 | 正确 | 实测 2026-11 与 2026-07 的 `utcoffset()` 均为 `8:00:00`，`dst()` 为 0 |
| T-27 | 386 | 自然周用半开区间，`BETWEEN` 会多算右端 | 正确 | `BETWEEN` 为闭区间，会包含下周一 00:00 的 slot |
| T-28 | 396 | 定长零填充使字典序等于时间序 | 正确 | 对 `YYYY-MM-DDTHH:MM:SSZ` 成立；注意这是字符串比较红利，不适用于带偏移或不等长格式 |
| T-29 | 203 | SQLite 没有 exclusion constraint | 正确 | SQLite 无 PostgreSQL 式排他约束，只能用唯一索引或触发器模拟 |
| T-30 | 280/293 | WAL 让读不被写阻塞 | 正确 | WAL 下读快照与单写者并行，读写不互斥（写写仍互斥） |
| T-31 | 108/476 | 唯一键为 `(equipment_id, slot_start)`，不含 `booking_id`；锁行 `booking_id IS NULL` | 正确 | 实测 SQLite 的 UNIQUE 允许多个 NULL，但那作用于**索引内列**；`booking_id` 不在唯一键内，故多把锁行各自占不同 slot 时互不冲突、同 slot 仍冲突，语义正确且不受 NULL 语义影响。两列均为 `NOT NULL`，也不存在"NULL 绕过唯一约束"的风险 |
| T-32 | 500/504/509 | 本机已核对版本；Python 3.12；SQLite 随 CPython 提供 | 不准确 | 见 N-2、N-3 |
| T-33 | 615 | 会话有效期只影响 `PERMANENT_SESSION_LIFETIME` | 不准确 | 见 N-5 |
| T-34 | 228-232 | 并发测试用 `spawn` 双进程 + 真实 HTTP + Barrier | 正确 | Windows 默认 `spawn`，且必须 `if __name__ == "__main__"` 保护；`test_client` 单进程无法证明跨连接并发，判断正确 |

## 四、被禁技术核查

| 技术 | 出现位置 | 是否被采纳 | 判定 |
| --- | --- | --- | --- |
| React / Vue / SPA | 339（被否决备选）、587（明确不引入） | 否 | 正确，仅作为反例 |
| MySQL / PostgreSQL | 304（被否决）、588（明确不引入） | 否 | 正确 |
| Redis | 197、307（被否决）、377、589（明确不引入） | 否 | 正确 |
| 消息队列 | 590（明确不引入） | 否 | 正确 |
| WebSocket / SSE | 591（明确不引入） | 否 | 正确 |
| Docker / 容器 | 553（明确不引入） | 否 | 正确 |

结论：**无被禁技术混入运行时栈**。所有出现均在"被否决的备选"或"明确不引入"表中，且第 583 行已声明"出现即视为范围蔓延"。运行期依赖清单（第 513 行）与第 502-511 行表格一致。

## 五、版本号核查

| 项 | 文档值 | 本机实测 | 判定 |
| --- | --- | --- | --- |
| Python | 3.12.x | 3.13.9（`py -0p` 另有 3.10，无 3.12） | 不准确（见 N-2） |
| Flask | 3.1.3 | 3.1.3 | 一致 |
| Jinja2 | 3.1.6 | 3.1.6 | 一致 |
| Werkzeug | 3.1.3 | 3.1.3 | 一致 |
| itsdangerous | 2.2.0 | 2.2.0 | 一致 |
| pytest | 8.4.2 | 8.4.2 | 一致 |
| SQLite | 3.37+ | 3.51.0 | 下限成立，但"随 CPython 3.12 提供"仅对 Windows 成立（见 N-3） |
| tzdata | ≥ 2024.1 | 2025.2 | 一致 |

版本号之间**无自相矛盾**：front-matter 的 `stack-lock`（Flask 3）与第 12 节精确版本（3.1.3）是主版本/精确版本关系，不冲突。唯一硬伤是"本机已核对 Python 3.12"这一句与运行环境不符；Python 3.12 于 2025-04 进入仅安全修复阶段，本身不算过时，但若目标机实际是 3.13，应直接改 pin 而不是留 3.12。

## 六、最小修改清单（按优先级）

1. 第 93 行：把"在 `COMMIT` 时报"改为"在 `INSERT` 语句处即抛出"（E-1）。
2. 第 361 行：补 `session.permanent = True` 与 `SESSION_REFRESH_EACH_REQUEST=False`（E-2）。
3. 第 360 行：改写载荷措辞，并注明"签名不加密"（E-3）。
4. 第 174 行：把重试限定为 `BEGIN IMMEDIATE` 阶段失败（N-1）。
5. 第 500/504/509 行：改为实测事实 + 在 3.12 环境复跑（N-2、N-3）。
6. 第 579、615 行：补限定语（N-4、N-5）。
7. 建议补充（非错误）：第 118 行注明自动索引名为 `sqlite_autoindex_occupancy_1`；第 172 行改用 `sqlite_errorname`；第 102-104 行注明 CHECK 不校验日历合法性。

## 七、无法在本机验证的项

| 项 | 原因 | 建议 |
| --- | --- | --- |
| Python 3.12 下的 SQLite 具体版本（3.43.x 量级） | 本机无 3.12 解释器 | 在目标环境执行 `python -c "import sqlite3;print(sqlite3.sqlite_version)"` 记录 |
| `tzdata` 缺失时的实际报错 | 本机已安装，未做卸载验证 | 结论依据 CPython 文档与 `zoneinfo.TZPATH` 指向 `tzdata` 目录，可判定成立 |
| Windows `spawn` 下 `Barrier` 的跨进程行为 | 未运行完整并发测试（本次只核查事实，不执行项目代码） | 属于实现验证，建议在 Story 1 的测试里跑通 |

## 附：本次实测命令要点

- 结构断言：`PRAGMA index_list('occupancy')` → `[(0,'sqlite_autoindex_occupancy_1',1,'u',0)]`；`PRAGMA index_info(...)` → `[(0,0,'equipment_id'),(1,1,'slot_start')]`
- 事务升级：A `BEGIN`+`SELECT`，B 提交写入后 A `INSERT` → `OperationalError: database is locked`（`SQLITE_BUSY_SNAPSHOT`），耗时 0.00s
- 冲突时机：`executemany` 内第二行冲突 → `IntegrityError: UNIQUE constraint failed: occupancy.equipment_id, occupancy.slot_start`，`COMMIT` 未执行
- `OR IGNORE`：3 行含 1 冲突 → `rowcount=2`，静默成功
- `REPLACE`：冲突行 rowid 1 → 5（删除后重插）
- CHECK：`2026-99-99T99:99:00Z` 被接受
- Flask：`SESSION_REFRESH_EACH_REQUEST=True`（默认）→ 每次请求 `Expires` 顺延；`False` → 后续请求不再下发 `Set-Cookie`
- Werkzeug：`generate_password_hash("pw")` → `scrypt:32768:8:1$…`
- zoneinfo：`TZPATH=('C:\\Users\\ADMIN\\anaconda3\\share\\zoneinfo',)`，Asia/Shanghai 冬夏均 +08:00、DST=0
