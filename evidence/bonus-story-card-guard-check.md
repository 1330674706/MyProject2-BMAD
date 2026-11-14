# BMB 自定义工作流：故事卡约束检查

## 选题与制作依据

实验 A 故事卡把文件交付位置与验收要求分开写，单独阅读任一行都不容易看出架构冲突。为减少按卡实现后的返工，定制 `lab-story-card-guard`，供开发者在编码前审查故事卡。

在项目的 BMAD 6.12.4 环境中安装 BMad Builder v2.2.2，按 `bmad-workflow-builder` 的 **Edit** 路径修订已有技能草稿，采用其“结果面向使用者、在真实输入上试运行、剔除多余步骤”的标准。采用独立的只读工作流技能；项目不需要新增运行期依赖，也不需要启动 Web 应用。自定义技能避开官方保留的 `bmad-` 前缀。

BMB v2.2.2 源文件来自官方标签；因本机无法直连 GitHub，通过 GitHub 连接取得 `skills/` 下 125 个文件并逐个核对 Git blob SHA，再交给安装器从本地镜像安装。项目的 `_bmad/_config/manifest.yaml` 现含 `bmb`，`.agents/skills/bmad-workflow-builder/SKILL.md` 可读取。安装清单中的 `sha` 是本地镜像提交号，不是官方标签提交号。

来源：

- BMB Workflow Builder：<https://github.com/bmad-code-org/bmad-builder/blob/main/skills/bmad-workflow-builder/SKILL.md>
- BMB 构建流程：<https://github.com/bmad-code-org/bmad-builder/blob/main/skills/bmad-workflow-builder/references/build-process.md>
- BMB 质量与命名约定：<https://github.com/bmad-code-org/bmad-builder/blob/main/skills/bmad-workflow-builder/references/skill-quality-principles.md>

## 实际效果：实验 A 故事卡

在本项目内调用 `lab-story-card-guard` 的审查流程。输入：`_bmad-output/implementation-artifacts/experiment-A-story-card.md`；约束：`project-context.md`。所得结论：**1 项明确冲突，1 项待澄清；建议先修卡。**

| 类型 | 故事卡证据 | 规则证据 | 判断与建议 |
| --- | --- | --- | --- |
| 明确冲突 | 第 28 行指定新增 `src/core/slotfmt.py`；第 30 行要求不改现有模块；第 38 行要求非连续输入抛 `ValueError` | `project-context.md` 第 10 行，R1：slot 形状校验只在 `src/app/slot_rules.py` | 三项合看会把连续性校验压到新建的 core 模块。最小改法：明确输入已由 `slot_rules.py` 校验为连续 slot，移除格式化函数的非连续输入验收项。若本故事必须完成校验，则扩展交付面，在 `slot_rules.py` 添加校验并由服务层调用。 |
| 待澄清 | 第 28 行指定新建 core 模块；第 39 行要求输出本地墙钟 | `project-context.md` 第 13 行，R4：`Asia/Shanghai` 转换只在 `src/core/timeutil.py` | 故事卡没有指定转换位置。应写明 `slotfmt.py` 调用 `timeutil.py` 的转换能力，不自行进行时区转换；现有文字尚不能判定违反 R4。 |

第 37 行的空列表异常也可能只是格式化函数的输入前提检查；证据不足，未列作明确 R1 违规。R2、R3、R5–R8 未见故事卡层面的明确冲突，实施后的测试顺序和代码行为仍须另行核验。

## 对照检查与边界

对照描述：“在 `src/core/slotfmt.py` 格式化已由 `slot_rules.py` 校验为连续的 slot；时区转换调用 `timeutil.py`；不在格式化函数内校验连续性。”按同一标准，此描述本身**不应因出现 `src/core/` 而被判 R1 违规**。这说明检查依据是交付位置与行为的组合，而非关键词。

## BMB 校验

使用已安装的 `bmad-workflow-builder/scripts/` 检查：`quick_validate.py` 通过；对待交付的纯技能目录运行 `scan-path-standards.py` 通过且无发现；`scan-scripts.py` 通过（技能没有自带脚本）。真实故事卡试审和上述对照描述分别检查漏报与误报风险。

BMB 制作过程的本地 `.memlog.md` 按 Builder 要求保留在技能目录，路径扫描器会把它误判为额外的提示词文件；交付的纯技能目录不包含该过程文件。上述结果是对文档的工作流试审，不是对系统运行或代码实现合规性的测试。
