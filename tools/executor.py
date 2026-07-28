import inspect
import json

# 从config模块导入client实例和主模型MODEL_ID
from config import MODEL_ID, client

# 从hooks模块导入钩子触发函数
from hooks import trigger_hooks

# 从prompt模块导入子系统提示词SUB_SYSTEM
from prompt import SUB_SYSTEM

# 从tools.handlers模块中导入TOOL_HANDLERS字典
from tools.handlers import TOOL_HANDLERS

# 从tools.schema导入BASE_TOOLS
from tools.schema import BASE_TOOLS

# 从utils模块导入assistant_message_dict和extract_text
from utils import assistant_message_dict, extract_text


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


# 定义允许子Agent的函数 参数为描述字符串 返回字符串类型


def run_spawn_subagent(description: str) -> str:
    # 打印子Agent 已启动的信息
    print("\n\x1b[35m[子 Agent 已启动]\x1b[0m")
    # 初始化消息列表 用户以描述作为第一条消息
    messages = [{"role": "user", "content": description}]
    # 最多进行30轮交互
    for _ in range(30):
        # 调用OpenAi接口创建一次聊天补全
        response = client.chat.completions.create(
            # 指定主模型
            model=MODEL_ID,
            # 系统消息和当前消息历史作为上下文
            messages=[{"role": "system", "content": SUB_SYSTEM}, *messages],
            # 指定可用工具
            tools=BASE_TOOLS,
            # 设置最大token数
            max_tokens=8000,
        )
        # 取出assistant回复内容
        assistant = response.choices[0].message
        # 将assistant回复格式化为dict并加入消息历史
        messages.append(assistant_message_dict(assistant))
        # 如果assistant没有工具调用 则跳出循环
        if not assistant.tool_calls:
            break
        # 遍历assistant需要调用的所有工具
        for tool_call in assistant.tool_calls:
            # 获取工具名称
            name = tool_call.function.name
            # 获取工具参数
            args = json.loads(tool_call.function.arguments or "{}")
            # 调用PreToolUse钩子判断是否被阻止
            blocked = trigger_hooks("PreToolUse", name, args)
            # 如果被阻止 加入一条tool回复 内容为阻止理由
            if blocked:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(blocked),
                    }
                )
                continue
            # 如果执行工具 如未注册则提示'未知工具'
            output = (
                execute_tool(name, args)
                if name in TOOL_HANDLERS
                else f"未知工具: {name}"
            )
            # 调用PostToolUse钩子
            trigger_hooks("PostToolUse", name, args, output)
            # 打印子agent的工具调用及输出内容简略
            print(f"  \x1b[90m[sub] {name}: {str(output)[:100]}\x1b[0m")
            # 将工具返回的内容添加到消息历史
            messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": output}
            )
    # 从所有消息的最后一条内容中提取文本为最终结果
    result = extract_text(messages[-1].get("content"))
    # 如果没有提取到 反向查找assistant角色信息提取结果
    if not result:
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                # 提取其内容
                result = extract_text(msg.get("content"))
                if result:
                    break
        # 如果还是没有结果
        if not result:
            result = "子 Agent 在 30 轮内未给出最终答案"
    # 打印子 Agent 完成的信息
    print("\x1b[35m[子 Agent 完成]\x1b[0m")
    # 返回最终结果
    return result


TOOL_HANDLERS["spawn_subagent"] = run_spawn_subagent
