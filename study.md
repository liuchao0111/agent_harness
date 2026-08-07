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


<!-- 学习task system 后续继续 -->
1.createtask
2.listtask
3. claimtask