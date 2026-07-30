# 从config中导入client对象
from config import client
from tools.schema import TOOLS


# 定义call_llm函数 参数包括system(系统消息)、message(消息列表)、max_tokens(最大token数)、model(模型名)
def call_llm(system: str, messages: list, max_tokens: int, model: str):
    # 调用client.chat.completions.create方法生成响应，传入模型名、拼接的消息、工具集合和最大token数
    return client.chat.completions.create(
        model=model,
        # 将系统提示和传入的消息列表组合成messages参数
        messages=[{"role": "system", "content": system}, *messages],
        tools=TOOLS,
        # 传入最大允许的token数
        max_tokens=max_tokens,
    )


# 定义一个函数，用于判断异常是否为提示过长相关错误
def is_prompt_too_long_error(e: Exception) -> bool:
    # 将异常对象转换为字符串，并转换为小写
    msg = str(e).lower()
    # 返回一个布尔值，判断是否包含与“提示过长”相关的各种关键字
    return (
        # 检查字符串中是否有 'prompt' 且有 'long'
        ("prompt" in msg and "long" in msg)
        # 检查是否有 'prompt_is_too_long'
        or "prompt_is_too_long" in msg
        # 检查是否有 'context_length_exceeded'
        or "context_length_exceeded" in msg
        # 检查是否有 'max_context_window'
        or "max_context_window" in msg
        # 检查是否有 'context_length'
        or "context_length" in msg
        # 检查是否有 'maximum context'
        or "maximum context" in msg
    )
