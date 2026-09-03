# 项目总结

## 基本信息

- **项目名称**: agentharness
- **版本**: 0.1.0
- **Python**: >= 3.14
- **入口**: `python main.py` 或 `uv run python main.py`

## 项目描述

本地 CLI 编程 Agent（Lead + 可选队友线程）。用 OpenAI 兼容 Chat Completions 驱动工具循环：读写文件、执行命令、跨会话任务看板、cron 定时唤醒、长期记忆、git worktree 隔离，以及进程内 mock MCP（`docs` / `deploy`）。

详细用法见 [README.md](README.md)。

## 依赖

| 包名 | 版本要求 | 用途 |
|------|----------|------|
| openai | >=2.47.0 | Chat Completions / 工具调用 |
| python-dotenv | >=1.2.2 | 加载 `.env` |
| requests | >=2.34.2 | HTTP（部分工具/扩展路径） |

安装：`uv sync` 或 `pip install -e .`（需配置 `.env` 中的 `OPENAI_API_KEY` 等）。

## 模块对照

| 文件 | 职责 |
|------|------|
| `agent.py` | Lead 主循环、队友屏障、每轮 `assemble_tool_pool` |
| `teams.py` | 队友线程、邮箱、计划协议、`await_teammates` |
| `tasks.py` | `.tasks/` 看板与依赖 |
| `worktrees.py` | git worktree 生命周期 |
| `mcp.py` | mock MCP 连接与 `mcp__*` 工具合并 |
| `cron.py` | 定时任务 |
| `memory.py` / `history.py` | 长期记忆 / 上下文压缩 |
| `tools/` | 工具 schema、handler、分发 |

## 近期能力（相对早期脚手架）

- 队友收尾屏障：Stop 前等待 `type=result`
- Worktree：`create_worktree` / `remove_worktree` / `keep_worktree`
- MCP：`connect_mcp` 后动态把外部工具并入 LLM 工具列表
