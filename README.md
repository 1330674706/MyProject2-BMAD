# MyProject2 · 实验室设备预约系统

40 名研究生共用几台实验室设备，原来靠微信群加纸质登记，同一天同一时段被两个人订走，到场才发现。这个系统把预约变成一次数据库写入：同一 30 分钟 slot 的第二次提交在唯一约束上失败，冲突从"到场那一刻"提前到"提交那一刻"。

BMAD 课程作业，3 Epic / 12 Story，两人 4 周。

## 怎么跑起来

需要 Python 3.12 及以上（本次在 3.13.9 上验过），不装数据库，不装 Node。

```powershell
python -m pip install -r requirements.txt

$env:LAB_SECRET_KEY      = "32 字节以上的随机串，随便打一串"
$env:LAB_DEFAULT_PASSWORD = "管理员重置学生密码时用的默认值，8 位以上"
$env:LAB_ADMIN_USER      = "admin"
$env:LAB_ADMIN_PASSWORD  = "你们设的管理员密码，8 位以上"

python -m src.seed     # 导入 seed/equipment.csv，并创建管理员账号；可重复执行
python -m src.serve    # 起服务，默认 0.0.0.0:5000
```

打开 <http://127.0.0.1:5000/health>，返回 200 就说明库通了。

| 环境变量 | 必填 | 说明 |
| --- | --- | --- |
| `LAB_SECRET_KEY` | 是 | 会话签名密钥，少于 32 字节直接启动失败 |
| `LAB_DEFAULT_PASSWORD` | 是 | 管理员重置学生密码时写入的默认密码，少于 8 位启动失败 |
| `LAB_DB_PATH` | 否 | 默认 `data/lab.db`，只有一个文件，整个库就是它 |
| `LAB_HOST` / `LAB_PORT` | 否 | 默认 `0.0.0.0` / `5000` |
| `LAB_ADMIN_USER` / `LAB_ADMIN_PASSWORD` | 否 | 两个都给才会建管理员；不给就跳过并在 stderr 提示 |

## 怎么用

- 学生用学号注册，登录后进 `/slots`，勾选连续 slot 提交。冲突时整单拒绝（409），页面回到原页并标出哪几格被占。
- 管理员进 `/admin/week` 看本周所有设备。可以按学号检索、改单（只能改时间，不能换设备）、锁定/解锁 slot、导出该周 CSV、看操作日志。

## 跑测试

```powershell
python -m pytest -q tests --basetemp=pytest_tmp_run -p no:cacheprovider
```

当前 209 passed。`--basetemp` 是因为本机 `%TEMP%` 有 ACL 限制，不加会在建临时目录时失败。

## 目录

| 路径 | 内容 |
| --- | --- |
| `src/web/` | 路由、状态码映射、CSRF |
| `src/app/` | 用例层：预约、改单、锁定、取消、导出、审计 |
| `src/data/` | 仓储与迁移，`tx.py` 是唯一写事务入口 |
| `src/core/` | 配置、时间、错误、脱敏 |
| `src/templates/`、`src/static/` | Jinja 模板与 CSS |
| `_bmad-output/planning-artifacts/` | brief、PRD、architecture、epics |
| `_bmad-output/implementation-artifacts/` | 12 份 spec、sprint-status、deferred-work、两个实验记录 |
| `evidence/` | 决策截图与并发测试输出 |

## 十份交付产物

| 产物 | 位置 |
| --- | --- |
| product-brief | `_bmad-output/planning-artifacts/product-brief.md` |
| PRD | `_bmad-output/planning-artifacts/PRD.md`（FR-1..FR-8、NFR-1..NFR-4、§11 溯源表） |
| architecture | `_bmad-output/planning-artifacts/architecture.md`（5 条 ADR，每条都写了被否决的备选） |
| epics + stories | `_bmad-output/planning-artifacts/epics.md`（3 Epic / 12 Story / 88 条 AC） |
| project-context | `project-context.md`（R1–R8）＋ `AGENTS.md`（指针） |
| sprint-status | `_bmad-output/implementation-artifacts/sprint-status.yaml` |
| 源码 + 测试 | `src/`、`tests/` |
| decision-log | `decision-log.md`（15 条，7 条否决） |
| retrospective | `retrospective.md` |
| README | 本文件 |

## 分工

| 学号 | 姓名 | 负责阶段 |
| --- | --- | --- |
| 2601020056 | 郑李林 | 规划产物（brief / PRD / architecture / epics / sprint-status）、决策裁决与记录、12 个 Story 的实现与测试、实验 A 与实验 B 的设计与记录 |
| 2601027168 | 吴金宝 | bmb 自定义工作流（加分项）、10 分钟演示录屏、GitHub 仓库发布与协作提交 |

详细到产出的分工与 50/50 的工作量划分见 `TEAM.md`。规划与实现阶段的 12 个 Story 在同一台开发机上连续完成，提交集中在一个 Git 作者名下；加分项、演示录屏与 GitHub 发布由吴金宝署名提交。

## AI 使用声明

本作业全程使用 AI 辅助，如实声明如下。

- **工具**：Codex 桌面版（OpenAI Codex CLI 内核）。
- **模型**：同一个模型贯穿全程，未切换。
- **用法**：BMAD 方法自带技能，按 `bmad-product-brief` → `bmad-prd` → `bmad-architecture` → `bmad-create-epics-and-stories` → `bmad-sprint-planning` → `bmad-build` → `bmad-code-review` → `bmad-retrospective` 的顺序推进；每个 Story 一个独立对话，不把多个工作流塞进同一上下文。
- **人做了什么**：所有决策由人裁决并记录在 `decision-log.md`，其中 7 条是否决或实质修改了 AI 的建议；实验 A 的 X/Y 对照、实验 B 的影响分析由人设计口径。
- **AI 做了什么**：文档初稿、代码与测试、评审与修复，全部经人复核后才提交。
- **会话记录**：关键决策的对话截图在 `evidence/`，按 `D-编号_日期_内容.png` 命名；实验 A 的两次对话截图是 `expA_2026-11-11_chat-*.png`。

`decision-log.md` 里 D-005、D-006 是早期两次讨论，当时没形成正式记录，所以编号跳过——不是漏了。

## 关键决策速查

| 编号 | 决定 | 否决了什么 |
| --- | --- | --- |
| D-001 | 30 分钟固定 slot，`UNIQUE (equipment_id, slot_start)` | 任意区间预约 |
| D-002 | 服务端渲染，表单 POST + 303 | React SPA + JSON API |
| D-003 | 故事由 11 条拆成 12 条，新增 2.4 | 把改单边界并进 3.2 |
| D-004 | Story 1.4 只交付三件事 | 顺手做管理员种子 |
| D-007 | 接受就绪门禁的 7 条顾虑 | 无视顾虑直接开工 |
| D-008 | 独立复审 9 条必修，10 条不修 | 全量修复 |
| D-009 | 不做 HTTPS 与 `__Host-` Cookie，风险记为已接受 | 首版上 TLS |
| D-010 | 7 天窗口逐格判定 | 只看首格 |
| D-011 | 改单只能改时间，不能换设备 | 改单换设备 |
| D-012 | 一律显示学号，不加姓名列 | 新增 `display_name` |
| D-013 | 400 分支保留用户已提交的选择 | 只保住 409 那条路径 |
| D-014 | 邮件提醒排到 v2 | 上线前直接加邮件 + `.ics` 桥接 |
| D-015 | 实验 A 用等价小任务 | 重跑真实 Story 做对照 |
| D-016 | 故事卡落点必须与模块边界一致 | 简化故事卡 |
| D-017 | v1 封版，32 条 deferred 顺延 v2 | 逐条补完 |

每条都写了触发、AI 建议、判断依据、结果、事后验证，见 `decision-log.md`。

## 已知未做

完整清单在 `_bmad-output/implementation-artifacts/deferred-work.md`（32 条，封版时归档了 4 条已完成的）。按主题说：

- **R5 红灯证据不可复核**：2.4、3.2、3.3 的测试和实现进了同一个 commit，spec 里写的"9 failed""13 failed"只有自述。这是最实在的一条欠账。
- **规划文档还有漂移**：2.2 的 L3 措辞、2.4 的 §11 与 FR-7 ADR 集合、3.2 的改设备表述。
- **启动与运维边界**：`/health` 数据库异常仍走 500 不是 503，双进程首启新库有迁移竞态，端口被占时打 traceback。
- **管理端可用性**：审计 `target_id` 只显示 uuid，日志超过 200 条后不可翻页，检索结果表没有改单入口。
- **测试脚手架复制了 7 份**：`connect/seed_user/seed_equipment/login_as` 一直没提到 `tests/conftest.py`。

这些都不影响 FR-1..FR-8 的验收链，取舍理由和重启条件写在 `decision-log.md` D-017 与 `retrospective.md` 第 3 节。

## 演示

10 分钟录屏，`demo/` 下（或见提交说明）。三段：

1. 2 分钟并发：两个浏览器同时抢同一 slot，一个 303 一个 409，数据库里只有一行。
2. 2 分钟溯源：挑一条 FR，从 PRD §11 走到 ADR、Story、测试文件。
3. 6 分钟决策日志：逐条讲否决了什么、为什么、后来证明对不对。
