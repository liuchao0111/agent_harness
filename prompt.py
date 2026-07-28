from config import WORKDIR

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
    ),
    # 'workspace' 键，对应当前的工作目录描述
    "workspace": f"工作目录 {WORKDIR}",
    # 'skill' 键，指明需要完整技术文档时的指引
    "skill": "需要完整技术说明时, 使用load_skill 加载相关文档",
}


# 定义函数 将各段拼接成完整的系统提示 skills为技能描述字符串
def _assemble_system_prompt(skills: str) -> str:
    # 初始化包含基本身份与工作目录的列表 sections
    sections = [PROMPT_SECTIONS["identity"], PROMPT_SECTIONS["workspace"]]
    # 若传入的技能描述非空 , 则将其与技能说明段落加入到sections
    if skills:
        sections.append(f"可用技能:\n{skills}")
        sections.append(PROMPT_SECTIONS["skill"])
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


# 定义一个函数 返回系统提示语
def get_system_prompt() -> str:
    # 内部调用技能文本拼接及总装配函数
    return _assemble_system_prompt(_skills_text())


# 定义子任务的系统提示语
SUB_SYSTEM = f"你是一个位于{WORKDIR}的编程Agent,直接行动，不要解释。完成分配给你的任务，然后返回简洁摘要。不要继续委派。"
