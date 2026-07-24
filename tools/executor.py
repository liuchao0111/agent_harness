# 导入inspect 模块 用于获取获取函数签名
import inspect

# 从tools.handlers模块中导入TOOL_HANDLERS字典
from tools.handlers import TOOL_HANDLERS


# 定义execute_tool函数 接收工具名称和参数字典 返回字符串
def execute_tool(name: str, args: dict) -> str:
    # 根据工具名称从TOOL_HANDLERS字典中获取对应的处理函数
    handler = TOOL_HANDLERS.get(name)
    # 如果没有找到处理函数 则返回未知工具提示
    if not handler:
        return f"未知工具: {name}"
    # 获取处理函数的参数签名
    sig = inspect.signature(handler)
    # 从输入的参数重筛选出处理函数所需要的有效参数
    valid = {k: v for k, v in args.items() if k in sig.parameters}
    return handler(**valid)
