---
name: commit
description: 根据当前改动生成符合仓库规范的 commit message，不执行 git 提交
when_to_use: 用户需要 commit message、/commit、写提交说明、或完成改动想拟定提交文案时
---

# /commit — 生成 Commit Message（只读，不提交）

## 核心约束（必须遵守）

本技能 **只生成提交说明文案**，**不得修改 Git 状态或项目文件**：

| 允许 | 禁止 |
|------|------|
| 只读 `bash`：`git status`、`git diff`、`git diff --staged`、`git log` | `git add`、`git commit`、`git push`、`git stash` |
| 在对话中输出建议的 commit message | 任何会改变工作区或索引的命令 |

若用户明确要求「帮我提交」，应说明本技能仅产出文案，请用户自行复制执行，或另开普通任务处理提交。

## 触发场景

- 用户输入 `/commit` 或「写个 commit message」「帮我拟提交说明」
- 一组改动已完成，需要符合仓库风格的提交文案
- 合并前想先确认提交说明是否合适

## 前置检查（必须执行）

在 PowerShell 中了解当前状态（只读）：

```powershell
git status
git diff
git diff --staged
git log -5 --oneline
```

分析要点：

1. **敏感文件提醒**：若 diff 含 `.env`、密钥、凭证等，在输出中警告「不应纳入提交」，但仍只生成文案、不执行 add
2. **改动范围**：区分已 stage / 未 stage，说明 message 对应哪部分改动
3. **对齐现有风格**：参考 `git log` 最近提交（本仓库常见：`s0X_模块名` 或 `N. 章节标题` 式说明）

## 提交信息规范

- **1–2 句**，说明 **为什么** 改，而非罗列 **改了什么**
- 使用完整句子，中文或英文均可，与仓库近期风格一致
- 类型语义：`add`（新功能）、`fix`（修复）、`update`（增强）、`refactor`（重构）、`docs`（文档）

示例：

```
s07_skill_loading：按需加载 skills 目录，SYSTEM 注入目录、运行时 load_skill
```

```
fix: 子 Agent 权限 hook 未触发导致危险命令放行
```

## 执行步骤

1. 运行只读 git 命令，理解改动内容与历史风格
2. 若改动混杂无关文件，在报告中分开说明，并给出 **主 message** 与可选的 **拆分建议**（仍不执行 add）
3. 输出结构化结果：

```markdown
## 建议的 Commit Message

\`\`\`
（可直接复制的一行或多行 message）
\`\`\`

## 依据摘要
- 主要改动：…
- 涉及文件：…
- 风格参考：最近提交 `abc1234 …`

## 注意事项（如有）
- 勿纳入：…
- 建议先 stage：`path/to/file`（由用户自行 `git add`）

## 手动提交（可选复制）
\`\`\`powershell
git add <用户自行选择的文件>
git commit -m "建议的 message"
\`\`\`
```

4. **不要** 替用户执行 `git add` 或 `git commit`

## 禁止事项

- 不要 `git add`、`git commit`、`git push` 或任何修改 Git 状态的命令
- 不要 `git config` 修改配置
- 不要在工作区创建临时文件存放 message

## 完成标准

- 用户收到可直接复制的 commit message 及简要依据
- `git status` 与执行本技能前一致（无新增 stage/commit）
