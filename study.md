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
