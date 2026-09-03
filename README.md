# AgentHarness

本地 CLI 编程 Agent：用 OpenAI 兼容接口驱动主 Agent（Lead），通过工具读写文件、执行命令，并支持跨会话任务看板、定时唤醒、长期记忆和多队友协作。

```
用户输入 → hooks → agent_loop（工具循环）→ 最终回复
                ↑
         cron 队列 / 队友 result / 收件箱
```

## 能力概览

| 能力 | 说明 |
|------|------|
| 工具循环 | bash / 读写下文件 / glob / todo，危险命令会拦截或要求确认 |
| 队友协作 | `spawn_teammate` 后台线程跑独立 Agent；文件邮箱通信；Stop 前等待 result |
| 任务看板 | `create_task` / `claim_task` / `complete_task`，支持 `blockedBy` 依赖；队友 idle 结束时可自动认领 |
| 定时任务 | 5 段 cron，可持久化到磁盘，到点注入 prompt 再跑一轮 Agent |
| Skills | 启动时扫描 `skills/*/SKILL.md`，需要时 `load_skill` 加载全文 |
| Memory | 任务结束后抽取长期记忆，写入 `.memory/`，下次注入系统提示 |
| 上下文压缩 | 历史过长时 compact / snip，并修复 tool 消息链 |

## 环境要求

- Python **>= 3.14**（见 `pyproject.toml`）
- OpenAI 兼容 API（官方或任意 `base_url` 网关）

## 快速开始

```bash
cd AgentHarness
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

在项目根目录创建 `.env`：

```env
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_ID=gpt-4o
# 可选：主模型连续失败时的备用模型
# FALLBACK_MODEL=gpt-4o-mini
```

启动：

```bash
python main.py
```

提示符 `>>` 后输入任务，回车发送。`q` / `exit` 退出。空行会被忽略。

## 模块结构

```
main.py          交互循环、cron 调度线程、agent 互斥锁
agent.py         Lead 主循环：LLM → 工具 → 压缩 / 记忆 / 队友屏障
config.py        环境变量、路径、超时与 token 上限
prompt.py        系统提示拼装（身份 + 技能简介 + 相关记忆）
llm.py           调用、重试、529、超长恢复
tools/           schema（工具定义）/ handlers（实现）/ executor（分发）
teams.py         队友线程、MessageBus、协议、收尾屏障
tasks.py         跨会话任务看板（.tasks/*.json）
cron.py          定时任务调度与队列
memory.py        记忆抽取、索引、合并
history.py       对话压缩与 tool 链修复
hooks.py         UserPromptSubmit / PreToolUse / PostToolUse / Stop
skills.py        扫描 skills/ 注册表
```

## 主循环在做什么

每次用户（或 cron）触发 `agent_loop`：

1. 消费已到点的 cron，把 prompt 注入对话
2. 把 Lead 收件箱（队友消息 / result）注入为 user 消息
3. 组装系统提示（技能简介 + 相关记忆）
4. 必要时压缩历史，调用 LLM
5. 若有 `tool_calls`：权限检查 → 执行 → 把结果追加进 messages，继续循环
6. 若无工具：若仍有未收回的队友 result，先 `await` 再给 Lead 一轮汇总（队友屏障）
7. 抽取 / 合并记忆后结束本轮

## 工具一览

**Lead（主 Agent）** 可用的主要工具：

| 工具 | 用途 |
|------|------|
| `bash` | 执行命令；`run_in_background=true` 可后台跑 |
| `read_file` / `write_file` / `edit_file` / `glob` | 文件操作 |
| `todo_write` | 本会话待办 |
| `load_skill` | 加载 `skills/<name>/SKILL.md` |
| `compact` | 摘要压缩较早对话 |
| `create_task` / `list_tasks` / `get_task` / `claim_task` / `complete_task` / `delete_task` | 跨会话任务看板 |
| `schedule_cron` / `list_crons` / `cancel_cron` | 定时唤醒 |
| `spawn_teammate` | 启动名为 `name` 的后台队友 |
| `send_message` | 经 MessageBus 发信（发送方不可伪造） |
| `await_teammates` | 阻塞等待队友 `result`（仅 Lead） |
| `request_plan` / `review_plan` | 要求队友提交计划并审批 |
| `request_shutdown` | 请队友优雅退出 |
| `spawn_subagent` | 同步子 Agent，只收回结论 |

**队友** 工具更少：文件与 bash、`send_message`、`submit_plan`、`todo_write`、`load_skill`。收件箱由运行时自动检查，不必自己 `check_inbox`。任务 idle 结束时由运行时调用 `claim_task` 自动认领，不经过模型工具调用。

## 队友协作

```
Lead ──spawn_teammate──► 后台线程（独立 messages + 身份 ContextVar）
  │                              │
  │  send_message / 协议          │  结束时 BUS.send(..., type=result, spawn_id)
  ▼                              ▼
.mailboxes/<agent>.jsonl     Lead 收件箱
```

- 每个 Agent 一个 `.jsonl` 收件箱，**读即消费**。
- 同名重启会换新的 `spawn_id`，上一轮残留的 `result` 不会误清「还在等」的屏障。
- Lead 准备结束但还有 pending result 时：最多等待 `TEAMMATE_WAIT_TIMEOUT`（默认 120s），注入收件箱后再给一轮汇总（`TEAMMATE_BARRIER_ROUNDS`，默认 1 次）。
- 计划审批：队友 `submit_plan` → Lead `review_plan(request_id, approve)` → 队友收到 `plan_approval_response` 后继续或改计划。

典型用法：派工后调用 `await_teammates`，**未看到 result 前不要向用户声称完成**。

## 任务看板

任务文件在 `.tasks/task_*.json`，状态：`pending` → `in_progress` → `completed`。

- `blockedBy`：依赖任务全部 `completed` 后才可认领。
- `owner`：认领者名称，取自当前 Agent 身份（`current_agent`），不能由模型伪造。
- 队友在 idle 轮询结束后，会扫描「pending、无 owner、依赖已满足」的任务并尝试认领第一条；成功则回到工作循环。

## 定时任务

`schedule_cron` 使用 **5 段** cron：`分 时 日 月 周`（支持 `*`、`*/n`、逗号、区间）。

- `recurring=true`：循环；`false`：触发一次后移除。
- `durable=true`：写入 `.scheduled_.tasks.json`，进程重启后仍在。
- 调度线程把到期任务放入队列；`main` 里的消费线程与用户输入共用 `agent_lock`，避免两轮 Agent 并行改同一份历史。

## Skills 与 Memory

**Skills**：目录 `skills/<name>/SKILL.md`（YAML frontmatter 的 `name` / `description`）。启动扫描进注册表，系统提示只放简介；模型调用 `load_skill` 才拿到全文。现成示例：`skills/commit`、`skills/code-review`。

**Memory**：任务结束从近期对话抽取条目，落到 `.memory/`，索引为 `.memory/MEMORY.md`。条数超过阈值会合并。下一次提问按相关性选片段注入系统提示。

二者区别：Skill 是预先写好的 SOP；Memory 是对话里沉淀的偏好与事实；Task 是跨会话的执行状态，不是聊天记录。

## 工作区目录（运行时生成）

| 路径 | 内容 |
|------|------|
| `.env` | API 密钥（不要提交） |
| `.tasks/` | 任务看板 JSON |
| `.mailboxes/` | 当前未读邮箱（读完即删） |
| `.mailboxes_backup/` | 邮箱追加备份 |
| `.scheduled_.tasks.json` | 持久化 cron |
| `.memory/` | 长期记忆与索引 |
| `.transcript/` | 会话转录 |
| `.task_outputs/tool-results/` | 过长工具输出落盘 |

## 权限

`hooks.py` / `permission.py` 在工具执行前检查：

- bash 命中禁止模式（如 `rm -rf /`、`sudo`）直接拒绝
- 含破坏性关键字（如 `rm`、`chmod 777`）需用户输入 `yes` / `y`
- `write_file` / `edit_file` 写出工作目录之外同样要确认

## 配置要点

见 `config.py`，常用项：

| 变量 | 默认 | 含义 |
|------|------|------|
| `DEFAULT_MAX_TOKENS` | 8000 | 单次补全上限 |
| `TEAMMATE_WAIT_TIMEOUT` | 120 | 等待队友 result 秒数 |
| `TEAMMATE_BARRIER_ROUNDS` | 1 | Stop 拦截最多几轮 |
| `IDLE_TIMEOUT` | 60（`teams.py`） | 队友无消息后空闲秒数 |
| `CONSOLIDATE_THRESHOLD` | 10 | 记忆合并条数阈值 |

## 许可与状态

个人/学习用 harness，版本 `0.1.0`。接口与工具集合仍在迭代，以仓库代码为准。
