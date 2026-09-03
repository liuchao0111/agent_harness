# 编程 Agent 的上下文账单：子任务、Skills、压缩和记忆

> AgentHarness 系列（二）。提交 `110678b` → `80486e8`（2026-07-28～08-06）。

上一篇把循环跑起来了，也加上了权限和本会话 todo。很快会出现另一种事故：**不是模型不听话，是窗口被撑爆了。**

一次 `bash` 的测试日志、一次读大文件、来回十几轮 tool_calls，messages 里全是重复的工具输出。再往 system 里塞「完整开发规范」，下一轮直接 `context_length_exceeded`。

这一篇补的是同一类问题的四层补丁：把大任务拆到干净上下文、把 SOP 按需加载、把历史压回去、把跨会话的偏好从聊天记录里拆出来。最后补 API 动不动挂掉的重试。

---

## 上一层留下了什么洞

Lead 的 `messages` 是唯一大脑。所有工具输出、所有规范、所有「用户上次说过喜欢 uv」都想挤进去。挤得进的时候显得聪明，挤爆的时候整轮报废。

## 子 Agent：干净上下文，不是多线程

`110678b`：大任务拆小，每个拿到的都是干净的上下文。

`spawn_subagent(description)` 是**同步函数调用**，不是后台队友（队友是八月底的 `spawn_teammate`）。它用 `BASE_TOOLS`、自己的 messages、大约 30 轮上限，结束只把摘要还给 Lead。Lead 的历史里不会留下子 Agent 读过的每一份文件。

适合：独立、边界清楚的一块活（「把这个函数的测试补齐」）。不适合：要和用户来回确认、要和其他人并行抢同一份代码——那是后两篇的事。

## Skills：简介进 prompt，全文当工具结果

`559710c` 扫 `skills/*/SKILL.md`，做成 `SKILL_REGISTRY`。系统提示只放名称和一句话描述。模型觉得需要时才 `load_skill(name)`，完整 SOP 作为 **tool 结果** 回来。

仓库里现成两份：`skills/commit`、`skills/code-review`。这是预先写好的操作手册，不是项目事实，也不是待办。

对比要写进文章里：把 100 页规范塞进 system，等于每轮都付一遍租金；按需 `load_skill`，等于用到再打开抽屉。

## 上下文压缩：先赶 tool 结果，再请 LLM 摘要

七月底三连提交，后来在 `history.py` 里叠成多层，主循环每一轮都会走：

| 层 | 提交 | 做什么 |
|----|------|--------|
| 大结果落盘 | `21b9296` | tool 输出太长 → 写到 `.task_outputs/tool-results/`，messages 里留路径和截断 |
| 条数裁剪 | `6917886` | 条数超过自定义阈值（当时是 50），留头留尾 |
| LLM 摘要 | `8f4b41f` 等 | 体积超过 `CONTEXT_LIMIT`，摘要成一条「已压缩」 |

现在的 `agent_loop` 里还能看到顺序：先 `tool_result_budget`，再 `snip_compact` / `micro_compact`，超限才 `compact_history`，最后 `repair_messages_chain` 补缺的 tool 响应。压缩会拆消息链，不修的话下一轮 LLM 会因为「有 tool_call 却没有 tool 结果」而报错。

**金句：上下文窗口是租金，tool 结果是最能把租金烧光的东西。**

## Memory：跨会话的偏好，不是聊天记录

`fecebdc` 加了 `memory.py`。任务结束从近期对话抽取条目，写到 `.memory/`，索引 `.memory/MEMORY.md`。下次提问按相关度选片段，追加到 system。条数多了会 consolidate。

务必和读者划清四样东西（这是本篇最有用的表）：

| | 存什么 | 生命周期 |
|--|--------|----------|
| Todo | 本次对话步骤 | 关进程就没了（当时） |
| History compact | 当前 messages 的体积 | 本轮对话 |
| Memory | 偏好与事实 | 跨会话 |
| Task（下一篇） | 执行状态、依赖、负责人 | 跨会话，在磁盘上 |

例子：用户说「以后提交信息用中文、别用 git commit -m 乱写」。抽成记忆后，下次开新会话，system 里已经有这条，不必再靠模型「想起上周聊过」。

## 重试：模型也会 429 / 529

压缩之后，失败换成了网关过载。`80486e8` 在 `llm.py` 做了 `with_retry`：429 指数退避；连续 529 可切 `FALLBACK_MODEL`；提示过长则 `reactive_compact` 再试。

后来踩过一个闭包坑，适合当注脚：retry 的 lambda 要用默认参数把本轮的 `system` / `messages` / `tools` 绑死；切备用模型时要读 `state.current_model`，而不是在创建 lambda 时把模型名拍死。否则你以为切了备用模型，重试还在打已经过载的那一个。

## 关键代码落在哪

- `tools/executor.py`：`run_spawn_subagent`
- `skills.py` + `skills/*/SKILL.md`
- `history.py`、`memory.py`、`llm.py` 的 `with_retry`
- `agent.py` 里压缩那几行和结束时的 `extract_memories`

## 还没解决的

上下文能活下去了，但 **关终端，进行中的活就没了**；`pip install` 会卡住整个 Lead 循环；也还没有第二个 Agent 帮你干活。下一篇是磁盘上的看板、后台线程、时钟唤醒，以及队友。
