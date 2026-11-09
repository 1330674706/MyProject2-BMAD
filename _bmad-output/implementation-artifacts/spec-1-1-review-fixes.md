---
title: 'Story 1.1 复审修复（F1/F2/F3/F4/F7/F8/F9/F11/F12）'
type: 'bugfix'
created: '2026-11-09'
status: 'done'
route: 'oneshot'
review_loop_iteration: 0
context:
  - project-context.md
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 1.1 复审的 19 条发现中，裁定只修复 9 条：匿名 CSRF 未绑定客户端（F1）、迁移绕过 write_tx（F2）、AC7 缺状态码断言（F3）、重置后缺旧密码 401 断言（F4）、重置未限制目标角色（F7）、IntegrityError 按消息文本分类（F8）、脱敏白名单缺 booking/equipment（F9）、.gitignore 缺 data/ 与 *.db（F11）、注册模板重复 minlength（F12）。

**Approach:** 每条先补/改测试并确认失败，再改实现。F1 改为独立 `csrf` cookie 的 double-submit，并新增「另一客户端用自己的 token → 400」用例。只修这 9 条，不碰 F5/F6/F10/F13/F14/F15-F18/F19。

</frozen-after-approval>

## Implementation Notes

范围以 `decision-log.md` D-008 为准；Story 1.1 在 `sprint-status.yaml` 结束时保持 `review`。

- 红灯基线：新增/修改测试后 `python -m pytest -q --ignore=_bmad` 为 11 failed / 6 passed。
- 绿灯结果：实现完成后同一命令为 23 passed。
- F1：`src/web/csrf.py` 改为签名 token 的独立 `csrf` cookie double-submit，不再把 token 写入 session；签名检查保留 12 小时服务端时效，登录与登出都轮换 token；`app.py` 的 `after_request` 负责回写 cookie。新增「另一客户端用自己的 token → 400」「篡改 cookie → 400」「CSRF 400 不带 session cookie」用例。
- F2：`src/data/migrations.py` 改为逐语句在 `write_tx()` 内执行，`PRAGMA user_version` 同事务提交；新增 write_tx 调用与失败回滚两个用例。
- F3/F4：按 D-008 属于断言缺口，测试补齐后现有实现即通过；未改业务代码。
- F7：`reset_password()` 在事务内校验目标 `role == "student"`，否则抛 `Validation`，HTTP 映射为 400。
- F8：`register()` 先按 `sqlite_errorname == "SQLITE_CONSTRAINT_UNIQUE"` 分类，再用冲突列补充判断。
- F9：白名单补 `booking`/`equipment`，字段取架构 §5/§10.2 的领域字段与 `slots`。
- F11：`.gitignore` 补 `/data/` 与 `*.db`；`data/lab.db` 命中忽略，`src/data/*.py` 不被误伤。
- F12：删除注册模板的 `minlength`，密码长度规则只保留在服务层。
- 环境说明：bmad-build 生成的 `_bmad/render/.../4cf7e3c20bffb8c39ffd` 带 ACL 拒绝，裸 `pytest -q` 会在收集阶段报 `PermissionError`；测试命令统一加 `--ignore=_bmad`。

## Review Triage Log

- 高｜`.gitignore` 的 `data/` 会误伤 `src/data/`：已改为 `/data/`，并验证 `git check-ignore src/data/booking_repo.py` 不命中。
- 低｜`*.db` 过宽且缺 WAL 伴生文件：按用户指定的 F11 范围保留 `*.db`，当前无 fixture 库或非 `data/` 运行库，暂不扩展。
- 中｜double-submit 与 ADR-004「token 存入会话」冲突：按用户 F1 指令实现，ADR-004 文本同步需文档负责人确认；本次不扩到架构/PRD。
- 高｜未签名 double-submit 可被钉 cookie 绕过：已改为 `SECRET_KEY` 签名 token，新增篡改 cookie 用例。
- 高｜token 失去服务端时效：签名 token 恢复 `max_age=12h` 服务端校验。
- 中｜登出不轮换 CSRF cookie：已补 `rotate_csrf_token()`，新增登录/登出轮换用例。
- 假｜非 ASCII token 500：签名校验先执行，非 ASCII 输入走 `BadSignature → 400`，不再触发 `compare_digest` 的 TypeError。
- 低｜cookie 属性硬编码/名称通用：当前单应用部署无实际影响，改配置抽取属重构，未做。
- 低｜`set_csrf_cookie` 放在 `log_request` 内：命名可读性问题，当前无早退分支，未做结构重构。
- 中｜`_statements` 不支持单行多语句：已改为逐字符按 `complete_statement` 切分，并新增单行多语句迁移用例。
- 低｜迁移脚本自带 BEGIN/COMMIT 的报错不明确：现有迁移不自管事务，新增守卫属范围外，未做。
- 中｜迁移测试缺成功路径与幂等：已补 `user_version == 1`、表已建、重复调用不重复执行断言。
- 高｜登录成功测试断言到 csrf cookie：已改为按 `session=` 筛选 `Set-Cookie`，AC2 恢复检查会话 cookie。
- 中｜新 csrf cookie 缺测试：已补 cookie 属性、表单/cookie 绑定、登录/登出轮换、篡改拒绝用例。
- 中｜删 `minlength` 后缺服务端 8 位测试：已补 7 位密码 → 400 且零行用例。
- 中｜`dump_fields` 对 `sqlite3.Row`/未知类型报错形态差：属于 2.1 首次写审计时的输入形态问题，F9 未要求改函数，暂缓。
- 中｜`booking`/`equipment` 白名单未绑定真实行形状：属 2.1 接入审计时验证，F9 只要求补白名单，暂缓。
- 低｜迁移/脱敏测试放在 `test_auth_login.py`：`epics.md` 指定 Story 1.1 测试文件即此文件，且对应 Story 尚未创建，维持现状。
- 低｜F7 用 400 而非 403、且失败路径先算哈希：目标角色是请求合法性校验，`Validation → 400` 符合 §11；已补文案断言。哈希在事务外计算可避免拉长 `BEGIN IMMEDIATE`，保留。
