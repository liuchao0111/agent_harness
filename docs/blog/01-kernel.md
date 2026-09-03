# 自己写一个编程 Agent：从能跑，到不敢乱执行

> AgentHarness 系列（一）。仓库提交 `f45de08` → `d04481f`（2026-07-24～27）。

很多人第一次写 Agent，是把用户那句话丢给 Chat Completions，再把模型回的字打印出来。那不叫 Agent，那叫聊天窗口。

Agent 的最小定义其实很土：**模型可以要工具，你的程序去跑，跑完把结果再喂回去，直到它不再要工具。** AgentHarness 就是从这一圈 `while True` 长出来的。后面所有功能——记忆、队友、cron、MCP——都是这圈循环在真实使用里一次次崩掉之后补上的层。

本文只讲最底下三层：循环本身、权限、以及「先写计划再动手」。

---

## 上一层留下了什么洞

没有上一层。洞是：模型只会说话，不会碰你的仓库。

## 这层补的是哪一块

```
用户输入
  → hooks（此时还没有）
  → agent_loop
        调 LLM（带 tools）
        有 tool_calls？执行，把结果 append 进 messages，再调
        没有？当作最终回复，结束
```

对应第一笔提交：`f45de08`「最小可运行的agent内核」。文件一开始就按职责切开，后面才没变成单文件巨兽：

| 文件 | 干什么 |
|------|--------|
| `main.py` | 读 `>>` 提示符，维护 `session_history` |
| `agent.py` | 工具循环 |
| `llm.py` | 调 OpenAI 兼容接口 |
| `tools/schema.py` | 告诉模型有哪些工具 |
| `tools/handlers.py` | 工具怎么执行 |
| `tools/executor.py` | 按名字分发 |
| `config.py` | key、模型、工作目录 |

接口用兼容 Chat Completions 的原因很实际：官方 API 和各种 `base_url` 网关都能接。密钥放 `.env`，很快就从 git 里拿掉了（`a232137`）——这不是功能，但这是你公开写博客时必须先做的卫生。

一个具体例子：用户说「看看当前目录有什么文件」。Lead 调 `glob` 或 `bash`，handler 在 `WORKDIR` 里跑，stdout 变成一条 `role=tool` 的消息，模型再组织成给人看的话。没有这条回灌，它只能编。

---

## 权限不该写在 prompt 里

循环能跑的第二天，洞就出现了：模型会 `rm`，会往工作区外面写文件。你在 system 里写「请不要删除生产数据」没有用，那是请求，不是闸门。

`5ee8922` 加了 `permission.py`：命中禁止模式（例如 `rm -rf /`、`sudo`）直接拒绝；带破坏性关键字（`rm`、`chmod 777`）要你在终端里打 `yes`。写文件如果解析后跑出工作目录，同样要确认。

两天后 `56e6fe7` 把这些检查收成 **hooks**，挂在循环外面，而不是写进 `agent_loop` 的肚子里：

- `UserPromptSubmit`：用户回车之后、进循环之前
- `PreToolUse`：工具执行前，可拦截
- `PostToolUse`：执行后
- `Stop`：模型准备结束本轮

循环仍然是「调模型 → 跑工具」。能不能跑、跑完记不记日志，是插在边上的。后面 cron、队友、MCP 都还走同一套 PreToolUse，不用各写一套审批。

**金句可以就这句话：权限是循环外的硬闸门，不是 prompt 里的「请你小心」。**

---

## 会跑偏：先让它写出步骤

循环加上权限之后，模型还是会东一榔头西一棒。`d04481f` 的提交说明写得很直白：ToDoWrite，计划 agent，不然会偏离。

`todo_write` 不是跨会话看板（那是八月才有的 Task），只是**这一次对话**里的清单：pending / in_progress / completed。连续多轮不更新，system 里会塞一条提醒。它解决的是「这一轮对话的注意力」，不是「这个项目跨天的进度」。

例子：用户说「给登录接口加测试并提交」。理想路径是先 `todo_write` 三条（读现有测试、补用例、按 skill 提交），再 `bash` / `edit_file`。没有这层，它经常直接开改，改到一半忘了测。

---

## 关键代码落在哪

- `agent.py`：`agent_loop`
- `permission.py` / `hooks.py`：硬闸门
- `tools/schema.py` 里的 `todo_write`
- 入口 `main.py` 的 `input` + `session_history`

## 还没解决的

这个内核默认：**同一时刻只有一个大脑，上下文会无限变长，关终端任务就蒸发。** 下一篇会先打上下文：子 Agent 拆任务、Skills 按需加载、把 tool 结果从 messages 里赶出去。
