# Claude-Mem 观察关联检查

[English](README.md)

队列深度显示 0，也不一定能回答每条工具调用后来发生了什么。排查工作进程重启或额度冷却时，这个小工具把两类只读线索放在一起：数据库关联计数，以及你指定的工作进程日志标记。

Claude-Mem 观察关联检查是一个只读 Python 命令行工具。它统计 `tool_uses` 表中 `observation_id` 为空的行，把近期记录与较早的复核线索分开；也可以统计日志里有记录的停放批次和会话结束标记。会话详情默认隐藏，需要时再显式显示。

它不会判定数据已经丢失。未关联记录可能仍在处理，也可能不会生成观察记录。

## 快速开始

~~~bash
git clone https://github.com/LydiaTools/claude-mem-observation-audit.git
cd claude-mem-observation-audit
python3 claude_mem_audit.py --demo
~~~

需要 Python 3.9 或更新版本，不需要安装第三方包。示例只使用合成的内存数据库，不会打开你本机的 Claude-Mem 文件。

示例输出：

~~~text
Claude-Mem observation audit
Read-only · aggregate counts only unless session details are requested

Database: synthetic in-memory demo
Tool-use rows: 4
Linked: 1 · unlinked: 3 (recent: 1)
Older than 24h: 2 row(s) across 1 session(s)

Interpretation: older unlinked rows are review candidates, not proof of lost memory.
Recent unlinked rows may still be processing or may not produce an observation.
~~~

## 检查本机数据库

Claude-Mem 默认数据库路径：

~~~bash
python3 claude_mem_audit.py ~/.claude-mem/claude-mem.db
~~~

也可以指定数据库路径和复核时间：

~~~bash
python3 claude_mem_audit.py /path/to/claude-mem.db --stale-hours 48
~~~

会话 ID 和项目名默认隐藏。需要定位具体记录时再显示：

~~~bash
python3 claude_mem_audit.py ~/.claude-mem/claude-mem.db --show-sessions --json
~~~

## 检查指定的工作进程日志

统计一个日志文件里的停放批次标记：

~~~bash
python3 claude_mem_audit.py --worker-log /path/to/worker.log
~~~

轮转日志可以重复传入；也可以把日志计数和数据库检查合并：

~~~bash
python3 claude_mem_audit.py --worker-log worker.log --worker-log worker.log.1
python3 claude_mem_audit.py ~/.claude-mem/claude-mem.db --worker-log worker.log --json
~~~

日志扫描识别公开讨论中记录的 `Batch parked` 标记（含 `parkedMessageIds` 和 `paidSendsSpent`），以及 `Session ended with parked batches; they were never resent`。输出只包含汇总计数，不显示消息 ID 或原始日志行。没有匹配到已支持的标记时会明确说明；零匹配不等于没有发生过问题。

## 它会检查什么

- 统计 tool_uses 表的总行数。
- 统计已关联和未关联 observation_id 的行数。
- 将近期记录与较早的复核线索分开。
- 可选列出较早记录所属的会话和项目名。
- 对指定日志计数停放批次、消息 ID 出现次数和重复次数、付费发送次数，以及会话结束丢弃标记。
- 数据库缺少预期表或必需字段时停止，不猜测结构。

工具以 SQLite mode=ro 打开数据库，只查询表结构和聚合计数；不会读取工具输入、工具响应或提示词字段，也不会联网发送数据。

## 它不会声称什么

- 较早的未关联记录不等于记忆已经丢失。
- 工具不会恢复、重发、删除或修改任何记录。
- 工具不会检查工作进程健康，也不会重建处理队列。
- 日志标记不等于数据库记录缺失或可恢复的证明；没有识别到日志标记，也不能证明没有队列事件丢失。
- 当前按 Claude-Mem v15.9.0 的 tool_uses 结构设计。结构变化时会停止，而不是猜字段。
- 日志识别仅覆盖上面列出的公开 15.x 消息格式，不是完整的工作进程日志解析器。

## 为什么做这个检查

用户曾报告额度冷却或工作进程重启后，有观察记录仍未关联：[issue #4580](https://github.com/thedotmack/claude-mem/issues/4580)。[issue #4737](https://github.com/thedotmack/claude-mem/issues/4737) 中也有用户报告停放批次和会话结束时的丢弃计数，并讨论队列深度为零时仍可能存在停放事件。Claude-Mem v15.9.0 的 [doctor 命令](https://github.com/thedotmack/claude-mem/blob/v15.9.0/src/npx-cli/commands/doctor.ts)会检查安装和工作进程健康状态，但不会查询 tool_uses.observation_id。

这个小工具让你查看数据库和指定日志中的线索，不读取工具内容，也不会联网发送本地数据。

## 预览状态与反馈

合成数据库示例已在 macOS Python 3.9 上运行。新的日志扫描仍是早期预览，依据公开的 15.x 日志标记实现；真实数据库和所有日志格式的兼容性尚未得到独立确认。试用后可以在 [Issues](https://github.com/LydiaTools/claude-mem-observation-audit/issues) 反馈 Claude-Mem 版本、操作系统、Python 版本和识别结果。

请勿在 Issue 中附上数据库、工作进程日志、提示词、工具输入或工具响应。

## 项目范围

- 仅使用 Python 标准库。
- 独立社区工具，与 Claude-Mem 维护者无隶属关系。
- MIT 许可证。
