# 并行改码要隔目录，外部工具不要写死在内核

> AgentHarness 系列（四）。提交 `1fa7cce` `553c574` `f4274ae`（2026-09-03）。

上一篇已经能派两个队友、用邮箱对结果、用屏障等到信。还剩两个洞，都是「协作一旦认真起来」才会撞上的：

- 两人改的是**同一棵工作树**，邮箱隔离救不了文件覆盖。  
- 每接一个外部系统就改 `handlers.py` / `schema.py`，内核会变成工具坟场。

所以同一天补了两层：git worktree，以及进程内的 mock MCP。

---

## Worktree：隔离的是目录和分支

`1fa7cce` 先挂工具，`553c574` 落地 `worktrees.py`。

`create_worktree(name, task_id?)` 在项目**父目录**下建 `.worktrees/<name>`，git 分支 `wt/<name>`。名称只允许 `[A-Za-z0-9._-]{1,64}`。可选 `task_id` 只写 `task.worktree`，**不改变** pending/in_progress——绑定不是认领。

文件类工具可以带 `cwd`，读写锁在这个 worktree 里。完成后两条路：

- `remove_worktree`：有未提交变更就拒绝，除非 `discard_changes=true`
- `keep_worktree`：目录和分支都留着，给人审查

事件追加 `.worktrees/events.jsonl`。

例子：任务「改登录」绑 worktree `login`，队友 A 只在 `.worktrees/login` 里编辑；任务「改支付」另开 `pay`。Lead 仍在主仓库对话。合并是你之后的 git 操作，Agent 负责的是别在同一棵树上互踩。

**金句：隔离的是文件系统和分支，不是「再开一个模型」。**

## MCP：连接、发现、带前缀调用

`f4274ae` 的 `mcp.py`。提交信息写了「标准协议」，实现上要**对读者诚实**：这是进程内 mock，用来把「工具运行时发现」走通，不是完整的 MCP 网络客户端。

流程：

```
connect_mcp("docs") 或 connect_mcp("deploy")
        → MOCK_SERVERS 工厂 new 一个 MCPClient
        → 放进 mcp_clients
        → 每轮 agent_loop 调 assemble_tool_pool()
        → LLM 看到 mcp__docs__search 等
        → execute_tool 用带 **kwargs 的 handler 转给 client.call_tool
```

| 服务器 | 工具 |
|--------|------|
| `docs` | `search(query)`、`get_version()` |
| `deploy` | `trigger(service)`、`status(service)` |

名字里的非法字符会收成下划线。system 会追加 `connected_mcp_summary()`，避免 prompt 缓存里还没有新工具说明。`connect_mcp` **同步成功之后**立刻重建工具池，同一轮后面的 tool_call 就能用；不要在后台线程还没连上时就刷新。

闭包必须用工厂 `_make_handler(client, tname)`，不能在 `for` 里直接 `lambda: client.call_tool(tname)`——那是 Python 循环变量晚绑定的老坑。

队友线程拿的是 `TEAMMATE_TOOLS`，**没有** `connect_mcp`。外部工具先留在 Lead 侧，避免两个身份同时触发部署。

例子：用户说「查一下 API 文档版本再看部署状态」。Lead 先 `connect_mcp("docs")`，再调 `mcp__docs__get_version`，然后 `connect_mcp("deploy")` + `mcp__deploy__status`。内核里始终只有一个 `connect_mcp`，具体能力是连上才出现的。

**金句：工具不必在写 harness 的那天全部想完；可以留一个「先连接、再发现」的口子。**

## 关键代码落在哪

- `worktrees.py`、`utils.safe_path(..., cwd)`
- `mcp.py`：`connect_mcp` / `assemble_tool_pool` / `connected_mcp_summary`
- `agent.py` 每轮重建工具池；`llm.call_llm(..., tools=tools)`
- `tools/executor.py` 对 `**kwargs` 整包透传

## 还没解决的（系列收束，也是下次迭代的钩子）

- mock 换成真实 MCP 传输（stdio / SSE）和鉴权  
- 队友能否安全使用只读 MCP，而不要 `deploy.trigger`  
- worktree 完成之后自动开 PR，而不是只 `keep_worktree`  
- 多 Lead、多仓库，而不只是单进程 `session_history`

四篇合在一起，Harness 的形状已经清楚：**一个带闸门的工具循环，外加上下文会计、跨会话状态、时间和队友、目录隔离、运行时扩工具。** 每一层都对应仓库里一次「先崩、再补」的提交。底稿和 hash 在 `docs/blog-source.md`。
