# AgentHarness 博客素材（按提交记录梳理）

> 用途：以后写博客/系列文时当提纲和事实底稿，**不是**对外 README。  
> 成稿（4 篇长文）：见 [`docs/blog/`](./blog/README.md)  
> 仓库：`liuchao0111/agent_harness`（本地目录 AgentHarness）  
> 跨度：2026-07-24 → 2026-09-03（约 6 周）  
> 统计：约 30 次有效提交（不含 merge / 清 .env 噪音）  
> 用法：每篇文章对应下面「建议系列」里的一集；细节从「时间线章节」抄问题、设计、关键文件和 commit hash。

---

## 一条主线（给读者讲什么）

不是「又一个 ChatGPT wrapper」，而是：**把编程 Agent 从「能调工具的循环」一层层补成接近真实产品的运行时。**

每一层都在修上一层暴露出来的洞：

```
能跑（LLM + 工具）
  → 不能乱删文件（权限 / hooks）
  → 会跑偏（todo）
  → 上下文爆炸（subagent / skills / 压缩）
  → 下次开场失忆（memory）
  → API 动不动挂（重试）
  → 关了终端任务就没了（task）
  → pip install 卡死主循环（后台）
  → 人得盯着（cron）
  → 一个人干不过来（队友 + 邮箱 + 协议）
  → 没等结果就跟用户说做完了（屏障）
  → 并行改码互相覆盖（worktree）
  → 工具不能全写进内核（MCP）
```

博客可以反复用这句话：**每加一层，都是上一层在真实使用里崩掉之后的补丁。**

---

## 建议拆成的系列（可直接当标题）

| 集 | 建议标题 | 覆盖提交 | 读者能带走什么 |
|----|----------|----------|----------------|
| 0 | 为什么要自己写一个 Agent Harness | 总述 | 产品形态：CLI Lead + 工具循环 |
| 1 | 最小内核：while True + tool_calls | `f45de08` | 20 行思想，agent/llm/tools 三分 |
| 2 | 权限不该交给模型自觉 | `5ee8922` `56e6fe7` | PreToolUse / 危险命令 |
| 3 | TodoWrite：先计划再动手 | `d04481f` | 防跑偏 |
| 4 | 子 Agent：干净上下文拆任务 | `110678b` | 同步 spawn，只收回结论 |
| 5 | Skills：SOP 按需加载，别塞满 system | `559710c` | 注册表 + load_skill |
| 6 | 上下文四层压缩 | `21b9296`～`905995a` | 落盘 / 条数 / 摘要 |
| 7 | Memory：跨会话的偏好，不是聊天记录 | `fecebdc` | 抽取、索引、注入 prompt |
| 8 | 重试与 529：模型也会过载 | `80486e8` | 指数退避、备用模型 |
| 9 | 任务看板：状态存在磁盘上 | `1ff97ab` `1d06c76` | pending / 依赖 / owner |
| 10 | 慢命令请滚去后台 | `c4e4407` | 线程 + 下一轮注入结果 |
| 11 | Cron：时间驱动唤醒 Agent | `22fbc8a` `da5e3a9` | 调度线程 vs agent_lock |
| 12 | 队友：线程、邮箱、计划审批 | `2920b96` | MessageBus + protocol |
| 13 | 收尾屏障：没看见 result 不许说完成 | `582460b` | pending set + Stop 拦截 |
| 14 | 看板自治：idle 时自己认领 | `d336e9f` | 运行时认领，不经模型 |
| 15 | Worktree：并行改码的目录隔离 | `1fa7cce` `553c574` | git worktree + cwd |
| 16 | MCP：工具不必写死在内核 | `f4274ae` | 连接 → 发现 → mcp__ 前缀 |

一周一更的话，这就是约 4 个月的存货；也可合成 4 篇长文：内核 / 上下文与记忆 / 协作与时间 / 隔离与扩展。

---

## 时间线章节（写文章时逐段展开）

### 2026-07-24 最小内核

- **Commit**：`f45de08` 最小可运行的agent内核
- **问题**：没有循环、没有工具，模型只能聊天。
- **做了什么**：`main` 读用户输入 → `agent_loop` 调 LLM → 有 `tool_calls` 就执行 bash/读写文件 → 结果塞回 messages 再调。
- **关键文件**：`agent.py` `llm.py` `tools/{schema,handlers,executor}.py` `config.py`
- **可写细节**：OpenAI 兼容接口（可换网关）；`.env` 后来从仓库拿掉（`a232137`），博客里强调密钥不入库。
- **不必写**：连续几次「清楚.env / ignore」属于卫生提交。

### 2026-07-25 权限

- **Commit**：`5ee8922` feat: 执行前做权限判断
- **问题**：模型会 `rm`、会写到工作区外。
- **做了什么**：`permission.py`；禁止模式直接拒，破坏性关键字要用户 `yes`。
- **金句**：权限是循环外的硬闸门，不是 prompt 里的「请你小心」。

### 2026-07-27 Hooks 与 Todo

- **Commit**：`56e6fe7` hooks创建 挂在循环之外；`d04481f` ToDoWrite 计划agent 不然会偏离
- **Hooks**：`UserPromptSubmit` / `PreToolUse` / `PostToolUse` / `Stop`，循环不改、行为可插。
- **Todo**：本会话清单，连续多轮不更新会提醒。博客可对比「ReAct 乱跑」vs「先写步骤」。

### 2026-07-28 子 Agent 与 Skills

- **Commit**：`110678b` subAgent；`559710c` skills 扫描与注入
- **子 Agent**：同步、最多约 30 轮、`BASE_TOOLS`、干净 messages，只把摘要还给 Lead。强调「不是多线程队友，是函数调用」。
- **Skills**：启动扫 `skills/*/SKILL.md`，system 只放简介，`load_skill` 才给全文。对比「把 100 页文档塞进 prompt」。

### 2026-07-29～30 上下文压缩（可写成技术向一篇）

| 层 | Commit | 机制 |
|----|--------|------|
| 大结果落盘 | `21b9296` | tool 输出过长 → 写文件，messages 里留路径+截断 |
| 条数裁剪 | `6917886` | 自定义 50 条，头尾保留 |
| LLM 摘要 | `8f4b41f` `54015b0` `905995a` | 超 `CONTEXT_LIMIT` 后 compact |

- **关键文件**：`history.py`（后来叠了 snip / micro / reactive compact）
- **金句**：上下文窗口是租金，tool 结果是最能把租金烧光的东西。

### 2026-08-05 Memory

- **Commit**：`fecebdc`（`ceb6b91` 为重复/同步，写博客时只提一次）
- **和 Skill / Task / Todo 的边界**（现成对比段，可直接扩写）：
  - Skill = 预先写好的 SOP
  - Memory = 对话里沉淀的偏好与事实（`.memory/`）
  - Task = 跨会话执行状态（`.tasks/`）
  - Todo = 本次会话清单
  - History compact = 只缩当前 messages 体积
- **流程**：任务结束 `extract_memories` → 写 md → 重建索引 → 下次按相关度注入 system。

### 2026-08-06 重试

- **Commit**：`80486e8`
- **问题**：429 / 529 / 上下文过长。
- **做了什么**：`with_retry`、指数退避、连续 529 切 `FALLBACK_MODEL`、过长则 reactive compact 再试。
- **可写坑**：retry 闭包要绑死本轮的 `system`/`messages`/`tools`，并在调用时读 `state.current_model`，否则切备用模型不生效。

### 2026-08-07 任务看板

- **Commit**：`1ff97ab` 工具面；`1d06c76` `tasks.py` 落地
- **状态机**：`pending` → `in_progress` → `completed`；`blockedBy` 全完成才能认领；`owner` 来自 `current_agent`，模型不能伪造。
- **金句**：看板是磁盘上的事实，不是模型脑子里的待办。

### 2026-08-08 后台慢命令

- **Commit**：`c4e4407`；缩进修复 `144d33f`
- **问题**：`pip install` 堵死 Lead 循环。
- **做了什么**：`background.py` 正则认慢命令，或 `run_in_background=true`；线程跑完，下一轮当 user 消息注入。
- **可写坑**：后台线程必须带上当前 `handlers`，否则后来的 MCP 工具会报「未知工具」。

### 2026-08-11 Cron

- **Commit**：`22fbc8a` schema/handler；`da5e3a9` `cron.py` + 调度线程
- **设计**：5 段 cron；`durable` 写 `.scheduled_.tasks.json`；调度线程只入队，`agent_lock` 保证和用户输入不同时跑两轮 Agent。
- **金句**：唤醒 Agent 的不一定是人，也可以是时钟。

### 2026-08-25 队友协议

- **Commit**：`2920b96`（大提交：`teams.py` +627）
- **形态**：Lead `spawn_teammate` → daemon 线程、独立 messages、`ContextVar` 身份。
- **通信**：`.mailboxes/<name>.jsonl` 读即消费；备份目录追加。
- **协议**：`request_plan` / `submit_plan` / `review_plan`；`request_shutdown`。
- **结束**：线程收尾 `BUS.send(..., type=result)`。
- **强调**：这是多线程队友，不是 07-28 那个同步 subagent。

### 2026-08-31 队友屏障

- **Commit**：`582460b`
- **问题**：result 还在邮箱里，Lead 已经对用户说「做完了」。
- **做了什么**：
  - 名单 `pending_teammate_results`
  - 主动：`await_teammates`（仅 Lead）
  - 兜底：无 `tool_calls` 时 `apply_teammate_stop_barrier`，最多 `TEAMMATE_BARRIER_ROUNDS` 次
- **可写坑**：工具必须挂在 Lead 的 `TOOLS` 上，不能挂在 `TEAMMATE_TOOLS`；同名重启要换 `spawn_id`，免得旧 result 清掉新一轮 pending。
- **金句**：异步派工的最后一公里，是「等到信」而不是「假设对方干完了」。

### 2026-09-01 看板自治

- **Commit**：`d336e9f`
- **做了什么**：队友 idle 结束时，运行时扫「pending、无 owner、依赖已满足」的任务并 `claim_task`，**不经过模型 tool_call**。
- **金句**：认领是调度策略，不必再问 LLM「你要不要领」。

### 2026-09-03 Worktree

- **Commit**：`1fa7cce` 工具声明；`553c574` `worktrees.py` 实现
- **问题**：两个队友同时改同一工作区会互相覆盖。
- **做了什么**：`create_worktree` → 父目录 `.worktrees/<name>` + 分支 `wt/<name>`；文件工具可带 `cwd`；`remove_worktree` / `keep_worktree`；可 `task_id` 绑定且不改任务状态。
- **金句**：隔离的是文件系统和分支，不是「再开一个模型」。

### 2026-09-03 MCP

- **Commit**：`f4274ae`
- **问题**：不可能把所有外部能力写进 `handlers.py`。
- **做了什么**：进程内 mock（`docs` / `deploy`）→ `connect_mcp` → `assemble_tool_pool` 合并为 `mcp__server__tool`；每轮重建工具池；闭包用工厂函数避免循环变量踩坑。
- **诚实写**：这是教学用 mock，不是完整 MCP 网络协议；队友线程拿不到这些工具。
- **随后**：`d636c64` 文档对齐；`05a033b` 小修复。

---

## 完整提交表（引用用）

日期均为提交日（git `%ad` short）。merge 已标出，写博客时可跳过。

| Hash | 日期 | 说明 | 建议归属 |
|------|------|------|----------|
| `f45de08` | 07-24 | 最小可运行的 agent 内核 | 第 1 集 |
| `ef630ab` `a5dd5f0` `1719bfb` `a232137` | 07-24 | 清 .env / gitignore | 卫生，一笔带过 |
| `5ee8922` | 07-25 | 执行前权限判断 | 第 2 集 |
| `56e6fe7` | 07-27 | hooks 挂在循环外 | 第 2 集 |
| `d04481f` | 07-27 | TodoWrite 防跑偏 | 第 3 集 |
| `110678b` | 07-28 | subAgent 干净上下文 | 第 4 集 |
| `559710c` | 07-28 | skills 扫描与按需加载 | 第 5 集 |
| `21b9296` | 07-29 | 大 tool 结果落盘 | 第 6 集 |
| `6917886` | 07-29 | 消息条数裁剪 | 第 6 集 |
| `8f4b41f` `54015b0` `905995a` | 07-30 | 历史摘要压缩 | 第 6 集 |
| `fecebdc` `ceb6b91` | 08-05 | 记忆 + 系统提示组装 | 第 7 集（写一次即可） |
| `25e6a2d` `1272a43` | 08-05 | Merge remote | 跳过 |
| `80486e8` | 08-06 | 错误重试 | 第 8 集 |
| `1ff97ab` `1d06c76` | 08-07 | 跨会话任务看板 | 第 9 集 |
| `c4e4407` | 08-08 | 慢命令后台 | 第 10 集 |
| `144d33f` | 08-08 | 编码缩进修复 | 第 10 集注脚 |
| `22fbc8a` `da5e3a9` | 08-11 | cron 定时唤醒 | 第 11 集 |
| `2920b96` | 08-25 | 队友协议 | 第 12 集 |
| `582460b` | 08-31 | 队友屏障 | 第 13 集 |
| `d336e9f` | 09-01 | 看板自动认领 | 第 14 集 |
| `1fa7cce` `553c574` | 09-03 | worktree 隔离 | 第 15 集 |
| `f4274ae` | 09-03 | MCP 外接工具 | 第 16 集 |
| `d636c64` | 09-03 | 更新 md | 文档，可附在对应集末 |
| `05a033b` | 09-03 | bug 修改 | 注脚 |

查某次改了哪些文件：

```bash
git show --stat <hash>
git show <hash> -- path/to/file
```

---

## 写的时候建议反复对比的概念

| 名字 | 是什么 | 不是什么 |
|------|--------|----------|
| `spawn_subagent` | 同步函数，干净上下文，返回摘要 | 后台队友 |
| `spawn_teammate` | daemon 线程 + 邮箱 + result | 子 Agent |
| Skill | 仓库里的 SOP | 记忆、任务 |
| Memory | 跨会话偏好/事实 | 当前对话历史 |
| Task | 磁盘上的执行状态 | Todo |
| Todo | 本会话清单 | 看板 |
| compact | 压缩 messages | 删除记忆 |
| worktree | 目录+分支隔离 | 新的模型实例 |
| MCP（本仓库） | 进程内 mock 发现工具 | 完整 MCP 服务器 |

---

## 真实踩过、适合写成「踩坑」小节的点

（来自开发过程，不必每篇都写，穿插即可。）

1. **异步派工没有屏障**：线程结束才寄 `result`，Lead 可能先 Stop。
2. **`await_teammates` 挂错工具表**：挂在队友工具上，Lead 看不见、队友调了会被拒。
3. **Stop 屏障死循环**：必须用 `TEAMMATE_BARRIER_ROUNDS` 封顶。
4. **retry 闭包晚绑定**：`system`/`tools` 要默认参数绑死；fallback 模型要读 `state.current_model`。
5. **后台执行丢了 handlers**：MCP 工具在后台会变成未知工具。
6. **Python 缩进混用空格数**：`unindent does not match`（`run_glob`）。
7. **文档漏句**：加 MCP 说明时盖掉了 worktree 收尾那句。

---

## 每篇可用的固定结构（复制填空）

```markdown
# 标题

## 上一层留下了什么洞
（用自己踩的现象，不要空讲架构）

## 这层补的是哪一块
（一张流程图，study.md 里已有若干）

## 关键代码落在哪
（3～5 个文件名即可）

## 一个具体例子
（用户说了一句什么 → Agent 调了哪些工具 → 磁盘上多了什么）

## 还没解决的
（为下一篇留钩子）
```

流程图可直接改编 `study.md`（Skills / Memory / Task / Cron / 屏障 / Worktree / MCP）。

---

## 不要写进博客的

- `.env`、API Key、具体模型网关密钥
- merge commit、重复同步记忆功能的那次
- IDE 配置（`.vscode/settings.json` 曾进过屏障那次提交，博客不必提）
- 把 mock MCP 写成「已实现完整 MCP 协议」

---

## 更新这份底稿

以后每做完一个大功能：

1. `git log --oneline` 补一行到提交表  
2. 在「时间线章节」加一小节（问题 / 做法 / 文件 / 金句）  
3. 若值得单独成篇，在「建议系列」加一集  

本地未提交的改动不要写进「已发生的历史」，等 commit 后再记。
