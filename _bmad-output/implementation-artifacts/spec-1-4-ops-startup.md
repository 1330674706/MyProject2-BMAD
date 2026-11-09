---
title: 'Story 1.4 一条命令启动与设备种子导入'
type: 'feature'
created: '2026-11-09'
status: 'in-review'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'e7b8989375bc925f13276d74323b780af52572e7'
context:
  - 'project-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 现在只能在测试里用 `create_app()`，没有 `python -m src.serve` 入口，也没有 `/health` 探针；设备只能由管理员逐条手工录入，换一台机器无法一条命令拉起可用服务。

**Approach:** 新增 `src/serve.py` 作为唯一启动入口（读环境变量、失败即退出），在应用工厂注册免鉴权的 `GET /health`（`SELECT 1`）；新增 `src/seed.py` 以整文件一个事务从 `seed/equipment.csv` 按 `equipment_id` upsert 设备，校验复用 1.2 的 `equipment_service` 规则。

## Boundaries & Constraints

**Always:** 缺 `LAB_SECRET_KEY`（<32 字节）或 `LAB_DEFAULT_PASSWORD`（<8 位）必须启动失败、非 0 退出且不监听端口，不得写默认值；`/health` 免鉴权且返回 200；启动顺序为读配置 → 打开数据库/迁移 → 注册蓝图 → 监听，`threaded=True`；种子按 `equipment_id` upsert，重复执行行数不变；整文件一个 `write_tx()`，任一行不合法则整体回滚并输出含物理行号的报错；设备窗口校验只调用 `equipment_service` 既有规则，不复制。

**Never:** 不新增运行期依赖（测试用 stdlib `urllib`，不用 `requests`）；不做 Docker、进程守护、日志轮转、自动备份；不实现 `LAB_ADMIN_USER` / `LAB_ADMIN_PASSWORD` 管理员种子（本次明确只交付三件事，留待 review 决定）；不碰 2.1 的预约提交、`occupancy` 写入或模板；不建 `slot` 表。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HEALTH_OK | 必需 env 齐全，`LAB_PORT` 指定 | 端口监听，`GET /health` 为 200 | N/A |
| MISSING_SECRET | 无 `LAB_SECRET_KEY` | 进程非 0 退出，报文含变量名，端口未监听 | 打印明确配置错误 |
| MISSING_PASSWORD | 无 `LAB_DEFAULT_PASSWORD` | 同上，报文含变量名 | 打印明确配置错误 |
| SEED_IDEMPOTENT | 3 行合法 CSV，连续跑两次 | 两次均 0，`equipment` 恰好 3 行 | N/A |
| SEED_UPSERT | 已存在同 `equipment_id` 的旧名称 | 名称/窗口更新，仍为 1 行 | N/A |
| SEED_BAD_ROW | 第 3 行缺 `open_start` | 非 0，stdout 含 `3`，`equipment` 为 0 行 | 整体回滚 |
| SEED_NO_FILE | 无 `seed/equipment.csv` | 非 0，报文含路径 | 不建库 |

</frozen-after-approval>

## Code Map

- `src/serve.py` -- 新建启动入口；`create_app()` 失败时捕获 `ConfigError` 并返回 2，成功时 `app.run(host, port, threaded=True, use_reloader=False)`。
- `src/web/health.py` -- 新建免鉴权蓝图；`get_db().execute("SELECT 1")` 后返回 200。
- `app.py` -- 注册 health 蓝图；不放业务判断。
- `src/core/config.py` -- 抽出 `resolve_db_path()` 供 serve/seed 共用，`load_config()` 行为不变。
- `src/data/equipment_repo.py` -- 新增 `upsert_equipment()`，`ON CONFLICT(id) DO UPDATE`（不是 `DO NOTHING`）。
- `src/app/equipment_service.py` -- 新增 `import_equipment_rows()`：逐行复用 `_validate_window()`，错误加行号，单事务 upsert。
- `src/seed.py` -- 新建种子入口；`utf-8-sig` 读固定四列，`csv.reader.line_num` 提供物理行号；失败打印 stdout 并返回 1。
- `seed/equipment.csv` -- 示例设备清单，列为 `equipment_id,name,open_start,open_end`。
- `tests/test_ops_startup.py` -- 新建；子进程真实启动/停止服务，stdlib `urllib` 请求；种子在临时 cwd 下执行。

## Tasks & Acceptance

**Execution:**
- [x] `tests/test_ops_startup.py` -- 先写 AC 与矩阵测试并运行，确认红灯 -- R5 证据。
- [x] `src/core/config.py` -- 抽出 `resolve_db_path()` -- serve 与 seed 共用同一路径解析。
- [x] `src/web/health.py`、`app.py` -- 注册 `/health` -- 免鉴权探针。
- [x] `src/serve.py` -- 启动入口与配置失败退出 -- 一条命令启动。
- [x] `src/data/equipment_repo.py`、`src/app/equipment_service.py` -- upsert 与逐行校验 -- 幂等且不复制 1.2 规则。
- [x] `src/seed.py`、`seed/equipment.csv` -- 种子入口与示例清单 -- 整文件事务、行号报错。
- [x] `tests/test_ops_startup.py` -- 全绿并跑全量回归 -- 证明 1.1–1.3 无回归。

**Acceptance Criteria:**
- Given 必需 env 齐全，When 执行 `python -m src.serve`，Then `GET /health` 为 200。
- Given 缺 `LAB_SECRET_KEY` 或 `LAB_DEFAULT_PASSWORD`，When 启动，Then 非 0 退出、报文含变量名、端口未监听。
- Given 3 行设备 CSV，When 连续执行两次 `python -m src.seed`，Then 两次均 0 且 `equipment` 为 3 行。
- Given 第 3 行缺 `open_start`，When 执行 seed，Then 非 0、stdout 含 `3`、`equipment` 为 0 行。

## Implementation Notes

- 红灯证据：`tests/test_ops_startup.py` 先落盘运行，7 failed；失败均为 `No module named src.serve` / `No module named src.seed`，证明测试测的是尚不存在的入口。
- 绿灯：同文件 7 passed；全量 64 passed（原 57 + 新 7）。
- 启动入口只做 `create_app()` → `app.run(threaded=True, use_reloader=False)`；`ConfigError` 返回 2，`LAB_PORT` 非整数同样返回 2，均不绑定端口。
- `/health` 在 `src/web/health.py` 注册，执行 `SELECT 1` 返回 200，无鉴权装饰器。
- 种子先校验完整 CSV 再 `initialize()`；行号用 `csv.reader.line_num`（物理行号），窗口规则调用 `equipment_service._validate_window()`，没有复制 1.2 的判断。
- `upsert_equipment()` 用 `ON CONFLICT(id) DO UPDATE`；未使用 `INSERT OR IGNORE` / `DO NOTHING`。
- 按用户本次范围，`LAB_ADMIN_USER` / `LAB_ADMIN_PASSWORD` 管理员种子未实现，Story 1.4 的对应 AC 留待 review 决策；未触碰 2.1 预约提交与 `occupancy` 写入。
- 评审补丁轮：新增 9 条测试后得到 5 红（审计为 0、重复 ID 被接受、GBK 直接 traceback、窗口收窄未拒绝、70000 端口未失败），修复后 16 passed、全量 73 passed。
- 种子写入改为「先 `prepare_equipment_rows()` 完整校验，再 `initialize()`」；重复 `equipment_id` 带行号拒绝，避免静默丢行和台数虚报。
- 种子写入在 `write_tx()` 内逐台比较旧值：未变化则跳过（重复执行不新增审计）；窗口变化复用 `_assert_window_covers_occupancy()`，收窄越过已占用 slot 时整文件回滚。
- 种子对实际变更写 `audit_log`（`action=equipment_update`、`actor_id=system`），满足 §4「审计与变更同事务」；`system` 是本 Story 定的运维主体，尚无真实用户。

## Review Triage Log

| 发现（合并同类） | 判定 | 处置 |
| --- | --- | --- |
| 缺 README / 管理员种子 / 单 .db 与复制 AC 测试 | defer | 超出用户本次三件事；已记 `deferred-work.md` |
| 种子窗口收窄越过已占用 slot | medium | patch：复用占用检查，整文件回滚，新增测试 |
| 种子写入无审计 | medium | patch：变更才写 `equipment_update`，`actor_id=system` |
| 重复 `equipment_id` 静默 last-wins | medium | patch：带行号拒绝，新增测试 |
| `initialize()` 早于逐行校验 | medium | patch：先 `prepare_equipment_rows()` 再建库 |
| 非 UTF-8 / 不可写路径 / 建库失败直接 traceback | medium | patch：统一 `SeedError` / `AppError` / `OSError` 报文 |
| `LAB_PORT` 未校验范围、解析晚于建库 | medium | patch：先解析并限 1–65535，再 `create_app()` |
| `create_app()` 的 sqlite/OSError 未兜底 | medium | patch：与 `ConfigError` 一并清晰退出 |
| `"3" in stdout` 断言可被 `:30` 蒙混 | medium | patch：改断言 `第 3 行`，并加第 4 行用例 |
| 回滚测试未在事务内制造失败 | medium | patch：预置 ABORT 触发器，验证首行也回滚 |
| `LAB_DB_PATH`、错误表头、`/health` 探库未被测 | medium | patch：各补一条测试 |
| 端口占用 / 主机不可解析的 OSError 提示 | low | defer：Werkzeug 自行退出，未影响三件事 |
| 测试端口 TOCTOU、探活单次请求 | low | defer：本机实测稳定，失败会带服务日志 |
| `/health` 每次探活写 INFO 日志 | low | defer：单机规模可接受 |
| 空 CSV 退出 0、ID 格式、引号换行行号、相对路径 | low | defer：未在本次意图内，已记 `deferred-work.md` |
| FR-2 归属文档矛盾 | low | defer：R7 文档改动不在本次范围 |
| `/health` 用 `SELECT 1` 对空库也 200、异常返回 500 | false | 启动时已迁移；异常非 200 即表达不可用，architecture 只约定可用时为 200 |
| seed 走 stdout、serve 走 stderr | false | Story AC 明确要求 seed 行号出现在 stdout |
| 空名称在 update_window 与 import 行为不同 | false | 管理员路径保留旧名、种子路径必须给全量数据，场景不同 |
| `import_equipment_rows` 带行号属越层 | false | 该函数即 seed 专用，行号是其契约；窗口规则仍只在服务层 |

## Verification

**Commands:**
- `python -m pytest -q -p no:cacheprovider --basetemp=.pytest_tmp_story14_review2 tests/test_ops_startup.py` -- 实际 16 passed。
- `python -m pytest -q -p no:cacheprovider --basetemp=.pytest_tmp_story14_full2` -- 实际 73 passed，无回归。
