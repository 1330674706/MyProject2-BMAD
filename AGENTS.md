# AGENTS.md

本仓库的智能体工作规则集中在 `project-context.md`（`bmad:context` 托管块）。开工前必须完整读取该文件；其中 `R1`–`R8` 是硬规则，违反即视为改动不成立，不得以「为了跑通」「这样更简单」为由豁免。

- 文档冲突时以 `_bmad-output/planning-artifacts/architecture.md` 为准。
- 改动 PRD、架构或故事文件，必须在同一改动中同步 `PRD.md` §11 溯源表。
- 新增运行期依赖前先补 ADR，且不得触碰 `architecture.md` §16 禁止技术表。
- 不得把任何 Story 的状态改为 `done`，最多 `review`。
