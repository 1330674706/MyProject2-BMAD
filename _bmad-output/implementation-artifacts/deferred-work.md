- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 补 README 的单条启动命令、环境变量表与 seed 说明。
  evidence: 本次用户明确只交付三件事，文档不在范围内；Story 1.4 AC1 的「README 中的命令」目前只有终端命令本身可用。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 实现 `LAB_ADMIN_USER` / `LAB_ADMIN_PASSWORD` 管理员种子并补 AC7 测试。
  evidence: 用户本次明确不交付管理员账号种子；`sprint-status.yaml` 置 review 而非 done，留待人工决定是否补做。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 补「数据目录恰好 1 个 .db」与「复制 .db 到新路径后 occupancy 计数一致」两条 Story AC 的断言。
  evidence: 两条不在用户本次三件事内；且 WAL 下非优雅停止后只复制 `.db` 可能丢最后提交，需先 `VACUUM INTO` 或连同 `-wal`/`-shm` 一起复制（architecture 评审 M-11）。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 让 `/health` 的数据库异常返回 503 而不是 Flask 默认 500，并避免每次探活都写一条 INFO 日志。
  evidence: architecture §15.1 只要求「可用时返回 200」，未规定异常状态；单机 40 人规模下 500 已能表达不可用，日志量可接受。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 拒绝表头正确但零数据行的 seed 文件，并校验 `equipment_id` 的字符/长度。
  evidence: 空清单按「幂等导入 0 台」处理是当前明确语义；architecture §11 允许可读 slug，但未给格式约束，新增规则需先改规划文档。

- source_spec: `_bmad-output/implementation-artifacts/spec-1-4-ops-startup.md`
  summary: 统一 `PRD.md` §11 与 `epics.md` 关于 FR-2 是否由 Story 1.4 承载的表述。
  evidence: 规划文档自相矛盾，属文档漂移；按 R7 修文档需同一改动同步 §11，不在本次代码交付范围。
