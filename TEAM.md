# 团队分工与贡献说明

本文件说明两名成员的分工、各自产出与工作量分配。条目后面的「核验方式」都能在仓库里直接查到。本文件随最终提交更新。

## 1. 成员

| 学号 | 姓名 | 角色 |
| --- | --- | --- |
| 2601020056 | 郑李林 | 规划与实现：产物撰写、决策裁决、12 个 Story 的实现与测试、实验 A/B |
| 2601027168 | 吴金宝 | 加分项与交付：BMB（BMad Builder）自定义工作流、演示录屏、GitHub 发布、文档校对 |

## 2. 工作量分配

按交付责任划分，两人各承担一半（50% / 50%）。

| 成员 | 交付内容 | 占比 |
| --- | --- | --- |
| 郑李林 | `product-brief.md`、`PRD.md`、`architecture.md`、`epics.md`、`project-context.md`、`sprint-status.yaml`；`decision-log.md` 15 条（7 条否决）；`src/` 与 `tests/` 全部代码与 209 条测试；实验 A 的 X/Y 对照、实验 B 的影响分析；`retrospective.md` | 50% |
| 吴金宝 | BMB（BMad Builder）自定义工作流的 skill 编写与动机/效果说明（加分项）；10 分钟演示录屏；GitHub 仓库发布与协作提交；全部交付文档校对与提交前检查 | 50% |

## 3. 郑李林的产出

| 阶段 | 产出 | 核验方式 |
| --- | --- | --- |
| 分析 | `product-brief.md` | 文件本身；`decision-log.md` D-001 |
| 规划 | `PRD.md`（FR-1..FR-8、NFR-1..NFR-4、§11 溯源表） | 文件本身；D-010 改 FR-4 窗口语义 |
| 方案 | `architecture.md`（5 条 ADR）、`epics.md`（3 Epic / 12 Story / 88 条 AC）、`project-context.md`（R1–R8）、`sprint-status.yaml` | 文件本身；D-002、D-003、D-016 |
| 实施 | `src/` 与 `tests/`，209 条测试通过 | `git log --oneline --grep="story"` |
| 复审与裁决 | 15 条决策记录，7 条是否决或实质修改 AI 建议 | `decision-log.md`；`evidence/` 下对话截图 |
| 实验 | 实验 A 的 X/Y 对照与记录、实验 B 的影响分析 | `experiment-A-record.md`、`experiment-B-impact.md` |
| 复盘 | `retrospective.md` | 文件本身；D-017 封版裁定 |

## 4. 吴金宝的产出

| 阶段 | 产出 | 核验方式 |
| --- | --- | --- |
| 加分项 | BMB（BMad Builder）自定义工作流的 `SKILL.md`，附动机、做法与实际效果 | 仓库内该 skill 目录；对应提交 |
| 演示 | 10 分钟录屏：登录、查看格子、预约、并发冲突、取消、管理员改单、锁定、CSV 导出 | 视频文件；`README.md` 演示章节 |
| 发布 | GitHub 仓库、协作者提交、最终提交检查 | 仓库地址；`git shortlog -sn` |
| 校对 | 全部交付文档的通读校对与提交清单核对 | 校对后的提交记录 |

## 5. 关于提交记录

规划与实现阶段（12 个 Story）在一台开发机上连续推进，中途换机器要重建数据库、虚拟环境和测试临时目录，所以这一段的提交集中在同一个 Git 作者名下。加分项、录屏与发布阶段的提交由吴金宝署名，`git shortlog -sn` 里能看到两个作者。

```powershell
git shortlog -sn
git log --oneline --grep="story"
git rev-list --count HEAD
```

## 6. 决策由谁做

`decision-log.md` 的 15 条记录，每条都写了触发、AI 的建议、判断依据、结果和事后验证，其中 7 条否决或实质修改了 AI 的建议。这些判断由负责该阶段的人作出并记录，不是「AI 建议、我们同意」的流水账。