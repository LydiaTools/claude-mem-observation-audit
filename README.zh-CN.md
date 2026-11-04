# Claude-Mem 观察关联检查

[English](README.md)

一次工具调用已经写入记录，不代表它已经关联到记忆观察。排查工作进程重启或额度冷却时，你可能想先看清：哪些记录还没有关联，它们已经等了多久。

Claude-Mem 观察关联检查是一个只读 Python 命令行工具。它统计 tool_uses 表中 observation_id 为空的行，把近期记录与较早的复核线索分开；会话详情默认隐藏，需要时再显式显示。

它不会判定数据已经丢失。未关联记录可能仍在处理，也可能不会生成观察记录。

## 先看示例

~~~bash
python3 claude_mem_audit.py --demo
~~~

示例只使用合成的内存数据库，不会打开你本机的 Claude-Mem 文件。

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

## 它会检查什么

- 统计 tool_uses 表的总行数。
- 统计已关联和未关联 observation_id 的行数。
- 将近期记录与较早的复核线索分开。
- 可选列出较早记录所属的会话和项目名。
- 数据库缺少预期表或必需字段时停止，不猜测结构。

工具以 SQLite mode=ro 打开数据库，只查询表结构和聚合计数；不会读取工具输入、工具响应或提示词字段，也不会联网发送数据。

## 它不会声称什么

- 较早的未关联记录不等于记忆已经丢失。
- 工具不会恢复、重发、删除或修改任何记录。
- 工具不会检查工作进程健康，也不会重建处理队列。
- 工具不解析日志。[Claude-Mem issue #4737](https://github.com/thedotmack/claude-mem/issues/4737) 中已有单独的停放批次日志计数方案；本项目检查的是 SQLite 中的关联状态。
- 当前按 Claude-Mem v15.9.0 的 tool_uses 结构设计。结构变化时会停止，而不是猜字段。

## 为什么做这个检查

用户曾报告额度冷却或工作进程重启后，有观察记录仍未关联：[issue #4580](https://github.com/thedotmack/claude-mem/issues/4580)。[issue #4737](https://github.com/thedotmack/claude-mem/issues/4737) 讨论了停放批次和恢复限制。Claude-Mem v15.9.0 的 [doctor 命令](https://github.com/thedotmack/claude-mem/blob/v15.9.0/src/npx-cli/commands/doctor.ts)会检查安装和工作进程健康状态，但不会查询 tool_uses.observation_id。

这个小工具让你看见数据库关联状态，同时不读取已存储的工具内容。

## 预览状态与反馈

合成示例已在 macOS Python 3.9 上运行。真实用户数据库的兼容性尚未得到独立确认。试用后可以在 [Issues](../../issues) 反馈 Claude-Mem 版本、操作系统、Python 版本和字段兼容问题。

请勿在 Issue 中附上数据库、工作进程日志、提示词、工具输入或工具响应。

## 项目范围

- 仅使用 Python 标准库。
- 独立社区工具，与 Claude-Mem 维护者无隶属关系。
- MIT 许可证。
