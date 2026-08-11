from config import MEMORY_INDEX, TEXT_ENCODING, WORKDIR

# 从 skills 模块导入技能注册表 SKILL_REGISTRY
from skills import SKILL_REGISTRY

# 定义一个包含提示语片段的字典 键为'identity'
PROMPT_SECTIONS = {
    # 'identity' 键对应一个多行字符串 作为智能体的系统身份提示
    "identity": (
        "你是一个编程 Agent。直接行动,不要解释。"
        "你将在 Windows cmd 环境下执行任务。使用 cmd 命令完成任务。"
        "所有破坏性操作需要用户批准。"
        "开始多步骤任务前，先用 todo_write 规划步骤；执行过程中及时更新状态。"
        "遇到复杂子问题时，使用 spawn_subagent 工具派生子Agent。"
        "上下文过长时可以使用 compact 工具。"
        "bash 支持 run_in_background 参数以在后台运行耗时命令。"
        "定时任务可使用 schedule_cron / list_crons / cancel_cron。"
    ),
    # 'workspace' 键，对应当前的工作目录描述
    "workspace": f"工作目录 {WORKDIR}",
    # 'skill' 键，指明需要完整技术文档时的指引
    "skill": "需要完整技术说明时, 使用load_skill 加载相关文档",
    # 'memory' 键，指明记忆的使用方式
    "memory": "下方会注入相关记忆正文，请遵守记忆中的用户偏好。用户说「记住」或表达明确偏好时，应提取为记忆。",
}


# 定义函数 将各段拼接成完整的系统提示 skills为技能描述字符串
def _assemble_system_prompt(skills: str, memories: str | None = None) -> str:
    # 初始化包含基本身份与工作目录的列表 sections
    sections = [PROMPT_SECTIONS["identity"], PROMPT_SECTIONS["workspace"]]
    # 若传入的技能描述非空 , 则将其与技能说明段落加入到sections
    if skills:
        sections.append(f"可用技能:\n{skills}")
        sections.append(PROMPT_SECTIONS["skill"])
    if memories:
        sections.append(f"可用记忆:\n{memories}")
        sections.append(PROMPT_SECTIONS["memory"])
    # 用两个换行符拼接所有片段并返回完整的系统提示
    return "\n\n".join(sections)


# 定义一个私有函数 , 生成所有注册技能的简介文本
def _skills_text() -> str:
    if not SKILL_REGISTRY:
        return ""
    lines = []
    for s in SKILL_REGISTRY.values():
        line = f"- **{s['name']}**: {s['description']}"
        lines.append(line)
    return "\n".join(lines)


# 最近一次生成系统提示词
_last_prompt = None
# 记录索引文件最近一次的修改时间
_last_memory_mtime = None


# 定义一个函数来 生成索引目录里面的所有文件
def _memory_index_text():
    if not MEMORY_INDEX.exists():
        return ""
    return MEMORY_INDEX.read_text(encoding=TEXT_ENCODING, errors="replace").strip()


# 定义一个函数 返回系统提示语
def get_system_prompt() -> str:
    global _last_prompt, _last_memory_mtime
    # 如果记忆索引文件存在 获取这个文件的最后修改时间 返回时一个秒级时间戳
    mtime = MEMORY_INDEX.stat().st_mtime if MEMORY_INDEX.exists() else 0
    # 如果有缓存的系统提示词存在 并且记忆文件的修改时间等于上次保存的记忆文件修改时间
    if _last_prompt is not None and mtime == _last_memory_mtime:
        return _last_prompt
    # 如果没有命中
    _last_memory_mtime = mtime
    # 内部调用技能文本拼接及总装配函数
    _last_prompt = _assemble_system_prompt(_skills_text(), _memory_index_text())
    return _last_prompt


# 定义子任务的系统提示语
SUB_SYSTEM = f"你是一个位于{WORKDIR}的编程Agent,直接行动，不要解释。完成分配给你的任务，然后返回简洁摘要。不要继续委派。"
