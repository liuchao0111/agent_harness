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
