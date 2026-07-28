from config import WORKDIR

# 定义一个包含提示语片段的字典 键为'identity'
PROMPT_SECTIONS = {
    # 'identity' 键对应一个多行字符串 作为智能体的系统身份提示
    "identity": (
        "你是一个编程 Agent。直接行动,不要解释。"
        "你将在 Windows cmd 环境下执行任务。使用 cmd 命令完成任务。"
        "所有破坏性操作需要用户批准。"
        "开始多步骤任务前，先用 todo_write 规划步骤；执行过程中及时更新状态。"
        "遇到复杂子问题时，使用 spawn_subagent 工具派生子Agent。"
    )
}


# 定义一个函数 返回系统提示语
def get_system_prompt() -> str:
    # 返回字典中 'identity'键对应的提示语
    return PROMPT_SECTIONS["identity"]


# 定义子任务的系统提示语
SUB_SYSTEM = f"你是一个位于{WORKDIR}的编程Agent,直接行动，不要解释。完成分配给你的任务，然后返回简洁摘要。不要继续委派。"
