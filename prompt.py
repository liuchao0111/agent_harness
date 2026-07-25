# 定义一个包含提示语片段的字典 键为'identity'
PROMPT_SECTIONS = {
    # 'identity' 键对应一个多行字符串 作为智能体的系统身份提示
    "identity": ("你是一个编程Agent。直接行动, 不要解释。所有破坏性操作需要用户批准。")
}


# 定义一个函数 返回系统提示语
def get_system_prompt() -> str:
    # 返回字典中 'identity'键对应的提示语
    return PROMPT_SECTIONS["identity"]
