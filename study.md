# Skills 工作流程
程序启动
  ↓
扫描 skills/*/SKILL.md
  ↓
建立 SKILL_REGISTRY
  ↓
System Prompt 注入技能名称和简介
  ↓
用户提出任务
  ↓
模型判断是否需要某个 Skill
  ↓
调用 load_skill(name)
  ↓
完整 Skill 作为 Tool 结果返回
  ↓
模型按照完整 Skill 工作

# Memory 工作流程
用户与 Agent 对话
  ↓
Agent 保存压缩前的消息快照 pre_compress
  ↓
Agent 完成本轮任务
  ↓
extract_memories() 从近期对话提取长期记忆
  ↓
write_memory_file() 写入 Markdown 文件
  ↓
rebuild_index() 更新记忆索引
  ↓
下一次用户提出问题
  ↓
select_relevant_memories() 选择相关记忆
  ↓
load_memories() 读取记忆正文
  ↓
追加到 System Prompt
  ↓
主 LLM 同时看到当前任务和相关长期记忆

### Skills：Agent 的“能力说明书 / 操作手册” Skill 不是当前项目的事实，也不是待办事项。它更像一份预先写好的 SOP（标准操作流程）：
###  History 压缩用于控制当前 messages 对话历史的体积，其中 Tool 输出是重点压缩对象；
###  Task System 用于让 Agent 跨会话保存和恢复“任务计划、状态、依赖与进度”，它不是原始对话记录，也不是模型本身的内部记忆 它保存的是执行状态
### Memory 这是长期背景知识。
### TODO 是本次会话的简单清单
### Worktree 是并行改码的目录/分支隔离，不是任务状态本身
### MCP 是运行时发现的外部工具（当前为 mock），名字带 mcp__server__tool 前缀


# tasks 工作流程
创建任务 A：搭建数据库
状态：pending

创建任务 B：实现登录功能
状态：pending
依赖：blockedBy = [任务 A]

尝试认领 B
  ↓
can_start(B)
  ↓
发现 A 还不是 completed
  ↓
B 不能开始，保持 pending

认领 A
  ↓
A: pending → in_progress

完成 A
  ↓
A: in_progress → completed

再次认领 B
  ↓
can_start(B)
  ↓
发现所有依赖均为 completed
  ↓
B: pending → in_progress



# 调度定时工作流程

程序启动
  ↓
load_durable_jobs()
  ↓
从 .scheduled_.tasks.json 读取持久化 CronJob
  ↓
放入 schedule_jobs
  ↓
cron_scheduler_loop() 永远循环检查 schedule_jobs
  ↓
时间不匹配
  ↓
什么也不做，cron_queue 仍为空
  ↓
时间匹配
  ↓
把“这一次触发事件”放入 cron_queue
  ↓
_queue_processor_loop() 发现 cron_queue 不为空
  ↓
调用 Agent
  ↓
agent_loop() 中 consume_cron_queue()
  ↓
取出这一次待执行事件并清空 cron_queue
  ↓
Agent 执行 prompt
  ↓
下一分钟 cron_scheduler_loop() 再次检查同一个 schedule_jobs 里的任务


# 队友屏障工作流程
Lead spawn_teammate(name)
  ↓
pending_teammate_results.add(name)
  ↓
队友线程干活，结束时 BUS.send(..., type=result, spawn_id)
  ↓
Lead 读收件箱 → _mark_results_received → discard(name)
  ↓
理想路径：Lead 调用 await_teammates → wait_for_teammates 轮询邮箱
  ↓
兜底：Lead 无 tool_calls 准备结束
  ↓
apply_teammate_stop_barrier
  ↓
仍有 pending → 等待 TEAMMATE_WAIT_TIMEOUT → 注入收件箱 → 再给 Lead 一轮汇总
  ↓
TEAMMATE_BARRIER_ROUNDS 用尽后允许真正 Stop

### 未看到 result 前不要向用户声称完成。同名重启会换 spawn_id，旧 result 不会误清新一轮屏障。


# Worktree 工作流程
create_worktree(name, task_id?)
  ↓
git worktree add ../.worktrees/<name> -b wt/<name>
  ↓
可选 bind_task_to_worktree（只写 task.worktree，不改任务状态）
  ↓
文件工具带 cwd，读写限制在该目录
  ↓
remove_worktree（有未提交变更则拒绝，除非 discard_changes）
或 keep_worktree（保留目录与分支供审查）
  ↓
事件追加 .worktrees/events.jsonl


# MCP 工作流程
connect_mcp("docs" | "deploy")
  ↓
MOCK_SERVERS 工厂创建 MCPClient 并 register 工具
  ↓
写入 mcp_clients
  ↓
agent_loop 每轮 assemble_tool_pool()
  ↓
TOOLS + mcp__docs__search / mcp__deploy__trigger 等
  ↓
execute_tool(..., handlers=动态池) 按前缀分发给 MCPClient.call_tool
  ↓
系统提示追加 connected_mcp_summary()

### 这是进程内 mock，不是真实 MCP 网络连接。队友线程看不到这些工具。
