# 关了终端任务还在：看板、后台、Cron 和队友

> AgentHarness 系列（三）。提交 `1ff97ab` → `d336e9f`（2026-08-07～09-01）。

上一篇把窗口租金压下来了。真正当「编程助手」用的时候，洞换成了三件更像产品的事：

1. 进程一关，做到一半的计划蒸发。  
2. `pip install` 堵死主循环，模型干等。  
3. 你不可能 24 小时盯着 `>>` 提示符，也很快会觉得一个 Lead 不够用。

于是有了任务看板、后台慢命令、cron，以及整段最重的代码：队友线程、邮箱、计划协议、收尾屏障，和 idle 时自动认领。

---

## 任务看板：状态在磁盘上

`1ff97ab` / `1d06c76`。任务是 `.tasks/task_*.json`，不是对话里的 todo。

状态机很短：`pending` → `in_progress` → `completed`。`blockedBy` 写依赖，依赖没全部完成就不能认领。`owner` 来自当前 Agent 的 `current_agent`（ContextVar），模型不能在参数里伪造「我是 lead」。

例子：任务 A「搭数据库」、任务 B「做登录」且 `blockedBy=[A]`。B 会一直 pending，直到 A completed。这是调度事实，不是模型记性。

**金句：看板是磁盘上的事实，不是模型脑子里的待办。**

## 慢命令请去后台

`c4e4407`（`144d33f` 修了缩进）。`background.py` 用正则认 `pip install`、`pytest`、`docker build` 这类命令，或看 `run_in_background=true`。主循环立刻返回「已派发 bg_0001」，线程跑完后，下一轮当作 user 消息注入。

Lead 可以在安装依赖的同时继续读文件、改 todo。后来接 MCP 时补过一刀：后台 `execute_tool` 必须带上当时的 `handlers`，否则动态工具会变成「未知工具」。

## Cron：时钟也可以唤醒 Agent

`22fbc8a` / `da5e3a9`。5 段 cron（分 时 日 月 周），`recurring` 循环或一次，`durable` 则写 `.scheduled_.tasks.json`，重启还在。

实现上刻意拆成两条线程：调度器只往队列丢「到点了」；消费线程拿着和用户输入同一把 `agent_lock` 再跑 `agent_loop`。不要两轮 Agent 同时改 `session_history`。

`main.py` 现在就是：启动调度 → 启动消费 → 再进入 `input(">> ")`。人不是唯一的触发源。

**金句：唤醒 Agent 的不一定是人，也可以是时钟。**

## 队友：线程、邮箱、协议

`2920b96` 一次加了六百多行 `teams.py`，这是本篇的重心。

和七月的 `spawn_subagent` 对比写清楚：

| | subAgent | teammate |
|--|----------|----------|
| 方式 | 同步函数 | `daemon` 线程 |
| 上下文 | 干净、用完丢 | 自己的 messages，可 idle |
| 通信 | 返回值摘要 | `.mailboxes/*.jsonl` |
| 结束 | 函数 return | `BUS.send(..., type=result)` |

Lead 调 `spawn_teammate(name, role, prompt)`。身份用 ContextVar，发信不能冒充别人。邮箱**读即消费**，备份在 `.mailboxes_backup/`。

需要审批时：Lead `request_plan` → 队友 `submit_plan` → Lead `review_plan(request_id, approve)` → 队友等到 `plan_approval_response` 再继续或改计划。`request_shutdown` 走优雅退出，不是直接杀线程。

例子：Lead 让 `alice` 写 API、`bob` 写测试，各干各的，用 `send_message` 对齐字段名。主循环不用同步堵住。

## 收尾屏障：没看见 result 不许说完成

异步的最后一公里最容易装懂。`582460b` 之前的典型事故：队友还在跑，result 还在邮箱里，Lead 已经对用户说「做完了」。

补丁是一张名单 `pending_teammate_results`：

- spawn 时 `add(name)`
- 读到 `type=result` 且 `spawn_id` 对得上，再 `discard`
- 理想路径：Lead 调 `await_teammates`，轮询收件箱，默认最多等 120 秒
- 兜底：模型突然不调工具、准备 Stop——在 Stop hook **之前**走 `apply_teammate_stop_barrier`，等待、注入收件箱、再给一轮汇总。次数封顶 `TEAMMATE_BARRIER_ROUNDS`（默认 1），防止拦完又说结束再拦。

同名重启会换新的 `spawn_id`，上一轮残留的 result 不会误清这一轮的 pending。

踩过的实现坑可以直接当段子：`await_teammates` 一度写进了队友的工具表。Lead 看不见，队友调了还被 handler 拒绝。这类工具必须挂在 Lead 的 `TOOLS` 上。

**金句：异步派工的最后一公里，是等到信，而不是假设对方干完了。**

## 看板自治：idle 时自己认领

`d336e9f`。队友空闲超时前，运行时扫描「pending、无 owner、依赖已满足」的第一条并 `claim_task`。这是调度策略，**不经过模型 tool_call**。

模型负责干活；认不认领由运行时按规则做。少一轮「你要不要领这个任务？」的幻觉。

## 关键代码落在哪

- `tasks.py`、`background.py`、`cron.py`
- `main.py` 的 `agent_lock` 与两条 cron 线程
- `teams.py`：spawn、MessageBus、屏障、idle 认领
- `agent.py` 里 Stop 前的 `apply_teammate_stop_barrier`

## 还没解决的

两个队友如果都在**同一工作目录**改文件，邮箱再隔离也救不了 git 冲突。外部能力也不该无限写进 `handlers.py`。下一篇是 worktree 和 MCP。
